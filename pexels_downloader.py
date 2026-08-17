from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Any


PEXELS_API_BASE = "https://api.pexels.com/v1/videos"
FALLBACK_QUERIES = [
    "nature",
    "landscape",
    "city",
    "travel",
    "people",
    "business",
    "technology",
    "food",
    "ocean",
    "mountain",
    "forest",
    "street",
    "lifestyle",
    "background",
    "cinematic",
]


def safe_name(value: str) -> str:
    value = re.sub(r"[^\w\-. ]+", "_", value, flags=re.UNICODE).strip()
    return value or "pexels"


def is_landscape_16x9(width: int, height: int, tolerance: float = 0.04) -> bool:
    if width <= 0 or height <= 0 or width <= height:
        return False
    return abs((width / height) - (16 / 9)) <= tolerance


def _path_name_is_16x9(path: Path) -> bool:
    match = re.search(r"_(\d+)x(\d+)$", path.stem)
    if not match:
        return True
    return is_landscape_16x9(int(match.group(1)), int(match.group(2)))


def _request_json(url: str, api_key: str) -> tuple[dict[str, Any], dict[str, str]]:
    request = urllib.request.Request(url, headers={"Authorization": api_key, "User-Agent": "srt-capcut-tool/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
            headers = {key: value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        if exc.code == 401:
            raise RuntimeError("Pexels API key khong dung hoac da het quyen truy cap.") from exc
        if exc.code == 429:
            raise RuntimeError("Pexels API bi gioi han request. Hay doi mot luc roi thu lai.") from exc
        raise RuntimeError(f"Pexels API loi HTTP {exc.code}: {detail[:300]}") from exc
    return json.loads(body), headers


def _download_file(url: str, target: Path, progress: Callable[[int, int | None], None] | None = None) -> None:
    temp = target.with_suffix(target.suffix + ".download")
    request = urllib.request.Request(url, headers={"User-Agent": "srt-capcut-tool/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response, temp.open("wb") as handle:
        total_text = response.headers.get("Content-Length")
        total = int(total_text) if total_text and total_text.isdigit() else None
        done = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    temp.replace(target)


def _best_video_file(video: dict[str, Any], *, only_16x9: bool, target_width: int, target_height: int) -> dict[str, Any] | None:
    files = []
    for item in video.get("video_files") or []:
        if item.get("file_type") != "video/mp4":
            continue
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        link = item.get("link")
        if not link or width <= 0 or height <= 0:
            continue
        if only_16x9 and not is_landscape_16x9(width, height):
            continue
        area = width * height
        over_target = width >= target_width and height >= target_height
        files.append((1 if over_target else 0, -abs(area - (target_width * target_height)), area, item))
    if not files:
        return None
    return max(files, key=lambda value: value[:3])[3]


def _search_url(query: str, *, page: int, per_page: int, only_16x9: bool) -> str:
    if query.strip():
        params = {
            "query": query.strip(),
            "page": page,
            "per_page": per_page,
            "orientation": "landscape" if only_16x9 else "",
            "size": "medium",
            "locale": "vi-VN",
        }
        params = {key: value for key, value in params.items() if value != ""}
        return f"{PEXELS_API_BASE}/search?{urllib.parse.urlencode(params)}"
    params = {
        "page": page,
        "per_page": per_page,
        "min_width": 1280 if only_16x9 else "",
        "min_height": 720 if only_16x9 else "",
    }
    params = {key: value for key, value in params.items() if value != ""}
    return f"{PEXELS_API_BASE}/popular?{urllib.parse.urlencode(params)}"


def _query_plan(query: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        clean = term.strip()
        key = clean.casefold()
        if key in seen:
            return
        seen.add(key)
        terms.append(clean)

    if query.strip():
        add(query)
    for fallback in FALLBACK_QUERIES:
        add(fallback)
    add("")
    return terms


def download_pexels_videos(
    *,
    api_key: str,
    query: str,
    output_dir: Path,
    target_count: int,
    only_16x9: bool = True,
    target_width: int = 1920,
    target_height: int = 1080,
    max_workers: int = 6,
    progress: Callable[[str], None] | None = None,
) -> list[Path]:
    api_key = api_key.strip() or os.environ.get("PEXELS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Chua nhap Pexels API key. Ban co the nhap trong GUI hoac dat bien moi truong PEXELS_API_KEY.")
    if target_count <= 0:
        raise RuntimeError("So video can tai tu Pexels phai lon hon 0.")

    output_dir.mkdir(parents=True, exist_ok=True)
    meta_path = output_dir / "pexels_attribution.json"
    try:
        attribution = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else []
    except Exception:
        attribution = []

    downloaded = sorted(output_dir.glob("pexels_*.mp4"))
    valid_existing = [
        path
        for path in downloaded
        if path.is_file() and path.stat().st_size > 1024 and (not only_16x9 or _path_name_is_16x9(path))
    ]
    if len(valid_existing) >= target_count:
        if progress:
            progress(f"Da co san {len(valid_existing)} video Pexels trong cache, bo qua tai moi.")
        return valid_existing[:target_count]

    result_paths = list(valid_existing)
    seen_ids = {path.stem for path in result_paths}
    per_page = 80
    candidates: list[tuple[Path, dict[str, Any], dict[str, Any]]] = []
    max_pages_per_query = min(20, max(3, (target_count // per_page) + 3))

    for search_query in _query_plan(query):
        if len(result_paths) + len(candidates) >= target_count:
            break
        if progress:
            if search_query:
                progress(f'Dang tim Pexels tu khoa "{search_query}"...')
            else:
                progress("Dang tim video pho bien tren Pexels...")

        page = 1
        added_before = len(candidates)
        while len(result_paths) + len(candidates) < target_count and page <= max_pages_per_query:
            url = _search_url(search_query, page=page, per_page=per_page, only_16x9=only_16x9)
            if progress:
                label = search_query or "popular"
                progress(f'Dang goi Pexels API "{label}" trang {page}...')
            data, headers = _request_json(url, api_key)
            remaining = headers.get("X-Ratelimit-Remaining")
            if remaining and progress:
                progress(f"Pexels API con lai: {remaining} request")
            videos = data.get("videos") or []
            if not videos:
                break

            for video in videos:
                if len(result_paths) + len(candidates) >= target_count:
                    break
                chosen = _best_video_file(video, only_16x9=only_16x9, target_width=target_width, target_height=target_height)
                if not chosen:
                    continue
                video_id = str(video.get("id") or "")
                file_id = str(chosen.get("id") or "")
                stem = safe_name(f"pexels_{video_id}_{file_id}_{chosen.get('width')}x{chosen.get('height')}")
                if stem in seen_ids:
                    continue
                seen_ids.add(stem)
                target = output_dir / f"{stem}.mp4"
                if target.is_file() and target.stat().st_size > 1024:
                    result_paths.append(target)
                    continue
                candidates.append((target, chosen, video))
            page += 1

        if progress:
            added = len(candidates) - added_before
            found_total = len(result_paths) + len(candidates)
            if found_total < target_count:
                label = search_query or "popular"
                progress(f'"{label}" them duoc {added} video; chua du {target_count}, tu dong thu nguon khac...')

    needed = target_count - len(result_paths)
    candidates = candidates[:needed]
    max_workers = min(10, max(1, int(max_workers)))
    if candidates and progress:
        progress(f"Bat dau tai {len(candidates)} video Pexels bang {max_workers} luong...")

    def download_one(index: int, target: Path, chosen: dict[str, Any], video: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
        if progress:
            credit = (video.get("user") or {}).get("name") or "Pexels"
            progress(f"Tai {index}/{len(candidates)}: {target.name} - {credit}")
        last_update = 0.0

        def file_progress(done: int, total: int | None) -> None:
            nonlocal last_update
            now = time.time()
            if not progress or now - last_update < 1.5:
                return
            last_update = now
            if total:
                progress(f"Dang tai {target.name}: {round(done / total * 100)}%")
            else:
                progress(f"Dang tai {target.name}: {round(done / 1024 / 1024, 1)} MB")

        _download_file(str(chosen["link"]), target, file_progress)
        item = {
            "file": target.name,
            "pexels_url": video.get("url"),
            "video_id": video.get("id"),
            "user": video.get("user"),
            "downloaded_file": {
                "id": chosen.get("id"),
                "width": chosen.get("width"),
                "height": chosen.get("height"),
                "quality": chosen.get("quality"),
            },
        }
        return target, item

    if candidates:
        completed = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(download_one, index, target, chosen, video)
                for index, (target, chosen, video) in enumerate(candidates, start=1)
            ]
            for future in as_completed(futures):
                target, item = future.result()
                result_paths.append(target)
                attribution.append(item)
                completed += 1
                if progress:
                    progress(f"Da tai xong {completed}/{len(candidates)} video Pexels")
                meta_path.write_text(json.dumps(attribution, ensure_ascii=False, indent=2), encoding="utf-8")

    if len(result_paths) < target_count:
        if not result_paths:
            raise RuntimeError("Pexels khong tim thay video 16:9 phu hop nao.")
        if progress:
            progress(
                f"Pexels chi tai duoc {len(result_paths)}/{target_count} video 16:9; "
                "tool se dung lai cac video da co de tao du timeline."
            )
        return result_paths
    return result_paths[:target_count]
