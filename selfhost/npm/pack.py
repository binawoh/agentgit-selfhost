"""Pack the Linux Hub binary without publishing or reading local Hub data."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import struct
import tarfile
import tempfile
import tomllib


def validate_binary(binary, architecture):
    machine = {"x64": 62, "arm64": 183}[architecture]
    if len(binary) < 64 or binary[:6] != b"\x7fELF\x02\x01" or struct.unpack_from("<H", binary, 18)[0] != machine:
        raise ValueError(f"Expected a little-endian Linux {architecture} ELF binary")
    offset = struct.unpack_from("<Q", binary, 32)[0]
    entry_size, count = struct.unpack_from("<HH", binary, 54)
    if entry_size < 56 or count == 0 or offset + entry_size * count > len(binary):
        raise ValueError("Invalid ELF program headers")
    for index in range(count):
        kind, _, start, _, _, size, _, _ = struct.unpack_from("<IIQQQQQQ", binary, offset + index * entry_size)
        if kind == 3:
            raise ValueError("Linux packages require static binaries without a dynamic interpreter")
        if kind == 2:
            if start + size > len(binary) or size % 16:
                raise ValueError("Invalid ELF dynamic section")
            for position in range(start, start + size, 16):
                tag, _ = struct.unpack_from("<qQ", binary, position)
                if tag == 1:
                    raise ValueError("Linux packages must not require dynamic libraries")
                if tag == 0:
                    break


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary-x64", type=Path, required=True)
    parser.add_argument("--binary-arm64", type=Path, required=True)
    parser.add_argument("--name", required=True, help="npm package name owned by the publisher")
    parser.add_argument("--source-commit", required=True, help="Git commit used to build the binary")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*", args.name):
        parser.error("Expected a lowercase npm package name")
    if len(args.name) > 214 or args.name.startswith("@einsia/"):
        parser.error("Use the fork publisher's own npm name, not the upstream namespace")
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_commit):
        parser.error("Expected the full source commit SHA")
    root = Path(__file__).resolve().parents[2]
    binaries = {"x64": args.binary_x64.read_bytes(), "arm64": args.binary_arm64.read_bytes()}
    for architecture, binary in binaries.items():
        try:
            validate_binary(binary, architecture)
        except ValueError as error:
            parser.error(str(error))
    version = tomllib.loads((root / "Cargo.toml").read_text("utf-8"))["package"]["version"]
    args.output.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve()
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if npm is None:
        parser.error("npm is required to create the package")
    with tempfile.TemporaryDirectory(prefix="agit-selfhost-npm-") as temporary:
        stage = Path(temporary)
        (stage / "bin").mkdir()
        for architecture, binary in binaries.items():
            executable = stage / f"bin/linux-{architecture}/agit-selfhost"
            executable.parent.mkdir()
            executable.write_bytes(binary)
            executable.chmod(0o755)
        launcher = stage / "bin/agit-selfhost"
        launcher.write_bytes((root / "selfhost/npm/agit-selfhost.sh").read_bytes().replace(b"\r\n", b"\n"))
        launcher.chmod(0o755)
        shutil.copyfile(root / "LICENSE", stage / "LICENSE")
        shutil.copyfile(root / "selfhost/npm/README.md", stage / "README.md")
        shutil.copyfile(root / "selfhost/RUNBOOK.md", stage / "RUNBOOK.md")
        shutil.copytree(root / "selfhost/deploy", stage / "deploy")
        manifest = {
            "name": args.name, "version": version,
            "description": "Private AgentGit Hub for Linux x64 and ARM64, with configurable storage quotas",
            "license": "MIT",
            "repository": {"type": "git", "url": "git+https://github.com/binawoh/agentgit-selfhost.git", "directory": "selfhost/npm"},
            "homepage": "https://github.com/binawoh/agentgit-selfhost/blob/main/selfhost/RUNBOOK.md",
            "os": ["linux"], "cpu": ["x64", "arm64"],
            "bin": {"agit-selfhost": "bin/agit-selfhost"},
            "files": ["bin/", "build.json", "README.md", "RUNBOOK.md", "LICENSE", "deploy/"],
            "publishConfig": {"access": "public", "registry": "https://registry.npmjs.org/"},
        }
        (stage / "package.json").write_text(json.dumps(manifest, indent=2) + "\n", "utf-8")
        (stage / "build.json").write_text(json.dumps({
            "source_commit": args.source_commit,
            "binaries": {architecture: {"sha256": hashlib.sha256(binary).hexdigest(),
                "target": {"x64": "x86_64-unknown-linux-musl", "arm64": "aarch64-unknown-linux-musl"}[architecture]}
                for architecture, binary in binaries.items()},
        }, indent=2) + "\n", "utf-8")
        result = subprocess.run([npm, "pack", "--ignore-scripts", "--json", "--pack-destination", str(output)],
                                cwd=stage, capture_output=True, check=True)
        reports = json.loads(result.stdout.decode("utf-8"))
        report = reports[0] if isinstance(reports, list) else reports[args.name]
        tarball = output / report["filename"]
        with tempfile.TemporaryDirectory(prefix="pack-mode-", dir=output) as mode_directory:
            normalized = Path(mode_directory) / tarball.name
            with tarfile.open(tarball, "r:gz") as source, tarfile.open(normalized, "w:gz") as target:
                for member in source.getmembers():
                    if member.name.startswith("package/bin/") and member.isfile():
                        member.mode = 0o755
                    target.addfile(member, source.extractfile(member) if member.isfile() else None)
            normalized.replace(tarball)
        checksum = hashlib.sha256(tarball.read_bytes()).hexdigest()
        tarball.with_suffix(tarball.suffix + ".sha256").write_text(f"{checksum}  {tarball.name}\n", "utf-8")
        print(json.dumps({"tarball": str(tarball), "sha256": checksum,
                          "files": [entry["path"] for entry in report["files"]]}, indent=2))


if __name__ == "__main__":
    main()
