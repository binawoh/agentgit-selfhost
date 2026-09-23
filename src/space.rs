use crate::state::State;
use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime};

const MIB: u64 = 1024 * 1024;

#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(default, deny_unknown_fields)]
pub struct Policy {
    pub quota_mib: u64,
    pub warn_percent: u8,
    pub min_free_mib: u64,
    pub temp_max_age_hours: u64,
    pub cleanup_interval_hours: u64,
}

impl Default for Policy {
    fn default() -> Self {
        Self {
            quota_mib: 5120,
            warn_percent: 80,
            min_free_mib: 3072,
            temp_max_age_hours: 168,
            cleanup_interval_hours: 24,
        }
    }
}

#[derive(clap::Args, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct PolicyUpdate {
    /// Total Hub data admission budget, including Git, LFS, indexes and temporary files.
    #[arg(long)]
    pub quota_mib: Option<u64>,
    /// Warn when this percentage of the quota is used.
    #[arg(long)]
    pub warn_percent: Option<u8>,
    /// Pause new uploads below this filesystem free-space reserve.
    #[arg(long)]
    pub min_free_mib: Option<u64>,
    /// Retain abandoned temporary files for this long; saved history never expires.
    #[arg(long)]
    pub temp_max_age_hours: Option<u64>,
    /// Time between automatic cleanup passes while the server is running.
    #[arg(long)]
    pub cleanup_interval_hours: Option<u64>,
}

impl PolicyUpdate {
    pub fn apply(&self, current: &Policy) -> Result<Policy> {
        let policy = Policy {
            quota_mib: self.quota_mib.unwrap_or(current.quota_mib),
            warn_percent: self.warn_percent.unwrap_or(current.warn_percent),
            min_free_mib: self.min_free_mib.unwrap_or(current.min_free_mib),
            temp_max_age_hours: self
                .temp_max_age_hours
                .unwrap_or(current.temp_max_age_hours),
            cleanup_interval_hours: self
                .cleanup_interval_hours
                .unwrap_or(current.cleanup_interval_hours),
        };
        policy.validate()?;
        Ok(policy)
    }
}

impl Policy {
    pub fn validate(&self) -> Result<()> {
        ensure!(
            self.quota_mib > 0 && self.quota_mib <= u64::MAX / MIB,
            "quota_mib must be positive and fit in bytes"
        );
        ensure!(
            (1..=100).contains(&self.warn_percent),
            "warn_percent must be between 1 and 100"
        );
        ensure!(
            self.min_free_mib <= u64::MAX / MIB,
            "min_free_mib is too large"
        );
        ensure!(
            (1..=876000).contains(&self.temp_max_age_hours),
            "temp_max_age_hours must be between 1 and 876000"
        );
        ensure!(
            (1..=8760).contains(&self.cleanup_interval_hours),
            "cleanup_interval_hours must be between 1 and 8760"
        );
        Ok(())
    }
}

#[derive(Debug)]
pub struct StorageLimit(pub String);
impl std::fmt::Display for StorageLimit {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        self.0.fmt(f)
    }
}
impl std::error::Error for StorageLimit {}

#[derive(Serialize)]
pub struct Status {
    pub policy: Policy,
    pub used_bytes: u64,
    pub quota_bytes: u64,
    pub available_bytes: u64,
    pub categories: BTreeMap<String, u64>,
    pub used_percent: f64,
    pub state: &'static str,
    pub warning: Option<String>,
    pub uploads_paused: bool,
}

fn inventory(root: &Path) -> Result<BTreeMap<String, u64>> {
    let mut categories = BTreeMap::<String, u64>::new();
    let mut pending = vec![root.to_owned()];
    while let Some(directory) = pending.pop() {
        for entry in fs::read_dir(directory)? {
            let entry = entry?;
            let kind = entry.file_type()?;
            ensure!(
                !kind.is_symlink(),
                "Hub storage must not contain symlinks: {}",
                entry.path().display()
            );
            if kind.is_dir() {
                pending.push(entry.path());
            } else if kind.is_file() {
                let relative = entry.path().strip_prefix(root)?.to_owned();
                let first = relative
                    .components()
                    .next()
                    .unwrap()
                    .as_os_str()
                    .to_string_lossy();
                let category = match first.as_ref() {
                    "repos" => "git",
                    "lfs" => "lfs",
                    "tmp" => "temporary",
                    name if name.starts_with("hub.sqlite3") => "database",
                    _ => "other",
                };
                let count = categories.entry(category.into()).or_default();
                *count = count
                    .checked_add(entry.metadata()?.len())
                    .context("Storage size overflow")?;
            }
        }
    }
    Ok(categories)
}

pub fn status(state: &State) -> Result<Status> {
    status_at(&state.root, &state.config.storage)
}

fn status_at(root: &Path, policy: &Policy) -> Result<Status> {
    let categories = inventory(root)?;
    let used = categories
        .values()
        .try_fold(0u64, |sum, n| sum.checked_add(*n))
        .context("Storage size overflow")?;
    Ok(evaluate(
        policy,
        used,
        fs2::available_space(root)?,
        categories,
    ))
}

fn evaluate(
    policy: &Policy,
    used: u64,
    available: u64,
    categories: BTreeMap<String, u64>,
) -> Status {
    let quota = policy.quota_mib * MIB;
    let (state, warning, paused) = if available < policy.min_free_mib * MIB {
        (
            "disk_low",
            Some(format!(
                "Uploads paused: filesystem has {available} bytes free, below the {} MiB reserve",
                policy.min_free_mib
            )),
            true,
        )
    } else if used >= quota {
        (
            "quota_exceeded",
            Some(format!(
                "Uploads paused: Hub uses {used} of {quota} quota bytes; review storage or increase quota_mib"
            )),
            true,
        )
    } else if (used as u128) * 100 >= (quota as u128) * u128::from(policy.warn_percent) {
        (
            "warning",
            Some(format!(
                "Hub storage warning: {used} of {quota} bytes used; configured warning threshold is {}%",
                policy.warn_percent
            )),
            false,
        )
    } else {
        ("ok", None, false)
    };
    Status {
        policy: policy.clone(),
        used_bytes: used,
        quota_bytes: quota,
        available_bytes: available,
        categories,
        used_percent: used as f64 * 100.0 / quota as f64,
        state,
        warning,
        uploads_paused: paused,
    }
}

pub fn check_write(state: &State, additional: u64) -> Result<()> {
    check_write_at(&state.root, &state.config.storage, additional)
}

pub fn check_write_at(root: &Path, policy: &Policy, additional: u64) -> Result<()> {
    let current = status_at(root, policy)?;
    if current.uploads_paused {
        return Err(StorageLimit(current.warning.unwrap()).into());
    }
    let room = current.quota_bytes.saturating_sub(current.used_bytes).min(
        current
            .available_bytes
            .saturating_sub(policy.min_free_mib * MIB),
    );
    if additional > room {
        return Err(StorageLimit(format!("Upload needs {additional} bytes but only {room} bytes remain within the Hub quota and disk reserve")).into());
    }
    Ok(())
}

pub struct UploadBudget {
    root: PathBuf,
    remaining: u64,
    reserve: u64,
}
impl UploadBudget {
    pub fn new(state: &State, announced: Option<usize>) -> Result<Self> {
        check_write(state, announced.unwrap_or(0) as u64)?;
        let current = status(state)?;
        Ok(Self {
            root: state.root.clone(),
            remaining: current.quota_bytes.saturating_sub(current.used_bytes),
            reserve: state.config.storage.min_free_mib * MIB,
        })
    }
    pub fn consume(&mut self, size: usize) -> Result<()> {
        let size = size as u64;
        if size > self.remaining
            || size > fs2::available_space(&self.root)?.saturating_sub(self.reserve)
        {
            return Err(StorageLimit(
                "Upload stopped before writing: Hub quota or filesystem reserve would be exceeded"
                    .into(),
            )
            .into());
        }
        self.remaining -= size;
        Ok(())
    }
}

pub fn copy_upload(
    state: &State,
    source: &mut dyn Read,
    destination: &mut dyn Write,
    announced: Option<usize>,
) -> Result<u64> {
    let mut budget = UploadBudget::new(state, announced)?;
    let mut total = 0;
    let mut buffer = [0u8; 65536];
    loop {
        let count = source.read(&mut buffer)?;
        if count == 0 {
            return Ok(total);
        }
        total += count as u64;
        budget.consume(count)?;
        destination.write_all(&buffer[..count])?;
    }
}

#[derive(Serialize)]
pub struct CleanupReport {
    pub applied: bool,
    pub candidate_files: usize,
    pub candidate_bytes: u64,
    pub removed_files: usize,
    pub removed_bytes: u64,
    pub files: Vec<String>,
}

pub fn cleanup(state: &State, apply: bool) -> Result<CleanupReport> {
    let cutoff = SystemTime::now()
        .checked_sub(Duration::from_secs(
            state.config.storage.temp_max_age_hours * 3600,
        ))
        .context("Invalid cleanup cutoff")?;
    let mut directories = vec![(state.root.join("tmp"), false)];
    for repo in state.repositories()? {
        directories.push((state.root.join("lfs").join(repo.id), true));
    }
    let mut report = CleanupReport {
        applied: apply,
        candidate_files: 0,
        candidate_bytes: 0,
        removed_files: 0,
        removed_bytes: 0,
        files: Vec::new(),
    };
    for (directory, legacy_lfs) in directories {
        let metadata = match fs::symlink_metadata(&directory) {
            Ok(value) => value,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => continue,
            Err(e) => return Err(e.into()),
        };
        ensure!(
            metadata.is_dir() && !metadata.file_type().is_symlink(),
            "Temporary directory must be a real directory"
        );
        for entry in fs::read_dir(&directory)? {
            let entry = entry?;
            let path = entry.path();
            let metadata = fs::symlink_metadata(&path)?;
            if !metadata.is_file()
                || metadata.file_type().is_symlink()
                || metadata.modified()? > cutoff
            {
                continue;
            }
            if legacy_lfs && !entry.file_name().to_string_lossy().starts_with(".tmp") {
                continue;
            }
            report.candidate_files += 1;
            report.candidate_bytes += metadata.len();
            report.files.push(
                path.strip_prefix(&state.root)?
                    .to_string_lossy()
                    .into_owned(),
            );
            if apply {
                fs::remove_file(&path)?;
                report.removed_files += 1;
                report.removed_bytes += metadata.len();
            }
        }
    }
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn thresholds_and_partial_updates_preserve_the_other_limits() {
        let policy = Policy {
            quota_mib: 10,
            min_free_mib: 2,
            warn_percent: 75,
            ..Policy::default()
        };
        assert_eq!(
            evaluate(&policy, 7 * MIB, 4 * MIB, BTreeMap::new()).state,
            "ok"
        );
        assert_eq!(
            evaluate(&policy, 8 * MIB, 4 * MIB, BTreeMap::new()).state,
            "warning"
        );
        assert!(evaluate(&policy, 10 * MIB, 4 * MIB, BTreeMap::new()).uploads_paused);
        assert_eq!(evaluate(&policy, 0, MIB, BTreeMap::new()).state, "disk_low");
        let update: PolicyUpdate = serde_json::from_str(r#"{"warn_percent":90}"#).unwrap();
        let changed = update.apply(&policy).unwrap();
        assert_eq!(
            (
                changed.quota_mib,
                changed.warn_percent,
                changed.min_free_mib
            ),
            (10, 90, 2)
        );
        assert!(
            PolicyUpdate {
                warn_percent: Some(0),
                ..Default::default()
            }
            .apply(&policy)
            .is_err()
        );
    }
}
