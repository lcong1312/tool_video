from __future__ import annotations

import argparse
import re
from pathlib import Path


def replace_one(path: Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    new_text, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise SystemExit(f"Could not update version in {path}")
    path.write_text(new_text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Set CapCut Video Tool version in source and installer.")
    parser.add_argument("version")
    args = parser.parse_args()

    version = args.version.strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise SystemExit("Version must look like X.Y.Z, for example 1.0.3")

    replace_one(
        Path("capcut_video_gui.py"),
        r'^APP_VERSION\s*=\s*"[^"]+"',
        f'APP_VERSION = "{version}"',
    )
    replace_one(
        Path("installer/CapCutVideoToolSetup.iss"),
        r'^#define MyAppVersion\s+"[^"]+"',
        f'#define MyAppVersion "{version}"',
    )
    print(f"Set app version to {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
