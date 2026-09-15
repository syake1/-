"""Streamlit front end for the short-video generation pipeline.

The app deliberately writes uploaded media and generated audio to a temporary
job directory.  Large binaries therefore never become part of the repository.
It prepares phrase-level VOICEVOX audio and a Remotion props file containing
measured frame ranges; an existing Remotion renderer can consume that file.
"""

from __future__ import annotations

import json
import random
import re
import shutil
import subprocess
import tempfile
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import requests
import streamlit as st


FPS = 30
VOICEVOX_URL = "http://127.0.0.1:50021"
MAX_UPLOAD_MB = 200
MEDIA_TYPES = ["png", "jpg", "jpeg", "webp", "gif", "mp4", "mov", "webm"]
STYLE_NAMES = ("hook", "neon", "yellow_band", "pink", "orange", "clean_blue")
SPEAKER_FALLBACKS = (2, 3, 8, 10, 14, 16)


@dataclass(frozen=True)
class Caption:
    text: str
    spoken_text: str
    start_frame: int
    duration_in_frames: int
    audio_path: str
    style: str
    accent_words: tuple[str, ...]


def normalize_text(text: str) -> str:
    """Normalize whitespace without destroying Japanese punctuation."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_phrases(text: str, target: int = 13) -> list[str]:
    """Split copy into short semantic captions instead of equal time slices."""
    text = normalize_text(text)
    if not text:
        return []

    clauses = [part.strip() for part in re.split(r"(?<=[。！？!?])|\n+", text) if part.strip()]
    phrases: list[str] = []
    for clause in clauses:
        chunks = [chunk.strip() for chunk in re.split(r"(?<=[、，,：:；;])", clause) if chunk.strip()]
        buffer = ""
        for chunk in chunks:
            if not buffer or len(buffer) + len(chunk) <= target + 3:
                buffer += chunk
                continue
            phrases.extend(_hard_split(buffer, target))
            buffer = chunk
        if buffer:
            phrases.extend(_hard_split(buffer, target))
    return phrases


def _hard_split(text: str, target: int) -> list[str]:
    if len(text) <= target + 3:
        return [text]
    result: list[str] = []
    rest = text
    while len(rest) > target + 3:
        candidates = [i for i in range(max(5, target - 3), min(len(rest), target + 4))]
        split_at = next((i + 1 for i in reversed(candidates) if rest[i] in "・）』】」 "), target)
        result.append(rest[:split_at].strip())
        rest = rest[split_at:].strip()
    if rest:
        result.append(rest)
    return result


def parse_pronunciations(value: str) -> dict[str, str]:
    """Parse one `表記=読み` correction per line."""
    corrections: dict[str, str] = {}
    for line in value.splitlines():
        if "=" not in line:
            continue
        written, reading = (item.strip() for item in line.split("=", 1))
        if written and reading:
            corrections[written] = reading
    return corrections


def spoken_version(text: str, corrections: dict[str, str]) -> str:
    # Longest first prevents a short key from changing part of a longer key.
    for written in sorted(corrections, key=len, reverse=True):
        text = text.replace(written, corrections[written])
    return text


def parse_direction(direction: str) -> dict[str, Any]:
    """Convert common natural-language revisions into strong render controls."""
    direction = normalize_text(direction)
    vivid = any(word in direction for word in ("カラフル", "派手", "インパクト", "目立"))
    calm = any(word in direction for word in ("落ち着", "シンプル", "上品"))
    fast = any(word in direction for word in ("テンポ", "速く", "短く"))
    large = any(word in direction for word in ("大き", "でか", "強調"))
    return {
        "raw": direction,
        "vivid": vivid and not calm,
        "calm": calm,
        "pace": "fast" if fast else "normal",
        "fontScale": 1.18 if large else 1.0,
        "shadowStrength": 1.45 if vivid else 1.0,
        "animationStrength": 1.35 if vivid else (0.75 if calm else 1.0),
    }


def get_speakers(base_url: str) -> list[tuple[int, str]]:
    response = requests.get(f"{base_url}/speakers", timeout=5)
    response.raise_for_status()
    result: list[tuple[int, str]] = []
    for speaker in response.json():
        for style in speaker.get("styles", []):
            result.append((int(style["id"]), f"{speaker['name']} / {style['name']}"))
    return result


def synthesize_phrase(text: str, speaker: int, output: Path, base_url: str) -> float:
    query_response = requests.post(
        f"{base_url}/audio_query", params={"text": text, "speaker": speaker}, timeout=30
    )
    query_response.raise_for_status()
    query = query_response.json()
    # Keep punctuation pauses produced by VOICEVOX; these durations drive captions.
    audio_response = requests.post(
        f"{base_url}/synthesis",
        params={"speaker": speaker},
        json=query,
        timeout=120,
    )
    audio_response.raise_for_status()
    output.write_bytes(audio_response.content)
    return wav_duration(output)


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav_file:
        return wav_file.getnframes() / float(wav_file.getframerate())


def emphasize_words(text: str) -> tuple[str, ...]:
    words = re.findall(r"[一-龥ァ-ヶA-Za-z0-9]{2,}", text)
    return tuple(sorted(words, key=len, reverse=True)[:2])


def choose_styles(count: int, controls: dict[str, Any]) -> Iterable[str]:
    palette = list(STYLE_NAMES)
    if controls["calm"]:
        palette = ["clean_blue", "hook", "orange"]
    elif controls["vivid"]:
        palette = ["neon", "yellow_band", "pink", "orange", "hook"]
    for index in range(count):
        yield "hook" if index == 0 else palette[(index - 1) % len(palette)]


def save_uploads(files: list[Any], media_dir: Path) -> list[dict[str, Any]]:
    media_dir.mkdir(parents=True, exist_ok=True)
    result: list[dict[str, Any]] = []
    for index, uploaded in enumerate(files):
        suffix = Path(uploaded.name).suffix.lower()
        path = media_dir / f"media_{index + 1:02d}{suffix}"
        path.write_bytes(uploaded.getbuffer())
        result.append({"path": str(path.resolve()), "name": uploaded.name, "order": index})
    return result


def build_timeline(
    phrases: list[str],
    corrections: dict[str, str],
    speaker: int,
    controls: dict[str, Any],
    audio_dir: Path,
    base_url: str,
) -> list[Caption]:
    audio_dir.mkdir(parents=True, exist_ok=True)
    captions: list[Caption] = []
    cursor = 0
    styles = choose_styles(len(phrases), controls)
    for index, (phrase, style) in enumerate(zip(phrases, styles), start=1):
        spoken = spoken_version(phrase, corrections)
        audio_file = audio_dir / f"caption_{index:02d}.wav"
        seconds = synthesize_phrase(spoken, speaker, audio_file, base_url)
        frames = max(1, round(seconds * FPS))
        captions.append(
            Caption(
                text=phrase,
                spoken_text=spoken,
                start_frame=cursor,
                duration_in_frames=frames,
                audio_path=str(audio_file.resolve()),
                style=style,
                accent_words=emphasize_words(phrase),
            )
        )
        cursor += frames
    return captions


def write_props(
    destination: Path,
    captions: list[Caption],
    media: list[dict[str, Any]],
    speaker: int,
    controls: dict[str, Any],
) -> None:
    total_frames = sum(caption.duration_in_frames for caption in captions)
    # All uploaded assets are assigned a stable window, with no asset silently dropped.
    media_windows = []
    for index, item in enumerate(media):
        start = round(total_frames * index / max(1, len(media)))
        end = round(total_frames * (index + 1) / max(1, len(media)))
        media_windows.append({**item, "startFrame": start, "durationInFrames": max(1, end - start)})
    payload = {
        "fps": FPS,
        "width": 1080,
        "height": 1920,
        "durationInFrames": total_frames,
        "speaker": speaker,
        "captions": [asdict(caption) for caption in captions],
        "media": media_windows,
        "captionSafeZone": {"top": 280, "right": 150, "bottom": 360, "left": 90},
        "direction": controls,
    }
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def combine_audio(captions: list[Caption], destination: Path) -> None:
    """Join WAV chunks losslessly so narration can never be cut short."""
    if not captions:
        raise ValueError("音声にする文章がありません。")
    first = Path(captions[0].audio_path)
    with wave.open(str(first), "rb") as source:
        params = source.getparams()
    with wave.open(str(destination), "wb") as output:
        output.setparams(params)
        for caption in captions:
            with wave.open(caption.audio_path, "rb") as source:
                if source.getparams()[:4] != params[:4]:
                    raise ValueError("VOICEVOXが異なる形式のWAVを返しました。")
                output.writeframes(source.readframes(source.getnframes()))


def render_with_remotion(props_path: Path, output_path: Path) -> None:
    entry = Path("remotion/src/index.ts")
    if not entry.exists():
        raise FileNotFoundError(
            "remotion/src/index.ts がありません。props JSON は生成済みなので、"
            "既存のRemotionプロジェクトから読み込んでください。"
        )
    subprocess.run(
        [
            "npx",
            "remotion",
            "render",
            str(entry),
            "ShortVideo",
            str(output_path),
            "--props",
            str(props_path),
        ],
        check=True,
    )


def main() -> None:
    st.set_page_config(page_title="Short Video Auto", page_icon="🎬", layout="wide")
    st.title("🎬 プロ風ショート動画 自動生成")
    st.caption("フレーズ別の実測音声で、テロップとVOICEVOXを同期します。")

    with st.sidebar:
        st.header("音声設定")
        base_url = st.text_input("VOICEVOX URL", VOICEVOX_URL)
        try:
            speakers = get_speakers(base_url)
        except requests.RequestException:
            speakers = [(speaker_id, f"スタイルID {speaker_id}") for speaker_id in SPEAKER_FALLBACKS]
            st.warning("VOICEVOXに接続できません。起動後に生成してください。")
        random_voice = st.toggle("毎回声を変える", value=True)
        labels = {speaker_id: label for speaker_id, label in speakers}
        selected_speaker = st.selectbox(
            "固定する声",
            options=list(labels),
            format_func=lambda speaker_id: labels[speaker_id],
            disabled=random_voice,
        )

    text = st.text_area("読み上げ文章", height=220, placeholder="動画で伝えたい文章を入力してください。")
    uploads = st.file_uploader(
        "画像・動画（選択順ですべて使用）",
        type=MEDIA_TYPES,
        accept_multiple_files=True,
    )
    correction_col, direction_col = st.columns(2)
    with correction_col:
        pronunciations = st.text_area(
            "読み方辞書（1行に 表記=よみ）",
            placeholder="VOICEVOX=ボイスボックス\n生成AI=せいせいえーあい",
        )
    with direction_col:
        direction = st.text_area(
            "訂正・演出指示（自然文）",
            placeholder="もっとカラフルに。重要語を大きくしてテンポよく。",
        )

    phrases = split_phrases(text)
    if phrases:
        st.subheader("自動分割プレビュー")
        st.write(" / ".join(phrases))

    if not st.button("動画データを生成", type="primary", use_container_width=True):
        return
    if not phrases:
        st.error("読み上げ文章を入力してください。")
        return
    if not uploads:
        st.error("画像または動画を1つ以上アップロードしてください。")
        return
    too_large = [uploaded.name for uploaded in uploads if uploaded.size > MAX_UPLOAD_MB * 1024 * 1024]
    if too_large:
        st.error(f"{MAX_UPLOAD_MB}MBを超えるファイルは処理できません: {', '.join(too_large)}")
        return

    job_dir = Path(tempfile.mkdtemp(prefix="short-video-"))
    try:
        controls = parse_direction(direction)
        speaker = random.choice([speaker_id for speaker_id, _ in speakers]) if random_voice else selected_speaker
        media = save_uploads(uploads, job_dir / "media")
        with st.status("VOICEVOX音声をフレーズごとに生成中…", expanded=True) as status:
            captions = build_timeline(
                phrases,
                parse_pronunciations(pronunciations),
                speaker,
                controls,
                job_dir / "audio",
                base_url,
            )
            props_path = job_dir / "remotion_props.json"
            narration_path = job_dir / "narration.wav"
            write_props(props_path, captions, media, speaker, controls)
            combine_audio(captions, narration_path)
            status.update(label="同期データを生成しました。", state="complete")

        total_seconds = sum(caption.duration_in_frames for caption in captions) / FPS
        st.success(f"{len(captions)}テロップ / {total_seconds:.2f}秒 / 話者ID {speaker}")
        with props_path.open("rb") as props_file:
            st.download_button("Remotion propsを保存", props_file, "remotion_props.json", "application/json")
        with narration_path.open("rb") as audio_file:
            audio_bytes = audio_file.read()
            st.audio(audio_bytes, format="audio/wav")
            st.download_button("同期済み音声を保存", audio_bytes, "narration.wav", "audio/wav")

        if st.button("RemotionでMP4を書き出す"):
            output_path = job_dir / "short-video.mp4"
            render_with_remotion(props_path, output_path)
            with output_path.open("rb") as video_file:
                st.download_button("完成動画を保存", video_file, "short-video.mp4", "video/mp4")
    except (OSError, ValueError, requests.RequestException, subprocess.CalledProcessError) as exc:
        st.error(f"生成に失敗しました: {exc}")
        shutil.rmtree(job_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
