# AgentGit Selfhost

A small, headless, single-owner AgentGit Hub for a private Linux VPS. Save
Codex and Claude Code conversation history, then search and read uploaded
sessions from either agent through the compatible client's MCP server.

This is an independent community backend. It is not the official AgentGit
cloud service. The source repository is public; your running Hub and its
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

## Client compatibility

Use the companion client built from the pinned revision of
[`binawoh/agent-git`](https://github.com/binawoh/agent-git/tree/69e7489ddd069420cc9d2a569a45bfe0fe6123c6),
based on upstream AgentGit 0.2.6.
It includes the private Hub `read_remote` MCP tool, archived Codex lookup,
atomic publishing, and Windows credential permission fixes.

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
