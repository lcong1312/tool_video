from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_source_version() -> str:
    gui_path = Path("capcut_video_gui.py")
    if not gui_path.is_file():
        return ""
    match = re.search(r'^APP_VERSION\s*=\s*"([^"]+)"', gui_path.read_text(encoding="utf-8"), re.MULTILINE)
    return match.group(1) if match else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Create latest.json for CapCut Video Tool updates.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--installer", default="installer_output/CapCutVideoToolSetup.exe")
    parser.add_argument("--out-dir", default="updates")
    parser.add_argument("--notes", default="")
    parser.add_argument("--skip-version-check", action="store_true")
    args = parser.parse_args()

    source_version = read_source_version()
    if not args.skip_version_check and source_version and source_version != args.version:
        raise SystemExit(
            f"Version mismatch: capcut_video_gui.py has {source_version}, "
            f"but manifest version is {args.version}. Run tools\\set_app_version.py {args.version} first."
        )

    installer = Path(args.installer).resolve()
    if not installer.is_file():
        raise SystemExit(f"Installer không tồn tại: {installer}")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target_installer = out_dir / installer.name
    if installer != target_installer.resolve():
        target_installer.write_bytes(installer.read_bytes())

    manifest = {
        "version": args.version,
        "file_name": target_installer.name,
        "download_url": target_installer.name,
        "sha256": sha256_file(target_installer),
        "notes": args.notes,
    }
    (out_dir / "latest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created {out_dir / 'latest.json'}")
    print(f"Copied installer: {target_installer}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
