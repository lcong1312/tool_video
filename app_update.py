from __future__ import annotations

import json
import os
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


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


def download_installer(
    update: UpdateInfo,
    target_dir: Path,
    *,
    timeout: float = 30.0,
    progress: Callable[[int, int], None] | None = None,
) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / Path(update.file_name).name
    partial = target.with_suffix(target.suffix + ".download")
    request = urllib.request.Request(
        update.download_url,
        headers={"User-Agent": "CapCutVideoTool-Updater"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            total = int(response.headers.get("Content-Length") or 0)
            downloaded = 0
            with partial.open("wb") as handle:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        progress(downloaded, total)
        partial.replace(target)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    if update.sha256:
        actual_sha256 = sha256_file(target)
        if actual_sha256.lower() != update.sha256.lower():
            target.unlink(missing_ok=True)
            raise ValueError("File update tải về không khớp SHA256.")
    return target


def run_installer(path: Path, *, delete_after_exit: bool = True, wait_for_pid: int | None = None) -> None:
    if wait_for_pid:
        schedule_installer_after_process_exit(path, wait_for_pid, delete_after_exit=delete_after_exit)
        return
    process = subprocess.Popen([str(path)], close_fds=True)
    if delete_after_exit:
        schedule_delete_after_process(path, process.pid)


def schedule_installer_after_process_exit(path: Path, pid: int, *, delete_after_exit: bool = True) -> None:
    escaped_path = str(path).replace("'", "''")
    cleanup = (
        "if ($installer) { Wait-Process -Id $installer.Id -ErrorAction SilentlyContinue }; "
        "Start-Sleep -Seconds 8; "
        f"Remove-Item -LiteralPath '{escaped_path}' -Force -ErrorAction SilentlyContinue"
        if delete_after_exit
        else ""
    )
    command = (
        f"$app=Get-Process -Id {pid} -ErrorAction SilentlyContinue; "
        "if ($app) { Wait-Process -Id $app.Id -ErrorAction SilentlyContinue }; "
        "Start-Sleep -Seconds 1; "
        f"$installer=Start-Process -FilePath '{escaped_path}' -PassThru; "
        f"{cleanup}"
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-Command",
            command,
        ],
        close_fds=True,
        creationflags=creationflags,
    )


def schedule_delete_after_process(path: Path, pid: int) -> None:
    escaped_path = str(path).replace("'", "''")
    command = (
        f"$p=Get-Process -Id {pid} -ErrorAction SilentlyContinue; "
        "if ($p) { Wait-Process -Id $p.Id -ErrorAction SilentlyContinue }; "
        "Start-Sleep -Seconds 8; "
        f"Remove-Item -LiteralPath '{escaped_path}' -Force -ErrorAction SilentlyContinue"
    )
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-Command",
            command,
        ],
        close_fds=True,
        creationflags=creationflags,
    )


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version_parts(value: str) -> list[int]:
    parts: list[int] = []
    for chunk in str(value).strip().split("."):
        digits = "".join(char for char in chunk if char.isdigit())
        parts.append(int(digits) if digits else 0)
    return parts or [0]
