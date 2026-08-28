from __future__ import annotations

import re
from pathlib import Path


def read_version(path: Path) -> str:
    if not path.is_file():
        return ""
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', path.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else ""


def read_inno_version(path: Path) -> str:
    if not path.is_file():
        return ""
    match = re.search(r'^#define MyAppVersion\s+"([^"]+)"', path.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else ""


def main() -> int:
    source_version = read_version(Path("app_version.py"))
    dist_version = read_version(Path("dist/CapCutVideoTool/app_version.py"))
    inno_version = read_inno_version(Path("installer/CapCutVideoToolSetup.iss"))
    if not source_version:
        raise SystemExit("Missing source version in app_version.py")
    if dist_version != source_version:
        raise SystemExit(f"Build version mismatch: source={source_version}, dist={dist_version or 'missing'}")
    if inno_version != source_version:
        raise SystemExit(f"Installer version mismatch: source={source_version}, inno={inno_version or 'missing'}")
    print(f"Build version OK: {source_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
