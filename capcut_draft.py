from __future__ import annotations

import json
import copy
import shutil
import sys
import time
import uuid
import subprocess
import tempfile
from pathlib import Path

from make_capcut_video import ffprobe_duration, ffprobe_video_size, run


APP_DIR = Path(__file__).resolve().parent
CAPCUT_DRAFT_ROOT = Path.home() / "AppData/Local/CapCut/User Data/Projects/com.lveditor.draft"
LOCAL_ACP_PYTHON = APP_DIR / "vendor" / "auto_capcut_pro" / "python" / "python.exe"
ACP_PYTHON = Path(r"C:\Program Files\Auto Capcut Pro\python\python.exe")
ACP_HELPER = Path(__file__).with_name("acp_build_project.py")


def _builder_python() -> str:
    if LOCAL_ACP_PYTHON.is_file():
        return str(LOCAL_ACP_PYTHON)
    if ACP_PYTHON.is_file():
        return str(ACP_PYTHON)
    return sys.executable


def _json_files(folder: Path) -> list[Path]:
    return list(folder.rglob("draft_content.json")) + [folder / "draft_meta_info.json"]


def _load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _save_json(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))


def _capcut_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def _create_cover(video: Path, project_folder: Path) -> Path:
    cover = project_folder / "draft_cover.jpg"
    try:
        run(
            [
                "ffmpeg",
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
            capture=True,
        )
    except Exception:
        pass
    return cover


def _unique_project_folder(name: str) -> Path:
    CAPCUT_DRAFT_ROOT.mkdir(parents=True, exist_ok=True)
    base = "".join(char for char in name if char not in r'<>:"/\|?*').strip() or "Auto video"
    candidate = CAPCUT_DRAFT_ROOT / base
    if not candidate.exists():
        return candidate
    for index in range(1, 1000):
        candidate = CAPCUT_DRAFT_ROOT / f"{base} ({index})"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Khong tao duoc ten project CapCut moi.")


def _find_template() -> Path:
    candidates = []
    for folder in CAPCUT_DRAFT_ROOT.iterdir():
        if not folder.is_dir() or folder.name.startswith(".") or folder.name.startswith("Auto "):
            continue
        lowered = folder.name.lower()
        if lowered.startswith("dl14") or "clone" in lowered or "test" in lowered:
            continue
        if (folder / "Resources" / "auto_clips").exists():
            continue
        content = folder / "draft_content.json"
        meta = folder / "draft_meta_info.json"
        if content.is_file() and meta.is_file():
            try:
                data = _load_json(content)
                duration = int(data.get("duration") or 0)
                segment_count = sum(len(track.get("segments") or []) for track in data.get("tracks", []))
            except Exception:
                duration = 999999
                segment_count = 999999
            clean_bonus = 0
            for extra in ("attachment_editing.json", "draft.extra", "draft_virtual_store.json"):
                if not (folder / extra).exists():
                    clean_bonus += 1
            candidates.append((1 if duration == 0 and segment_count == 0 else 0, clean_bonus, folder.stat().st_mtime, folder))
    if not candidates:
        raise RuntimeError("Khong tim thay draft CapCut mau de tao project moi.")
    return max(candidates, key=lambda item: (item[0], item[1], item[2]))[3]


def find_latest_capcut_project() -> Path:
    candidates = []
    for folder in CAPCUT_DRAFT_ROOT.iterdir():
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        content_path = folder / "draft_content.json"
        if content_path.is_file() and (folder / "draft_meta_info.json").is_file():
            try:
                content = _load_json(content_path)
                duration = int(content.get("duration") or 0)
                segment_count = sum(len(track.get("segments") or []) for track in content.get("tracks", []))
            except Exception:
                continue
            if duration > 1_000_000 or segment_count > 0:
                continue
            candidates.append(folder)
    if not candidates:
        raise RuntimeError("Chua tim thay project CapCut trong. Hay mo CapCut, bam Tao du an moi, dong tab edit neu can, roi chay lai.")
    return max(candidates, key=lambda item: item.stat().st_mtime)


def _video_material(video_id: str, video: Path, duration_us: int, width: int, height: int) -> dict:
    return {
        "id": video_id,
        "unique_id": "",
        "type": "video",
        "duration": duration_us,
        "path": _capcut_path(video),
        "media_path": "",
        "local_id": "",
        "has_audio": False,
        "reverse_path": "",
        "intensifies_path": "",
        "reverse_intensifies_path": "",
        "intensifies_audio_path": "",
        "cartoon_path": "",
        "width": width,
        "height": height,
        "category_id": "",
        "category_name": "",
        "material_id": "",
        "material_name": video.name,
        "material_url": "",
        "crop": {
            "upper_left_x": 0.0,
            "upper_left_y": 0.0,
            "upper_right_x": 1.0,
            "upper_right_y": 0.0,
            "lower_left_x": 0.0,
            "lower_left_y": 1.0,
            "lower_right_x": 1.0,
            "lower_right_y": 1.0,
        },
        "crop_ratio": "free",
        "audio_fade": None,
        "crop_scale": 1.0,
        "extra_type_option": 0,
        "stable": {"stable_level": 0, "matrix_path": "", "time_range": {"start": 0, "duration": 0}},
        "source": 0,
        "source_platform": 0,
        "formula_id": "",
        "check_flag": 62978047,
    }


def _segment(material_id: str, duration_us: int, start_us: int, refs: list[str]) -> dict:
    return {
        "id": str(uuid.uuid4()).upper(),
        "source_timerange": {"start": 0, "duration": duration_us},
        "target_timerange": {"start": start_us, "duration": duration_us},
        "render_timerange": {"start": 0, "duration": 0},
        "desc": "",
        "state": 0,
        "speed": 1.0,
        "is_loop": False,
        "is_tone_modify": False,
        "reverse": False,
        "intensifies_audio": False,
        "cartoon": False,
        "volume": 1.0,
        "last_nonzero_volume": 1.0,
        "clip": {
            "scale": {"x": 1.0, "y": 1.0},
            "rotation": 0.0,
            "transform": {"x": 0.0, "y": 0.0},
            "flip": {"vertical": False, "horizontal": False},
            "alpha": 1.0,
        },
        "uniform_scale": {"on": True, "value": 1.0},
        "material_id": material_id,
        "extra_material_refs": refs,
        "render_index": 0,
        "keyframe_refs": [],
        "enable_lut": True,
        "enable_adjust": True,
        "enable_hsl": False,
        "visible": True,
        "group_id": "",
        "enable_color_curves": True,
        "enable_hsl_curves": True,
        "track_render_index": 0,
        "hdr_settings": {"mode": 1, "intensity": 1.0, "nits": 1000},
        "enable_color_wheels": True,
        "track_attribute": 0,
        "is_placeholder": False,
        "template_id": "",
        "enable_smart_color_adjust": False,
        "template_scene": "default",
        "common_keyframes": [],
        "caption_info": None,
        "responsive_layout": {
            "enable": False,
            "target_follow": "",
            "size_layout": 0,
            "horizontal_pos_layout": 0,
            "vertical_pos_layout": 0,
        },
        "enable_color_match_adjust": False,
        "enable_color_correct_adjust": False,
        "enable_adjust_mask": False,
        "raw_segment_id": "",
        "lyric_keyframes": None,
        "enable_video_mask": True,
        "digital_human_template_group_id": "",
        "color_correct_alg_result": "",
        "source": "segmentsourcenormal",
        "enable_mask_stroke": False,
        "enable_mask_shadow": False,
        "enable_color_adjust_pro": False,
        "segment_color_tag": "",
    }


def _update_content(data: dict, video: Path, duration_us: int, width: int, height: int) -> dict:
    return _update_content_for_clips(data, [(video, duration_us, width, height)])


def _update_content_for_clips(data: dict, clips: list[tuple[Path, int, int, int]]) -> dict:
    now = int(time.time())
    canvas_id = str(uuid.uuid4()).upper()
    track_id = str(uuid.uuid4()).upper()
    total_duration_us = sum(item[1] for item in clips)

    data["id"] = str(uuid.uuid4()).upper()
    data["name"] = ""
    data["duration"] = total_duration_us
    data["create_time"] = now
    data["update_time"] = now
    data["canvas_config"] = {
        "ratio": "original",
        "width": clips[0][2],
        "height": clips[0][3],
        "background": None,
    }
    template_videos = data.get("materials", {}).get("videos", [])
    template_segments = []
    for track in data.get("tracks", []):
        if track.get("type") == "video":
            template_segments = track.get("segments", [])
            break
    video_template = copy.deepcopy(template_videos[0]) if template_videos else None
    segment_template = copy.deepcopy(template_segments[0]) if template_segments else None

    videos = []
    segments = []
    speeds = []
    placeholders = []
    channel_mappings = []
    material_colors = []
    vocal_separations = []
    start_us = 0
    for video, duration_us, width, height in clips:
        video_id = str(uuid.uuid4()).upper()
        speed_id = str(uuid.uuid4()).upper()
        placeholder_id = str(uuid.uuid4()).upper()
        channel_id = str(uuid.uuid4()).upper()
        color_id = str(uuid.uuid4()).upper()
        vocal_id = str(uuid.uuid4()).upper()
        refs = [speed_id, placeholder_id, canvas_id, channel_id, color_id, vocal_id]
        if video_template:
            material = copy.deepcopy(video_template)
            material["id"] = video_id
            material["duration"] = duration_us
            material["path"] = _capcut_path(video)
            material["media_path"] = ""
            material["material_name"] = video.name
            material["width"] = width
            material["height"] = height
            material["has_audio"] = False
            videos.append(material)
        else:
            videos.append(_video_material(video_id, video, duration_us, width, height))

        if segment_template:
            segment = copy.deepcopy(segment_template)
            segment["id"] = str(uuid.uuid4()).upper()
            segment["material_id"] = video_id
            segment["extra_material_refs"] = refs
            segment["source_timerange"] = {"start": 0, "duration": duration_us}
            segment["target_timerange"] = {"start": start_us, "duration": duration_us}
            segment["render_timerange"] = {"start": 0, "duration": 0}
            segment["render_index"] = 0
            segment["track_render_index"] = 0
            segments.append(segment)
        else:
            segments.append(_segment(video_id, duration_us, start_us, refs))
        speeds.append({"id": speed_id, "type": "speed", "mode": 0, "speed": 1.0, "curve_speed": None})
        placeholders.append({"id": placeholder_id, "type": "placeholder_info", "meta_type": "none", "res_path": "", "res_text": "", "error_path": "", "error_text": ""})
        channel_mappings.append({"id": channel_id, "type": "", "audio_channel_mapping": 0, "is_config_open": False})
        material_colors.append({"id": color_id, "is_color_clip": False, "is_gradient": False, "solid_color": "", "gradient_colors": [], "gradient_percents": [], "gradient_angle": 90.0, "width": 0.0, "height": 0.0})
        vocal_separations.append({"id": vocal_id, "type": "vocal_separation", "choice": 0, "removed_sounds": [], "time_range": None, "production_path": "", "final_algorithm": "", "enter_from": ""})
        start_us += duration_us

    data["tracks"] = [
        {
            "id": track_id,
            "type": "video",
            "segments": segments,
            "flag": 0,
            "attribute": 0,
            "name": "",
            "is_default_name": True,
        }
    ]

    materials = data.setdefault("materials", {})
    for key, value in list(materials.items()):
        if isinstance(value, list):
            materials[key] = []
    materials["videos"] = videos
    materials["speeds"] = speeds
    materials["placeholder_infos"] = placeholders
    materials["canvases"] = [
        {"id": canvas_id, "type": "canvas_color", "color": "", "blur": 0.0, "image": "", "album_image": "", "image_id": "", "image_name": "", "source_platform": 0, "team_id": ""}
    ]
    materials["sound_channel_mappings"] = channel_mappings
    materials["material_colors"] = material_colors
    materials["vocal_separations"] = vocal_separations
    data["keyframes"] = {"videos": [], "audios": [], "texts": [], "stickers": [], "filters": [], "adjusts": [], "handwrites": [], "effects": []}
    return data


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


def _update_meta(data: dict, project_folder: Path, project_name: str, video: Path, duration_us: int) -> dict:
    now_us = int(time.time() * 1_000_000)
    data["draft_id"] = str(uuid.uuid4()).upper()
    data["draft_name"] = project_name
    data["draft_cover"] = "draft_cover.jpg"
    data["draft_fold_path"] = _capcut_path(project_folder)
    data["draft_root_path"] = str(CAPCUT_DRAFT_ROOT).replace("/", "\\")
    data["tm_draft_create"] = now_us
    data["tm_draft_modified"] = now_us
    data["tm_duration"] = duration_us
    data["draft_materials"] = _empty_meta_materials()
    return data


def _update_root_meta(meta: dict, project_folder: Path, project_name: str, video: Path, duration_us: int) -> None:
    root_path = CAPCUT_DRAFT_ROOT / "root_meta_info.json"
    if root_path.is_file():
        root = _load_json(root_path)
    else:
        root = {"all_draft_store": [], "draft_ids": 0, "root_path": _capcut_path(CAPCUT_DRAFT_ROOT)}

    stores = root.setdefault("all_draft_store", [])
    folder_path = _capcut_path(project_folder)
    stores[:] = [item for item in stores if item.get("draft_fold_path") != folder_path]

    entry = {
        "cloud_draft_cover": False,
        "cloud_draft_sync": False,
        "draft_cloud_last_action_download": False,
        "draft_cloud_purchase_info": "",
        "draft_cloud_template_id": "",
        "draft_cloud_tutorial_info": "",
        "draft_cloud_videocut_purchase_info": "",
        "draft_cover": _capcut_path(project_folder / "draft_cover.jpg"),
        "draft_fold_path": folder_path,
        "draft_id": meta.get("draft_id", str(uuid.uuid4()).upper()),
        "draft_is_ai_shorts": False,
        "draft_is_cloud_temp_draft": False,
        "draft_is_invisible": False,
        "draft_is_pippit_draft": False,
        "draft_is_web_article_video": False,
        "draft_json_file": _capcut_path(project_folder / "draft_content.json"),
        "draft_name": project_name,
        "draft_new_version": "",
        "draft_root_path": _capcut_path(CAPCUT_DRAFT_ROOT),
        "draft_timeline_materials_size": video.stat().st_size if video.is_file() else 0,
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
        "tm_draft_create": meta.get("tm_draft_create", int(time.time() * 1_000_000)),
        "tm_draft_modified": meta.get("tm_draft_modified", int(time.time() * 1_000_000)),
        "tm_draft_removed": 0,
        "tm_duration": duration_us,
    }
    stores.insert(0, entry)
    root["draft_ids"] = len(stores)
    root["root_path"] = _capcut_path(CAPCUT_DRAFT_ROOT)
    _save_json(root_path, root)


def _copy_support_files(template: Path, project_folder: Path) -> None:
    for name in [
        "adjust_mask",
        "common_attachment",
        "matting",
        "qr_upload",
        "Resources",
        "smart_crop",
        "subdraft",
    ]:
        source = template / name
        target = project_folder / name
        if source.is_dir() and not target.exists():
            try:
                import shutil

                shutil.copytree(source, target, ignore_dangling_symlinks=True)
            except OSError:
                target.mkdir(parents=True, exist_ok=True)
        elif source.exists():
            try:
                target.write_bytes(source.read_bytes())
            except OSError:
                pass


def _write_timeline_project(timelines_dir: Path, timeline_id: str) -> None:
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
    _save_json(timelines_dir / "project.json", data)
    _save_json(timelines_dir / "project.json.bak", data)


def _write_common_attachment_stubs(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    stubs = {
        "attachment_action_scene.json": {"action_scene": {"removed_segments": [], "segment_infos": []}},
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
        "attachment_plugin_draft.json": {"plugin_draft": {"plugin_segments": [], "version": "1.0.0"}},
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
    for filename, data in stubs.items():
        _save_json(folder / filename, data)


def _write_modern_support_files(project_folder: Path, content: dict, clips: list[Path], template: Path) -> None:
    timeline_id = content["id"]
    timelines_dir = project_folder / "Timelines"
    timeline_folder = timelines_dir / timeline_id
    if timelines_dir.exists():
        shutil.rmtree(timelines_dir)
    timeline_folder.mkdir(parents=True, exist_ok=True)
    _write_timeline_project(timelines_dir, timeline_id)

    _save_json(project_folder / "draft_content.json", content)
    _save_json(project_folder / "draft_content.json.bak", content)
    _save_json(project_folder / "template-2.tmp", content)
    _save_json(timeline_folder / "draft_content.json", content)
    _save_json(timeline_folder / "draft_content.json.bak", content)
    _save_json(timeline_folder / "template-2.tmp", content)

    copied_template_tmp = False
    for candidate in (template / "Timelines").glob("*/template.tmp"):
        try:
            shutil.copy2(candidate, timeline_folder / "template.tmp")
            copied_template_tmp = True
            break
        except OSError:
            pass
    if not copied_template_tmp:
        _save_json(timeline_folder / "template.tmp", {"id": timeline_id, "tracks": [], "materials": {}})

    _write_common_attachment_stubs(project_folder / "common_attachment")
    _write_common_attachment_stubs(timeline_folder / "common_attachment")
    (timeline_folder / "attachment").mkdir(parents=True, exist_ok=True)

    for filename in ["attachment_editing.json", "attachment_pc_common.json", "draft.extra", "draft_cover.jpg"]:
        source = project_folder / filename
        if source.is_file():
            try:
                shutil.copy2(source, timeline_folder / filename)
            except OSError:
                pass

    material_ids = [
        item.get("id", "")
        for item in content.get("materials", {}).get("videos", [])
        if item.get("id")
    ]
    _save_json(
        project_folder / "timeline_layout.json",
        {
            "dockItems": [
                {
                    "dockIndex": 0,
                    "ratio": 1,
                    "timelineIds": [timeline_id],
                    "timelineNames": ["Timeline 01"],
                }
            ],
            "layoutOrientation": 1,
        },
    )
    _save_json(
        project_folder / "draft_biz_config.json",
        {"timeline_settings": {timeline_id: {"adsorb_enabled": False, "linkage_enabled": False}}},
    )
    _save_json(
        project_folder / "draft_virtual_store.json",
        {
            "draft_materials": [],
            "draft_virtual_store": [
                {"type": 0, "value": []},
                {"type": 1, "value": [{"child_id": item, "parent_id": ""} for item in material_ids]},
                {"type": 2, "value": []},
            ],
        },
    )

    for filename in [
        "attachment_pc_common.json",
        "draft_agency_config.json",
        "draft_biz_config.json",
        "draft_settings",
        "draft_virtual_store.json",
        "key_value.json",
        "performance_opt_info.json",
        "timeline_layout.json",
    ]:
        source = template / filename
        if source.is_file():
            try:
                (project_folder / filename).write_bytes(source.read_bytes())
            except OSError:
                pass


def create_capcut_project(video: Path, duration_seconds: float, project_name: str | None = None) -> Path:
    if not video.is_file():
        raise RuntimeError(f"Khong tim thay video de dua vao CapCut: {video}")

    template = _find_template()
    name = project_name or f"Auto {time.strftime('%Y%m%d %H%M%S')}"
    project_folder = _unique_project_folder(name)
    project_folder.mkdir(parents=True, exist_ok=False)

    duration_us = int(duration_seconds * 1_000_000)
    width, height = ffprobe_video_size(video)

    content_template = _load_json(template / "draft_content.json")
    meta_template = _load_json(template / "draft_meta_info.json")

    content = _update_content(content_template, video, duration_us, width, height)
    meta = _update_meta(meta_template, project_folder, project_folder.name, video, duration_us)
    _create_cover(video, project_folder)
    _copy_support_files(template, project_folder)
    _write_modern_support_files(project_folder, content, [video], template)
    _save_json(project_folder / "draft_meta_info.json", meta)
    _update_root_meta(meta, project_folder, project_folder.name, video, duration_us)

    return project_folder


def create_capcut_project_from_clips(
    clips: list[Path],
    project_name: str | None = None,
    fallback_clip_duration: float | None = None,
    clip_durations: list[float] | None = None,
    srt_path: Path | None = None,
    project_folder: Path | None = None,
    clips_are_internal: bool = False,
    backup_project: bool = False,
) -> Path:
    if not clips:
        raise RuntimeError("Khong co clip nao de dua vao CapCut.")
    for clip in clips:
        if not clip.is_file():
            raise RuntimeError(f"Khong tim thay clip: {clip}")

    if ACP_HELPER.is_file():
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
            request_path = Path(handle.name)
            json.dump(
                {
                    "clips": [str(clip.resolve()) for clip in clips],
                    "project_name": project_name or f"Auto Clips {time.strftime('%Y%m%d %H%M%S')}",
                    "width": 1920,
                    "height": 1080,
                    "project_folder": str(project_folder) if project_folder else "",
                    "clips_are_internal": clips_are_internal,
                    "backup_project": backup_project,
                    "clip_durations": clip_durations or [],
                    "srt_path": str(srt_path.resolve()) if srt_path else "",
                },
                handle,
                ensure_ascii=False,
            )
        try:
            result = subprocess.run(
                [_builder_python(), str(ACP_HELPER), str(request_path)],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(exc.stderr or exc.stdout or "Auto Capcut Pro draft builder failed") from exc
        finally:
            request_path.unlink(missing_ok=True)
        output = result.stdout.strip().splitlines()[-1]
        return Path(output)

    template = _find_template()
    name = project_name or f"Auto Clips {time.strftime('%Y%m%d %H%M%S')}"
    project_folder = _unique_project_folder(name)
    project_folder.mkdir(parents=True, exist_ok=False)

    clip_infos = []
    for clip in clips:
        try:
            duration_seconds = ffprobe_duration(clip)
        except Exception:
            if fallback_clip_duration is None:
                raise
            duration_seconds = fallback_clip_duration
        duration_us = int(duration_seconds * 1_000_000)
        width, height = ffprobe_video_size(clip)
        if clip_durations and len(clip_durations) > len(clip_infos):
            duration_us = int(float(clip_durations[len(clip_infos)]) * 1_000_000)
        clip_infos.append((clip, duration_us, width, height))

    total_duration_us = sum(item[1] for item in clip_infos)
    content = _update_content_for_clips(_load_json(template / "draft_content.json"), clip_infos)
    meta = _update_meta(
        _load_json(template / "draft_meta_info.json"),
        project_folder,
        project_folder.name,
        clips[0],
        total_duration_us,
    )
    meta["draft_materials"] = _empty_meta_materials()
    _create_cover(clips[0], project_folder)
    _copy_support_files(template, project_folder)
    _write_modern_support_files(project_folder, content, clips, template)
    _save_json(project_folder / "draft_meta_info.json", meta)
    _update_root_meta(meta, project_folder, project_folder.name, clips[0], total_duration_us)
    return project_folder


def prepare_capcut_project(project_name: str, resume: bool = False) -> Path:
    if not ACP_HELPER.is_file():
        raise RuntimeError(f"Khong tim thay file builder: {ACP_HELPER}")
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        request_path = Path(handle.name)
        json.dump(
            {"action": "prepare", "project_name": project_name, "resume": resume},
            handle,
            ensure_ascii=False,
        )
    try:
        result = subprocess.run(
            [_builder_python(), str(ACP_HELPER), str(request_path)],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(exc.stderr or exc.stdout or "Prepare CapCut project failed") from exc
    finally:
        request_path.unlink(missing_ok=True)
    return Path(result.stdout.strip().splitlines()[-1])
