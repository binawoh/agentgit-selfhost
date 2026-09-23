"""Verify configurable storage admission and temporary-file cleanup with isolated data."""

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    server = args.server.resolve()
    with tempfile.TemporaryDirectory(prefix="agentgit-storage-") as temporary:
        root = Path(temporary)
        data = root / "data"
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        origin = f"http://127.0.0.1:{port}"
        opener = build_opener(ProxyHandler({}))
        access = None
        process = None

        def cli(*arguments):
            return subprocess.run([str(server), "--data", str(data), *arguments], check=True,
                                  capture_output=True, text=True, encoding="utf-8", timeout=30).stdout

        def api(path, method="GET", body=None, expected=200, headers=None, authenticated=True):
            encoded = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
            request_headers = {"Content-Type": "application/json", **(headers or {})}
            if authenticated and access:
                request_headers["Authorization"] = f"Bearer {access}"
            request = Request(origin + path, data=encoded, method=method, headers=request_headers)
            try:
                response = opener.open(request, timeout=30)
            except HTTPError as failure:
                response = failure
            with response:
                payload = response.read()
                assert response.status == expected, (path, response.status, payload[:200])
                result = json.loads(payload) if "json" in response.headers.get("Content-Type", "") else payload
                return result, response.headers

        def start():
            log = (root / "server.log").open("ab")
            child = subprocess.Popen([str(server), "--data", str(data), "serve", "--listen", f"127.0.0.1:{port}"],
                                     stdout=log, stderr=log)
            log.close()
            for _ in range(100):
                if child.poll() is not None:
                    raise AssertionError((root / "server.log").read_text())
                try:
                    api("/api/health", authenticated=False)
                    return child
                except OSError:
                    time.sleep(0.1)
            child.terminate()
            child.wait(timeout=10)
            raise AssertionError("Storage test server did not start")

        try:
            pat = cli("init", "--owner", "tester", "--public-url", origin, "--quota-mib", "8", "--warn-percent", "1",
                      "--min-free-mib", "0", "--temp-max-age-hours", "1", "--cleanup-interval-hours", "1").strip()
            old = data / "tmp" / "abandoned-upload"
            old.write_bytes(b"expired temporary bytes")
            os.utime(old, (time.time() - 7200,) * 2)
            current = data / "tmp" / "recent-upload"
            current.write_bytes(b"active bytes")
            process = start()
            access = api("/api/auth/login", "POST", {"token": pat}, authenticated=False)[0]["access_token"]
            api("/api/storage", authenticated=False, expected=401)
            assert not old.exists() and current.exists()
            status, headers = api("/api/storage")
            assert status["state"] == "warning" and headers["X-AgentGit-Storage-Warning"]
            assert status["policy"]["quota_mib"] == 8
            policy = api("/api/storage/policy", "PATCH", {"warn_percent": 90})[0]["policy"]
            assert policy["quota_mib"] == 8 and policy["warn_percent"] == 90
            api("/api/storage/policy", "PATCH", {"warn_percent": 0}, expected=400)
            assert api("/api/storage")[0]["policy"] == policy

            repo = api("/api/agents", "POST", {"name": "storage", "public": False}, expected=201)[0]
            auth = {"X-AgentGit-Expected-Agent-Id": repo["agent_id"]}
            payload = b"saved attachment survives quota exhaustion"
            oid = hashlib.sha256(payload).hexdigest()
            object_url = f"/tester/storage.git/info/lfs/objects/{oid}"
            api(object_url, "PUT", payload, headers=auth)
            artifact = data / "lfs" / repo["agent_id"] / oid
            os.utime(artifact, (time.time() - 7200,) * 2)
            stale = data / "tmp" / "stale-upload"
            stale.write_bytes(b"remove only this temporary file")
            os.utime(stale, (time.time() - 7200,) * 2)
            legacy = artifact.parent / ".tmpLegacyUpload"
            legacy.write_bytes(b"old interrupted LFS upload")
            os.utime(legacy, (time.time() - 7200,) * 2)
            if os.name != "nt":
                (data / "tmp" / "external-link").symlink_to(artifact)
            preview = api("/api/storage/cleanup", "POST", {})[0]
            assert preview["candidate_files"] == 2 and preview["removed_files"] == 0
            assert stale.exists() and legacy.exists()
            cleaned = api("/api/storage/cleanup", "POST", {"apply": True})[0]
            assert cleaned["removed_files"] == 2 and artifact.exists() and current.exists()
            if os.name != "nt":
                (data / "tmp" / "external-link").unlink()
            assert api(object_url, headers=auth)[0] == payload

            api("/api/storage/policy", "PATCH", {"quota_mib": 1})
            oversized = b"x" * (2 * 1024 * 1024)
            rejected_oid = hashlib.sha256(oversized).hexdigest()
            rejected_url = f"/tester/storage.git/info/lfs/objects/{rejected_oid}"
            rejected = api(rejected_url, "PUT", oversized, expected=507, headers=auth)[0]
            assert rejected["kind"] == "storage_limit"
            assert not (artifact.parent / rejected_oid).exists()
            current_usage = api("/api/storage")[0]
            remaining = current_usage["quota_bytes"] - current_usage["used_bytes"]
            assert remaining > 0
            streaming = b"x" * (remaining + 1)
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
            try:
                try:
                    connection.request("PUT", rejected_url,
                                       body=(streaming[i:i + 65536] for i in range(0, len(streaming), 65536)),
                                       headers={"Authorization": f"Bearer {access}", **auth}, encode_chunked=True)
                except ConnectionError:
                    # A server may reject a streaming body before the client finishes sending it.
                    pass
                response = connection.getresponse()
                assert response.status == 507, response.read()
                response.read()
            finally:
                connection.close()
            assert not (artifact.parent / rejected_oid).exists()
            assert list((data / "tmp").iterdir()) == [current]

            padding = data / "quota-test-padding"
            with padding.open("wb") as stream:
                stream.truncate(1024 * 1024)
            assert api("/api/storage")[0]["state"] == "quota_exceeded"
            api("/api/agents", "POST", {"name": "blocked"}, expected=507)
            api("/tester/storage.git/git-receive-pack", "POST", b"0000", expected=507, headers=auth)
            assert api(object_url, headers=auth)[0] == payload
            padding.unlink()
            available = api("/api/storage")[0]["available_bytes"]
            api("/api/storage/policy", "PATCH", {"min_free_mib": available // (1024 * 1024) + 1})
            assert api("/api/storage")[0]["state"] == "disk_low"
            api(rejected_url, "PUT", b"small", expected=507, headers=auth)
            assert api(object_url, headers=auth)[0] == payload
            api("/api/storage/policy", "PATCH", {"quota_mib": 8, "warn_percent": 65, "min_free_mib": 0})
            process.terminate()
            process.wait(timeout=10)
            process = start()
            assert api("/api/storage")[0]["policy"]["warn_percent"] == 65
            assert api(object_url, headers=auth)[0] == payload
            process.terminate()
            process.wait(timeout=10)
            process = None
            config_path = data / "config.json"
            original = json.loads(config_path.read_text())
            del original["storage"]
            config_path.write_text(json.dumps(original))
            migrated = json.loads(cli("storage-status"))
            assert migrated["policy"]["quota_mib"] == 5120 and migrated["policy"]["warn_percent"] == 80
            updated = json.loads(cli("storage-configure", "--quota-mib", "16", "--warn-percent", "70", "--min-free-mib", "0"))
            assert updated["policy"]["quota_mib"] == 16 and updated["policy"]["warn_percent"] == 70
            assert json.loads(cli("storage-cleanup"))["applied"] is False
            report = {"status": "passed", "checks": ["custom policy and persistence", "warning headers", "startup cleanup",
                      "preview and safe cleanup", "known-length and chunked upload quotas", "Git admission",
                      "disk reserve", "reads after upload pause", "legacy configuration defaults", "CLI management"]}
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report))
        finally:
            if process is not None:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
