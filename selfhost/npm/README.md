# Private AgentGit Hub npm package

This package distributes a prebuilt private Hub from
[binawoh/agentgit-selfhost](https://github.com/binawoh/agentgit-selfhost).
The service and its data run on your own VPS. The npm registry hosts the
installation package; it does not host the service or save your conversations.

Version 0.2.0 includes static musl binaries for **Linux x64 and ARM64**. A small
shell launcher selects the host architecture; glibc and Alpine/musl systems are
supported. CI tests Ubuntu 24.04, Debian Bookworm, and Alpine on both architectures.
Windows, macOS, and 32-bit systems are not supported by this npm package.
Git, a POSIX shell, `uname`, and `readlink -f` must be installed separately
(the latter utilities are provided by coreutils or BusyBox). Node.js/npm are only needed to install or
update the package; the running server is a native executable. The package has
no JavaScript dependencies or install scripts, and installation does not start
services, create credentials, or import sessions.

## Install from npm

The published package is
[`@jooooesg/agit-selfhost`](https://www.npmjs.com/package/@jooooesg/agit-selfhost).
For a new Linux x64 or ARM64 installation, install Git first (`apt-get install git`
on Debian/Ubuntu, or `apk add git` on Alpine):

```sh
sudo npm install --global --prefix /opt/agit-selfhost --ignore-scripts \
  --no-audit --no-fund @jooooesg/agit-selfhost@0.2.0
/opt/agit-selfhost/bin/agit-selfhost --help
```

Pin a version for reproducible installs. The published `0.1.0` package was built
from the original `binawoh/agent-git` fork at
`66c3a042c6b6643de7627b19b8a65984054beb1c`; its provenance does not change when
the backend moves to this repository.
Complete the service and HTTPS setup in `RUNBOOK.md` before connecting clients.
For an existing standalone installation, preserve its executable path as
described below.

## Install a downloaded package

Verify the tarball against the checksum supplied by the release, then use a
stable prefix outside the Hub data directory:

```sh
sha256sum --check PACKAGE.tgz.sha256
sudo npm install --global --prefix /opt/agit-selfhost --ignore-scripts \
  --no-audit --no-fund ./PACKAGE.tgz
/opt/agit-selfhost/bin/agit-selfhost --help
```

Follow `RUNBOOK.md` to create the service user, initialize the Hub, configure
HTTPS, and set up clients. Use `/opt/agit-selfhost/bin/agit-selfhost` for both
initialization and the systemd `ExecStart` executable. Persistent data belongs
in `/var/lib/agit-selfhost`, outside the npm installation.
The systemd example applies to systemd distributions; on Alpine, run `serve`
under the host's service manager. Installation never configures a service itself.

Quota and warning thresholds are configurable, for example:

```sh
/opt/agit-selfhost/bin/agit-selfhost --data /var/lib/agit-selfhost init \
  --owner YOUR_OWNER --public-url https://history.example.com \
  --quota-mib 10240 --warn-percent 90
```

Defaults are a 5 GiB upload budget, an 80% warning, a 3 GiB free-disk reserve,
and daily cleanup of abandoned temporary files older than seven days. Saved
conversations and completed attachments never expire automatically. Use
`storage-status`, `storage-configure`, or the authenticated API described in
`RUNBOOK.md` to inspect and change the policy.

Do not run a persistent Hub through `npx`: its cache path is not a stable
installation location. Git receive hooks record the real executable's absolute
path. Keep the same npm prefix and package name for updates, stop the service
before replacing the package, then start and verify it. Moving from a standalone
binary installation to npm requires preserving the original executable path for
existing hooks; installing a package alone does not migrate those hooks.

## Build and publish

Use the GitHub Actions workflow for native builds of both architectures. For
manual builds, install musl-tools and build the appropriate target on each native
architecture from the same source commit (x64 example):

```sh
rustup target add x86_64-unknown-linux-musl
CC_x86_64_unknown_linux_musl=musl-gcc \
  CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_LINKER=musl-gcc \
  cargo build --locked --release --target x86_64-unknown-linux-musl
```

Use `aarch64-unknown-linux-musl` and the corresponding compiler environment
variables on ARM64. Collect both binaries, then use Python 3.11 or later and npm:

```sh
python3 selfhost/npm/pack.py --binary-x64 /path/to/x64/agit-selfhost \
  --binary-arm64 /path/to/arm64/agit-selfhost \
  --name @YOUR_NPM_ACCOUNT/agit-selfhost --source-commit "$(git rev-parse HEAD)" \
  --output selfhost/artifacts/npm
```

Replace the package name with a lowercase name owned by your actual npm account.
The packer validates both ELF architectures and rejects dynamic-library dependencies.
It does not publish anything. Its allowlist includes only the binaries, launcher,
license, deployment examples, and documentation. The build metadata contains the
checksums, target architectures, and the source commit supplied by the caller; build from that
commit before packing. Run the protocol test against the installed package before
publishing.

After logging into your npm account, a verified tarball can be published with
`npm publish ./PACKAGE.tgz --access public --tag next`. This is separate from the
upstream `@einsia/agent-git` CLI package. Local tarball installation does not
require an npm account or a public registry release.
