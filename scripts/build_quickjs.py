"""Build the pinned upstream QuickJS source for yt-dlp's EJS challenges."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "2026-06-04"
SHA256 = "b376e839b322978313d929fd20663b11ba58b75df5a46c126dd19ea2fa70ad2a"


def main():
    source = ROOT / "vendor/sources" / f"quickjs-{VERSION}.tar.xz"
    if hashlib.sha256(source.read_bytes()).hexdigest() != SHA256:
        raise SystemExit("QuickJSソースのSHA256が一致しません。")
    build = ROOT / "vendor/build"
    build.mkdir(parents=True, exist_ok=True)
    target = build / f"quickjs-{VERSION}"
    if not target.exists():
        with tarfile.open(source, "r:xz") as archive:
            archive.extractall(build, filter="data")
    subprocess.run(["make", "-j4", "qjs"], cwd=target, check=True)
    binaries = ROOT / "vendor/bin"
    binaries.mkdir(parents=True, exist_ok=True)
    shutil.copy2(target / "qjs", binaries / "qjs")
    print("QuickJS:", binaries / "qjs")


if __name__ == "__main__":
    main()
