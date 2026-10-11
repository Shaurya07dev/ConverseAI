from __future__ import annotations

import os
import shutil
from pathlib import Path

from ai_core.config import PROJECT_ROOT


def _binary_filename(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


def resolve_audio_binary(name: str) -> str | None:
    env_var = f"{name.upper()}_BINARY"
    configured = os.getenv(env_var)
    if configured and Path(configured).exists():
        return str(Path(configured).resolve())

    path_binary = shutil.which(name)
    if path_binary:
        return path_binary

    local_pattern = f"tools/ffmpeg/**/bin/{_binary_filename(name)}"
    for candidate in PROJECT_ROOT.glob(local_pattern):
        if candidate.is_file():
            return str(candidate.resolve())

    return None


def configure_audio_binaries() -> dict[str, str]:
    resolved: dict[str, str] = {}

    ffmpeg_path = resolve_audio_binary("ffmpeg")
    ffprobe_path = resolve_audio_binary("ffprobe")

    if ffmpeg_path:
        resolved["ffmpeg"] = ffmpeg_path
    if ffprobe_path:
        resolved["ffprobe"] = ffprobe_path

    bin_dirs = {
        str(Path(binary_path).resolve().parent)
        for binary_path in resolved.values()
    }
    if bin_dirs:
        existing_path = os.environ.get("PATH", "")
        current_entries = existing_path.split(os.pathsep) if existing_path else []
        merged_entries = [*bin_dirs, *current_entries]
        os.environ["PATH"] = os.pathsep.join(dict.fromkeys(merged_entries))

    return resolved
