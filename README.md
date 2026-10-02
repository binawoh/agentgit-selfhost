# AgentGit Selfhost

English | [简体中文](README.zh-CN.md)

A small, headless, single-owner AgentGit Hub for a private Linux VPS. Save
Codex and Claude Code conversation history, then search and read uploaded
sessions from either agent through the compatible client's MCP server.

This is an independent community backend. It is not the official AgentGit
cloud service and is not affiliated with Einsia; the official hosted backend is
not open source. The source repository is public; your running Hub and its
conversation repositories remain private and authenticated.

## What it supports

- Private Git Smart HTTP repositories with atomic ref updates and immutable
  version tags.
- Git LFS attachment storage with content hash verification.
- Personal access tokens, expiring access tokens, rotating refresh tokens,
  and token revocation.
- Session search and bounded transcript reads without cloning a repository.
- Codex archived-session collection and Claude Code transcript collection
  through an explicit local client operation.
- CLI administration, systemd deployment, an HTTPS reverse proxy, and native
  Linux binary distribution through npm.
- Configurable storage quota, warning threshold, free-disk reserve, and periodic
  cleanup of expired temporary uploads.

There is no web dashboard, remote agent execution, automatic native-session
upload, or automatic backup. Saved conversations and completed attachments never
expire automatically. Keep a separate backup.

One Hub serves one owner. To share the software with other people, each person
runs their own Hub.

## Quick start

You need:

- A Linux x64 or ARM64 server with Git, npm (only to install the package),
  systemd, and an HTTPS reverse proxy for a domain you control. The examples use
  `history.example.com`, nginx and a Let's Encrypt certificate.
- On each computer whose sessions you want to save: Git, Git LFS, Python 3.11 or
  newer, and the [companion client](#companion-client).

### 1. Install and initialize the Hub

```sh
sudo apt-get update && sudo apt-get install -y git
sudo npm install --global --prefix /opt/agit-selfhost --ignore-scripts \
  --no-audit --no-fund @jooooesg/agit-selfhost@0.2.1
sudo useradd --system --home /var/lib/agit-selfhost --shell /usr/sbin/nologin agit-hub
sudo install -d -o agit-hub -g agit-hub -m 0700 /var/lib/agit-selfhost
sudo -u agit-hub /opt/agit-selfhost/bin/agit-selfhost --data /var/lib/agit-selfhost init \
  --owner YOUR_NAME --public-url https://history.example.com
```

`init` prints the first personal access token (PAT) once. Store it in a password
manager. `YOUR_NAME` becomes the owner in repository names such as
`YOUR_NAME/history`, and the public URL is the HTTPS address clients will use.
Add the [storage policy](#choose-your-storage-policy) options to `init` to change
the defaults.

### 2. Run it as a service

```sh
sed 's#/usr/local/bin/agit-selfhost#/opt/agit-selfhost/bin/agit-selfhost#' \
  /opt/agit-selfhost/lib/node_modules/@jooooesg/agit-selfhost/deploy/agit-selfhost.service \
  | sudo tee /etc/systemd/system/agit-selfhost.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now agit-selfhost
curl --fail http://127.0.0.1:8177/api/health
```

The service listens on loopback only; do not open port 8177 to the internet.
Repository hooks record the installed executable's path, so later updates must
keep the same npm prefix and package name. Without systemd, run `serve` under the
host's own service manager.

### 3. Publish it over HTTPS

Adapt `deploy/nginx.conf.example`, also installed with the package, to your domain
and certificate. Then check nginx, reload it, and verify the Hub from outside:

```sh
sudo nginx -t && sudo systemctl reload nginx
curl --fail https://history.example.com/api/health
curl -s -o /dev/null -w '%{http_code}\n' https://history.example.com/api/agents
```

The last command prints `401`: the API refuses requests without a token.

### 4. Connect a computer

Build the [companion client](#companion-client) and sign in. Use the first PAT, or
issue one per computer with `issue-token --label NAME` so each can be revoked on its
own ([runbook](selfhost/RUNBOOK.md#restore-maintain-and-back-up)).

PowerShell:

```powershell
$env:AGIT_HOME = Join-Path $env:USERPROFILE 'agit-private'
$env:AGIT_USE_SYSTEM_GIT = '1'
$env:AGIT_TELEMETRY_DISABLED = '1'
$env:AGIT_HUB_URL = 'https://history.example.com'
agit login --hub $env:AGIT_HUB_URL --with-token
agit whoami --check
```

macOS and Linux:

```sh
export AGIT_HOME="$HOME/agit-private" AGIT_USE_SYSTEM_GIT=1 \
  AGIT_TELEMETRY_DISABLED=1 AGIT_HUB_URL=https://history.example.com
agit login --hub "$AGIT_HUB_URL" --with-token
agit whoami --check
```

`--with-token` reads the PAT from standard input until the input ends: paste it,
then press Ctrl-D (Ctrl-Z and Enter in a Windows console), or pipe it from your
password manager. Never pass a PAT as a command-line argument. Set these variables
persistently, for example in your user environment or shell profile, so every agit
process and MCP server uses the same `AGIT_HOME` and Hub. Keep `AGIT_HOME` short on
Windows; very long paths make privacy protection withhold content.

### 5. Save and search sessions

Clone this repository on the computer to use its collection script. The first
command lists what would be uploaded; the second imports and privately publishes it.

```sh
python3 selfhost/collect.py --agit /path/to/agit --repo YOUR_NAME/history
python3 selfhost/collect.py --agit /path/to/agit --repo YOUR_NAME/history --apply --push
```

On Windows, run `python -X utf8` with the `agit.exe` path. Re-running publishes new
turns of sessions collected before. Then give each agent the client's MCP server so
it can `search` and `read_remote` uploaded sessions:

```sh
claude mcp add --scope user agit -e AGIT_HOME="$HOME/agit-private" \
  -e AGIT_HUB_URL=https://history.example.com -e AGIT_USE_SYSTEM_GIT=1 \
  -e AGIT_TELEMETRY_DISABLED=1 -- /path/to/agit mcp
```

For Codex, in `~/.codex/config.toml`:

```toml
[mcp_servers.agit]
command = "/path/to/agit"
args = ["mcp"]
env = { AGIT_HOME = "/home/you/agit-private", AGIT_HUB_URL = "https://history.example.com", AGIT_USE_SYSTEM_GIT = "1", AGIT_TELEMETRY_DISABLED = "1" }
```

MCP reads what is already on the Hub; it does not upload the current conversation.
See the [runbook](selfhost/RUNBOOK.md) for single-session import, restore, token
management, backups and server upgrades.

## Choose your storage policy

For example, choose a 10 GiB quota and a warning at 90% during initialization:

```sh
agit-selfhost --data /var/lib/agit-selfhost init --owner YOUR_OWNER \
  --public-url https://history.example.com --quota-mib 10240 --warn-percent 90
```

The defaults are 5 GiB, an 80% warning, a 3 GiB free-disk reserve, and daily
cleanup of temporary files older than seven days. All five settings are
configurable. Existing installations can change individual settings with
`storage-configure` while stopped, or the authenticated HTTP API while running.
`storage-status` reports usage and warnings. At the quota or disk reserve, new
uploads pause while saved data remains readable. See the
[storage policy reference](selfhost/RUNBOOK.md#storage-policy-and-cleanup) for
commands, warning delivery, and the upload budget's limits.

## Build

Install Git and Rust through rustup. The toolchain and dependency versions are
pinned in this repository. Git remains a runtime dependency of the server.

```sh
cargo build --locked --release
cargo test --locked
target/release/agit-selfhost --help
```

The shared AgentGit library is fetched from
[`binawoh/agent-git`](https://github.com/binawoh/agent-git) at the exact revision
in `Cargo.toml`. It is compiled without CLI features. Building the server does
not require installing Codex, Claude Code, or Node.js on the VPS.

Follow the [deployment and operations runbook](selfhost/RUNBOOK.md) to create
the service account, initialize authentication, and configure HTTPS. Keep
private data outside the source checkout and bind the service to loopback.

## Companion client

Use the client built from the pinned revision of
[`binawoh/agent-git`](https://github.com/binawoh/agent-git/tree/69e7489ddd069420cc9d2a569a45bfe0fe6123c6),
based on upstream AgentGit 0.2.6.
It includes the private Hub `read_remote` MCP tool, archived Codex lookup,
atomic publishing, and Windows credential permission fixes. The official client
is not tested against this Hub.

No prebuilt client is published; build it with Git and
[rustup](https://rustup.rs). The checkout pins its Rust toolchain, which rustup
installs on the first build. On Windows, install the Microsoft C++ Build Tools first.

```sh
git clone https://github.com/binawoh/agent-git agit-companion
cd agit-companion
git checkout 69e7489ddd069420cc9d2a569a45bfe0fe6123c6
cargo build --release --locked --bin agit
```

The client is `target/release/agit` (`agit.exe` on Windows). Put it on `PATH`
ahead of any official `agit`. Do not run `agit upgrade` with it: that command
replaces it with the official release. When this repository pins a new revision,
rebuild from that revision.

Configuring MCP enables access to records that have already been uploaded.
It does not upload your current conversation. See the runbook for explicit
collection, import, push, and restore commands. The `agit rc` remote-control
service is outside this backend's scope.

## Verification

The GitHub Actions workflow builds static musl servers and the pinned companion
client on native Ubuntu x64 and ARM64 runners. It installs the combined npm
artifact and runs protocol and storage tests on Ubuntu, plus storage tests in
Debian and Alpine containers on both architectures. All conversations used by
the tests are synthetic. Artifacts include both binaries, the npm tarball with
its checksum and source metadata, and test reports.

To run the protocol test with a compatible client you already built:

```sh
python3 selfhost/e2e.py --agit /path/to/agit --server target/release/agit-selfhost \
  --output selfhost/artifacts/e2e-linux.json
python3 selfhost/storage_e2e.py --server target/release/agit-selfhost
```

Use Python 3.11 or newer. On Windows, use `python -X utf8`, `.exe` binary paths,
and `--state-parent "$env:USERPROFILE"` for the test's private state directory.

## npm distribution

[`@jooooesg/agit-selfhost`](https://www.npmjs.com/package/@jooooesg/agit-selfhost)
distributes native static Linux x64 and ARM64 servers, with automatic architecture
selection. npm hosts the installation
package, not your running service or your conversations. See the
[package documentation](selfhost/npm/README.md).

The published `0.1.0` package was built from the original fork before this
repository was extracted. Its source provenance remains that original commit;
creating this repository does not replace or republish an npm version.

## License and origin

MIT. See [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md). This backend reuses
the MIT-licensed [Einsia/agent-git](https://github.com/Einsia/agent-git) core
through the pinned companion fork. Contributions here do not submit changes
to the upstream project.
