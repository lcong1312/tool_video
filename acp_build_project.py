from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import uuid
import urllib.request
from pathlib import Path


ACP_ROOT = Path(r"C:\Program Files\Auto Capcut Pro")
CAPMATE_ROOT = ACP_ROOT / "capcut-mate"
TEMPLATE_DIR = CAPMATE_ROOT / "template" / "default2"
CAPCUT_DRAFT_ROOT = Path.home() / "AppData/Local/CapCut/User Data/Projects/com.lveditor.draft"
BUILD_ROOT = CAPCUT_DRAFT_ROOT / ".building_projects"
APP_BIN = Path(__file__).resolve().parent / "bin"
APP_DIR = Path(__file__).resolve().parent

if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(CAPMATE_ROOT))

import src.pyJianYingDraft as draft  # noqa: E402
from src.pyJianYingDraft import ScriptFile, TrackType, trange  # noqa: E402
from src.pyJianYingDraft.local_materials import VideoMaterial  # noqa: E402
from src.pyJianYingDraft.video_segment import VideoSegment  # noqa: E402


REAL_TEMPLATE_NAME = "0813 (5)"


def capcut_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def windows_path(path: Path) -> str:
    return str(path.resolve())


def capcut_child_path(parent: Path, child_name: str) -> str:
    return capcut_path(parent) + "\\" + child_name


def normalize_json_paths(value):
    if isinstance(value, dict):
        return {key: normalize_json_paths(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_json_paths(item) for item in value]
    if isinstance(value, str):
        return value.replace("\\", "/")
    return value


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def save_json(path: Path, data: dict, *, normalize_paths: bool = True) -> None:
    if normalize_paths:
        data = normalize_json_paths(data)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=4)


def unique_project_folder(name: str) -> Path:
    CAPCUT_DRAFT_ROOT.mkdir(parents=True, exist_ok=True)
    base = "".join(char for char in name if char not in r'<>:"/\|?*').strip() or "Auto Clips"
    candidate = CAPCUT_DRAFT_ROOT / base
    if not candidate.exists():
        return candidate
    for index in range(1, 1000):
        candidate = CAPCUT_DRAFT_ROOT / f"{base} ({index})"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Cannot create unique CapCut project folder.")


def unique_build_folder(name: str) -> Path:
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    candidate = build_folder_for_name(name)
    base = candidate.name
    if not candidate.exists():
        return candidate
    for index in range(1, 1000):
        candidate = BUILD_ROOT / f"{base} ({index})"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Cannot create unique temporary build folder.")


def build_folder_for_name(name: str) -> Path:
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    base = "".join(char for char in name if char not in r'<>:"/\|?*').strip() or "Auto Clips"
    return BUILD_ROOT / base


def promote_build_folder(build_folder: Path, project_name: str) -> Path:
    final_folder = unique_project_folder(project_name)
    if final_folder.exists():
        shutil.rmtree(final_folder)
    shutil.move(str(build_folder), str(final_folder))
    return final_folder


def copy_template(project_folder: Path) -> None:
    if project_folder.exists():
        shutil.rmtree(project_folder)
    source = find_capcut_template()
    shutil.copytree(source, project_folder, ignore=shutil.ignore_patterns("draft_content.json.bak"))


def find_capcut_template() -> Path:
    candidates = []
    for folder in CAPCUT_DRAFT_ROOT.iterdir():
        if not folder.is_dir() or folder.name.startswith(".") or folder.name.startswith("Auto") or folder.name.startswith("ACP"):
            continue
        lowered = folder.name.lower()
        if lowered.startswith("dl14") or "clone" in lowered or "test" in lowered:
            continue
        if (folder / "Resources" / "auto_clips").exists():
            continue
        if (folder / "draft_content.json").is_file() and (folder / "draft_meta_info.json").is_file():
            try:
                content = load_json(folder / "draft_content.json")
                segment_count = sum(len(track.get("segments") or []) for track in content.get("tracks", []))
                duration = int(content.get("duration") or 0)
            except Exception:
                segment_count = 999999
                duration = 999999
            clean_bonus = 0
            for extra in ("attachment_editing.json", "draft.extra", "draft_virtual_store.json"):
                if not (folder / extra).exists():
                    clean_bonus += 1
            is_blank = duration == 0 and segment_count == 0
            candidates.append((1 if is_blank else 0, clean_bonus, folder.stat().st_mtime, folder))
    if candidates:
        return max(candidates, key=lambda item: (item[0], item[1], item[2]))[3]
    return TEMPLATE_DIR


def create_cover(video: Path, project_folder: Path) -> None:
    ffmpeg = APP_BIN / "ffmpeg.exe"
    if not ffmpeg.is_file():
        ffmpeg = ACP_ROOT / "ffmpeg.exe"
    if not ffmpeg.is_file():
        ffmpeg = Path("ffmpeg")
    cover = project_folder / "draft_cover.jpg"
    try:
        subprocess.run(
            [
                str(ffmpeg),
                "-y",
                "-ss",
                "0.2",
                "-i",
                str(video),
                "-frames:v",
                "1",
                "-q:v",
                "3",
                str(cover),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def trigger_directory_scan(project_folder: Path) -> None:
    tmp = project_folder.with_name(project_folder.name + ".tmp")
    try:
        subprocess.run(
            [
                "robocopy",
                str(project_folder),
                str(tmp),
                "/E",
                "/COPY:DAT",
                "/R:1",
                "/W:1",
                "/NP",
                "/NJH",
                "/NJS",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    finally:
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


def backup_project_folder(project_folder: Path) -> Path:
    backup = project_folder.with_name(project_folder.name + f" backup auto {time.strftime('%Y%m%d_%H%M%S')}")
    shutil.copytree(project_folder, backup, ignore=shutil.ignore_patterns("Resources"))
    return backup


def find_real_template() -> Path:
    preferred = CAPCUT_DRAFT_ROOT / REAL_TEMPLATE_NAME
    if (preferred / "draft_content.json").is_file():
        return preferred
    return find_capcut_template()


def new_id() -> str:
    return str(uuid.uuid4()).upper()


def clone_real_project(clips: list[Path], project_name: str, copy_media: bool = True) -> Path:
    template = find_real_template()
    project_folder = unique_project_folder(project_name)
    if project_folder.exists():
        shutil.rmtree(project_folder)
    shutil.copytree(template, project_folder, ignore=shutil.ignore_patterns("draft_content.json.bak"))

    media_dir = project_folder / "Resources" / "auto_clips"
    media_dir.mkdir(parents=True, exist_ok=True)
    if copy_media:
        project_clips = []
        for index, clip in enumerate(clips, start=1):
            target = media_dir / f"clip_{index:04d}{clip.suffix.lower()}"
            shutil.copy2(clip, target)
            project_clips.append(target)
    else:
        project_clips = clips

    content = load_json(template / "draft_content.json")
    video_track_template = next(track for track in content["tracks"] if track.get("type") == "video" and track.get("segments"))
    segment_template = video_track_template["segments"][0]
    material_template = content["materials"]["videos"][0]

    materials = content.setdefault("materials", {})
    for key, value in list(materials.items()):
        if isinstance(value, list):
            materials[key] = []

    content["tracks"] = [
        {
            **{key: value for key, value in video_track_template.items() if key != "segments"},
            "id": new_id(),
            "type": "video",
            "segments": [],
            "flag": 0,
            "attribute": 0,
            "name": "",
            "is_default_name": True,
        }
    ]

    cursor = 0
    first_width = 1920
    first_height = 1080
    for index, clip in enumerate(project_clips, start=1):
        from make_capcut_video import ffprobe_duration, ffprobe_video_size

        duration_us = int(ffprobe_duration(clip) * 1_000_000)
        width, height = ffprobe_video_size(clip)
        if index == 1:
            first_width, first_height = width, height

        material_id = new_id()
        speed_id = new_id()
        placeholder_id = new_id()
        canvas_id = new_id()
        channel_id = new_id()
        color_id = new_id()
        vocal_id = new_id()

        material = json.loads(json.dumps(material_template))
        material.update(
            {
                "id": material_id,
                "type": "video",
                "duration": duration_us,
                "path": str(clip.resolve()),
                "media_path": "",
                "material_id": "",
                "material_name": clip.name,
                "width": width,
                "height": height,
                "has_audio": False,
                "check_flag": 62978047,
            }
        )
        materials["videos"].append(material)

        segment = json.loads(json.dumps(segment_template))
        segment["id"] = new_id()
        segment["material_id"] = material_id
        segment["source_timerange"] = {"start": 0, "duration": duration_us}
        segment["target_timerange"] = {"start": cursor, "duration": duration_us}
        segment["render_timerange"] = {"start": 0, "duration": 0}
        segment["extra_material_refs"] = [speed_id, placeholder_id, canvas_id, channel_id, color_id, vocal_id]
        segment["volume"] = 0.0
        segment["last_nonzero_volume"] = 1.0
        content["tracks"][0]["segments"].append(segment)

        materials.setdefault("speeds", []).append({"id": speed_id, "type": "speed", "mode": 0, "speed": 1.0, "curve_speed": None})
        materials.setdefault("placeholder_infos", []).append({"id": placeholder_id, "type": "placeholder_info", "meta_type": "none", "res_path": "", "res_text": "", "error_path": "", "error_text": ""})
        materials.setdefault("canvases", []).append({"id": canvas_id, "type": "canvas_color", "color": "", "blur": 0.0, "image": "", "album_image": "", "image_id": "", "image_name": "", "source_platform": 0, "team_id": ""})
        materials.setdefault("sound_channel_mappings", []).append({"id": channel_id, "type": "", "audio_channel_mapping": 0, "is_config_open": False})
        materials.setdefault("material_colors", []).append({"id": color_id, "is_color_clip": False, "is_gradient": False, "solid_color": "", "gradient_colors": [], "gradient_percents": [], "gradient_angle": 90.0, "width": 0.0, "height": 0.0})
        materials.setdefault("vocal_separations", []).append({"id": vocal_id, "type": "vocal_separation", "choice": 0, "removed_sounds": [], "time_range": None, "production_path": "", "final_algorithm": "", "enter_from": ""})
        cursor += duration_us

    content["id"] = new_id()
    content["duration"] = cursor
    content["canvas_config"] = {"ratio": "original", "width": first_width, "height": first_height, "background": None}
    content["keyframes"] = {"videos": [], "audios": [], "texts": [], "stickers": [], "filters": [], "adjusts": [], "handwrites": [], "effects": []}

    timelines = project_folder / "Timelines"
    if timelines.exists():
        shutil.rmtree(timelines)
    timeline_dir = timelines / content["id"]
    timeline_dir.mkdir(parents=True, exist_ok=True)
    write_timeline_project(timelines, content["id"])

    save_json(project_folder / "draft_content.json", content, normalize_paths=False)
    save_json(project_folder / "draft_info.json", content, normalize_paths=False)
    save_json(project_folder / "template-2.tmp", content, normalize_paths=False)
    save_json(project_folder / "draft_content.json.bak", content, normalize_paths=False)
    save_json(timeline_dir / "draft_content.json", content, normalize_paths=False)

    create_cover(project_clips[0], project_folder)
    meta = update_meta(project_folder, project_folder.name, cursor, project_clips[0], normalize_paths=False)
    meta["draft_materials"] = [{"type": 0, "value": str(clip.resolve())} for clip in project_clips]
    save_json(project_folder / "draft_meta_info.json", meta, normalize_paths=False)
    update_root_meta(project_folder, project_folder.name, meta, cursor, project_clips[0])
    trigger_directory_scan(project_folder)
    return project_folder


def clone_real_project_split_video(video: Path, clip_count: int, clip_length: float, project_name: str) -> Path:
    from make_capcut_video import ffprobe_duration, ffprobe_video_size

    template = find_real_template()
    project_folder = unique_project_folder(project_name)
    if project_folder.exists():
        shutil.rmtree(project_folder)
    shutil.copytree(template, project_folder, ignore=shutil.ignore_patterns("draft_content.json.bak"))

    media_dir = project_folder / "Resources" / "auto_clips"
    media_dir.mkdir(parents=True, exist_ok=True)
    project_video = media_dir / video.name
    shutil.copy2(video, project_video)

    content = load_json(template / "draft_content.json")
    video_track_template = next(track for track in content["tracks"] if track.get("type") == "video" and track.get("segments"))
    segment_template = video_track_template["segments"][0]
    material_template = content["materials"]["videos"][0]

    materials = content.setdefault("materials", {})
    for key, value in list(materials.items()):
        if isinstance(value, list):
            materials[key] = []

    content["tracks"] = [
        {
            **{key: value for key, value in video_track_template.items() if key != "segments"},
            "id": new_id(),
            "type": "video",
            "segments": [],
            "flag": 0,
            "attribute": 0,
            "name": "",
            "is_default_name": True,
        }
    ]

    total_duration_us = int(ffprobe_duration(project_video) * 1_000_000)
    width, height = ffprobe_video_size(project_video)
    material_id = new_id()

    material = json.loads(json.dumps(material_template))
    material.update(
        {
            "id": material_id,
            "type": "video",
            "duration": total_duration_us,
            "path": str(project_video.resolve()),
            "media_path": "",
            "material_id": "",
            "material_name": project_video.name,
            "width": width,
            "height": height,
            "has_audio": False,
            "check_flag": 62978047,
        }
    )
    materials["videos"].append(material)

    clip_us = int(clip_length * 1_000_000)
    cursor = 0
    for index in range(clip_count):
        remaining = total_duration_us - cursor
        if remaining <= 0:
            break
        duration_us = min(clip_us, remaining)
        speed_id = new_id()
        placeholder_id = new_id()
        canvas_id = new_id()
        channel_id = new_id()
        color_id = new_id()
        vocal_id = new_id()

        segment = json.loads(json.dumps(segment_template))
        segment["id"] = new_id()
        segment["material_id"] = material_id
        segment["source_timerange"] = {"start": cursor, "duration": duration_us}
        segment["target_timerange"] = {"start": cursor, "duration": duration_us}
        segment["render_timerange"] = {"start": 0, "duration": 0}
        segment["extra_material_refs"] = [speed_id, placeholder_id, canvas_id, channel_id, color_id, vocal_id]
        segment["volume"] = 0.0
        segment["last_nonzero_volume"] = 1.0
        content["tracks"][0]["segments"].append(segment)

        materials.setdefault("speeds", []).append({"id": speed_id, "type": "speed", "mode": 0, "speed": 1.0, "curve_speed": None})
        materials.setdefault("placeholder_infos", []).append({"id": placeholder_id, "type": "placeholder_info", "meta_type": "none", "res_path": "", "res_text": "", "error_path": "", "error_text": ""})
        materials.setdefault("canvases", []).append({"id": canvas_id, "type": "canvas_color", "color": "", "blur": 0.0, "image": "", "album_image": "", "image_id": "", "image_name": "", "source_platform": 0, "team_id": ""})
        materials.setdefault("sound_channel_mappings", []).append({"id": channel_id, "type": "", "audio_channel_mapping": 0, "is_config_open": False})
        materials.setdefault("material_colors", []).append({"id": color_id, "is_color_clip": False, "is_gradient": False, "solid_color": "", "gradient_colors": [], "gradient_percents": [], "gradient_angle": 90.0, "width": 0.0, "height": 0.0})
        materials.setdefault("vocal_separations", []).append({"id": vocal_id, "type": "vocal_separation", "choice": 0, "removed_sounds": [], "time_range": None, "production_path": "", "final_algorithm": "", "enter_from": ""})
        cursor += duration_us

    content["id"] = new_id()
    content["duration"] = cursor
    content["canvas_config"] = {"ratio": "original", "width": width, "height": height, "background": None}
    content["keyframes"] = {"videos": [], "audios": [], "texts": [], "stickers": [], "filters": [], "adjusts": [], "handwrites": [], "effects": []}

    timelines = project_folder / "Timelines"
    if timelines.exists():
        shutil.rmtree(timelines)
    timeline_dir = timelines / content["id"]
    timeline_dir.mkdir(parents=True, exist_ok=True)
    write_timeline_project(timelines, content["id"])

    save_json(project_folder / "draft_content.json", content, normalize_paths=False)
    save_json(project_folder / "draft_info.json", content, normalize_paths=False)
    save_json(project_folder / "template-2.tmp", content, normalize_paths=False)
    save_json(project_folder / "draft_content.json.bak", content, normalize_paths=False)
    save_json(timeline_dir / "draft_content.json", content, normalize_paths=False)

    create_cover(project_video, project_folder)
    meta = update_meta(project_folder, project_folder.name, cursor, project_video, normalize_paths=False)
    meta["draft_materials"] = [{"type": 0, "value": str(project_video.resolve())}]
    save_json(project_folder / "draft_meta_info.json", meta, normalize_paths=False)
    update_root_meta(project_folder, project_folder.name, meta, cursor, project_video)
    trigger_directory_scan(project_folder)
    return project_folder


def build_with_acp_api(clips: list[Path], project_name: str, copy_media: bool = True) -> Path:
    from make_capcut_video import ffprobe_duration, ffprobe_video_size

    project_folder = unique_project_folder(project_name)
    copy_template(project_folder)
    media_dir = project_folder / "Resources" / "auto_clips"
    media_dir.mkdir(parents=True, exist_ok=True)
    if copy_media:
        project_clips = []
        for index, clip in enumerate(clips, start=1):
            target = media_dir / f"clip_{index:04d}{clip.suffix.lower()}"
            shutil.copy2(clip, target)
            project_clips.append(target)
    else:
        project_clips = clips

    segments = []
    cursor = 0
    for index, clip in enumerate(project_clips):
        duration_us = int(ffprobe_duration(clip) * 1_000_000)
        segments.append(
            {
                "index": index,
                "text": f"clip {index + 1}",
                "audio_path": "",
                "video_path": str(clip.resolve()),
                "audio_duration_us": duration_us,
                "video_duration_us": duration_us,
                "video_clips": [str(clip.resolve())],
            }
        )
        cursor += duration_us

    width, height = ffprobe_video_size(project_clips[0])
    req = {"canvas": {"width": width, "height": height}, "segments": segments}
    data = json.dumps(req).encode("utf-8")
    request = urllib.request.Request(
        "http://127.0.0.1:9100/openapi/capcut-mate/v1/build_draft",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode("utf-8"))
    if body.get("code") != 0:
        raise RuntimeError(body.get("message", "ACP build_draft failed"))
    content = body["data"]["draft_content"]
    _api_meta = body["data"]["draft_meta_info"]
    content["id"] = new_id()

    timelines = project_folder / "Timelines"
    if timelines.exists():
        shutil.rmtree(timelines)
    timeline_dir = timelines / content["id"]
    timeline_dir.mkdir(parents=True, exist_ok=True)
    write_timeline_project(timelines, content["id"])

    save_json(project_folder / "draft_content.json", content, normalize_paths=False)
    save_json(project_folder / "draft_info.json", content, normalize_paths=False)
    save_json(project_folder / "template-2.tmp", content, normalize_paths=False)
    save_json(project_folder / "draft_content.json.bak", content, normalize_paths=False)
    save_json(timeline_dir / "draft_content.json", content, normalize_paths=False)
    create_cover(project_clips[0], project_folder)
    meta = update_meta(
        project_folder,
        project_folder.name,
        content.get("duration", cursor),
        project_clips[0],
        normalize_paths=False,
    )
    meta["draft_timeline_materials_size_"] = sum(path.stat().st_size for path in project_clips)
    meta["draft_materials"] = [
        {
            "type": 0,
            "value": [
                {
                    "file_Path": str(path.resolve()).replace("\\", "/"),
                    "height": 0,
                    "width": 0,
                    "id": str(uuid.uuid4()),
                    "duration": 0,
                    "type": 0,
                    "import_time": int(time.time()),
                    "create_time": int(time.time()),
                    "extra_info": path.name,
                }
                for path in project_clips
            ],
        }
    ]
    save_json(project_folder / "draft_meta_info.json", meta, normalize_paths=False)
    update_root_meta(project_folder, project_folder.name, meta, meta["tm_duration"], project_clips[0])
    trigger_directory_scan(project_folder)
    return project_folder


def update_meta(
    project_folder: Path,
    project_name: str,
    duration_us: int,
    first_clip: Path,
    *,
    normalize_paths: bool = True,
) -> dict:
    meta_path = project_folder / "draft_meta_info.json"
    meta = load_json(meta_path)
    now_us = int(time.time() * 1_000_000)
    draft_id = str(uuid.uuid4()).upper()
    meta["draft_id"] = draft_id
    meta["draft_name"] = project_name
    meta["draft_fold_path"] = capcut_path(project_folder)
    meta["draft_root_path"] = windows_path(CAPCUT_DRAFT_ROOT)
    meta["draft_cover"] = "draft_cover.jpg"
    meta["draft_json_file"] = None
    meta["tm_draft_create"] = now_us
    meta["tm_draft_modified"] = now_us
    meta["tm_duration"] = duration_us
    meta["draft_materials"] = [{"type": 0, "value": capcut_path(first_clip)}]
    save_json(meta_path, meta, normalize_paths=False)
    return meta


def update_root_meta(project_folder: Path, project_name: str, meta: dict, duration_us: int, first_clip: Path) -> None:
    root_path = CAPCUT_DRAFT_ROOT / "root_meta_info.json"
    root = load_json(root_path) if root_path.is_file() else {
        "all_draft_store": [],
        "draft_ids": 0,
        "root_path": capcut_path(CAPCUT_DRAFT_ROOT),
    }
    stores = root.setdefault("all_draft_store", [])
    folder_path = capcut_path(project_folder)
    normalized_folder_path = folder_path.replace("\\", "/")
    tmp_folder_path = capcut_path(project_folder.with_name(project_folder.name + ".tmp")).replace("\\", "/")
    tmp_project_name = project_name + ".tmp"
    stores[:] = [
        item
        for item in stores
        if item.get("draft_name") != project_name
        and item.get("draft_name") != tmp_project_name
        and item.get("draft_fold_path", "").replace("\\", "/") != normalized_folder_path
        and item.get("draft_fold_path", "").replace("\\", "/") != tmp_folder_path
    ]
    entry = {
        "cloud_draft_cover": False,
        "cloud_draft_sync": False,
        "draft_cloud_last_action_download": False,
        "draft_cloud_purchase_info": "",
        "draft_cloud_template_id": "",
        "draft_cloud_tutorial_info": "",
        "draft_cloud_videocut_purchase_info": "",
        "draft_cover": capcut_child_path(project_folder, "draft_cover.jpg"),
        "draft_fold_path": folder_path,
        "draft_id": meta.get("draft_id", uuid.uuid4().hex.upper()),
        "draft_is_ai_shorts": False,
        "draft_is_cloud_temp_draft": False,
        "draft_is_invisible": False,
        "draft_is_pippit_draft": False,
        "draft_is_web_article_video": False,
        "draft_json_file": capcut_child_path(project_folder, "draft_content.json"),
        "draft_name": project_name,
        "draft_new_version": "",
        "draft_root_path": windows_path(CAPCUT_DRAFT_ROOT),
        "draft_timeline_materials_size": sum(path.stat().st_size for path in project_folder.rglob("*") if path.is_file()),
        "draft_type": "",
        "draft_web_article_video_enter_from": "",
        "pippit_avatar_url": "",
        "pippit_extra_info": "",
        "pippit_id": "",
        "pippit_user_name": "",
        "streaming_edit_draft_ready": True,
        "tm_draft_cloud_completed": "",
        "tm_draft_cloud_entry_id": -1,
        "tm_draft_cloud_modified": 0,
        "tm_draft_cloud_parent_entry_id": -1,
        "tm_draft_cloud_space_id": -1,
        "tm_draft_cloud_user_id": -1,
        "tm_draft_create": meta["tm_draft_create"],
        "tm_draft_modified": meta["tm_draft_modified"],
        "tm_draft_removed": 0,
        "tm_duration": duration_us,
    }
    stores.insert(0, entry)
    root["draft_ids"] = len(stores)
    root["root_path"] = capcut_path(CAPCUT_DRAFT_ROOT)
    save_json(root_path, root, normalize_paths=False)


def write_timeline_project(timelines_dir: Path, timeline_id: str) -> None:
    now_us = int(time.time() * 1_000_000)
    data = {
        "config": {
            "color_space": -1,
            "mixed_track_mode_on": False,
            "render_index_track_mode_on": False,
            "use_float_render": False,
        },
        "create_time": now_us,
        "id": str(uuid.uuid4()).upper(),
        "main_timeline_id": timeline_id,
        "timelines": [
            {
                "create_time": now_us,
                "id": timeline_id,
                "is_marked_delete": False,
                "name": "Timeline 01",
                "update_time": now_us,
            }
        ],
        "update_time": now_us,
        "version": 0,
    }
    timelines_dir.mkdir(parents=True, exist_ok=True)
    save_json(timelines_dir / "project.json", data, normalize_paths=False)
    save_json(timelines_dir / "project.json.bak", data, normalize_paths=False)


def _json_clone(value):
    return json.loads(json.dumps(value, ensure_ascii=False))


def _first_video_track(content: dict) -> dict | None:
    for track in content.get("tracks", []):
        if track.get("type") == "video":
            return track
    return None


def _upgrade_content_schema(content: dict, width: int, height: int) -> dict:
    """Patch pyJianYingDraft output up to the schema CapCut currently writes.

    CapCut 9.x rejects older/minimal draft_content files even when paths and
    timeline ids are correct. We use a real local CapCut draft as a schema
    donor, then keep our generated ids, paths, durations and segments.
    """
    try:
        template = load_json(find_real_template() / "draft_content.json")
    except Exception:
        template = {}

    for key, value in template.items():
        if key in ("tracks", "materials"):
            continue
        if key not in content:
            content[key] = _json_clone(value)

    if template.get("new_version"):
        content["new_version"] = template["new_version"]
    if template.get("version"):
        content["version"] = template["version"]
    content["draft_type"] = template.get("draft_type", "video")
    content["path"] = ""
    content["source"] = template.get("source", "default")
    content["mixed_track_mode_on"] = template.get("mixed_track_mode_on", False)
    content["render_index_track_mode_on"] = template.get("render_index_track_mode_on", False)
    content["free_render_index_mode_on"] = template.get("free_render_index_mode_on", False)
    content["is_drop_frame_timecode"] = template.get("is_drop_frame_timecode", False)
    content["canvas_config"] = {
        "ratio": "16:9" if width == 1920 and height == 1080 else "original",
        "width": width,
        "height": height,
        "background": None,
    }

    template_config = template.get("config", {})
    config = content.setdefault("config", {})
    for key, value in template_config.items():
        config.setdefault(key, _json_clone(value))
    config.setdefault("use_float_render", False)
    config.setdefault("voice_change_sync", False)

    materials = content.setdefault("materials", {})
    if "masks" in materials and "common_mask" not in materials:
        materials["common_mask"] = materials.pop("masks")
    else:
        materials.pop("masks", None)
    for key, value in template.get("materials", {}).items():
        materials.setdefault(key, [] if isinstance(value, list) else _json_clone(value))

    template_video = None
    template_videos = template.get("materials", {}).get("videos", [])
    if template_videos:
        template_video = template_videos[0]
    if template_video:
        for video in materials.get("videos", []):
            keep = _json_clone(video)
            upgraded = _json_clone(template_video)
            upgraded.update(keep)
            upgraded["has_audio"] = False
            upgraded.setdefault("source", 0)
            upgraded.setdefault("source_platform", 0)
            video.clear()
            video.update(upgraded)

    template_track = _first_video_track(template)
    template_segment = None
    if template_track and template_track.get("segments"):
        template_segment = template_track["segments"][0]
    if template_segment:
        for track in content.get("tracks", []):
            if track.get("type") != "video":
                continue
            for segment in track.get("segments", []):
                keep = _json_clone(segment)
                upgraded = _json_clone(template_segment)
                upgraded.update(keep)
                upgraded.setdefault("render_timerange", {"start": 0, "duration": 0})
                upgraded.setdefault("source", "segmentsourcenormal")
                segment.clear()
                segment.update(upgraded)

    _normalize_segment_extra_refs(content, template)
    return content


def _template_material(template: dict, key: str) -> dict:
    items = template.get("materials", {}).get(key, [])
    if items:
        return _json_clone(items[0])
    defaults = {
        "drafts": {"id": "", "type": "composition"},
        "speeds": {"id": "", "type": "speed", "mode": 0, "speed": 1.0, "curve_speed": None},
        "placeholder_infos": {
            "id": "",
            "type": "placeholder_info",
            "meta_type": "none",
            "res_path": "",
            "res_text": "",
            "error_path": "",
            "error_text": "",
        },
        "canvases": {
            "id": "",
            "type": "canvas_color",
            "color": "",
            "blur": 0.0,
            "image": "",
            "album_image": "",
            "image_id": "",
            "image_name": "",
            "source_platform": 0,
            "team_id": "",
        },
        "sound_channel_mappings": {"id": "", "type": "none", "audio_channel_mapping": 0, "is_config_open": False},
        "material_colors": {
            "id": "",
            "is_color_clip": False,
            "is_gradient": False,
            "solid_color": "",
            "gradient_colors": [],
            "gradient_percents": [],
            "gradient_angle": 90.0,
            "width": 0.0,
            "height": 0.0,
        },
        "vocal_separations": {
            "id": "",
            "type": "vocal_separation",
            "choice": 0,
            "removed_sounds": [],
            "time_range": None,
            "production_path": "",
            "final_algorithm": "",
            "enter_from": "",
        },
    }
    return _json_clone(defaults[key])


def _normalize_segment_extra_refs(content: dict, template: dict) -> None:
    materials = content.setdefault("materials", {})
    ref_keys = [
        "drafts",
        "speeds",
        "placeholder_infos",
        "canvases",
        "sound_channel_mappings",
        "material_colors",
        "vocal_separations",
    ]
    for key in ref_keys:
        materials[key] = []

    for track in content.get("tracks", []):
        if track.get("type") != "video":
            continue
        for segment in track.get("segments", []):
            refs = []
            for key in ref_keys:
                ref_id = new_id()
                obj = _template_material(template, key)
                obj["id"] = ref_id
                if key == "drafts":
                    obj["category_id"] = ""
                    obj["category_name"] = ""
                materials[key].append(obj)
                refs.append(ref_id)
            segment["extra_material_refs"] = refs


def find_segment_schema_template() -> Path:
    candidates = []
    for folder in CAPCUT_DRAFT_ROOT.iterdir():
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        lowered = folder.name.lower()
        if lowered.startswith("dl14") or "clone" in lowered or "test" in lowered:
            continue
        if (folder / "Resources" / "auto_clips").exists():
            continue
        content_path = folder / "draft_content.json"
        if not content_path.is_file():
            continue
        try:
            content = load_json(content_path)
        except Exception:
            continue
        video_tracks = [
            track
            for track in content.get("tracks", [])
            if track.get("type") == "video" and track.get("segments")
        ]
        if video_tracks and content.get("materials", {}).get("videos"):
            candidates.append(folder)
    if candidates:
        return max(candidates, key=lambda item: item.stat().st_mtime)
    return find_real_template()


def find_text_schema_template() -> Path | None:
    candidates = []
    for folder in CAPCUT_DRAFT_ROOT.iterdir():
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        if (folder / "Resources" / "auto_clips").exists():
            continue
        content_path = folder / "draft_content.json"
        if not content_path.is_file():
            continue
        try:
            content = load_json(content_path)
        except Exception:
            continue
        has_text_track = any(
            track.get("type") == "text" and track.get("segments")
            for track in content.get("tracks", [])
        )
        if has_text_track and content.get("materials", {}).get("texts"):
            candidates.append(folder)
    if candidates:
        return max(candidates, key=lambda item: item.stat().st_mtime)
    return None


def parse_srt_cues(path: Path) -> list[tuple[int, int, str]]:
    from make_capcut_video import parse_srt_timestamp

    text = path.read_text(encoding="utf-8-sig", errors="replace")
    blocks = text.replace("\r\n", "\n").replace("\r", "\n").split("\n\n")
    cues: list[tuple[int, int, str]] = []
    for block in blocks:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue
        time_index = next((idx for idx, line in enumerate(lines) if "-->" in line), -1)
        if time_index < 0:
            continue
        start_text, end_text = lines[time_index].split("-->", 1)
        start_token = start_text.strip().split()[0]
        end_token = end_text.strip().split()[0]
        body = " ".join(lines[time_index + 1 :]).strip()
        if not body:
            continue
        start_us = int(parse_srt_timestamp(start_token) * 1_000_000)
        end_us = int(parse_srt_timestamp(end_token) * 1_000_000)
        duration_us = max(1, end_us - start_us)
        cues.append((start_us, duration_us, body))
    return cues


def _set_text_material_content(material: dict, text: str) -> None:
    try:
        payload = json.loads(material.get("content") or "{}")
    except Exception:
        payload = {}
    payload["text"] = text
    styles = payload.get("styles")
    if isinstance(styles, list):
        for style in styles:
            if isinstance(style, dict):
                style["range"] = [0, len(text)]
    material["content"] = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    material["recognize_text"] = text
    material["base_content"] = ""
    if isinstance(material.get("words"), dict):
        material["words"] = {"start_time": [], "end_time": [], "text": []}
    if isinstance(material.get("current_words"), dict):
        material["current_words"] = {"start_time": [], "end_time": [], "text": []}


def _unlock_track(track: dict) -> None:
    track["flag"] = 0
    track["attribute"] = 0
    for key in ("locked", "is_locked", "isLock", "is_lock"):
        if key in track:
            track[key] = False


def _unlock_segment(segment: dict) -> None:
    segment["track_attribute"] = 0
    segment["visible"] = True
    for key in ("locked", "is_locked", "isLock", "is_lock"):
        if key in segment:
            segment[key] = False


def add_srt_to_content(content: dict, srt_path: Path) -> None:
    cues = parse_srt_cues(srt_path)
    if not cues:
        return
    schema_folder = find_text_schema_template()
    if not schema_folder:
        raise RuntimeError("Khong tim thay project CapCut mau co subtitle/text track de import SRT.")
    schema_content = load_json(schema_folder / "draft_content.json")
    schema_track = next(
        track
        for track in schema_content.get("tracks", [])
        if track.get("type") == "text" and track.get("segments")
    )
    schema_segment = schema_track["segments"][0]
    schema_text = schema_content.get("materials", {}).get("texts", [None])[0]
    schema_animation = schema_content.get("materials", {}).get("material_animations", [None])[0]
    if not schema_text or not schema_animation:
        raise RuntimeError("Project mau khong du text material de import SRT.")

    materials = content.setdefault("materials", {})
    for key, value in schema_content.get("materials", {}).items():
        materials.setdefault(key, [] if isinstance(value, list) else _json_clone(value))
    materials.setdefault("texts", [])
    materials.setdefault("material_animations", [])

    text_track = _json_clone(schema_track)
    text_track["id"] = new_id()
    text_track["segments"] = []
    text_track["type"] = "text"
    text_track["name"] = ""
    text_track["is_default_name"] = True
    _unlock_track(text_track)

    for index, (start_us, duration_us, cue_text) in enumerate(cues):
        text_id = new_id()
        animation_id = new_id()

        text_material = _json_clone(schema_text)
        text_material["id"] = text_id
        text_material["type"] = "subtitle"
        text_material["group_id"] = f"import_{int(time.time() * 1000)}"
        _set_text_material_content(text_material, cue_text)
        materials["texts"].append(text_material)

        animation = _json_clone(schema_animation)
        animation["id"] = animation_id
        materials["material_animations"].append(animation)

        segment = _json_clone(schema_segment)
        segment.update(
            {
                "id": new_id(),
                "material_id": text_id,
                "target_timerange": {"start": start_us, "duration": duration_us},
                "render_timerange": {"start": 0, "duration": 0},
                "source_timerange": None,
                "extra_material_refs": [animation_id],
                "render_index": 14000 + index,
                "track_render_index": 2,
                "visible": True,
                "track_attribute": 0,
            }
        )
        _unlock_segment(segment)
        text_track["segments"].append(segment)

    content.setdefault("tracks", []).append(text_track)


def _clear_material_lists(materials: dict) -> None:
    for key, value in list(materials.items()):
        if isinstance(value, list):
            materials[key] = []


def _new_ref_material(schema_content: dict, key: str) -> tuple[str, dict]:
    ref_id = new_id()
    obj = _template_material(schema_content, key)
    obj["id"] = ref_id
    return ref_id, obj


def build_content_from_real_schema(
    base_content: dict,
    clips: list[Path],
    width: int,
    height: int,
    clip_durations: list[float] | None = None,
    srt_path: Path | None = None,
) -> tuple[dict, int]:
    from make_capcut_video import ffprobe_duration, ffprobe_video_size

    schema_content = load_json(find_segment_schema_template() / "draft_content.json")
    schema_track = _first_video_track(schema_content)
    if not schema_track or not schema_track.get("segments"):
        raise RuntimeError("Khong tim thay video segment mau trong project CapCut that.")
    schema_segment = schema_track["segments"][0]
    schema_video = schema_content.get("materials", {}).get("videos", [None])[0]
    if not schema_video:
        raise RuntimeError("Khong tim thay video material mau trong project CapCut that.")

    content = _json_clone(base_content)
    timeline_id = content.get("id") or new_id()
    content["id"] = timeline_id
    content["duration"] = 0
    content["canvas_config"] = {
        "ratio": "16:9" if width == 1920 and height == 1080 else "original",
        "width": width,
        "height": height,
        "background": None,
    }
    content["draft_type"] = schema_content.get("draft_type", content.get("draft_type", "video"))
    content["new_version"] = schema_content.get("new_version", content.get("new_version", "181.0.0"))
    content["version"] = schema_content.get("version", content.get("version", 360000))
    content["path"] = ""
    content["source"] = schema_content.get("source", content.get("source", "default"))
    content["create_time"] = 0
    content["update_time"] = 0

    materials = content.setdefault("materials", {})
    for key, value in schema_content.get("materials", {}).items():
        materials.setdefault(key, [] if isinstance(value, list) else _json_clone(value))
    if "masks" in materials and "common_mask" not in materials:
        materials["common_mask"] = materials.pop("masks")
    else:
        materials.pop("masks", None)
    _clear_material_lists(materials)

    track = _json_clone(schema_track)
    track["id"] = new_id()
    track["segments"] = []
    track["type"] = "video"
    track["name"] = ""
    track["is_default_name"] = True
    _unlock_track(track)

    cursor_us = 0
    ref_keys = [
        "drafts",
        "speeds",
        "placeholder_infos",
        "canvases",
        "sound_channel_mappings",
        "material_colors",
        "vocal_separations",
    ]

    for index, clip in enumerate(clips):
        media_duration_us = int(ffprobe_duration(clip) * 1_000_000)
        if clip_durations and index < len(clip_durations):
            duration_us = max(1, int(float(clip_durations[index]) * 1_000_000))
            source_duration_us = min(duration_us, media_duration_us)
        else:
            duration_us = media_duration_us
            source_duration_us = media_duration_us
        clip_width, clip_height = ffprobe_video_size(clip)

        material_id = new_id()
        video = _json_clone(schema_video)
        video.update(
            {
                "id": material_id,
                "type": "video",
                "duration": media_duration_us,
                "path": capcut_path(clip),
                "media_path": "",
                "material_id": "",
                "material_name": clip.name,
                "width": clip_width,
                "height": clip_height,
                "has_audio": False,
                "check_flag": 62978047,
            }
        )
        materials.setdefault("videos", []).append(video)

        refs = []
        for key in ref_keys:
            ref_id, obj = _new_ref_material(schema_content, key)
            materials.setdefault(key, []).append(obj)
            refs.append(ref_id)

        segment = _json_clone(schema_segment)
        segment.update(
            {
                "id": new_id(),
                "material_id": material_id,
                "source_timerange": {"start": 0, "duration": source_duration_us},
                "target_timerange": {"start": cursor_us, "duration": duration_us},
                "render_timerange": {"start": 0, "duration": 0},
                "extra_material_refs": refs,
                "volume": 0.0,
                "last_nonzero_volume": 1.0,
                "render_index": 0,
                "track_render_index": 0,
                "visible": True,
                "track_attribute": 0,
            }
        )
        _unlock_segment(segment)
        track["segments"].append(segment)
        cursor_us += duration_us

    content["tracks"] = [track]
    content["duration"] = cursor_us
    if srt_path and srt_path.is_file():
        add_srt_to_content(content, srt_path)
        cue_end = 0
        for start_us, duration_us, _text in parse_srt_cues(srt_path):
            cue_end = max(cue_end, start_us + duration_us)
        content["duration"] = max(content["duration"], cue_end)
        cursor_us = content["duration"]
    content["keyframes"] = {
        "videos": [],
        "audios": [],
        "texts": [],
        "stickers": [],
        "filters": [],
        "adjusts": [],
        "handwrites": [],
        "effects": [],
    }
    return content, cursor_us


def _empty_attachment_editing() -> dict:
    return {
        "editing_draft": {
            "ai_remove_filter_words": {"enter_source": "", "right_id": ""},
            "ai_shorts_info": {"report_params": "", "type": 0},
            "cover_extra_info": {
                "draft_id": "",
                "position": 0,
                "select_segment_id": "",
                "select_segment_source_start": 0,
                "select_segment_target_start": 0,
                "slot_image_path": "",
                "slot_info_config": {"slot_image_path": "", "used_video_algorithm_configs": []},
                "type": 1,
                "video_draft_source": -1,
            },
            "crop_info_extra": {"crop_mirror_type": 0, "crop_rotate": 0.0, "crop_rotate_total": 0.0},
            "digital_human_template_to_video_info": {"has_upload_material": False, "template_type": 0},
            "draft_used_recommend_function": "",
            "edit_type": 0,
            "eye_correct_enabled_multi_face_time": 0,
            "has_adjusted_render_layer": False,
            "image_ai_chat_info": {
                "before_chat_edit": False,
                "draft_modify_time": 0,
                "generate_type": "",
                "inspiration_item_id": "",
                "inspiration_item_name": "",
                "keyword_content": "",
                "keyword_id": "",
                "keyword_name": "",
                "keyword_type": "",
                "message_id": "",
                "model_name": "",
                "need_restore": False,
                "picture_id": "",
                "prompt_content": "",
                "prompt_from": "",
                "sugs_info": [],
            },
            "image_ai_template_info": {"first_draw_type": "", "inspiration_id": "", "request_id": ""},
            "is_open_expand_player": False,
            "is_template_text_ai_generate": False,
            "is_use_adjust": False,
            "is_use_ai_expand": False,
            "is_use_ai_image": False,
            "is_use_ai_remove": False,
            "is_use_ai_video": False,
            "is_use_audio_separation": False,
            "is_use_chroma_key": False,
            "is_use_curve_speed": False,
            "is_use_digital_human": False,
            "is_use_edit_multi_camera": False,
            "is_use_lip_sync": False,
            "is_use_lock_object": False,
            "is_use_loudness_unify": False,
            "is_use_noise_reduction": False,
            "is_use_one_click_beauty": False,
            "is_use_one_click_ultra_hd": False,
            "is_use_retouch_face": False,
            "is_use_smart_adjust_color": False,
            "is_use_smart_body_beautify": False,
            "is_use_smart_motion": False,
            "is_use_subtitle_recognition": False,
            "is_use_text_to_audio": False,
            "material_edit_session": {"material_edit_info": [], "session_id": "", "session_time": 0},
            "paste_segment_list": [],
            "profile_entrance_type": "",
            "publish_enter_from": "",
            "publish_type": "",
            "single_function_type": 0,
            "text_convert_case_types": [],
            "version": "1.0.0",
            "video_recording_create_draft": "",
        }
    }


def _pc_common_attachment() -> dict:
    report = {
        "caption_id_list": [],
        "commercial_material": "",
        "material_source": "",
        "method": "",
        "page_from": "",
        "style": "",
        "task_id": "",
        "text_style": "",
        "tos_id": "",
        "video_category": "",
    }
    return {
        "ai_packaging_infos": [],
        "ai_packaging_report_info": _json_clone(report),
        "broll": {"ai_packaging_infos": [], "ai_packaging_report_info": _json_clone(report)},
        "commercial_music_category_ids": [],
        "pc_feature_flag": 0,
        "recognize_tasks": [],
        "reference_lines_config": {
            "horizontal_lines": [],
            "is_lock": False,
            "is_visible": False,
            "vertical_lines": [],
        },
        "safe_area_type": 0,
        "template_item_infos": [],
        "unlock_template_ids": [],
    }


def _common_attachment_files() -> dict[str, dict]:
    return {
        "attachment_action_scene.json": {
            "action_scene": {"removed_segments": [], "segment_infos": []}
        },
        "attachment_gen_ai_info.json": {
            "gen_ai": {
                "ai_func_config": {
                    "ai_common_configs": [],
                    "ai_effect_configs": [],
                    "ai_func_list": [],
                    "aigc_generation_configs": [],
                },
                "cc_agent_info": {
                    "agent_stringent_section_id_list": [],
                    "agent_stringent_used_tool_list": [],
                    "click_cnt": 0,
                    "consume_credits_function_list": [],
                    "conversation_ids": [],
                    "generate_success_cnt": 0,
                    "is_agent_stringent_used": False,
                    "is_agent_used": False,
                    "local_section_id_list": [],
                    "real_skill_list": [],
                    "request_cnt": 0,
                    "request_from": [],
                    "tool_list": [],
                    "user_select_skill_list": [],
                },
                "id": "",
                "scene": "",
                "version": "1.0.0",
            }
        },
        "attachment_id_mapping.json": {"id_mapping": {"mapping": []}},
        "attachment_pc_timeline.json": {
            "reference_lines_config": {
                "horizontal_lines": [],
                "is_lock": False,
                "is_visible": False,
                "vertical_lines": [],
            },
            "safe_area_type": 0,
        },
        "attachment_plugin_draft.json": {
            "plugin_draft": {"plugin_segments": [], "version": "1.0.0"}
        },
        "attachment_script_video.json": {
            "script_video": {
                "attachment_valid": False,
                "language": "",
                "overdub_recover": [],
                "overdub_sentence_ids": [],
                "parts": [],
                "sync_subtitle": False,
                "translate_segments": [],
                "translate_type": "",
                "version": "1.0.0",
            }
        },
    }


def write_common_attachments(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for filename, data in _common_attachment_files().items():
        save_json(folder / filename, data, normalize_paths=False)


def _timeline_layout(timeline_id: str) -> dict:
    return {
        "dockItems": [
            {
                "dockIndex": 0,
                "ratio": 1,
                "timelineIds": [timeline_id],
                "timelineNames": ["Timeline 01"],
            }
        ],
        "layoutOrientation": 1,
    }


def _timeline_template(timeline_id: str, width: int, height: int) -> dict:
    return {
        "canvas_config": {"background": None, "height": height, "ratio": "original", "width": width},
        "color_space": -1,
        "config": {
            "adjust_max_index": 1,
            "attachment_info": [],
            "combination_max_index": 1,
            "export_range": None,
            "extract_audio_last_index": 1,
            "lyrics_recognition_id": "",
            "lyrics_sync": True,
            "lyrics_taskinfo": [],
            "maintrack_adsorb": True,
            "material_save_mode": 0,
            "multi_language_current": "none",
            "multi_language_list": [],
            "multi_language_main": "none",
            "multi_language_mode": "none",
            "original_sound_last_index": 1,
            "record_audio_last_index": 1,
            "sticker_max_index": 1,
            "subtitle_keywords_config": None,
            "subtitle_recognition_id": "",
            "subtitle_sync": True,
            "subtitle_taskinfo": [],
            "system_font_list": [],
            "use_float_render": False,
            "video_mute": False,
            "voice_change_sync": False,
            "zoom_info_params": None,
        },
        "cover": None,
        "create_time": 0,
        "draft_type": "video",
        "duration": 0,
        "extra_info": None,
        "fps": 30.0,
        "free_render_index_mode_on": False,
        "function_assistant_info": {},
        "group_container": None,
        "id": timeline_id,
        "is_drop_frame_timecode": False,
        "keyframe_graph_list": [],
        "keyframes": {
            "adjusts": [],
            "audios": [],
            "effects": [],
            "filters": [],
            "handwrites": [],
            "stickers": [],
            "texts": [],
            "videos": [],
        },
        "materials": {},
        "mixed_track_mode_on": False,
        "mutable_config": None,
        "name": "",
        "new_version": "75.0.0",
        "path": "",
        "relationships": [],
        "render_index_track_mode_on": False,
        "source": "default",
        "static_cover_image_path": "",
        "time_marks": None,
        "tracks": [],
        "update_time": 0,
        "version": 360000,
    }


def _virtual_store(material_ids: list[str]) -> dict:
    return {
        "draft_materials": [],
        "draft_virtual_store": [
            {"type": 0, "value": []},
            {"type": 1, "value": [{"child_id": item, "parent_id": ""} for item in material_ids]},
            {"type": 2, "value": []},
        ],
    }


def _key_value() -> dict:
    return {}


def _draft_settings() -> str:
    now_s = int(time.time())
    return (
        "[General]\n"
        f"draft_create_time={now_s}\n"
        f"draft_last_edit_time={now_s}\n"
        "real_edit_seconds=0\n"
        "real_edit_keys=1\n"
    )


def _meta_materials(clips: list[Path]) -> list[dict]:
    from make_capcut_video import ffprobe_duration, ffprobe_video_size

    now_s = int(time.time())
    now_ms = int(time.time() * 1_000_000)
    values = []
    for clip in clips:
        try:
            duration_us = int(ffprobe_duration(clip) * 1_000_000)
            width, height = ffprobe_video_size(clip)
        except Exception:
            duration_us = 0
            width, height = 0, 0
        values.append(
            {
                "ai_group_type": "",
                "create_time": now_s,
                "duration": duration_us,
                "enter_from": 0,
                "extra_info": clip.name,
                "file_Path": capcut_path(clip),
                "height": height,
                "id": str(uuid.uuid4()).lower(),
                "import_time": now_s,
                "import_time_ms": now_ms,
                "item_source": 1,
                "material_color_tag": "",
                "md5": "",
                "metetype": "video",
                "roughcut_time_range": {"duration": duration_us, "start": 0},
                "sub_time_range": {"duration": -1, "start": -1},
                "type": 0,
                "width": width,
            }
        )
    return [
        {"type": 0, "value": values},
        {"type": 1, "value": []},
        {"type": 2, "value": [{"draft_id": "", "draft_name": "", "draft_url": ""}]},
        {"type": 3, "value": []},
        {"type": 6, "value": []},
        {"type": 7, "value": []},
        {"type": 8, "value": []},
    ]


def _empty_meta_materials() -> list[dict]:
    return [
        {"type": 0, "value": []},
        {"type": 1, "value": []},
        {"type": 2, "value": []},
        {"type": 3, "value": []},
        {"type": 6, "value": []},
        {"type": 7, "value": []},
        {"type": 8, "value": []},
    ]


def write_modern_project_files(
    project_folder: Path,
    content: dict,
    clips: list[Path],
    project_name: str,
    width: int,
    height: int,
) -> None:
    timeline_id = content["id"]
    timelines_dir = project_folder / "Timelines"
    timelines_dir.mkdir(parents=True, exist_ok=True)

    existing_timeline_dir = None
    if (timelines_dir / "project.json").is_file():
        try:
            old_project = load_json(timelines_dir / "project.json")
            old_timeline_id = old_project.get("main_timeline_id")
            if old_timeline_id and (timelines_dir / old_timeline_id).is_dir():
                existing_timeline_dir = timelines_dir / old_timeline_id
        except Exception:
            existing_timeline_dir = None
    if existing_timeline_dir is None:
        for child in timelines_dir.iterdir():
            if child.is_dir():
                existing_timeline_dir = child
                break

    timeline_dir = timelines_dir / timeline_id
    if existing_timeline_dir and existing_timeline_dir != timeline_dir:
        if timeline_dir.exists():
            shutil.rmtree(timeline_dir)
        shutil.move(str(existing_timeline_dir), str(timeline_dir))
    timeline_dir.mkdir(parents=True, exist_ok=True)

    material_ids = [
        item.get("id", "")
        for item in content.get("materials", {}).get("videos", [])
        if item.get("id")
    ]
    content["id"] = timeline_id

    save_json(project_folder / "draft_content.json", content, normalize_paths=False)
    save_json(project_folder / "draft_content.json.bak", content, normalize_paths=False)
    save_json(project_folder / "template-2.tmp", content, normalize_paths=False)
    if (project_folder / "draft_info.json").exists():
        (project_folder / "draft_info.json").unlink(missing_ok=True)

    write_timeline_project(timelines_dir, timeline_id)
    save_json(timeline_dir / "draft_content.json", content, normalize_paths=False)
    save_json(timeline_dir / "draft_content.json.bak", content, normalize_paths=False)
    save_json(timeline_dir / "template-2.tmp", content, normalize_paths=False)
    if not (timeline_dir / "template.tmp").is_file():
        save_json(timeline_dir / "template.tmp", _timeline_template(timeline_id, width, height), normalize_paths=False)

    if not (project_folder / "common_attachment").is_dir():
        write_common_attachments(project_folder / "common_attachment")
    if not (timeline_dir / "common_attachment").is_dir():
        write_common_attachments(timeline_dir / "common_attachment")
    if not (timeline_dir / "attachment").exists():
        (timeline_dir / "attachment").mkdir(parents=True, exist_ok=True)

    if not (project_folder / "attachment_pc_common.json").is_file():
        save_json(project_folder / "attachment_pc_common.json", _pc_common_attachment(), normalize_paths=False)
    if not (timeline_dir / "attachment_pc_common.json").is_file():
        save_json(timeline_dir / "attachment_pc_common.json", _pc_common_attachment(), normalize_paths=False)
    if not (timeline_dir / "attachment_editing.json").is_file():
        save_json(timeline_dir / "attachment_editing.json", _empty_attachment_editing(), normalize_paths=False)

    save_json(project_folder / "timeline_layout.json", _timeline_layout(timeline_id), normalize_paths=False)
    if not (project_folder / "performance_opt_info.json").is_file():
        save_json(
            project_folder / "performance_opt_info.json",
            {"manual_cancle_precombine_segs": None, "need_auto_precombine_segs": None},
            normalize_paths=False,
        )
    if not (project_folder / "draft_agency_config.json").is_file():
        save_json(
            project_folder / "draft_agency_config.json",
            {
                "is_auto_agency_enabled": False,
                "is_auto_agency_popup": False,
                "is_single_agency_mode": False,
                "marterials": None,
                "use_converter": False,
                "video_resolution": 720,
            },
            normalize_paths=False,
        )
    biz_path = project_folder / "draft_biz_config.json"
    if biz_path.is_file() and biz_path.stat().st_size > 0:
        save_json(
            biz_path,
            {"timeline_settings": {timeline_id: {"adsorb_enabled": False, "linkage_enabled": False}}},
            normalize_paths=False,
        )
    if (project_folder / "draft_virtual_store.json").is_file():
        save_json(project_folder / "draft_virtual_store.json", _virtual_store(material_ids), normalize_paths=False)
    if not (project_folder / "key_value.json").is_file():
        save_json(project_folder / "key_value.json", _key_value(), normalize_paths=False)
    (project_folder / "draft_settings").write_text(_draft_settings(), encoding="utf-8")
    if (project_folder / "draft_cover.jpg").is_file():
        shutil.copy2(project_folder / "draft_cover.jpg", timeline_dir / "draft_cover.jpg")


def build_project(
    clips: list[Path],
    project_name: str,
    width: int,
    height: int,
    clip_durations: list[float] | None = None,
    srt_path: Path | None = None,
    project_folder: Path | None = None,
    clips_are_internal: bool = False,
    legacy_mode: bool = False,
    normalize_paths: bool = True,
    copy_media: bool = True,
    backup_project: bool = False,
) -> Path:
    if project_folder is None:
        project_folder = unique_project_folder(project_name)
        copy_template(project_folder)
    elif not project_folder.exists():
        copy_template(project_folder)
    elif backup_project:
        backup_project_folder(project_folder)
    timelines_dir = project_folder / "Timelines"
    if timelines_dir.exists() and not legacy_mode:
        shutil.rmtree(timelines_dir)
    media_dir = project_folder / "Resources" / "auto_clips"
    media_dir.mkdir(parents=True, exist_ok=True)
    if clips_are_internal:
        project_clips = clips
    elif not copy_media:
        project_clips = clips
    else:
        project_clips = []
        for index, clip in enumerate(clips, start=1):
            target = media_dir / f"clip_{index:04d}{clip.suffix.lower()}"
            shutil.copy2(clip, target)
            project_clips.append(target)

    if BUILD_ROOT == project_folder.parent:
        project_folder = promote_build_folder(project_folder, project_name)
        project_clips = sorted((project_folder / "Resources" / "auto_clips").glob("*.mp4"))
        timelines_dir = project_folder / "Timelines"

    base_content = load_json(project_folder / "draft_content.json")
    content, cursor_us = build_content_from_real_schema(
        base_content,
        project_clips,
        width,
        height,
        clip_durations=clip_durations,
        srt_path=srt_path,
    )
    if normalize_paths:
        content = normalize_json_paths(content)

    create_cover(project_clips[0], project_folder)
    if legacy_mode:
        save_json(project_folder / "draft_content.json", content, normalize_paths=normalize_paths)
        save_json(project_folder / "draft_info.json", content, normalize_paths=normalize_paths)
        save_json(project_folder / "template-2.tmp", content, normalize_paths=normalize_paths)
        save_json(project_folder / "draft_content.json.bak", content, normalize_paths=normalize_paths)
    else:
        write_modern_project_files(
            project_folder,
            content,
            project_clips,
            project_name,
            width,
            height,
        )
    meta = update_meta(
        project_folder,
        project_name,
        cursor_us,
        project_clips[0],
        normalize_paths=normalize_paths,
    )
    meta["draft_timeline_materials_size_"] = sum(path.stat().st_size for path in project_clips if path.is_file())
    meta["draft_materials"] = _empty_meta_materials()
    save_json(project_folder / "draft_meta_info.json", meta, normalize_paths=False)
    trigger_directory_scan(project_folder)
    update_root_meta(project_folder, project_name, meta, cursor_us, project_clips[0])
    return project_folder


def main() -> int:
    request_path = Path(sys.argv[1])
    request = load_json(request_path)
    if request.get("action") == "prepare":
        project_name = request.get("project_name") or f"Auto Clips {time.strftime('%Y%m%d %H%M%S')}"
        if request.get("resume"):
            project_folder = build_folder_for_name(project_name)
            if not (project_folder / "draft_content.json").is_file() or not (project_folder / "draft_meta_info.json").is_file():
                copy_template(project_folder)
        else:
            project_folder = unique_build_folder(project_name)
            copy_template(project_folder)
        media_dir = project_folder / "Resources" / "auto_clips"
        media_dir.mkdir(parents=True, exist_ok=True)
        print(project_folder)
        return 0
    clips = [Path(item) for item in request["clips"]]
    project = build_project(
        clips=clips,
        project_name=request.get("project_name") or f"Auto Clips {time.strftime('%Y%m%d %H%M%S')}",
        width=int(request.get("width", 1920)),
        height=int(request.get("height", 1080)),
        clip_durations=[float(item) for item in request.get("clip_durations", [])],
        srt_path=Path(request["srt_path"]) if request.get("srt_path") else None,
        project_folder=Path(request["project_folder"]) if request.get("project_folder") else None,
        clips_are_internal=bool(request.get("clips_are_internal", False)),
        legacy_mode=bool(request.get("legacy_mode", False)),
        normalize_paths=bool(request.get("normalize_paths", True)),
        copy_media=bool(request.get("copy_media", True)),
        backup_project=bool(request.get("backup_project", False)),
    )
    print(project)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
