import os
import re
import sys
import time
import wave
import struct
import threading
import traceback
import json
import hashlib
import mimetypes
import importlib.metadata
import httpx
from pathlib import Path
from datetime import timedelta
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from dotenv import load_dotenv
    from fishaudio import FishAudio
    from fishaudio.utils import save
except Exception as exc:
    print("Thiếu thư viện cần thiết:", exc)
    print("Hãy chạy RUN_FISH_GUI_V4.bat để tự cài phần còn thiếu.")
    sys.exit(1)

try:
    from tkinterdnd2 import DND_FILES, DND_TEXT, TkinterDnD
    HAS_DND = True
except Exception:
    DND_FILES = None
    DND_TEXT = None
    TkinterDnD = None
    HAS_DND = False

APP_TITLE = "Fish Story GUI v5.3.2 - Clone REST trực tiếp"
APP_VERSION = "5.3.2"
DEFAULT_MODEL = "s2.1-pro-free"
DEFAULT_VOICE_LABEL = "GIỌNG MẶC ĐỊNH FISH (không dùng Voice ID)"
DEFAULT_SPEED = "0.95"
DEFAULT_MAX_CHARS = "500"
DEFAULT_RETRY = "3"
SETTINGS_FILENAME = "fish_story_v53_settings.json"
DEFAULT_VOICE_KEY = "__fish_default__"
SUPPORTED_AUDIO = [("Audio files", "*.wav *.mp3 *.m4a *.opus"), ("All files", "*.*")]
SUPPORTED_TEXT_EXTS = {".txt", ".md", ".srt", ".csv", ".json", ".log"}

LANGUAGES = {
    "ja": {
        "name": "Tiếng Nhật",
        "cue_name": "Japanese",
        "clone_title": "Japanese Story Voice",
        "clone_description": "Voice clone for Japanese storytelling",
        "defaults": {
            "model": "s2.1-pro-free",
            "speed": "0.95",
            "max_chars": "500",
            "retry_count": "3",
            "latency_mode": "normal",
            "auto_s2_cues": True,
            "s2_cue_mode": "natural",
            "exact_pause": True,
            "strict_commas": False,
            "pause_comma": "120",
            "pause_sentence": "380",
            "pause_question": "480",
            "pause_ellipsis": "700",
            "pause_paragraph": "900",
        },
    },
    "zh-TW": {
        "name": "Tiếng Trung Đài Loan",
        "cue_name": "Taiwanese Mandarin",
        "clone_title": "Taiwan Story Voice",
        "clone_description": "Voice clone for Traditional Chinese storytelling",
        "defaults": {
            "model": "s2.1-pro-free",
            "speed": "0.93",
            "max_chars": "500",
            "retry_count": "3",
            "latency_mode": "normal",
            "auto_s2_cues": True,
            "s2_cue_mode": "natural",
            "exact_pause": True,
            "strict_commas": False,
            "pause_comma": "120",
            "pause_sentence": "420",
            "pause_question": "520",
            "pause_ellipsis": "750",
            "pause_paragraph": "950",
        },
    },
    "es-MX": {
        "name": "Tiếng Tây Ban Nha Mexico",
        "cue_name": "Mexican Spanish",
        "clone_title": "Mexico Story Voice",
        "clone_description": "Voice clone for Mexican Spanish storytelling",
        "defaults": {
            "model": "s2.1-pro-free",
            "speed": "0.93",
            "max_chars": "650",
            "retry_count": "3",
            "latency_mode": "normal",
            "auto_s2_cues": True,
            "s2_cue_mode": "natural",
            "exact_pause": True,
            "strict_commas": False,
            "pause_comma": "100",
            "pause_sentence": "400",
            "pause_question": "500",
            "pause_ellipsis": "700",
            "pause_paragraph": "900",
        },
    },
}
LANGUAGE_NAME_TO_CODE = {value["name"]: code for code, value in LANGUAGES.items()}
LANGUAGE_CODE_TO_NAME = {code: value["name"] for code, value in LANGUAGES.items()}


def app_root_dir() -> Path:
    # File BAT và CapCut GUI mở chương trình với thư mục làm việc là thư mục tool hiện tại.
    return Path.cwd()


def update_env_value(env_path: Path, key: str, value: str) -> None:
    lines = env_path.read_text(encoding="utf-8-sig").splitlines() if env_path.exists() else []
    found = False
    output = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            output.append(f"{key}={value}")
            found = True
        else:
            output.append(line)
    if not found:
        output.append(f"{key}={value}")
    env_path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")



class SettingsStore:
    def __init__(self, path: Path):
        self.path = path
        self.data = {
            "version": 1,
            "last_language": "ja",
            "last_voice_by_language": {},
            "voice_languages": {},
            "voice_presets": {},
            "manual_voices": {},
        }
        self.load()

    def load(self):
        if not self.path.exists():
            return
        try:
            value = json.loads(self.path.read_text(encoding="utf-8-sig"))
            if isinstance(value, dict):
                self.data.update(value)
        except Exception:
            backup = self.path.with_suffix(".corrupt.json")
            try:
                self.path.replace(backup)
            except Exception:
                pass

    def save(self):
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    @staticmethod
    def preset_key(language_code: str, voice_key: str) -> str:
        return f"{language_code}::{voice_key or DEFAULT_VOICE_KEY}"

    def get_preset(self, language_code: str, voice_key: str):
        return self.data.setdefault("voice_presets", {}).get(
            self.preset_key(language_code, voice_key)
        )

    def set_preset(self, language_code: str, voice_key: str, preset: dict):
        self.data.setdefault("voice_presets", {})[
            self.preset_key(language_code, voice_key)
        ] = preset

    def get_voice_language(self, voice_id: str):
        value = self.data.setdefault("voice_languages", {}).get(voice_id)
        if isinstance(value, str):
            return value if value in LANGUAGES else None
        if isinstance(value, list):
            for language_code in LANGUAGES:
                if language_code in value:
                    return language_code
        return None

    def set_voice_language(self, voice_id: str, language_code):
        if language_code in LANGUAGES:
            self.data.setdefault("voice_languages", {})[voice_id] = language_code
        else:
            self.data.setdefault("voice_languages", {}).pop(voice_id, None)

    def add_manual_voice(self, voice_id: str, title: str, language_code: str):
        self.data.setdefault("manual_voices", {})[voice_id] = {
            "title": title or "Voice ID thủ công",
        }
        self.set_voice_language(voice_id, language_code)


def voice_metadata_blob(voice) -> str:
    values = [
        str(getattr(voice, "title", "") or ""),
        str(getattr(voice, "description", "") or ""),
    ]
    for field in ("tags", "languages"):
        item = getattr(voice, field, None) or []
        if isinstance(item, str):
            values.append(item)
        else:
            values.extend(str(value) for value in item)
    return " ".join(values).lower()


def infer_voice_language(voice):
    blob = voice_metadata_blob(voice)
    if re.search(r"zh[-_]?tw|taiwan|taiwanese|台灣|臺灣|繁體|華語", blob, re.I):
        return "zh-TW"
    if re.search(r"es[-_]?mx|mexico|méxico|mexican|mexicano", blob, re.I):
        return "es-MX"
    if re.search(r"\bja\b|\bjp\b|japanese|日本語|日本", blob, re.I):
        return "ja"
    if re.search(r"mandarin|chinese|中文", blob, re.I):
        return "zh-TW"
    if re.search(r"spanish|español", blob, re.I):
        return "es-MX"
    return None


def split_japanese_text(text: str, max_chars: int = 300):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks = []

    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            chunks.append(paragraph)
            continue

        sentences = [s.strip() for s in re.split(r"(?<=[。！？!?])\s*", paragraph) if s.strip()]
        if not sentences:
            sentences = [paragraph]

        current = ""
        for sentence in sentences:
            if len(sentence) > max_chars:
                if current:
                    chunks.append(current.strip())
                    current = ""
                for index in range(0, len(sentence), max_chars):
                    piece = sentence[index:index + max_chars].strip()
                    if piece:
                        chunks.append(piece)
                continue

            if not current:
                current = sentence
            elif len(current) + 1 + len(sentence) <= max_chars:
                current += " " + sentence
            else:
                chunks.append(current.strip())
                current = sentence

        if current.strip():
            chunks.append(current.strip())

    return [chunk for chunk in chunks if chunk.strip()]



def split_long_speech_unit(text: str, max_chars: int):
    """Split a speech unit without adding a pause between the pieces."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    pieces = []
    remaining = text
    while len(remaining) > max_chars:
        cut = max_chars
        candidates = [
            remaining.rfind("、", 0, max_chars + 1),
            remaining.rfind("，", 0, max_chars + 1),
            remaining.rfind(",", 0, max_chars + 1),
            remaining.rfind(" ", 0, max_chars + 1),
        ]
        best = max(candidates)
        if best >= max(20, int(max_chars * 0.45)):
            cut = best + 1
        piece = remaining[:cut].strip()
        if piece:
            pieces.append(piece)
        remaining = remaining[cut:].strip()
    if remaining:
        pieces.append(remaining)
    return pieces


def build_pause_units(
    text: str,
    max_chars: int,
    comma_ms: int,
    sentence_ms: int,
    question_ms: int,
    ellipsis_ms: int,
    paragraph_ms: int,
    strict_commas: bool,
):
    """
    Return [{text, pause_ms, reason}]. Major punctuation is split into separate
    TTS requests so the final pause can be enforced by inserting silent WAV frames.
    Commas are only split when strict_commas=True because doing so increases API
    calls and can make intonation sound more segmented.
    Manual marker supported: [[PAUSE=800]] (milliseconds).
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    units = []
    buffer = []
    i = 0
    closing_quotes = set('」』”’】）》\"\'')
    comma_chars = set('、，,；;：:')
    sentence_chars = set('。．.!')
    question_chars = set('！？?')

    def emit(pause_ms: int, reason: str):
        raw = ''.join(buffer).strip()
        buffer.clear()
        if not raw:
            if units and pause_ms > units[-1]['pause_ms']:
                units[-1]['pause_ms'] = pause_ms
                units[-1]['reason'] = reason
            return
        parts = split_long_speech_unit(raw, max_chars)
        for part_index, part in enumerate(parts):
            units.append({
                'text': part,
                'pause_ms': pause_ms if part_index == len(parts) - 1 else 0,
                'reason': reason if part_index == len(parts) - 1 else 'split',
            })

    while i < len(text):
        manual = re.match(r'\[\[\s*PAUSE\s*=\s*(\d{1,5})\s*\]\]', text[i:], flags=re.I)
        if manual:
            emit(min(int(manual.group(1)), 10000), 'manual')
            i += manual.end()
            continue

        ch = text[i]

        if ch == '\n':
            count = 1
            while i + count < len(text) and text[i + count] == '\n':
                count += 1
            # A single intentional line break gets a sentence-like pause;
            # a blank line gets the full paragraph pause.
            emit(paragraph_ms if count >= 2 else sentence_ms, 'paragraph' if count >= 2 else 'newline')
            i += count
            continue

        buffer.append(ch)

        if ch == '…':
            while i + 1 < len(text) and text[i + 1] == '…':
                i += 1
                buffer.append(text[i])
            while i + 1 < len(text) and text[i + 1] in closing_quotes:
                i += 1
                buffer.append(text[i])
            emit(ellipsis_ms, 'ellipsis')
        elif ch in question_chars:
            while i + 1 < len(text) and text[i + 1] in question_chars:
                i += 1
                buffer.append(text[i])
            while i + 1 < len(text) and text[i + 1] in closing_quotes:
                i += 1
                buffer.append(text[i])
            emit(question_ms, 'question')
        elif ch in sentence_chars:
            while i + 1 < len(text) and text[i + 1] in sentence_chars:
                i += 1
                buffer.append(text[i])
            while i + 1 < len(text) and text[i + 1] in closing_quotes:
                i += 1
                buffer.append(text[i])
            emit(sentence_ms, 'sentence')
        elif strict_commas and ch in comma_chars:
            while i + 1 < len(text) and text[i + 1] in closing_quotes:
                i += 1
                buffer.append(text[i])
            emit(comma_ms, 'comma')

        i += 1

    emit(0, 'end')
    return [u for u in units if u['text'].strip()]



def sanitize_problem_ellipsis(text: str, ellipsis_ms: int):
    """
    Remove dangerous standalone/leading ellipses before TTS.

    - 「……」 / 『……』 / 「……  -> real silence only
    - 「……ごめんなさい」      -> silence, then 「ごめんなさい」
    - ……ごめんなさい          -> silence, then ごめんなさい
    - Ellipses in the middle/end of a spoken sentence remain unchanged
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    output_lines = []
    report = []

    only_ellipsis_re = re.compile(
        r'^[「『“"\']?\s*(?:…{1,}|\.{3,}|・{3,})\s*[」』”"\']?$'
    )
    quoted_leading_re = re.compile(
        r'^([「『“"\'])\s*(?:…{1,}|\.{3,}|・{3,})\s*(.+)$'
    )
    plain_leading_re = re.compile(
        r'^(?:…{1,}|\.{3,}|・{3,})\s*(.+)$'
    )

    for line_number, line in enumerate(normalized.split("\n"), start=1):
        stripped = line.strip()
        indent = line[:len(line) - len(line.lstrip())]

        if not stripped:
            output_lines.append(line)
            continue

        if only_ellipsis_re.fullmatch(stripped):
            replacement = f"[[PAUSE={int(ellipsis_ms)}]]"
            output_lines.append(indent + replacement)
            report.append(
                f"Dòng {line_number}: {stripped} -> {replacement} "
                "(không gửi dấu ba chấm sang Fish)"
            )
            continue

        quoted = quoted_leading_re.match(stripped)
        if quoted:
            opening_quote, remaining = quoted.groups()
            replacement = (
                f"[[PAUSE={int(ellipsis_ms)}]]"
                f"{opening_quote}{remaining.lstrip()}"
            )
            output_lines.append(indent + replacement)
            report.append(
                f"Dòng {line_number}: {stripped} -> {replacement}"
            )
            continue

        plain = plain_leading_re.match(stripped)
        if plain:
            remaining = plain.group(1)
            replacement = f"[[PAUSE={int(ellipsis_ms)}]]{remaining.lstrip()}"
            output_lines.append(indent + replacement)
            report.append(
                f"Dòng {line_number}: {stripped} -> {replacement}"
            )
            continue

        output_lines.append(line)

    return "\n".join(output_lines), report


def _contains_any(text: str, patterns) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in patterns)


EMOTION_PATTERNS = {
    "ja": {
        "crying_loudly": [r"泣き叫", r"号泣", r"声を上げて泣", r"泣き崩"],
        "sobbing": [r"すすり泣", r"嗚咽", r"泣きながら", r"涙声", r"声を震わせ"],
        "screaming": [r"絶叫", r"悲鳴", r"金切り声"],
        "shouting": [r"怒鳴", r"叫び", r"大声", r"声を荒らげ", r"一喝"],
        "whispering": [r"囁", r"ささや", r"小さな声", r"声を潜め"],
        "laughing": [r"笑いながら", r"くすくす", r"苦笑", r"吹き出"],
        "sighing": [r"ため息", r"溜め息", r"深く息を吐"],
        "gasping": [r"息を呑", r"息をのん", r"はっと息"],
        "angry": [r"激怒", r"怒り", r"黙れ", r"出ていけ", r"許さない"],
        "pleading": [r"お願い", r"頼む", r"行かないで", r"許して", r"助けて"],
        "fear": [r"怖", r"恐ろ", r"怯", r"震え", r"青ざめ"],
        "sad": [r"涙", r"泣", r"悲し", r"寂し", r"ごめん", r"別れ"],
        "surprised": [r"信じられ", r"どういうこと", r"驚", r"まさか"],
    },
    "zh-TW": {
        "crying_loudly": [r"放聲大哭", r"嚎啕大哭", r"哭喊", r"崩潰大哭"],
        "sobbing": [r"哭著說", r"哽咽", r"啜泣", r"抽泣", r"聲音顫抖"],
        "screaming": [r"尖叫", r"驚叫", r"慘叫"],
        "shouting": [r"大吼", r"怒吼", r"喊道", r"咆哮", r"厲聲"],
        "whispering": [r"低聲說", r"小聲說", r"耳語", r"輕聲說"],
        "laughing": [r"笑著說", r"冷笑", r"苦笑", r"大笑"],
        "sighing": [r"嘆了一口氣", r"嘆氣", r"長嘆"],
        "gasping": [r"倒抽一口氣", r"屏住呼吸"],
        "angry": [r"憤怒", r"生氣", r"閉嘴", r"滾出去"],
        "pleading": [r"拜託", r"求你", r"不要走", r"原諒我"],
        "fear": [r"害怕", r"恐懼", r"發抖", r"救命"],
        "sad": [r"眼淚", r"哭", r"悲傷", r"難過", r"對不起"],
        "surprised": [r"不敢相信", r"怎麼可能", r"震驚", r"沒想到"],
    },
    "es-MX": {
        "crying_loudly": [r"rompió a llorar", r"estalló en llanto", r"llorando a gritos"],
        "sobbing": [r"entre lágrimas", r"voz quebrada", r"solloz", r"llorando"],
        "screaming": [r"chilló", r"gritó de terror", r"grito desgarrador"],
        "shouting": [r"gritó", r"vociferó", r"alzó la voz", r"bramó", r"rugió"],
        "whispering": [r"susurró", r"murmuró", r"en voz baja", r"bajó la voz"],
        "laughing": [r"rió", r"se rio", r"carcajada", r"risa amarga"],
        "sighing": [r"suspiró", r"soltó un suspiro"],
        "gasping": [r"jadeó", r"contuvo el aliento", r"sin aliento"],
        "angry": [r"furios", r"enojad", r"con rabia", r"cállate", r"lárgate"],
        "pleading": [r"por favor", r"te lo ruego", r"no te vayas", r"perdóname"],
        "fear": [r"miedo", r"aterrad", r"tembl", r"pálid", r"auxilio"],
        "sad": [r"lágrimas", r"llor", r"triste", r"dolor", r"lo siento"],
        "surprised": [r"no podía creer", r"cómo es posible", r"sorprendid", r"no puede ser"],
    },
}


def _is_dialogue_text(text: str, language_code: str) -> bool:
    if language_code in {"ja", "zh-TW"}:
        return bool(re.search(r'[「『“"]|[」』”"]', text))
    return bool(re.search(r'[“"«]|[”"»]', text))


def detect_following_dialogue_hint(text: str, language_code: str):
    raw = text.strip()
    if not raw or _is_dialogue_text(raw, language_code):
        return None
    patterns = EMOTION_PATTERNS[language_code]
    for effect in (
        "crying_loudly", "sobbing", "screaming", "shouting",
        "whispering", "laughing", "sighing", "gasping",
    ):
        if _contains_any(raw, patterns[effect]):
            return effect
    return None


def make_s2_cue(
    text: str,
    language_code: str,
    mode: str = "natural",
    inherited_hint=None,
) -> str:
    raw = text.strip()
    if not raw:
        return raw
    if re.match(r"^\s*\[[^\]\n]{1,240}\]", raw):
        return raw

    patterns = EMOTION_PATTERNS[language_code]
    language_name = LANGUAGES[language_code]["cue_name"]
    dialogue = _is_dialogue_text(raw, language_code)

    mode = (mode or "natural").lower()
    if mode == "strong":
        base = f"deliberate pacing, highly expressive {language_name} drama performance"
    elif mode == "drama":
        base = f"slow, expressive {language_name} drama delivery"
    else:
        base = f"natural {language_name} delivery with clear articulation"

    descriptors = [base]
    effect = inherited_hint if dialogue else None

    if dialogue:
        for candidate in (
            "crying_loudly", "sobbing", "screaming", "shouting",
            "whispering", "laughing", "sighing", "gasping",
        ):
            if _contains_any(raw, patterns[candidate]):
                effect = candidate
                break

    effect_text = {
        "crying_loudly": "crying loudly, words breaking apart with grief",
        "sobbing": "sobbing softly, tearful voice trembling",
        "screaming": "terrified, screaming in panic",
        "shouting": "angry and shouting",
        "whispering": "whispering softly and intimately",
        "laughing": "laughing naturally while speaking",
        "sighing": "sighing before speaking, emotionally tired",
        "gasping": "gasping in shock before speaking",
    }

    if effect:
        descriptors.append(effect_text[effect])
    elif _contains_any(raw, patterns["angry"]):
        descriptors.append("restrained anger" if mode == "natural" else "angry and forceful")
    elif _contains_any(raw, patterns["pleading"]):
        descriptors.append("desperate and pleading")
    elif _contains_any(raw, patterns["fear"]):
        descriptors.append("frightened and tense")
    elif _contains_any(raw, patterns["sad"]):
        descriptors.append("sad with restrained emotion")
    elif _contains_any(raw, patterns["surprised"]):
        descriptors.append("shocked and breathless")
    elif re.search(r"…{1,}|\.{3,}", raw):
        descriptors.append("hesitant with a reflective pause")

    descriptors.append(
        f"{language_name} dialogue"
        if dialogue
        else f"{language_name} audiobook narration"
    )
    return "[" + ", ".join(descriptors) + "]\n" + raw


def build_s2_requests(units, mode: str, language_code: str):
    requests = []
    pending_hint = None
    for unit in units:
        raw = unit["text"].strip()
        if _is_dialogue_text(raw, language_code):
            requests.append(
                make_s2_cue(raw, language_code, mode, pending_hint)
            )
            pending_hint = None
        else:
            requests.append(make_s2_cue(raw, language_code, mode, None))
            hint = detect_following_dialogue_hint(raw, language_code)
            if hint:
                pending_hint = hint
    return requests


def build_s2_preview(units, mode: str, language_code: str):
    tagged = []
    requests = build_s2_requests(units, mode, language_code)
    for index, tagged_text in enumerate(requests, start=1):
        tagged.append(f"--- ĐOẠN {index:04d} ---\n{tagged_text}")
    return "\n\n".join(tagged)


def _read_actual_wav_data(path: Path):
    """
    Đọc PCM theo kích thước dữ liệu THỰC của file.

    Một số WAV streaming do Fish trả về đặt nframes/data-size ở giá trị placeholder
    gần 2^31. Python wave.getnframes() khi đó cho thời lượng giả khoảng 13 giờ.
    Hàm này bỏ qua placeholder và dùng số byte thực đang có trong chunk "data".
    """
    path = Path(path)
    file_size = path.stat().st_size

    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        frame_rate = wav_file.getframerate()
        comp_type = wav_file.getcomptype()
        comp_name = wav_file.getcompname()

    data_offset = None
    data_size = None

    with path.open("rb") as stream:
        header = stream.read(12)
        if len(header) != 12 or header[:4] not in (b"RIFF", b"RF64") or header[8:12] != b"WAVE":
            raise ValueError(f"Không phải WAV hợp lệ: {path.name}")

        while stream.tell() + 8 <= file_size:
            chunk_header = stream.read(8)
            if len(chunk_header) < 8:
                break
            chunk_id, declared_size = struct.unpack("<4sI", chunk_header)
            chunk_start = stream.tell()
            available = max(0, file_size - chunk_start)

            # Fish streaming WAV có thể dùng 0x7FFFFFFF/0xFFFFFFFF làm placeholder.
            if declared_size in (0x7FFFFFFF, 0xFFFFFFFF) or declared_size > available:
                actual_size = available
            else:
                actual_size = declared_size

            if chunk_id == b"data":
                data_offset = chunk_start
                data_size = actual_size
                break

            next_pos = chunk_start + actual_size
            if declared_size not in (0x7FFFFFFF, 0xFFFFFFFF) and declared_size <= available:
                next_pos += declared_size & 1
            stream.seek(min(next_pos, file_size))

        if data_offset is None or data_size is None:
            raise ValueError(f"Không tìm thấy chunk data trong {path.name}")

        stream.seek(data_offset)
        pcm_data = stream.read(data_size)

    block_align = channels * sample_width
    if block_align <= 0 or frame_rate <= 0:
        raise ValueError(f"Thông số WAV không hợp lệ: {path.name}")

    # Bỏ byte lẻ nếu file kết thúc không đúng block.
    pcm_data = pcm_data[: len(pcm_data) - (len(pcm_data) % block_align)]
    duration = len(pcm_data) / float(block_align * frame_rate)

    return {
        "channels": channels,
        "sample_width": sample_width,
        "frame_rate": frame_rate,
        "comp_type": comp_type,
        "comp_name": comp_name,
        "pcm_data": pcm_data,
        "duration": duration,
    }


def make_silence_frames(audio_info, milliseconds: int) -> bytes:
    if milliseconds <= 0:
        return b""
    frame_count = int(audio_info["frame_rate"] * milliseconds / 1000.0)
    return b"\x00" * frame_count * audio_info["channels"] * audio_info["sample_width"]


def merge_wavs_with_pauses(input_paths, pauses_ms, output_path):
    if not input_paths:
        raise ValueError("Không có file WAV để ghép.")
    if len(input_paths) != len(pauses_ms):
        raise ValueError("Số file WAV và số khoảng nghỉ không khớp.")

    first_info = _read_actual_wav_data(Path(input_paths[0]))

    with wave.open(str(output_path), "wb") as output:
        output.setnchannels(first_info["channels"])
        output.setsampwidth(first_info["sample_width"])
        output.setframerate(first_info["frame_rate"])
        output.setcomptype(first_info["comp_type"], first_info["comp_name"])

        for wav_path, pause_ms in zip(input_paths, pauses_ms):
            info = _read_actual_wav_data(Path(wav_path))
            if (
                info["channels"] != first_info["channels"]
                or info["sample_width"] != first_info["sample_width"]
                or info["frame_rate"] != first_info["frame_rate"]
            ):
                raise ValueError(f"Thông số WAV không khớp: {Path(wav_path).name}")

            output.writeframesraw(info["pcm_data"])
            output.writeframesraw(make_silence_frames(first_info, int(pause_ms)))


def write_srt_with_pauses(units, speech_durations, output_path: Path):
    timeline = 0.0
    with output_path.open("w", encoding="utf-8") as output:
        for index, (unit, speech_duration) in enumerate(zip(units, speech_durations), start=1):
            speech_start = timeline
            speech_end = speech_start + speech_duration
            output.write(f"{index}\n")
            output.write(f"{srt_timestamp(speech_start)} --> {srt_timestamp(speech_end)}\n")
            output.write(unit["text"].strip() + "\n\n")
            timeline = speech_end + (unit["pause_ms"] / 1000.0)


def wav_duration_seconds(path: Path) -> float:
    return _read_actual_wav_data(Path(path))["duration"]


def merge_wavs(input_paths, output_path):
    merge_wavs_with_pauses(input_paths, [0] * len(input_paths), output_path)


def srt_timestamp(seconds: float) -> str:
    milliseconds_total = max(0, int(round(seconds * 1000)))
    td = timedelta(milliseconds=milliseconds_total)
    total_seconds = int(td.total_seconds())
    milliseconds = milliseconds_total % 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def write_srt(chunks, durations, output_path: Path):
    start = 0.0
    with output_path.open("w", encoding="utf-8") as output:
        for index, (text, duration) in enumerate(zip(chunks, durations), start=1):
            end = start + duration
            output.write(f"{index}\n")
            output.write(f"{srt_timestamp(start)} --> {srt_timestamp(end)}\n")
            output.write(text.strip() + "\n\n")
            start = end


def read_text_file(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        try:
            from docx import Document
        except Exception as exc:
            raise RuntimeError("Thiếu python-docx. Hãy chạy RUN_FISH_GUI_V3.bat lại.") from exc
        document = Document(str(path))
        return "\n".join(p.text for p in document.paragraphs if p.text.strip())

    if path.suffix.lower() not in SUPPORTED_TEXT_EXTS:
        raise ValueError("Chỉ hỗ trợ TXT, MD, SRT, CSV, JSON, LOG hoặc DOCX.")

    for encoding in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "big5", "cp1252"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise UnicodeError("Không đọc được bảng mã của file.")



def clone_audio_mime(path: Path) -> str:
    suffix = path.suffix.lower()
    mapping = {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".opus": "audio/opus",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac",
    }
    return mapping.get(
        suffix,
        mimetypes.guess_type(path.name)[0] or "application/octet-stream",
    )


def build_direct_clone_multipart(params: dict, upload_title: str):
    audio_path = Path(params["audio_path"])
    audio_bytes = audio_path.read_bytes()
    mime_type = clone_audio_mime(audio_path)

    parts = [
        ("type", (None, "tts")),
        ("title", (None, upload_title)),
        ("train_mode", (None, "fast")),
        ("visibility", (None, params["visibility"])),
        (
            "enhance_audio_quality",
            (None, "true" if params["enhance"] else "false"),
        ),
        ("generate_sample", (None, "false")),
    ]

    description = str(params.get("description") or "").strip()
    if description:
        parts.append(("description", (None, description)))

    transcript = str(params.get("transcript") or "").strip()
    if transcript:
        parts.append(("texts", (None, transcript)))

    # Khác SDK: có filename và MIME thật, giúp server nhận đúng loại audio.
    parts.append(
        (
            "voices",
            (
                audio_path.name,
                audio_bytes,
                mime_type,
            ),
        )
    )
    return parts, audio_bytes, mime_type


def clone_response_identifiers(response) -> dict:
    names = [
        "x-request-id",
        "request-id",
        "x-correlation-id",
        "x-trace-id",
        "traceparent",
        "cf-ray",
        "server",
        "date",
    ]
    return {
        name: response.headers.get(name)
        for name in names
        if response.headers.get(name)
    }


def safe_sdk_version() -> str:
    try:
        return importlib.metadata.version("fish-audio-sdk")
    except Exception:
        return "không xác định"



class FishStoryGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1120x900")
        self.root.minsize(1000, 820)

        self.stop_requested = False
        self.worker = None
        self.clone_worker = None
        self.voice_worker = None
        self.voice_lookup = {}
        self.all_voices = []
        self.manager_index_to_voice_id = {}
        self.store = SettingsStore(app_root_dir() / SETTINGS_FILENAME)
        self.active_language_code = self.store.data.get("last_language", "ja")
        if self.active_language_code not in LANGUAGES:
            self.active_language_code = "ja"
        self.loading_preset = False
        self.preset_after_id = None

        self.language_display = tk.StringVar(
            value=LANGUAGE_CODE_TO_NAME[self.active_language_code]
        )
        self.clone_language_display = tk.StringVar(
            value=LANGUAGE_CODE_TO_NAME[self.active_language_code]
        )
        self.manager_language_display = tk.StringVar(value="Chưa phân loại")
        self.preset_status = tk.StringVar(value="Preset: chưa nạp")

        self.source_label = tk.StringVar(value="Nguồn: dán trực tiếp hoặc kéo thả file vào khung bên dưới")
        self.output_dir = tk.StringVar(value=str(app_root_dir() / "02.OUTPUT"))
        self.reference_id = tk.StringVar()
        self.voice_display = tk.StringVar()
        self.model = tk.StringVar(value=DEFAULT_MODEL)
        self.speed = tk.StringVar(value=DEFAULT_SPEED)
        self.max_chars = tk.StringVar(value=DEFAULT_MAX_CHARS)
        self.retry_count = tk.StringVar(value=DEFAULT_RETRY)
        self.latency_mode = tk.StringVar(value="normal")
        self.auto_s2_cues = tk.BooleanVar(value=True)
        self.s2_cue_mode = tk.StringVar(value="natural")
        self.exact_pause = tk.BooleanVar(value=True)
        self.strict_commas = tk.BooleanVar(value=False)
        self.pause_comma = tk.StringVar(value="120")
        self.pause_sentence = tk.StringVar(value="380")
        self.pause_question = tk.StringVar(value="480")
        self.pause_ellipsis = tk.StringVar(value="700")
        self.pause_paragraph = tk.StringVar(value="900")
        self.status_text = tk.StringVar(value="Sẵn sàng")
        self.progress_value = tk.DoubleVar(value=0.0)
        self.char_count = tk.StringVar(value="0 ký tự")

        self.clone_audio_path = tk.StringVar()
        self.clone_title = tk.StringVar(value=LANGUAGES[self.active_language_code]["clone_title"])
        self.clone_description = tk.StringVar(value=LANGUAGES[self.active_language_code]["clone_description"])
        self.clone_visibility = tk.StringVar(value="private")
        self.clone_enhance = tk.BooleanVar(value=True)
        self.clone_status = tk.StringVar(value="Chưa clone")
        self.cloned_voice_id = tk.StringVar()

        self._build_ui()
        self._bind_preset_autosave()
        self._load_env()
        self.load_preset_for_current_voice()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(500, self.refresh_voices)

    def ui(self, function, *args, **kwargs):
        self.root.after(0, lambda: function(*args, **kwargs))

    def _load_env(self):
        env_path = app_root_dir() / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=True)
            self.reference_id.set(os.getenv("REFERENCE_ID", ""))
        else:
            self.log("Chưa thấy file .env trong thư mục cài đặt.")

    def _build_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self.notebook = notebook

        tts_tab = ttk.Frame(notebook, padding=10)
        clone_tab = ttk.Frame(notebook, padding=10)
        manager_tab = ttk.Frame(notebook, padding=10)
        notebook.add(tts_tab, text="TẠO AUDIO")
        notebook.add(clone_tab, text="CLONE GIỌNG")
        notebook.add(manager_tab, text="QUẢN LÝ GIỌNG")

        self._build_tts_tab(tts_tab)
        self._build_clone_tab(clone_tab)
        self._build_voice_manager_tab(manager_tab)

    def _build_tts_tab(self, main):
        main.columnconfigure(1, weight=1)
        row = 0

        ttk.Label(main, text="Ngôn ngữ:").grid(row=row, column=0, sticky="w", pady=4)
        language_combo = ttk.Combobox(
            main,
            textvariable=self.language_display,
            values=[LANGUAGES[code]["name"] for code in LANGUAGES],
            state="readonly",
        )
        language_combo.grid(row=row, column=1, sticky="ew", pady=4, padx=8)
        language_combo.bind("<<ComboboxSelected>>", self.on_language_selected)
        ttk.Button(
            main,
            text="Quản lý giọng",
            command=lambda: self.notebook.select(2),
        ).grid(row=row, column=2, sticky="ew", pady=4)
        row += 1

        ttk.Label(main, text="Chọn giọng:").grid(row=row, column=0, sticky="w", pady=4)
        self.voice_combo = ttk.Combobox(main, textvariable=self.voice_display, state="readonly")
        self.voice_combo.grid(row=row, column=1, sticky="ew", pady=4, padx=8)
        self.voice_combo.bind("<<ComboboxSelected>>", self.on_voice_selected)
        voice_buttons = ttk.Frame(main)
        voice_buttons.grid(row=row, column=2, sticky="ew")
        ttk.Button(voice_buttons, text="Làm mới", command=self.refresh_voices).pack(side="left")
        ttk.Button(voice_buttons, text="Clone mới", command=lambda: self.notebook.select(1)).pack(side="left", padx=(5, 0))
        row += 1

        ttk.Label(main, text="Voice ID đang dùng:").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(main, textvariable=self.reference_id, state="readonly").grid(
            row=row, column=1, sticky="ew", pady=4, padx=8
        )
        ttk.Button(main, text="Nhập ID thủ công", command=self.enter_manual_voice_id).grid(row=row, column=2, sticky="ew", pady=4)
        row += 1

        ttk.Label(main, textvariable=self.preset_status).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        ttk.Button(
            main,
            text="Lưu preset giọng",
            command=lambda: self.save_current_preset(show_message=True),
        ).grid(row=row, column=2, sticky="ew", pady=(0, 4))
        row += 1

        ttk.Label(main, text="Thư mục output:").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(main, textvariable=self.output_dir).grid(row=row, column=1, sticky="ew", pady=4, padx=8)
        ttk.Button(main, text="Chọn thư mục", command=self.browse_output).grid(row=row, column=2, sticky="ew", pady=4)
        row += 1

        ttk.Label(main, text="Model:").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(
            main,
            textvariable=self.model,
            values=["s2.1-pro-free", "s2.1-pro", "s2-pro"],
            state="readonly",
            width=24,
        ).grid(row=row, column=1, sticky="w", pady=4, padx=8)
        row += 1

        options = ttk.Frame(main)
        options.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(6, 6))
        for column in range(7):
            options.columnconfigure(column, weight=1)

        ttk.Label(options, text="Tốc độ").grid(row=0, column=0, sticky="w")
        ttk.Entry(options, textvariable=self.speed, width=10).grid(row=1, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(options, text="Ký tự tối đa / câu").grid(row=0, column=1, sticky="w")
        ttk.Entry(options, textvariable=self.max_chars, width=10).grid(row=1, column=1, sticky="ew", padx=(0, 8))
        ttk.Label(options, text="Số lần thử lại").grid(row=0, column=2, sticky="w")
        ttk.Entry(options, textvariable=self.retry_count, width=10).grid(row=1, column=2, sticky="ew", padx=(0, 8))
        ttk.Label(options, text="Chế độ API").grid(row=0, column=3, sticky="w")
        ttk.Combobox(options, textvariable=self.latency_mode, values=["normal", "balanced"], state="readonly", width=12).grid(
            row=1, column=3, sticky="ew", padx=(0, 8)
        )
        ttk.Label(options, text="normal = ưu tiên chất lượng; balanced = nhanh hơn").grid(
            row=1, column=4, columnspan=3, sticky="w"
        )
        row += 1

        s2_box = ttk.LabelFrame(main, text="CHỈ DẪN CẢM XÚC S2 TỰ ĐỘNG", padding=8)
        s2_box.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 7))
        for column in range(6):
            s2_box.columnconfigure(column, weight=1)

        ttk.Checkbutton(
            s2_box,
            text="Tự động tạo tag S2 — không sửa chữ trong kịch bản và SRT",
            variable=self.auto_s2_cues,
        ).grid(row=0, column=0, columnspan=3, sticky="w")

        ttk.Label(s2_box, text="Mức diễn:").grid(row=0, column=3, sticky="e", padx=(8, 4))
        ttk.Combobox(
            s2_box,
            textvariable=self.s2_cue_mode,
            values=["natural", "drama", "strong"],
            state="readonly",
            width=12,
        ).grid(row=0, column=4, sticky="ew", padx=(0, 6))
        ttk.Button(s2_box, text="XEM TAG TRƯỚC", command=self.preview_s2_cues).grid(
            row=0, column=5, sticky="ew"
        )
        ttk.Label(
            s2_box,
            text="natural = nhẹ; drama = rõ cảm xúc; strong = diễn mạnh. "
                 "Tag chỉ được gửi cho Fish, phụ đề vẫn giữ nguyên văn.",
        ).grid(row=1, column=0, columnspan=6, sticky="w", pady=(5, 0))
        row += 1

        pause_box = ttk.LabelFrame(main, text="NGẮT NGHỈ CHÍNH XÁC (mili-giây)", padding=8)
        pause_box.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 7))
        for column in range(7):
            pause_box.columnconfigure(column, weight=1)

        ttk.Checkbutton(pause_box, text="Bật chèn im lặng thật", variable=self.exact_pause).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(
            pause_box,
            text="Ép dừng cả dấu phẩy (tốn nhiều lượt API, có thể hơi rời câu)",
            variable=self.strict_commas,
        ).grid(row=0, column=2, columnspan=5, sticky="w")

        labels = [
            ("Dấu phẩy", self.pause_comma),
            ("Dấu chấm", self.pause_sentence),
            ("? / !", self.pause_question),
            ("Dấu …", self.pause_ellipsis),
            ("Xuống đoạn", self.pause_paragraph),
        ]
        for index, (label, variable) in enumerate(labels):
            ttk.Label(pause_box, text=label).grid(row=1, column=index, sticky="w", pady=(5, 0))
            ttk.Entry(pause_box, textvariable=variable, width=9).grid(row=2, column=index, sticky="ew", padx=(0, 7))
        ttk.Button(pause_box, text="Preset tự nhiên", command=lambda: self.apply_pause_preset("natural")).grid(row=2, column=5, sticky="ew", padx=3)
        ttk.Button(pause_box, text="Preset drama", command=lambda: self.apply_pause_preset("drama")).grid(row=2, column=6, sticky="ew", padx=3)
        ttk.Label(
            pause_box,
            text="Chèn nghỉ thủ công trong kịch bản bằng [[PAUSE=800]].",
        ).grid(row=3, column=0, columnspan=7, sticky="w", pady=(5, 0))
        row += 1

        ttk.Separator(main).grid(row=row, column=0, columnspan=3, sticky="ew", pady=4)
        row += 1

        header = ttk.Frame(main)
        header.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(2, 4))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="DÁN KỊCH BẢN VÀO ĐÂY", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.char_count).grid(row=0, column=1, sticky="e")
        row += 1

        ttk.Label(main, textvariable=self.source_label).grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 4))
        row += 1

        script_frame = ttk.Frame(main)
        script_frame.grid(row=row, column=0, columnspan=3, sticky="nsew")
        script_frame.columnconfigure(0, weight=1)
        script_frame.rowconfigure(0, weight=1)

        script_scrollbar = ttk.Scrollbar(script_frame, orient="vertical")
        script_scrollbar.grid(row=0, column=1, sticky="ns")

        self.script_text = tk.Text(
            script_frame,
            height=18,
            wrap="word",
            undo=True,
            yscrollcommand=script_scrollbar.set,
        )
        self.script_text.grid(row=0, column=0, sticky="nsew")
        script_scrollbar.configure(command=self.script_text.yview)

        self.script_text.bind("<<Modified>>", self.on_text_modified)
        main.rowconfigure(row, weight=1)
        self._enable_drag_drop()
        row += 1

        input_buttons = ttk.Frame(main)
        input_buttons.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(5, 8))
        ttk.Button(input_buttons, text="DÁN TỪ CLIPBOARD", command=self.paste_from_clipboard).pack(side="left")
        ttk.Button(input_buttons, text="MỞ FILE", command=self.open_script_file).pack(side="left", padx=6)
        ttk.Button(input_buttons, text="XÓA NỘI DUNG", command=self.clear_script).pack(side="left")
        if HAS_DND:
            ttk.Label(input_buttons, text="Có thể kéo thả TXT/DOCX trực tiếp vào khung.").pack(side="left", padx=12)
        else:
            ttk.Label(input_buttons, text="Kéo thả chưa bật; dùng Dán hoặc Mở file.").pack(side="left", padx=12)
        row += 1

        buttons = ttk.Frame(main)
        buttons.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        ttk.Button(buttons, text="TẠO AUDIO", command=self.start_generate).pack(side="left")
        ttk.Button(buttons, text="DỪNG", command=self.request_stop).pack(side="left", padx=8)
        ttk.Button(buttons, text="MỞ OUTPUT", command=self.open_output).pack(side="left")
        ttk.Button(buttons, text="MỞ .ENV", command=self.open_env).pack(side="left", padx=8)
        row += 1

        ttk.Label(main, textvariable=self.status_text).grid(row=row, column=0, columnspan=3, sticky="w", pady=2)
        row += 1
        ttk.Progressbar(main, variable=self.progress_value, maximum=100).grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=(0, 8)
        )
        row += 1

        ttk.Label(main, text="Log:").grid(row=row, column=0, sticky="w")
        row += 1
        self.log_box = tk.Text(main, height=8, wrap="word")
        self.log_box.grid(row=row, column=0, columnspan=3, sticky="nsew")
        main.rowconfigure(row, weight=1)
        self.log("Ứng dụng đã sẵn sàng.")

    def _build_clone_tab(self, main):
        main.columnconfigure(1, weight=1)
        row = 0

        info = (
            "Dùng giọng bạn sở hữu hoặc có quyền sử dụng. Audio nên sạch, chỉ một người nói, "
            "không nhạc nền. Khuyến nghị 10–30 giây; transcript nên khớp chính xác."
        )
        ttk.Label(main, text=info, wraplength=900, justify="left").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 10)
        )
        row += 1

        ttk.Label(main, text="Ngôn ngữ của giọng:").grid(
            row=row, column=0, sticky="w", pady=4
        )
        clone_language_combo = ttk.Combobox(
            main,
            textvariable=self.clone_language_display,
            values=[LANGUAGES[code]["name"] for code in LANGUAGES],
            state="readonly",
        )
        clone_language_combo.grid(row=row, column=1, sticky="ew", pady=4, padx=8)
        clone_language_combo.bind(
            "<<ComboboxSelected>>", self.on_clone_language_selected
        )
        row += 1

        ttk.Label(main, text="Audio mẫu:").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(main, textvariable=self.clone_audio_path).grid(row=row, column=1, sticky="ew", pady=4, padx=8)
        audio_buttons = ttk.Frame(main)
        audio_buttons.grid(row=row, column=2, sticky="ew")
        ttk.Button(audio_buttons, text="Chọn audio", command=self.browse_clone_audio).pack(side="left")
        ttk.Button(audio_buttons, text="Nghe", command=self.play_clone_audio).pack(side="left", padx=(5, 0))
        row += 1

        ttk.Label(main, text="Tên giọng:").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(main, textvariable=self.clone_title).grid(row=row, column=1, sticky="ew", pady=4, padx=8)
        row += 1

        ttk.Label(main, text="Mô tả:").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(main, textvariable=self.clone_description).grid(row=row, column=1, sticky="ew", pady=4, padx=8)
        row += 1

        ttk.Label(main, text="Quyền riêng tư:").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Combobox(
            main,
            textvariable=self.clone_visibility,
            values=["private", "unlist", "public"],
            state="readonly",
            width=18,
        ).grid(row=row, column=1, sticky="w", pady=4, padx=8)
        ttk.Checkbutton(main, text="Lọc nhiễu / chuẩn hóa audio", variable=self.clone_enhance).grid(
            row=row, column=2, sticky="w"
        )
        row += 1

        ttk.Label(main, text="Transcript chính xác của audio mẫu:").grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(10, 3)
        )
        row += 1
        self.clone_transcript = tk.Text(main, height=11, wrap="word")
        self.clone_transcript.grid(row=row, column=0, columnspan=3, sticky="nsew")
        main.rowconfigure(row, weight=1)
        row += 1

        clone_buttons = ttk.Frame(main)
        clone_buttons.grid(row=row, column=0, columnspan=3, sticky="ew", pady=8)
        self.clone_button = ttk.Button(clone_buttons, text="CLONE GIỌNG", command=self.start_clone_voice)
        self.clone_button.pack(side="left")
        ttk.Button(clone_buttons, text="DÙNG GIỌNG NÀY", command=self.use_cloned_voice).pack(side="left", padx=8)
        ttk.Button(clone_buttons, text="SAO CHÉP VOICE ID", command=self.copy_voice_id).pack(side="left")
        row += 1

        ttk.Label(main, text="Voice ID vừa tạo:").grid(row=row, column=0, sticky="w", pady=4)
        ttk.Entry(main, textvariable=self.cloned_voice_id, state="readonly").grid(
            row=row, column=1, columnspan=2, sticky="ew", pady=4, padx=8
        )
        row += 1

        ttk.Label(main, textvariable=self.clone_status).grid(row=row, column=0, columnspan=3, sticky="w", pady=(4, 6))
        row += 1
        ttk.Label(main, text="Log clone:").grid(row=row, column=0, sticky="w")
        row += 1
        self.clone_log_box = tk.Text(main, height=10, wrap="word")
        self.clone_log_box.grid(row=row, column=0, columnspan=3, sticky="nsew")
        main.rowconfigure(row, weight=1)
        self.clone_log("Sẵn sàng clone giọng.")

    def _build_voice_manager_tab(self, main):
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, weight=0)
        main.rowconfigure(1, weight=1)

        ttk.Label(
            main,
            text=(
                "Mỗi Voice ID chỉ thuộc một ngôn ngữ. "
                "Giọng chưa phân loại sẽ không xuất hiện trong tab TẠO AUDIO."
            ),
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        list_frame = ttk.Frame(main)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        self.manager_listbox = tk.Listbox(
            list_frame,
            exportselection=False,
            font=("Segoe UI", 10),
        )
        self.manager_listbox.grid(row=0, column=0, sticky="nsew")
        self.manager_listbox.bind(
            "<<ListboxSelect>>", self.on_manager_voice_selected
        )
        manager_scroll = ttk.Scrollbar(
            list_frame, orient="vertical", command=self.manager_listbox.yview
        )
        manager_scroll.grid(row=0, column=1, sticky="ns")
        self.manager_listbox.configure(yscrollcommand=manager_scroll.set)

        control = ttk.LabelFrame(main, text="Gán ngôn ngữ", padding=10)
        control.grid(row=1, column=1, sticky="ns")

        ttk.Label(control, text="Ngôn ngữ duy nhất:").grid(
            row=0, column=0, sticky="w", pady=(0, 5)
        )
        ttk.Combobox(
            control,
            textvariable=self.manager_language_display,
            values=[
                "Chưa phân loại",
                *[LANGUAGES[code]["name"] for code in LANGUAGES],
            ],
            state="readonly",
            width=30,
        ).grid(row=1, column=0, sticky="ew", pady=5)

        ttk.Button(
            control,
            text="LƯU NGÔN NGỮ",
            command=self.save_voice_assignment,
        ).grid(row=2, column=0, sticky="ew", pady=(12, 5))
        ttk.Button(
            control,
            text="ĐƯA VỀ CHƯA PHÂN LOẠI",
            command=self.clear_voice_assignment,
        ).grid(row=3, column=0, sticky="ew", pady=5)
        ttk.Button(
            control,
            text="LÀM MỚI TỪ FISH",
            command=self.refresh_voices,
        ).grid(row=4, column=0, sticky="ew", pady=5)

    def current_voice_key(self):
        return self.reference_id.get().strip() or DEFAULT_VOICE_KEY

    def collect_current_preset(self):
        return {
            "model": self.model.get().strip() or DEFAULT_MODEL,
            "speed": self.speed.get().strip(),
            "max_chars": self.max_chars.get().strip(),
            "retry_count": self.retry_count.get().strip(),
            "latency_mode": self.latency_mode.get().strip() or "normal",
            "auto_s2_cues": bool(self.auto_s2_cues.get()),
            "s2_cue_mode": self.s2_cue_mode.get().strip() or "natural",
            "exact_pause": bool(self.exact_pause.get()),
            "strict_commas": bool(self.strict_commas.get()),
            "pause_comma": self.pause_comma.get().strip(),
            "pause_sentence": self.pause_sentence.get().strip(),
            "pause_question": self.pause_question.get().strip(),
            "pause_ellipsis": self.pause_ellipsis.get().strip(),
            "pause_paragraph": self.pause_paragraph.get().strip(),
        }

    def apply_preset_data(self, preset):
        self.loading_preset = True
        try:
            self.model.set(str(preset.get("model", DEFAULT_MODEL)))
            self.speed.set(str(preset.get("speed", DEFAULT_SPEED)))
            self.max_chars.set(str(preset.get("max_chars", DEFAULT_MAX_CHARS)))
            self.retry_count.set(str(preset.get("retry_count", DEFAULT_RETRY)))
            self.latency_mode.set(str(preset.get("latency_mode", "normal")))
            self.auto_s2_cues.set(bool(preset.get("auto_s2_cues", True)))
            self.s2_cue_mode.set(str(preset.get("s2_cue_mode", "natural")))
            self.exact_pause.set(bool(preset.get("exact_pause", True)))
            self.strict_commas.set(bool(preset.get("strict_commas", False)))
            self.pause_comma.set(str(preset.get("pause_comma", "120")))
            self.pause_sentence.set(str(preset.get("pause_sentence", "380")))
            self.pause_question.set(str(preset.get("pause_question", "480")))
            self.pause_ellipsis.set(str(preset.get("pause_ellipsis", "700")))
            self.pause_paragraph.set(str(preset.get("pause_paragraph", "900")))
        finally:
            self.loading_preset = False

    def load_preset_for_current_voice(self):
        preset = self.store.get_preset(
            self.active_language_code,
            self.current_voice_key(),
        )
        if preset:
            self.apply_preset_data(preset)
            self.preset_status.set("Preset: đã nạp lần dùng trước của giọng này")
        else:
            self.apply_preset_data(
                LANGUAGES[self.active_language_code]["defaults"]
            )
            self.preset_status.set("Preset: mặc định mới của ngôn ngữ")

    def save_current_preset(self, show_message=False):
        if self.loading_preset:
            return
        self.store.set_preset(
            self.active_language_code,
            self.current_voice_key(),
            self.collect_current_preset(),
        )
        self.store.data["last_language"] = self.active_language_code
        self.store.data.setdefault("last_voice_by_language", {})[
            self.active_language_code
        ] = self.current_voice_key()
        self.store.save()
        self.preset_status.set("Preset: đã lưu riêng cho giọng này")
        if show_message:
            messagebox.showinfo(
                APP_TITLE,
                "Đã lưu preset riêng cho ngôn ngữ và giọng đang chọn.",
            )

    def _bind_preset_autosave(self):
        variables = [
            self.model, self.speed, self.max_chars, self.retry_count,
            self.latency_mode, self.auto_s2_cues, self.s2_cue_mode,
            self.exact_pause, self.strict_commas, self.pause_comma,
            self.pause_sentence, self.pause_question, self.pause_ellipsis,
            self.pause_paragraph,
        ]
        for variable in variables:
            variable.trace_add("write", self.schedule_preset_save)

    def schedule_preset_save(self, *_):
        if self.loading_preset:
            return
        if self.preset_after_id:
            try:
                self.root.after_cancel(self.preset_after_id)
            except Exception:
                pass
        self.preset_after_id = self.root.after(
            700, self._autosave_preset
        )

    def _autosave_preset(self):
        self.preset_after_id = None
        try:
            self.save_current_preset(show_message=False)
        except Exception:
            pass

    def on_close(self):
        try:
            self.save_current_preset(show_message=False)
        except Exception:
            pass
        self.root.destroy()

    def on_language_selected(self, _event=None):
        self.save_current_preset(show_message=False)
        language_code = LANGUAGE_NAME_TO_CODE.get(
            self.language_display.get(),
            "ja",
        )
        self.active_language_code = language_code
        self.store.data["last_language"] = language_code
        self.store.save()
        self.populate_voice_combo(select_saved=True)

    def on_clone_language_selected(self, _event=None):
        language_code = LANGUAGE_NAME_TO_CODE.get(
            self.clone_language_display.get(),
            self.active_language_code,
        )
        self.clone_title.set(LANGUAGES[language_code]["clone_title"])
        self.clone_description.set(
            LANGUAGES[language_code]["clone_description"]
        )

    def populate_voice_combo(self, select_saved=True):
        lookup = {DEFAULT_VOICE_LABEL: ""}
        displays = [DEFAULT_VOICE_LABEL]

        for voice in self.all_voices:
            voice_id = str(
                getattr(voice, "id", "")
                or getattr(voice, "_id", "")
            )
            if not voice_id:
                continue
            if self.store.get_voice_language(voice_id) != self.active_language_code:
                continue
            title = str(getattr(voice, "title", "Không tên"))
            display = f"{title}  —  {voice_id[:10]}…"
            base = display
            suffix = 2
            while display in lookup:
                display = f"{base} ({suffix})"
                suffix += 1
            lookup[display] = voice_id
            displays.append(display)

        for voice_id, info in self.store.data.setdefault(
            "manual_voices", {}
        ).items():
            if self.store.get_voice_language(voice_id) != self.active_language_code:
                continue
            if voice_id in lookup.values():
                continue
            title = str(info.get("title") or "Voice ID thủ công")
            display = f"[Thủ công] {title}  —  {voice_id[:10]}…"
            lookup[display] = voice_id
            displays.append(display)

        self.voice_lookup = lookup
        self.voice_combo.configure(values=displays)

        desired_key = DEFAULT_VOICE_KEY
        if select_saved:
            desired_key = self.store.data.setdefault(
                "last_voice_by_language", {}
            ).get(self.active_language_code, DEFAULT_VOICE_KEY)

        selected_display = DEFAULT_VOICE_LABEL
        if desired_key != DEFAULT_VOICE_KEY:
            selected_display = next(
                (
                    display
                    for display, voice_id in lookup.items()
                    if voice_id == desired_key
                ),
                DEFAULT_VOICE_LABEL,
            )

        self.voice_display.set(selected_display)
        selected_id = lookup.get(selected_display, "")
        self.reference_id.set(selected_id)
        update_env_value(
            app_root_dir() / ".env",
            "REFERENCE_ID",
            selected_id,
        )
        self.load_preset_for_current_voice()

    def populate_manager_list(self):
        self.manager_listbox.delete(0, "end")
        self.manager_index_to_voice_id = {}
        row = 0
        seen = set()

        for voice in self.all_voices:
            voice_id = str(
                getattr(voice, "id", "")
                or getattr(voice, "_id", "")
            )
            if not voice_id:
                continue
            title = str(getattr(voice, "title", "Không tên"))
            assigned = self.store.get_voice_language(voice_id)
            language_name = (
                LANGUAGE_CODE_TO_NAME[assigned]
                if assigned
                else "Chưa phân loại"
            )
            self.manager_listbox.insert(
                "end",
                f"{title}  —  {voice_id[:12]}…   [{language_name}]",
            )
            self.manager_index_to_voice_id[row] = voice_id
            seen.add(voice_id)
            row += 1

        for voice_id, info in self.store.data.setdefault(
            "manual_voices", {}
        ).items():
            if voice_id in seen:
                continue
            title = str(info.get("title") or "Voice ID thủ công")
            assigned = self.store.get_voice_language(voice_id)
            language_name = (
                LANGUAGE_CODE_TO_NAME[assigned]
                if assigned
                else "Chưa phân loại"
            )
            self.manager_listbox.insert(
                "end",
                f"[Thủ công] {title}  —  {voice_id[:12]}…   [{language_name}]",
            )
            self.manager_index_to_voice_id[row] = voice_id
            row += 1

    def selected_manager_voice_id(self):
        selection = self.manager_listbox.curselection()
        if not selection:
            return None
        return self.manager_index_to_voice_id.get(selection[0])

    def on_manager_voice_selected(self, _event=None):
        voice_id = self.selected_manager_voice_id()
        language_code = (
            self.store.get_voice_language(voice_id)
            if voice_id
            else None
        )
        self.manager_language_display.set(
            LANGUAGE_CODE_TO_NAME[language_code]
            if language_code
            else "Chưa phân loại"
        )

    def save_voice_assignment(self):
        voice_id = self.selected_manager_voice_id()
        if not voice_id:
            messagebox.showwarning(APP_TITLE, "Hãy chọn một giọng.")
            return
        language_code = LANGUAGE_NAME_TO_CODE.get(
            self.manager_language_display.get()
        )
        self.store.set_voice_language(voice_id, language_code)
        self.store.save()
        self.populate_manager_list()
        self.populate_voice_combo(select_saved=True)

    def clear_voice_assignment(self):
        voice_id = self.selected_manager_voice_id()
        if not voice_id:
            return
        self.store.set_voice_language(voice_id, None)
        self.store.save()
        self.manager_language_display.set("Chưa phân loại")
        self.populate_manager_list()
        self.populate_voice_combo(select_saved=True)

    def _enable_drag_drop(self):
        if not HAS_DND:
            return
        try:
            self.script_text.drop_target_register(DND_FILES, DND_TEXT)
            self.script_text.dnd_bind("<<Drop>>", self.handle_drop)
        except Exception as exc:
            self.log(f"Không bật được kéo thả: {exc}")

    def handle_drop(self, event):
        data = event.data.strip()
        try:
            paths = list(self.root.tk.splitlist(data))
        except Exception:
            paths = [data]

        existing = [Path(p) for p in paths if Path(p).exists()]
        if existing:
            self.load_script_path(existing[0])
        else:
            self.script_text.insert("insert", data)
            self.source_label.set("Nguồn: văn bản kéo thả trực tiếp")
            self.update_char_count()
        return event.action

    def log(self, message: str):
        def append():
            stamp = time.strftime("%H:%M:%S")
            self.log_box.insert("end", f"[{stamp}] {message}\n")
            self.log_box.see("end")
        self.ui(append)

    def clone_log(self, message: str):
        def append():
            stamp = time.strftime("%H:%M:%S")
            self.clone_log_box.insert("end", f"[{stamp}] {message}\n")
            self.clone_log_box.see("end")
        self.ui(append)

    def on_text_modified(self, _event=None):
        if self.script_text.edit_modified():
            self.update_char_count()
            self.script_text.edit_modified(False)

    def update_char_count(self):
        count = len(self.script_text.get("1.0", "end-1c"))
        self.char_count.set(f"{count:,} ký tự")

    def paste_from_clipboard(self):
        try:
            content = self.root.clipboard_get()
        except Exception:
            messagebox.showwarning(APP_TITLE, "Clipboard không có văn bản.")
            return
        self.script_text.delete("1.0", "end")
        self.script_text.insert("1.0", content)
        self.source_label.set("Nguồn: dán từ clipboard")
        self.update_char_count()

    def clear_script(self):
        if self.script_text.get("1.0", "end-1c").strip() and not messagebox.askyesno(APP_TITLE, "Xóa toàn bộ kịch bản?"):
            return
        self.script_text.delete("1.0", "end")
        self.source_label.set("Nguồn: dán trực tiếp hoặc kéo thả file vào khung bên dưới")
        self.update_char_count()

    def open_script_file(self):
        path = filedialog.askopenfilename(
            filetypes=[
                ("Script", "*.txt *.md *.docx *.srt *.csv *.json *.log"),
                ("All files", "*.*"),
            ]
        )
        if path:
            self.load_script_path(Path(path))

    def load_script_path(self, path: Path):
        try:
            content = read_text_file(path)
            self.script_text.delete("1.0", "end")
            self.script_text.insert("1.0", content)
            self.source_label.set(f"Nguồn: {path}")
            self.update_char_count()
            self.log(f"Đã nạp kịch bản: {path}")
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Không đọc được file:\n{exc}")

    def apply_pause_preset(self, preset: str):
        if preset == "drama":
            values = (150, 480, 620, 900, 1200)
        else:
            values = (100, 320, 420, 600, 800)
        for variable, value in zip(
            (self.pause_comma, self.pause_sentence, self.pause_question, self.pause_ellipsis, self.pause_paragraph),
            values,
        ):
            variable.set(str(value))
        self.log(f"Đã áp dụng preset ngắt nghỉ: {preset}")

    def browse_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output_dir.set(path)

    def browse_clone_audio(self):
        path = filedialog.askopenfilename(filetypes=SUPPORTED_AUDIO)
        if path:
            self.clone_audio_path.set(path)
            self.clone_log(f"Đã chọn audio: {path}")

    def play_clone_audio(self):
        path = Path(self.clone_audio_path.get().strip())
        if not path.exists():
            messagebox.showwarning(APP_TITLE, "Chưa chọn audio mẫu hợp lệ.")
            return
        try:
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror(APP_TITLE, f"Không mở được audio:\n{exc}")

    def refresh_voices(self):
        if self.voice_worker and self.voice_worker.is_alive():
            return
        self.status_text.set("Đang tải danh sách giọng...")
        self.voice_worker = threading.Thread(target=self._run_refresh_voices, daemon=True)
        self.voice_worker.start()

    def _run_refresh_voices(self):
        try:
            load_dotenv(app_root_dir() / ".env", override=True)
            if not os.getenv("FISH_API_KEY"):
                raise RuntimeError("Chưa có FISH_API_KEY trong file .env")

            client = FishAudio()
            voices = []
            page = 1
            while page <= 10:
                result = client.voices.list(
                    page_size=100,
                    page_number=page,
                    self_only=True,
                    sort_by="created_at",
                )
                voices.extend(list(getattr(result, "items", []) or []))
                if not getattr(result, "has_more", False):
                    break
                page += 1

            changed = False
            for voice in voices:
                voice_id = str(
                    getattr(voice, "id", "")
                    or getattr(voice, "_id", "")
                )
                if not voice_id:
                    continue
                if self.store.get_voice_language(voice_id) is None:
                    inferred = infer_voice_language(voice)
                    if inferred:
                        self.store.set_voice_language(voice_id, inferred)
                        changed = True
            if changed:
                self.store.save()

            self.all_voices = voices
            self.ui(self._finish_voice_refresh)
        except Exception as exc:
            self.ui(self.status_text.set, "Không tải được danh sách giọng")
            self.log(f"Lỗi tải danh sách giọng: {exc}")

    def _finish_voice_refresh(self):
        self.populate_voice_combo(select_saved=True)
        self.populate_manager_list()
        assigned_count = sum(
            1
            for voice in self.all_voices
            if self.store.get_voice_language(
                str(
                    getattr(voice, "id", "")
                    or getattr(voice, "_id", "")
                )
            )
            == self.active_language_code
        )
        self.status_text.set(
            f"Đã tải {len(self.all_voices)} giọng; "
            f"{assigned_count} giọng thuộc "
            f"{LANGUAGE_CODE_TO_NAME[self.active_language_code]}"
        )
        self.log(
            f"Đã tải {len(self.all_voices)} giọng từ Fish. "
            "Danh sách TTS đang lọc theo ngôn ngữ."
        )

    def on_voice_selected(self, _event=None):
        self.save_current_preset(show_message=False)
        display = self.voice_display.get()
        voice_id = self.voice_lookup.get(display, "")

        self.reference_id.set(voice_id)
        update_env_value(
            app_root_dir() / ".env",
            "REFERENCE_ID",
            voice_id,
        )
        self.store.data.setdefault("last_voice_by_language", {})[
            self.active_language_code
        ] = voice_id or DEFAULT_VOICE_KEY
        self.store.save()
        self.load_preset_for_current_voice()

        if voice_id:
            self.log(f"Đã chọn giọng: {display}")
        else:
            self.log(
                "Đã chọn giọng mặc định Fish. "
                "Tool sẽ không gửi reference_id."
            )

    def enter_manual_voice_id(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Nhập Voice ID")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("560x180")
        value = tk.StringVar(value=self.reference_id.get())
        title = tk.StringVar(value="Voice ID thủ công")

        ttk.Label(dialog, text="Tên dễ nhớ:").pack(
            anchor="w", padx=12, pady=(12, 4)
        )
        ttk.Entry(dialog, textvariable=title).pack(fill="x", padx=12)
        ttk.Label(dialog, text="Voice ID:").pack(
            anchor="w", padx=12, pady=(8, 4)
        )
        entry = ttk.Entry(dialog, textvariable=value)
        entry.pack(fill="x", padx=12)
        entry.focus_set()

        def save_id():
            voice_id = value.get().strip()
            if not voice_id:
                return
            self.save_current_preset(show_message=False)
            self.store.add_manual_voice(
                voice_id,
                title.get().strip(),
                self.active_language_code,
            )
            self.store.data.setdefault("last_voice_by_language", {})[
                self.active_language_code
            ] = voice_id
            self.store.save()
            self.populate_voice_combo(select_saved=True)
            self.populate_manager_list()
            dialog.destroy()

        ttk.Button(dialog, text="Lưu", command=save_id).pack(
            anchor="e", padx=12, pady=10
        )

    def open_output(self):
        output = Path(self.output_dir.get().strip())
        output.mkdir(parents=True, exist_ok=True)
        os.startfile(str(output))

    def open_env(self):
        env_path = app_root_dir() / ".env"
        if not env_path.exists():
            env_path.write_text("FISH_API_KEY=\nREFERENCE_ID=\n", encoding="utf-8")
        os.startfile(str(env_path))

    def preview_s2_cues(self):
        text = self.script_text.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning(APP_TITLE, "Hãy dán kịch bản trước khi xem tag S2.")
            return

        try:
            max_chars = int(self.max_chars.get().strip())
            pause_values = {
                "comma_ms": int(self.pause_comma.get().strip()),
                "sentence_ms": int(self.pause_sentence.get().strip()),
                "question_ms": int(self.pause_question.get().strip()),
                "ellipsis_ms": int(self.pause_ellipsis.get().strip()),
                "paragraph_ms": int(self.pause_paragraph.get().strip()),
            }
        except ValueError:
            messagebox.showwarning(APP_TITLE, "Thiết lập ký tự hoặc ngắt nghỉ chưa hợp lệ.")
            return

        cleaned_text, cleanup_report = sanitize_problem_ellipsis(
            text, pause_values["ellipsis_ms"]
        )
        units = build_pause_units(
            cleaned_text,
            max_chars,
            pause_values["comma_ms"],
            pause_values["sentence_ms"],
            pause_values["question_ms"],
            pause_values["ellipsis_ms"],
            pause_values["paragraph_ms"],
            bool(self.strict_commas.get()),
        )
        if not units:
            messagebox.showwarning(APP_TITLE, "Không tạo được bản xem trước.")
            return

        preview = tk.Toplevel(self.root)
        preview.title("Xem trước chỉ dẫn S2")
        preview.geometry("900x680")
        preview.transient(self.root)

        frame = ttk.Frame(preview, padding=10)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        ttk.Label(
            frame,
            text=(
                f"Chế độ: {self.s2_cue_mode.get()} — {len(units)} đoạn; "
                f"đã xử lý {len(cleanup_report)} dòng dấu ba chấm nguy hiểm. "
                "Đây là bản Fish nhận; SRT không chứa tag."
            ),
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        text_box = tk.Text(frame, wrap="word")
        text_box.grid(row=1, column=0, sticky="nsew")
        text_box.insert("1.0", build_s2_preview(units, self.s2_cue_mode.get(), self.active_language_code))
        text_box.configure(state="disabled")

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, sticky="e", pady=(7, 0))

        def copy_all():
            preview.clipboard_clear()
            preview.clipboard_append(build_s2_preview(units, self.s2_cue_mode.get(), self.active_language_code))
            messagebox.showinfo(APP_TITLE, "Đã sao chép bản gắn tag S2.")

        ttk.Button(buttons, text="SAO CHÉP", command=copy_all).pack(side="left")
        ttk.Button(buttons, text="ĐÓNG", command=preview.destroy).pack(side="left", padx=(8, 0))

    def validate_tts_inputs(self):
        text = self.script_text.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning(APP_TITLE, "Hãy dán hoặc nạp kịch bản vào khung lớn.")
            return None

        reference_id = self.reference_id.get().strip()

        try:
            speed = float(self.speed.get().strip())
            if not 0.5 <= speed <= 2.0:
                raise ValueError
        except ValueError:
            messagebox.showwarning(APP_TITLE, "Tốc độ phải nằm trong khoảng 0.5–2.0.")
            return None

        try:
            max_chars = int(self.max_chars.get().strip())
            if max_chars < 50:
                raise ValueError
        except ValueError:
            messagebox.showwarning(APP_TITLE, "Ký tự / đoạn không hợp lệ.")
            return None

        try:
            retry_count = int(self.retry_count.get().strip())
            if retry_count < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning(APP_TITLE, "Số lần thử lại không hợp lệ.")
            return None

        try:
            pause_values = {
                "comma_ms": int(self.pause_comma.get().strip()),
                "sentence_ms": int(self.pause_sentence.get().strip()),
                "question_ms": int(self.pause_question.get().strip()),
                "ellipsis_ms": int(self.pause_ellipsis.get().strip()),
                "paragraph_ms": int(self.pause_paragraph.get().strip()),
            }
            if any(value < 0 or value > 10000 for value in pause_values.values()):
                raise ValueError
        except ValueError:
            messagebox.showwarning(APP_TITLE, "Thời gian ngắt phải là số từ 0 đến 10000 mili-giây.")
            return None

        output = Path(self.output_dir.get().strip())
        output.mkdir(parents=True, exist_ok=True)
        return {
            "text": text,
            "language_code": self.active_language_code,
            "language_name": LANGUAGE_CODE_TO_NAME[self.active_language_code],
            "reference_id": reference_id,
            "voice_display": self.voice_display.get().strip() or DEFAULT_VOICE_LABEL,
            "speed": speed,
            "max_chars": max_chars,
            "retry_count": retry_count,
            "model": self.model.get().strip() or DEFAULT_MODEL,
            "latency": self.latency_mode.get().strip() or "normal",
            "auto_s2_cues": bool(self.auto_s2_cues.get()),
            "s2_cue_mode": self.s2_cue_mode.get().strip() or "natural",
            "exact_pause": bool(self.exact_pause.get()),
            "strict_commas": bool(self.strict_commas.get()),
            **pause_values,
            "out_dir": output,
        }

    def start_generate(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_TITLE, "Đang có tiến trình tạo audio.")
            return
        params = self.validate_tts_inputs()
        if not params:
            return
        self.stop_requested = False
        self.progress_value.set(0)
        self.status_text.set("Đang chuẩn bị...")
        self.worker = threading.Thread(target=self._run_generate, args=(params,), daemon=True)
        self.worker.start()

    def request_stop(self):
        self.stop_requested = True
        self.log("Đã gửi yêu cầu dừng; tiến trình sẽ dừng sau đoạn hiện tại.")
        self.status_text.set("Đang chờ dừng...")

    def _run_generate(self, params):
        try:
            load_dotenv(app_root_dir() / ".env", override=True)
            if not os.getenv("FISH_API_KEY"):
                raise RuntimeError("Chưa có FISH_API_KEY trong file .env")

            client = FishAudio()
            cleaned_text, ellipsis_cleanup_report = sanitize_problem_ellipsis(
                params["text"], params["ellipsis_ms"]
            )
            units = build_pause_units(
                cleaned_text,
                params["max_chars"],
                params["comma_ms"],
                params["sentence_ms"],
                params["question_ms"],
                params["ellipsis_ms"],
                params["paragraph_ms"],
                params["strict_commas"],
            )
            if not units:
                raise RuntimeError("Không tách được nội dung thành các đoạn đọc.")
            if not params["exact_pause"]:
                for unit in units:
                    unit["pause_ms"] = 0

            self.log(f"Đã chia script thành {len(units)} đoạn đọc.")
            self.log(
                f"Ngắt chính xác: {'BẬT' if params['exact_pause'] else 'TẮT'}; "
                f"ép dấu phẩy: {'BẬT' if params['strict_commas'] else 'TẮT'}"
            )
            self.log(
                f"Chỉ dẫn S2 tự động: {'BẬT' if params['auto_s2_cues'] else 'TẮT'}; "
                f"mức diễn: {params['s2_cue_mode']}"
            )
            if params["reference_id"]:
                self.log(f"Giọng: Voice ID {params['reference_id'][:10]}…")
            else:
                self.log("Giọng: mặc định Fish (không gửi reference_id)")
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            job_dir = params["out_dir"] / f"job_{timestamp}"
            chunks_dir = job_dir / "chunks"
            chunks_dir.mkdir(parents=True, exist_ok=True)
            (job_dir / "script_used.txt").write_text(
                params["text"], encoding="utf-8"
            )
            (job_dir / "script_tts_cleaned.txt").write_text(
                cleaned_text, encoding="utf-8"
            )
            (job_dir / "ellipsis_cleanup_report.txt").write_text(
                "\n".join(ellipsis_cleanup_report)
                if ellipsis_cleanup_report
                else "Không phát hiện dòng chỉ có hoặc bắt đầu bằng dấu ba chấm nguy hiểm.\n",
                encoding="utf-8",
            )

            preset_data = {
                "app_version": APP_VERSION,
                "created_at": timestamp,
                "model": params["model"],
                "language_code": params["language_code"],
                "language_name": params["language_name"],
                "voice_name": params["voice_display"],
                "reference_id": params["reference_id"],
                "speed": params["speed"],
                "max_chars_per_unit": params["max_chars"],
                "retry_count": params["retry_count"],
                "api_latency": params["latency"],
                "auto_s2_cues": params["auto_s2_cues"],
                "s2_cue_mode": params["s2_cue_mode"],
                "exact_silence_enabled": params["exact_pause"],
                "split_on_every_comma": params["strict_commas"],
                "pause_comma_ms": params["comma_ms"],
                "pause_sentence_ms": params["sentence_ms"],
                "pause_question_exclamation_ms": params["question_ms"],
                "pause_ellipsis_ms": params["ellipsis_ms"],
                "pause_paragraph_ms": params["paragraph_ms"],
                "input_characters": len(params["text"]),
                "speech_units": len(units),
                "dangerous_ellipsis_lines_cleaned": len(ellipsis_cleanup_report),
                "api_key_saved": False,
            }
            (job_dir / "preset_used.json").write_text(
                json.dumps(preset_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            preset_text = [
                "FISH STORY GUI — PRESET ĐÃ DÙNG",
                "================================",
                f"Phiên bản GUI: {APP_VERSION}",
                f"Thời điểm: {timestamp}",
                f"Model: {params['model']}",
                f"Ngôn ngữ: {params['language_name']}",
                f"Tên giọng: {params['voice_display']}",
                f"Voice ID: {params['reference_id'] or 'GIỌNG MẶC ĐỊNH FISH'}",
                f"Tốc độ: {params['speed']}",
                f"Ký tự tối đa / đơn vị: {params['max_chars']}",
                f"Số lần thử lại: {params['retry_count']}",
                f"Chế độ API: {params['latency']}",
                f"Tag S2 tự động: {'BẬT' if params['auto_s2_cues'] else 'TẮT'}",
                f"Mức diễn: {params['s2_cue_mode']}",
                f"Chèn im lặng thật: {'BẬT' if params['exact_pause'] else 'TẮT'}",
                f"Ép dừng mọi dấu phẩy: {'BẬT' if params['strict_commas'] else 'TẮT'}",
                f"Dấu phẩy: {params['comma_ms']} ms",
                f"Dấu chấm: {params['sentence_ms']} ms",
                f"? / !: {params['question_ms']} ms",
                f"Dấu …: {params['ellipsis_ms']} ms",
                f"Xuống đoạn: {params['paragraph_ms']} ms",
                f"Dòng dấu ba chấm nguy hiểm đã xử lý: {len(ellipsis_cleanup_report)}",
                "",
                "API key không được lưu trong output.",
            ]
            (job_dir / "preset_used.txt").write_text(
                "\n".join(preset_text) + "\n", encoding="utf-8"
            )

            if ellipsis_cleanup_report:
                self.log(
                    f"Đã xử lý {len(ellipsis_cleanup_report)} dòng chỉ có "
                    "hoặc bắt đầu bằng dấu ba chấm."
                )

            wav_paths = []
            durations = []
            pauses_ms = []
            pause_plan_lines = []
            s2_plan_lines = []
            tagged_script_blocks = []
            s2_requests = (
                build_s2_requests(units, params["s2_cue_mode"], params["language_code"])
                if params["auto_s2_cues"]
                else [unit["text"] for unit in units]
            )
            for index, unit in enumerate(units, start=1):
                chunk_text = unit["text"]
                request_text = s2_requests[index - 1]
                tagged_script_blocks.append(request_text)
                if self.stop_requested:
                    self.ui(self.status_text.set, "Đã dừng")
                    self.log("Đã dừng theo yêu cầu.")
                    return

                self.ui(self.status_text.set, f"Đang tạo đoạn {index}/{len(units)}")
                self.ui(self.progress_value.set, ((index - 1) / len(units)) * 100)
                self.log(f"Tạo đoạn {index}/{len(units)}...")

                output_path = chunks_dir / f"chunk_{index:04d}.wav"
                success = False
                last_error = None
                for attempt in range(1, params["retry_count"] + 2):
                    try:
                        request_args = {
                            "text": request_text,
                            "model": params["model"],
                            "format": "wav",
                            "speed": params["speed"],
                            "latency": params["latency"],
                        }
                        if params["reference_id"]:
                            request_args["reference_id"] = params["reference_id"]

                        audio = client.tts.convert(**request_args)
                        save(audio, str(output_path))
                        duration = wav_duration_seconds(output_path)
                        wav_paths.append(output_path)
                        durations.append(duration)
                        pauses_ms.append(int(unit["pause_ms"]))
                        pause_plan_lines.append(
                            f"{index:04d} | speech={duration:.3f}s | pause={unit['pause_ms']}ms | "
                            f"reason={unit['reason']} | {chunk_text}"
                        )
                        s2_plan_lines.append(
                            f"{index:04d}\nORIGINAL: {chunk_text}\nSENT TO FISH: {request_text}\n"
                        )
                        self.log(
                            f"OK đoạn {index}: {duration:.2f} giây + nghỉ {unit['pause_ms']} ms ({unit['reason']})"
                        )
                        success = True
                        break
                    except Exception as exc:
                        last_error = exc
                        self.log(f"Lỗi đoạn {index}, lần {attempt}: {exc}")
                        time.sleep(1)

                if not success:
                    raise RuntimeError(f"Không tạo được đoạn {index}. Lỗi cuối: {last_error}")

            final_wav = job_dir / "final.wav"
            final_srt = job_dir / "final.srt"
            merge_wavs_with_pauses(wav_paths, pauses_ms, final_wav)
            write_srt_with_pauses(units, durations, final_srt)
            (job_dir / "pause_plan.txt").write_text("\n".join(pause_plan_lines), encoding="utf-8")
            (job_dir / "script_s2_tagged.txt").write_text(
                "\n\n".join(tagged_script_blocks), encoding="utf-8"
            )
            (job_dir / "s2_tag_plan.txt").write_text(
                "\n".join(s2_plan_lines), encoding="utf-8"
            )
            self.ui(self.progress_value.set, 100)
            self.ui(self.status_text.set, "Hoàn tất")
            self.log(f"Hoàn tất: {final_wav}")
            self.log(f"SRT: {final_srt}")
            self.log(f"Kế hoạch ngắt: {job_dir / 'pause_plan.txt'}")
            self.log(f"Bản đã gắn tag S2: {job_dir / 'script_s2_tagged.txt'}")
            self.log(f"Bản TTS đã làm sạch: {job_dir / 'script_tts_cleaned.txt'}")
            self.log(f"Báo cáo dấu ba chấm: {job_dir / 'ellipsis_cleanup_report.txt'}")
            self.log(f"Preset đã dùng: {job_dir / 'preset_used.txt'}")
            os.startfile(str(job_dir))
        except Exception as exc:
            self.ui(self.status_text.set, "Lỗi")
            self.log(f"LỖI: {exc}")
            self.log(traceback.format_exc())
            self.ui(messagebox.showerror, APP_TITLE, f"Đã xảy ra lỗi:\n{exc}")

    def start_clone_voice(self):
        if self.clone_worker and self.clone_worker.is_alive():
            messagebox.showinfo(APP_TITLE, "Đang clone giọng. Hãy chờ hoàn tất.")
            return

        audio_path = Path(self.clone_audio_path.get().strip())
        if not audio_path.exists():
            messagebox.showwarning(APP_TITLE, "Chưa chọn audio mẫu hợp lệ.")
            return

        title = self.clone_title.get().strip()
        if not title:
            messagebox.showwarning(APP_TITLE, "Bạn chưa nhập tên giọng.")
            return

        transcript = self.clone_transcript.get("1.0", "end-1c").strip()
        clone_language_code = LANGUAGE_NAME_TO_CODE.get(
            self.clone_language_display.get(),
            self.active_language_code,
        )
        params = {
            "audio_path": audio_path,
            "language_code": clone_language_code,
            "title": title,
            "description": self.clone_description.get().strip(),
            "transcript": transcript,
            "visibility": self.clone_visibility.get().strip() or "private",
            "enhance": bool(self.clone_enhance.get()),
        }

        if not messagebox.askyesno(
            APP_TITLE,
            "Bạn xác nhận mình sở hữu hoặc có quyền sử dụng giọng nói trong audio này?",
        ):
            return

        self.clone_status.set("Đang tải audio và clone giọng...")
        self.clone_button.config(state="disabled")
        self.clone_log("Bắt đầu clone giọng...")
        self.clone_worker = threading.Thread(target=self._run_clone_voice, args=(params,), daemon=True)
        self.clone_worker.start()

    def _run_clone_voice(self, params):
        diagnostic_path = app_root_dir() / "clone_diagnostic_latest.txt"
        report = []
        try:
            load_dotenv(app_root_dir() / ".env", override=True)
            api_key = os.getenv("FISH_API_KEY", "").strip()
            if not api_key:
                raise RuntimeError("Chưa có FISH_API_KEY trong file .env")

            audio_path = Path(params["audio_path"])
            if not audio_path.exists():
                raise RuntimeError(f"Không tìm thấy audio: {audio_path}")
            if audio_path.stat().st_size <= 0:
                raise RuntimeError("File audio rỗng.")

            self.clone_log("Đang kiểm tra tài khoản và request clone...")
            client = FishAudio(api_key=api_key)

            credit_value = "không đọc được"
            package_value = "không đọc được"
            model_total = "không đọc được"
            existing_titles = set()

            try:
                credits = client.account.get_credits(
                    check_free_credit=True
                )
                credit_value = str(getattr(credits, "credit", "không rõ"))
            except Exception as exc:
                credit_value = f"lỗi: {exc}"

            try:
                package = client.account.get_package()
                package_value = (
                    f"type={getattr(package, 'type', 'không rõ')}, "
                    f"balance={getattr(package, 'balance', 'không rõ')}, "
                    f"total={getattr(package, 'total', 'không rõ')}"
                )
            except Exception as exc:
                package_value = f"lỗi: {exc}"

            try:
                voice_page = client.voices.list(
                    page_size=100,
                    page_number=1,
                    self_only=True,
                    sort_by="created_at",
                )
                model_total = str(
                    getattr(
                        voice_page,
                        "total",
                        len(list(getattr(voice_page, "items", []) or [])),
                    )
                )
                for item in list(
                    getattr(voice_page, "items", []) or []
                ):
                    existing_titles.add(
                        str(getattr(item, "title", "") or "").strip().lower()
                    )
            except Exception as exc:
                model_total = f"lỗi: {exc}"

            upload_title = params["title"].strip()
            if upload_title.lower() in existing_titles:
                upload_title = (
                    upload_title + "_" + time.strftime("%Y%m%d_%H%M%S")
                )
                self.clone_log(
                    "Tên giọng đã tồn tại; đổi tên upload thành: "
                    + upload_title
                )

            parts, audio_bytes, mime_type = build_direct_clone_multipart(
                params,
                upload_title,
            )
            audio_sha256 = hashlib.sha256(audio_bytes).hexdigest()

            report.extend([
                "FISH STORY GUI — CHẨN ĐOÁN CLONE REST TRỰC TIẾP",
                "=" * 58,
                f"Thời gian: {time.strftime('%Y-%m-%d %H:%M:%S')}",
                f"GUI: {APP_VERSION}",
                f"Fish SDK: {safe_sdk_version()}",
                f"API endpoint: POST https://api.fish.audio/model",
                "",
                "TÀI KHOẢN",
                f"API credit: {credit_value}",
                f"Package: {package_value}",
                f"Số model/voice: {model_total}",
                "",
                "AUDIO",
                f"Đường dẫn: {audio_path}",
                f"Tên gửi lên: {audio_path.name}",
                f"MIME: {mime_type}",
                f"Kích thước: {len(audio_bytes)} bytes",
                f"SHA256: {audio_sha256}",
                "",
                "REQUEST",
                f"title: {upload_title}",
                f"type: tts",
                f"train_mode: fast",
                f"visibility: {params['visibility']}",
                f"enhance_audio_quality: {str(params['enhance']).lower()}",
                f"generate_sample: false",
                f"description length: {len(params.get('description', ''))}",
                f"transcript length: {len(params.get('transcript', ''))}",
                "Multipart filename và Content-Type: CÓ",
                "",
            ])

            self.clone_log(
                "Đang gọi trực tiếp POST /model bằng multipart có "
                f"filename={audio_path.name}, MIME={mime_type}..."
            )

            headers = {
                "Authorization": f"Bearer {api_key}",
                "User-Agent": (
                    f"Fish-Story-GUI/{APP_VERSION} "
                    f"fish-audio-sdk/{safe_sdk_version()}"
                ),
                "Accept": "application/json",
            }

            with httpx.Client(
                timeout=httpx.Timeout(240.0),
                follow_redirects=True,
            ) as http_client:
                response = http_client.post(
                    "https://api.fish.audio/model",
                    headers=headers,
                    files=parts,
                )

            identifiers = clone_response_identifiers(response)
            response_text = response.text or ""

            report.extend([
                "RESPONSE",
                f"HTTP status: {response.status_code}",
                f"Identifiers: {json.dumps(identifiers, ensure_ascii=False)}",
                f"Content-Type: {response.headers.get('content-type', '')}",
                "Body:",
                response_text[:12000],
                "",
            ])
            diagnostic_path.write_text(
                "\n".join(report),
                encoding="utf-8",
            )

            if response.status_code not in (200, 201):
                request_info = (
                    identifiers.get("x-request-id")
                    or identifiers.get("request-id")
                    or identifiers.get("x-correlation-id")
                    or identifiers.get("cf-ray")
                    or "không có"
                )
                if response.status_code >= 500:
                    raise RuntimeError(
                        "Fish tiếp tục trả lỗi máy chủ khi gọi REST trực "
                        "tiếp, không qua SDK.\n\n"
                        f"HTTP: {response.status_code}\n"
                        f"Request/Trace ID: {request_info}\n"
                        f"API credit: {credit_value}\n"
                        f"Số model hiện có: {model_total}\n\n"
                        "Báo cáo đầy đủ đã lưu tại:\n"
                        f"{diagnostic_path}\n\n"
                        "Đến bước này lỗi nằm ở tài khoản hoặc endpoint "
                        "của Fish, không còn nằm trong GUI/audio/transcript."
                    )
                raise RuntimeError(
                    f"Fish từ chối request clone.\n\n"
                    f"HTTP: {response.status_code}\n"
                    f"Phản hồi: {response_text[:2000]}\n\n"
                    f"Báo cáo: {diagnostic_path}"
                )

            try:
                payload = response.json()
            except Exception as exc:
                raise RuntimeError(
                    "Fish báo thành công nhưng phản hồi không phải JSON.\n"
                    f"Báo cáo: {diagnostic_path}"
                ) from exc

            voice_id = str(
                payload.get("_id")
                or payload.get("id")
                or ""
            ).strip()
            if not voice_id:
                raise RuntimeError(
                    "Fish không trả về Voice ID.\n"
                    f"Báo cáo: {diagnostic_path}"
                )

            state = str(payload.get("state") or "created")
            update_env_value(
                app_root_dir() / ".env",
                "REFERENCE_ID",
                voice_id,
            )
            self.store.set_voice_language(
                voice_id,
                params["language_code"],
            )
            self.store.data.setdefault(
                "last_voice_by_language",
                {},
            )[params["language_code"]] = voice_id
            self.store.save()

            self.ui(self.cloned_voice_id.set, voice_id)
            self.ui(self.reference_id.set, voice_id)
            self.ui(
                self.clone_status.set,
                f"Clone thành công — trạng thái: {state}",
            )
            self.clone_log(
                "Clone REST trực tiếp thành công. Voice ID: "
                + voice_id
            )
            self.ui(
                messagebox.showinfo,
                APP_TITLE,
                "Clone thành công bằng REST trực tiếp.\n\n"
                f"Voice ID: {voice_id}",
            )
            self.ui(self.refresh_voices)

        except Exception as exc:
            try:
                if not diagnostic_path.exists():
                    report.extend([
                        "LỖI TRƯỚC KHI NHẬN RESPONSE",
                        str(exc),
                        "",
                        traceback.format_exc(),
                    ])
                    diagnostic_path.write_text(
                        "\n".join(report),
                        encoding="utf-8",
                    )
            except Exception:
                pass

            self.ui(self.clone_status.set, "Clone thất bại")
            self.clone_log(f"LỖI: {exc}")
            self.clone_log(
                "Báo cáo: " + str(diagnostic_path)
            )
            self.clone_log(traceback.format_exc())
            self.ui(
                messagebox.showerror,
                APP_TITLE,
                f"{exc}",
            )
        finally:
            self.ui(self.clone_button.config, state="normal")

    def use_cloned_voice(self):
        voice_id = self.cloned_voice_id.get().strip()
        if not voice_id:
            messagebox.showwarning(APP_TITLE, "Chưa có Voice ID vừa clone.")
            return
        language_code = self.store.get_voice_language(voice_id)
        if language_code:
            self.active_language_code = language_code
            self.language_display.set(
                LANGUAGE_CODE_TO_NAME[language_code]
            )
        self.reference_id.set(voice_id)
        update_env_value(app_root_dir() / ".env", "REFERENCE_ID", voice_id)
        self.store.data.setdefault("last_voice_by_language", {})[
            self.active_language_code
        ] = voice_id
        self.store.save()
        self.notebook.select(0)
        self.refresh_voices()
        self.log(f"Đã chọn giọng clone: {voice_id}")

    def copy_voice_id(self):
        voice_id = self.cloned_voice_id.get().strip()
        if not voice_id:
            messagebox.showwarning(APP_TITLE, "Chưa có Voice ID để sao chép.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(voice_id)
        self.clone_status.set("Đã sao chép Voice ID")


def main():
    if HAS_DND:
        root = TkinterDnD.Tk()
    else:
        root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except Exception:
        pass
    FishStoryGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
