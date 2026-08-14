"""Stateless build_draft service for Auto Capcut Pro local mode.

Receives a BuildDraftRequest (canvas + segments with local Windows paths),
builds a CapCut draft in-memory using pyJianYingDraft, and returns
draft_content and draft_meta_info as plain Python dicts — no files written.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path

import src.pyJianYingDraft as draft
from src.pyJianYingDraft import ScriptFile, trange, TrackType
from src.pyJianYingDraft.local_materials import VideoMaterial, AudioMaterial
from src.pyJianYingDraft.audio_segment import AudioSegment
from src.pyJianYingDraft.video_segment import VideoSegment
from src.pyJianYingDraft.text_segment import TextStyle
from src.pyJianYingDraft.segment import ClipSettings
from src.pyJianYingDraft.keyframe import KeyframeProperty
from src.schemas.build_draft import BuildDraftRequest, Segment
from src.utils.logger import logger

import config

# Path to the shipped template meta file — used as the meta_info base
_TEMPLATE_META = os.path.join(config.TEMPLATE_DIR, "default2", "draft_meta_info.json")


def _to_forward_slash(win_path: str) -> str:
    """Convert Windows backslashes to forward slashes (CapCut JSON expectation)."""
    return win_path.replace("\\", "/")


def _build_meta_info(draft_id: str, draft_name: str, duration_us: int) -> dict:
    """Build a minimal draft_meta_info dict for local deployment."""
    now_us = int(time.time() * 1_000_000)

    # Load the shipped template as base and patch key fields
    if os.path.exists(_TEMPLATE_META):
        with open(_TEMPLATE_META, "r", encoding="utf-8") as f:
            meta = json.load(f)
    else:
        meta = {}

    meta["draft_id"] = draft_id
    meta["draft_name"] = draft_name
    meta["tm_draft_create"] = now_us
    meta["tm_draft_modified"] = now_us
    meta["tm_duration"] = duration_us
    # Clear cloud-only fields
    meta["draft_fold_path"] = ""
    meta["draft_root_path"] = ""
    meta["draft_cloud_materials"] = []
    return meta


def build_draft(req: BuildDraftRequest) -> tuple[dict, dict]:
    """Build CapCut draft from request and return (draft_content_dict, draft_meta_info_dict).

    All paths in req.segments are absolute Windows paths — they are embedded as-is
    (forward-slash normalised) into the draft JSON so CapCut can find them locally.
    """
    draft_id = uuid.uuid4().hex.upper()
    draft_name = f"acp_{draft_id[:8]}"

    logger.info("build_draft: id=%s canvas=%dx%d segments=%d",
                draft_id, req.canvas.width, req.canvas.height, len(req.segments))

    # 1. Create a fresh ScriptFile (uses internal pyJianYingDraft asset template)
    script = ScriptFile(width=req.canvas.width, height=req.canvas.height)

    # 2. Tracks (bottom → top):
    #       audio_main   — TTS
    #       video_main   — Pexels B-roll (full screen)
    #       video_overlay — newspaper card / image overlay (PIP)
    #       text_captions — created later by import_srt if srt_path set
    script.add_track(TrackType.video, "video_main", relative_index=0)
    script.add_track(TrackType.video, "video_overlay", relative_index=1)
    script.add_track(TrackType.audio, "audio_main", relative_index=0)

    # 3. Build timeline — each input segment placed end-to-end
    #    Audio blocks stay 1:1; video blocks may contain several <=3s slots.
    #    Overlay track: consecutive segments sharing the same overlay image
    #    are merged into ONE overlay spanning their combined duration so
    #    CapCut shows a single continuous image instead of N duplicate clips.
    sorted_segs = sorted(req.segments, key=lambda s: s.index)

    cursor_us: int = 0
    seg_positions: list[tuple[Segment, int]] = []

    for seg in sorted_segs:
        _add_segment(script, seg, cursor_us)
        seg_positions.append((seg, cursor_us))
        cursor_us += max(seg.audio_duration_us, seg.video_duration_us)

    _add_grouped_overlays(script, seg_positions)

    total_duration_us = cursor_us

    # 4. Optional subtitle track — import SRT if the caller provided one.
    #    import_srt() creates a dedicated text track sitting above the
    #    video, styled to match CapCut's default caption look.
    #
    #    Before importing the SRT we pre-create 3 empty spacer video tracks
    #    (relative_index 1/2/3) so the text track lands at CapCut's lane 5
    #    instead of lane 2 — the SRT_CAPTIONS_TARGET_LAYER design choice.
    #    Tracks export with whatever segments they contain; CapCut renders
    #    the empty spacers as visible lanes ready for user content (extra
    #    B-roll, overlays, etc.) above the main video.
    if req.srt_path:
        for i in range(1, 4):
            spacer_name = "video_spacer_%d" % i
            if spacer_name not in script.tracks:
                script.add_track(TrackType.video, spacer_name, relative_index=i)
        if os.path.exists(req.srt_path):
            try:
                # max_line_width bumped 0.82 -> 0.98 so Vietnamese cues
                # (which fit one line after SplitByPunctuation but were
                # being clipped at 82% canvas width) don't trigger
                # CapCut's hard-cut mid-word wrap fallback. With
                # phrase-level cues the actual wrapping almost never
                # fires now; the extra width is purely insurance.
                script.import_srt(
                    req.srt_path,
                    track_name="text_captions",
                    text_style=TextStyle(
                        size=7,
                        color=(0.925, 0.114, 0.114),
                        alpha=1.0,
                        align=1,
                        auto_wrapping=True,
                        max_line_width=0.98,
                        line_spacing=0.17,
                        letter_spacing=0,
                    ),
                    clip_settings=ClipSettings(transform_y=-0.78),
                )
                logger.info("build_draft: imported SRT %s", req.srt_path)
            except Exception as exc:
                logger.warning("build_draft: import_srt failed: %s — skipping", exc)
        else:
            logger.warning("build_draft: srt_path %s not found — skipping", req.srt_path)

    # 5. Serialise draft_content to dict (dumps → parse avoids save_path requirement)
    draft_content_str = script.dumps()
    draft_content = json.loads(draft_content_str)

    # 6. Build draft_meta_info
    draft_meta_info = _build_meta_info(draft_id, draft_name, total_duration_us)

    logger.info("build_draft OK: total_duration=%dµs", total_duration_us)
    return draft_content, draft_meta_info


def _add_segment(script: ScriptFile, seg: Segment, start_us: int) -> None:
    """Add one or more video (or photo) slots, plus an audio segment when an
    audio path is provided.

    Video path is mandatory — without it there's nothing to place on the
    timeline so we skip. Audio path is OPTIONAL: the SRT-import pipeline
    (Auto Capcut Pro Decision #2) doesn't synthesize TTS so its segments
    arrive audio-less, and the user supplies the voice-over inside CapCut
    after the draft opens. The regular build pipeline always provides
    both paths so its behaviour is unchanged.

    Image inputs (.jpg / .jpeg / .png / .webp / .bmp) are accepted as
    video_path — VideoMaterial auto-detects them via libmediainfo and
    tags the material as "photo", so a still image renders as a held
    frame on the video track without any pre-encoding.
    """
    if not seg.video_path:
        logger.warning("build_draft: segment %d missing video path — skipping", seg.index)
        return
    video_dur = seg.video_duration_us

    # --- Video / Photo ---
    # A downloaded voice segment is persisted as individual <=3s slots. Add
    # every slot to the same track so CapCut exposes the real cut rhythm.
    video_paths = list(getattr(seg, "video_clips", []) or [])
    if not video_paths:
        video_paths = [seg.video_path]
    remaining_us = video_dur
    offset_us = 0
    for clip_index, raw_path in enumerate(video_paths):
        if remaining_us <= 0:
            break
        slot_dur_us = min(3_000_000, remaining_us) if len(video_paths) > 1 else remaining_us
        video_path = _to_forward_slash(os.path.abspath(raw_path))
        try:
            video_mat = VideoMaterial(video_path)
            # For photo materials VideoMaterial.duration is a synthetic 3h
            # constant; clamp source_timerange to the requested slot length.
            src_dur = min(video_mat.duration, slot_dur_us) if slot_dur_us > 0 else video_mat.duration
            video_seg = VideoSegment(
                material=video_mat,
                target_timerange=trange(start=start_us + offset_us, duration=slot_dur_us),
                source_timerange=trange(start=0, duration=src_dur),
                volume=0.0,  # mute video native audio; TTS owns the audio track
            )
            script.add_segment(video_seg, "video_main")
        except Exception as exc:
            logger.error(
                "build_draft: video segment %d clip %d failed: %s",
                seg.index,
                clip_index,
                exc,
            )
            raise
        offset_us += slot_dur_us
        remaining_us -= slot_dur_us

    # --- Audio (TTS) — only when the caller supplied an audio path ---
    if not seg.audio_path:
        return
    audio_path = _to_forward_slash(os.path.abspath(seg.audio_path))
    audio_dur = seg.audio_duration_us
    try:
        audio_mat = AudioMaterial(audio_path)
        audio_seg = AudioSegment(
            material=audio_mat,
            target_timerange=trange(start=start_us, duration=audio_dur),
            source_timerange=trange(start=0, duration=min(audio_mat.duration, audio_dur)),
            volume=1.0,
        )
        script.add_segment(audio_seg, "audio_main")
    except Exception as exc:
        logger.error("build_draft: audio segment %d failed: %s", seg.index, exc)
        raise


_KEYFRAME_PROPERTY_MAP = {
    "position_x":    KeyframeProperty.position_x,
    "position_y":    KeyframeProperty.position_y,
    "rotation":      KeyframeProperty.rotation,
    "uniform_scale": KeyframeProperty.uniform_scale,
    "scale_x":       KeyframeProperty.scale_x,
    "scale_y":       KeyframeProperty.scale_y,
    "alpha":         KeyframeProperty.alpha,
}


def _get_overlay_key(seg: Segment) -> tuple[str, float] | None:
    """Return the grouping key for a segment's overlay, or None if no overlay."""
    path = (seg.card_path or "").strip() or (seg.image_path or "").strip()
    if not path:
        return None
    scale = getattr(seg, 'overlay_scale', 0) or 0.75
    return (path, scale)


def _add_grouped_overlays(
    script: ScriptFile,
    seg_positions: list[tuple[Segment, int]],
) -> None:
    """Group consecutive segments sharing the same overlay image+scale and
    create ONE overlay VideoSegment per group on the video_overlay track.
    """
    if not seg_positions:
        return

    groups: list[list[tuple[Segment, int]]] = []
    current_group: list[tuple[Segment, int]] = []
    current_key: tuple[str, float] | None = None

    for seg, start_us in seg_positions:
        key = _get_overlay_key(seg)
        if key is None:
            if current_group:
                groups.append(current_group)
                current_group = []
                current_key = None
            continue
        if key == current_key:
            current_group.append((seg, start_us))
        else:
            if current_group:
                groups.append(current_group)
            current_group = [(seg, start_us)]
            current_key = key

    if current_group:
        groups.append(current_group)

    for group in groups:
        first_seg, group_start_us = group[0]
        last_seg, last_start_us = group[-1]
        group_end_us = last_start_us + max(last_seg.audio_duration_us, last_seg.video_duration_us)
        group_dur = group_end_us - group_start_us
        first_seg_dur = max(first_seg.audio_duration_us, first_seg.video_duration_us)

        scaled_keyframes = []
        if first_seg.overlay_keyframes and first_seg_dur > 0:
            ratio = group_dur / first_seg_dur
            for kf in first_seg.overlay_keyframes:
                scaled_keyframes.append(type(kf)(
                    property=kf.property,
                    time_offset_us=int(kf.time_offset_us * ratio),
                    value=kf.value,
                ))

        overlay_path = first_seg.card_path or first_seg.image_path
        logger.info("_add_grouped_overlay: seg %d, group_size=%d, dur=%d, path=%r",
                     first_seg.index, len(group), group_dur, overlay_path)
        if not overlay_path:
            continue
        overlay_path = _to_forward_slash(os.path.abspath(overlay_path))
        if not os.path.exists(overlay_path):
            logger.warning("build_draft: overlay %s not found — skipping", overlay_path)
            continue

        try:
            mat = VideoMaterial(overlay_path)
            src_dur = min(mat.duration, group_dur) if mat.material_type == "video" else group_dur
            scale = getattr(first_seg, 'overlay_scale', 0) or 0.75
            ty = 0.0 if scale >= 1.0 else 0.22
            overlay_seg = VideoSegment(
                material=mat,
                target_timerange=trange(start=group_start_us, duration=group_dur),
                source_timerange=trange(start=0, duration=src_dur),
                volume=0.0,
                clip_settings=ClipSettings(
                    scale_x=scale,
                    scale_y=scale,
                    transform_y=ty,
                ),
            )
            script.add_segment(overlay_seg, "video_overlay")

            for kf in scaled_keyframes:
                prop = _KEYFRAME_PROPERTY_MAP.get(kf.property)
                if prop is None:
                    continue
                try:
                    overlay_seg.add_keyframe(prop, int(kf.time_offset_us), float(kf.value))
                except Exception as exc:
                    logger.warning("build_draft: keyframe failed on merged seg %d: %s",
                                   first_seg.index, exc)

        except Exception as exc:
            logger.warning("build_draft: overlay seg %d failed: %s — skipping",
                           first_seg.index, exc)
