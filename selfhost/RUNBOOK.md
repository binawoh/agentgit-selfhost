# Private headless AgentGit Hub

This repository provides a single-owner private Hub for the AgentGit client.
It stores Git history and LFS attachments, authenticates with personal access
tokens (PATs), and serves session search and bounded transcript reads. There is
no browser management UI, subscription service, public sharing, organization
management, or remote agent execution. Unsupported API operations fail explicitly.

Use the companion client from `binawoh/agent-git` at
`66c3a042c6b6643de7627b19b8a65984054beb1c`, also pinned as the core dependency
in `Cargo.toml`. It adds `read_remote` to MCP, archive-aware Codex ID lookup,
atomic Hub pushes, and a Windows OWNER RIGHTS permission fix.
It retains all other credential checks.

## Build and verify

Install Rust through rustup, Python 3, Git and Git LFS. The repository pins its
Rust toolchain. Ordinary source builds use system Git; Git is still required.

```sh
cargo build --locked
cargo test --locked
python3 selfhost/e2e.py --agit /path/to/compatible/agit --server target/debug/agit-selfhost \
  --output selfhost/artifacts/e2e-linux.json
```

On Windows use `python -X utf8`, `.exe` binaries, and a trusted state parent:

```powershell
python -X utf8 selfhost/e2e.py --agit C:/path/to/compatible/agit.exe --server target/debug/agit-selfhost.exe --state-parent $env:USERPROFILE --output selfhost/artifacts/e2e-windows.json
```

The test creates isolated client homes and synthetic transcripts, including an
archived Codex file. It starts and stops its own loopback Hub. It checks real
Git transport, Chinese search, filters, MCP reads before cloning, incremental
versions, Git LFS restoration, rejected transactions, restart persistence and
token revocation. It retains temporary data for diagnosis and prints that path.
No real native sessions are read. Raw local test reports are ignored by Git.
The `Verify private Hub` workflow builds static musl binaries on native x64 and
ARM64 Ubuntu runners, then runs the protocol and storage tests against the
installed npm package. It also runs storage tests on Debian and Alpine on each
architecture. Artifacts include `server-x64`, `server-arm64`, the combined
`agit-selfhost-npm` tarball with its checksum, and `protocol-evidence-*` reports.

Run storage tests independently with
`python3 selfhost/storage_e2e.py --server target/debug/agit-selfhost`.

## Ubuntu deployment

An optional [npm package](npm/README.md) distributes the same native server.
Installing a local tarball does not require an npm account. The VPS still hosts
the running service and data; package publication is only a distribution step.

Inspect the actual VPS OS, architecture, free disk, memory, installed services,
firewall and domain before applying these examples. They assume a Linux host
using systemd and an HTTPS domain routed to that host. The HTTP service binds to
loopback; do not expose port 8177 directly. Existing web-server configuration
must be integrated without replacing unrelated sites.

Build on a machine matching the VPS architecture, or on the VPS if it has enough
build memory. The server is independent of Claude/Codex binaries and model runtimes.

```sh
cargo build --locked --release
sudo apt-get update
sudo apt-get install -y git
sudo useradd --system --home /var/lib/agit-selfhost --shell /usr/sbin/nologin agit-hub
sudo install -d -o agit-hub -g agit-hub -m 0700 /var/lib/agit-selfhost
sudo install -m 0755 target/release/agit-selfhost /usr/local/bin/agit-selfhost
sudo -u agit-hub /usr/local/bin/agit-selfhost --data /var/lib/agit-selfhost init \
  --owner YOUR_OWNER --public-url https://history.example.com
```

`init` prints the initial PAT once. Store it in a password manager; do not paste
it into Git, shell command arguments or server logs. The database stores token
hashes. Access tokens expire after an hour; refresh tokens rotate and expire
after 30 days. Revoking a PAT also revokes every session issued from it.

```sh
sudo install -m 0644 selfhost/deploy/agit-selfhost.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now agit-selfhost
curl --fail http://127.0.0.1:8177/api/health
```

Configure the existing HTTPS reverse proxy using
[`deploy/nginx.conf.example`](deploy/nginx.conf.example) as a reference. Obtain
a valid certificate using the host's existing certificate management method.
Validate the proxy configuration before reloading it. Verify the public health
endpoint and confirm `/api/agents` returns 401 without credentials.

The service example has a 768 MiB memory ceiling. This is a failure-containment
setting, not a measured minimum or a capacity promise. Default request limits
are 256 MiB per Git/LFS upload and 64 MiB per materialized LOG or VIEW. Parsing,
indexing and Git add overhead beyond those buffers. Measure representative
synthetic data before deciding whether the VPS can handle your longest sessions.
`init --max-snapshot-mib` and `--max-upload-mib` set these limits; proxy limits
must agree. Requests are processed serially; this is a personal archive service.

Keep the executable at `/usr/local/bin/agit-selfhost`: repository receive hooks
record its absolute path. Stop the service before replacing the executable.

## Storage policy and cleanup

All settings are optional at `init` and can be changed later:

| CLI option / JSON field | Default | Meaning |
| --- | --- | --- |
| `--quota-mib` / `quota_mib` | 5120 | Total data admission budget in MiB; positive integer |
| `--warn-percent` / `warn_percent` | 80 | Warn at this percentage of quota; 1 to 100 |
| `--min-free-mib` / `min_free_mib` | 3072 | Pause uploads below this filesystem reserve; 0 disables the reserve |
| `--temp-max-age-hours` / `temp_max_age_hours` | 168 | Expire abandoned temporary files after this many hours; 1 to 876000 |
| `--cleanup-interval-hours` / `cleanup_interval_hours` | 24 | Cleanup interval while running; 1 to 8760 |

1 GiB is 1024 MiB. For example, set 10 GiB with a 90% warning and keep other
settings unchanged:

```sh
sudo systemctl stop agit-selfhost
sudo -u agit-hub /usr/local/bin/agit-selfhost --data /var/lib/agit-selfhost \
  storage-configure --quota-mib 10240 --warn-percent 90
sudo systemctl start agit-selfhost
sudo -u agit-hub /usr/local/bin/agit-selfhost --data /var/lib/agit-selfhost storage-status
```

Changes persist in `config.json`. Old configurations without a storage policy
use the defaults. Lowering the quota below current usage pauses uploads without
deleting data; increasing it allows uploads again if disk space is sufficient.

Authenticated management endpoints also accept the existing access token:

- `GET /api/storage`: policy, usage by category, free bytes, percentage,
  `state`, `warning`, and `uploads_paused`.
- `PATCH /api/storage/policy`: a partial JSON object such as
  `{"quota_mib":10240,"warn_percent":90}`; applies immediately without a restart.
- `POST /api/storage/cleanup`: `{}` previews; `{"apply":true}` deletes the listed
  expired temporary files.

Warnings appear in `storage-status`, the API, `read_remote` transcript results
(a `storage_warning` field visible to the calling agent), authenticated response headers
`X-AgentGit-Storage-State` and `X-AgentGit-Storage-Warning`, Git receive messages,
and server logs when the state changes. This release does not send email or
desktop notifications. Clients must display the warning or query the status;
existing MCP search tools do not automatically display response headers.
New uploads that exceed the admission budget receive HTTP 507, or a Git
pre-receive rejection. Searches, transcript reads, clones, and attachment
downloads remain available while uploads are paused.

Usage counts logical file bytes under the data directory, including Git, LFS,
SQLite/WAL, and temporary files. External backups and unrelated VPS files are
outside the quota but reduce filesystem free space. This is an upload admission
budget, not an operating-system hard quota: Git unpacking, SQLite commits,
authentication, and read-response spooling can use additional transient space.
Keep the disk reserve and per-request limits appropriate for the VPS. Indexing
may pause after Git has accepted a push; searches report `incomplete` until space
is available and `reindex` succeeds. No saved content is evicted to make room.

Cleanup runs once on server startup and then at the configured interval, between
requests. It removes only expired regular files directly in the server-owned
`tmp/` directory and legacy `.tmp*` files inside known LFS repository directories.
It skips symlinks and directories. Saved Git history, completed attachments,
including unreferenced uploads, and native Codex/Claude transcripts are preserved.
Do not store unrelated files in `tmp/`. Inspect or apply manually while stopped:

```sh
sudo systemctl stop agit-selfhost
sudo -u agit-hub /usr/local/bin/agit-selfhost --data /var/lib/agit-selfhost storage-cleanup
sudo -u agit-hub /usr/local/bin/agit-selfhost --data /var/lib/agit-selfhost storage-cleanup --apply
sudo systemctl start agit-selfhost
```

## Windows client and collection

Use a private `AGIT_HOME` outside ancestors writable by other users. A path under
the current user's profile can work when some AppData ancestors do not. The
fork reports the specific rejected ancestor. Do not bypass checks or weaken ACLs.
Set environment variables for the client process and its MCP process; using a
different `AGIT_HOME` means a different login and local repository store.

```powershell
$env:AGIT_HOME = Join-Path $env:USERPROFILE 'agit-private'
$env:AGIT_USE_SYSTEM_GIT = '1'
$env:AGIT_TELEMETRY_DISABLED = '1'
$env:AGIT_HUB_URL = 'https://history.example.com'
agit login --hub $env:AGIT_HUB_URL --with-token
agit whoami --check
```

`--with-token` reads from stdin. Supply the PAT through stdin using your terminal
or password manager. Do not put the PAT in the command line. `AGIT_HOME` contains
credentials and local snapshots; the VPS does not automatically eliminate this
local copy or the original Codex/Claude transcript.

First inventory exactly what would be collected:

```powershell
python -X utf8 selfhost/collect.py --agit C:/path/to/agit.exe --repo YOUR_OWNER/history
```

Collection includes Codex `sessions` and `archived_sessions`, and Claude's main
project transcripts. It skips Claude subagent files, fails on duplicate native
IDs, and never deletes or resumes native conversations. Add `--session ID` to
select exact IDs. After reviewing the inventory, add `--apply --push` to import
and privately publish those branches. Re-running uses the same runtime/ID branch
and settles new content. A session already claimed on another branch is refused
instead of silently rerouted. Native formats or headers it cannot recognize are
not a complete backup; inspect the inventory and failed commands.

For one explicitly selected session:

```text
agit import NATIVE_ID --from codex --into YOUR_OWNER/history@codex-ID --independent
agit push YOUR_OWNER/history@codex-ID --private
```

Configure each agent's stdio MCP server to launch the companion client's `agit mcp`, with
the same private `AGIT_HOME` and Hub URL. `search` returns saved hits; `read_remote`
takes `repo`, `session_id`, the immutable commit from the hit URL's `ref` query
parameter as `reference`, and optional `from`. Follow `next_from` with the same
commit. Reads return original source records in bounded turn ranges. Regular
`show` remains a local-repository operation.

```json
{"command":"C:/path/to/agit.exe","args":["mcp"],"env":{"AGIT_HOME":"C:/Users/YOU/agit-private","AGIT_USE_SYSTEM_GIT":"1","AGIT_HUB_URL":"https://history.example.com","AGIT_TELEMETRY_DISABLED":"1"}}
```

This is a server definition to place in the agent's own MCP configuration format,
not a command that changes all agents automatically.

## Restore, maintain and back up

```text
agit clone YOUR_OWNER/history@BRANCH --no-bind
agit file get PATH --into YOUR_OWNER/history@BRANCH --output DESTINATION
```

Clone retrieves Git snapshots and version tags. LFS files initially remain
pointers; `file get` downloads and verifies the requested attachment. Test a cold
restore with a new `AGIT_HOME`, including historical tags and attachment hashes,
before any local retention changes.

Server administration is local:

```sh
sudo -u agit-hub /usr/local/bin/agit-selfhost --data /var/lib/agit-selfhost list-tokens
sudo -u agit-hub /usr/local/bin/agit-selfhost --data /var/lib/agit-selfhost issue-token --label laptop
sudo -u agit-hub /usr/local/bin/agit-selfhost --data /var/lib/agit-selfhost revoke-token TOKEN_ID
sudo systemctl stop agit-selfhost
sudo -u agit-hub /usr/local/bin/agit-selfhost --data /var/lib/agit-selfhost reindex
sudo systemctl start agit-selfhost
sudo journalctl -u agit-selfhost
```

`reindex` rebuilds derived search tables from saved Git history and requires the
service to be stopped. It preserves repository identities and credentials. Failed indexing preserves Git
history and sets `incomplete=true` on searches until a successful indexing run.
An oversized event is indexed up to a bounded prefix and marks that snapshot
incomplete; later events and other valid snapshots are still indexed. Original
Git data is retained. Rebuild continues across failures and returns a failing
exit code while any repository remains incomplete. Search caps candidate scanning
and reports truncation as incomplete. Unsupported
filters are rejected or exposed through the query's `unknown` field. The index
deduplicates event bodies, but retains snapshot memberships, so disk usage is
not identical to compressed Git history. Configure the storage policy above and
keep a separate backup; saved history is never automatically evicted.

For a consistent server backup, stop the service, copy the entire private data
directory (including config, SQLite/WAL, repositories and LFS), then restart.
Encrypt the backup and store it outside this VPS. Restoring the whole directory
preserves repository UUIDs and tokens. Test restoration on a separate loopback
instance. Copying only `.git` repositories omits authentication and LFS objects.

The client's `.git/agit/secret-dictionary/` and its keys are not pushed. They need
a separate encrypted client backup if restoration of substituted secrets is
required. Git/LFS cold restoration does not prove recovery of native plaintext
secrets. Do not delete original transcripts or dictionaries on that assumption.

Each Git receive transaction is atomic, rejects ref deletion/rewrites and invalid
version tags, and checks LFS existence before publishing refs. Normal client push
still uploads LFS, branches and tags in separate stages. An interrupted push can
leave uploaded but unreferenced objects or branches awaiting tag retry; re-run
push and verify tags. This service does not claim a single transaction across
those three client stages.
