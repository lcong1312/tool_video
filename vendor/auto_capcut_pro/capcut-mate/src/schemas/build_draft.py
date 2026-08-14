"""Pydantic schemas for POST /build_draft — local Auto Capcut Pro endpoint."""

from __future__ import annotations
from typing import Any, Optional
from pydantic import BaseModel, Field


class Canvas(BaseModel):
    width: int = Field(1080, ge=360, le=7680, description="Canvas width in pixels")
    height: int = Field(1920, ge=360, le=7680, description="Canvas height in pixels")


class TextStyle(BaseModel):
    font_size: int = Field(8, ge=1, le=100)
    color: str = Field("0xFFFFFFFF", description="ARGB hex color string")
    bold: bool = False
    italic: bool = False
    has_shadow: bool = False
    shadow_color: str = Field("0xFF000000", description="Shadow ARGB hex color string")


class KeyframeOp(BaseModel):
    """Single (property, time, value) tuple applied to the overlay
    VideoSegment. Property names must match pyJianYingDraft's
    KeyframeProperty enum (position_x, position_y, rotation,
    uniform_scale, alpha)."""
    property: str
    time_offset_us: int
    value: float


class Segment(BaseModel):
    index: int = Field(..., ge=0, description="Zero-based segment index")
    text: str = Field(..., min_length=1, description="Segment transcript text")
    audio_path: str = Field(..., description="Absolute Windows path to WAV/MP3 audio")
    video_path: str = Field(..., description="Absolute Windows path to video clip")
    audio_duration_us: int = Field(..., gt=0, description="Audio duration in microseconds")
    video_duration_us: int = Field(..., gt=0, description="Video clip duration in microseconds")
    video_clips: list[str] = Field(
        default_factory=list,
        description="Optional individual video slots placed consecutively on the main track",
    )
    card_path: str = Field("", description="Optional rendered card PNG path (overlay track)")
    image_path: str = Field("", description="Optional raw image path, used as overlay fallback")
    overlay_keyframes: list[KeyframeOp] = Field(
        default_factory=list,
        description="Pre-computed keyframe animation for the overlay track. "
                    "Empty = static overlay.",
    )
    overlay_scale: float = Field(0, description="Overlay scale 0=default 0.75, 1.0=fullscreen")
    emotion: str = Field("", description="Emotion tag (optional)")
    mood: str = Field("", description="Mood tag (optional)")
    transition: str = Field("", description="Transition type name (optional)")
    text_style: Optional[TextStyle] = None


class BuildDraftRequest(BaseModel):
    canvas: Canvas = Field(default_factory=Canvas)
    segments: list[Segment] = Field(..., min_length=1)
    srt_path: Optional[str] = Field(
        None,
        description="Optional absolute path to a UTF-8 .srt file. When provided, "
                    "capmate imports it as a CapCut text track layered over the "
                    "video. Timestamps must be cumulative from 0.",
    )


class BuildDraftResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: BuildDraftData


class BuildDraftData(BaseModel):
    draft_content: Any = Field(..., description="draft_content.json as object")
    draft_meta_info: Any = Field(..., description="draft_meta_info.json as object")
