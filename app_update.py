from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path


MANIFEST_ENV_VAR = "CAPCUT_VIDEO_TOOL_UPDATE_URL"
DEFAULT_MANIFEST_URL = "https://update.nexflow.click/latest.json"


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    download_url: str
    notes: str = ""
    sha256: str = ""
    file_name: str = "CapCutVideoToolSetup.exe"


def normalize_manifest_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme:
        url = "https://" + url
        parsed = urllib.parse.urlparse(url)
    if parsed.path.endswith("/"):
        return urllib.parse.urljoin(url, "latest.json")
    if not parsed.path:
        return urllib.parse.urljoin(url + "/", "latest.json")
    return url


def compare_versions(left: str, right: str) -> int:
    left_parts = _version_parts(left)
    right_parts = _version_parts(right)
    max_len = max(len(left_parts), len(right_parts))
    left_parts.extend([0] * (max_len - len(left_parts)))
    right_parts.extend([0] * (max_len - len(right_parts)))
    if left_parts == right_parts:
        return 0
    return 1 if left_parts > right_parts else -1


def fetch_update_info(manifest_url: str, timeout: float = 8.0) -> UpdateInfo | None:
    manifest_url = normalize_manifest_url(manifest_url or os.environ.get(MANIFEST_ENV_VAR, "") or DEFAULT_MANIFEST_URL)
    if not manifest_url:
        return None
    request = urllib.request.Request(
        manifest_url,
        headers={"User-Agent": "CapCutVideoTool-Updater"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = json.loads(response.read().decode("utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Manifest update không hợp lệ.")

    version = str(data.get("version") or "").strip()
    download_url = str(data.get("download_url") or "").strip()
    if not version or not download_url:
        raise ValueError("Manifest update thiếu version hoặc download_url.")

    download_url = urllib.parse.urljoin(manifest_url, download_url)
    return UpdateInfo(
        version=version,
        download_url=download_url,
        notes=str(data.get("notes") or "").strip(),
        sha256=str(data.get("sha256") or "").strip().lower(),
        file_name=str(data.get("file_name") or "CapCutVideoToolSetup.exe").strip() or "CapCutVideoToolSetup.exe",
    )


def is_newer_version(current_version: str, latest_version: str) -> bool:
    return compare_versions(latest_version, current_version) > 0


def open_download(update: UpdateInfo) -> None:
    if sys.platform.startswith("win"):
        os.startfile(update.download_url)  # type: ignore[attr-defined]
        return
    subprocess.Popen([_open_command(), update.download_url], close_fds=True)


def download_installer(update: UpdateInfo, timeout: float = 30.0) -> Path:
    target_dir = Path(tempfile.gettempdir()) / "CapCutVideoToolUpdates"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / Path(update.file_name).name
    request = urllib.request.Request(
        update.download_url,
        headers={"User-Agent": "CapCutVideoTool-Updater"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        target.write_bytes(response.read())
    return target


def run_installer(path: Path) -> None:
    subprocess.Popen([str(path)], close_fds=True)


def _version_parts(value: str) -> list[int]:
    parts: list[int] = []
    for chunk in str(value).strip().split("."):
        digits = "".join(char for char in chunk if char.isdigit())
        parts.append(int(digits) if digits else 0)
    return parts or [0]


def _open_command() -> str:
    if sys.platform == "darwin":
        return "open"
    return "xdg-open"
