"""ffmpeg/ffprobe helpers for the packaging stage (PRD FR-8).

Shells out to the ``ffmpeg`` and ``ffprobe`` binaries rather than pulling a python-ffmpeg
dependency — the pipeline already requires ffmpeg on PATH (config.preflight), and a couple of
narrow subprocess calls are easier to reason about (and to surface stderr from) than a wrapper.

Three concerns:
- :func:`clip_duration_sec` — the measured length of one clip, the unit chapter marks are built
  from (a requested 1.5s silence renders ~1.3s, so chapter times MUST come from measurement).
- :func:`make_silence` — a silent MP3 for the inter-clip gaps (section boundaries; speaker
  changes in a future two-host mode).
- :func:`stitch` — decode every clip + interleaved silence through the concat filter, loudness-
  normalize the whole thing in the same graph (so levels are consistent across clip seams), and
  re-encode to a tagged mono MP3. Returns the final MEASURED duration.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import Config


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run an ffmpeg/ffprobe command, raising with captured stderr on failure."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"{cmd[0]} failed (exit {proc.returncode}):\n{proc.stderr.strip()}"
        )
    return proc


def clip_duration_sec(path: str | Path) -> float:
    """Measured duration of an audio file in seconds, via ``ffprobe``."""
    proc = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    return float(proc.stdout.strip())


def make_silence(
    seconds: float,
    out_path: str | Path,
    sample_rate: int = 44100,
    channels: int = 1,
) -> Path:
    """Generate a silent MP3 of ``seconds`` at ``sample_rate``/``channels`` (anullsrc)."""
    out_path = Path(out_path)
    layout = "mono" if channels == 1 else "stereo"
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"anullsrc=channel_layout={layout}:sample_rate={sample_rate}",
            "-t",
            f"{seconds}",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(out_path),
        ]
    )
    return out_path


def stitch(
    clips: list[Path],
    boundaries: list[int],
    settings: "Config",
    out_path: str | Path,
    id3: dict[str, Any],
) -> float:
    """Concatenate ``clips`` in order, insert silence at boundaries, loudnorm, and tag.

    ``boundaries`` holds the clip indices that open a new SECTION — a
    ``gap_section_boundary_ms`` silence is inserted immediately before each. Speaker-change
    gaps (``gap_speaker_change_ms``) are wired for the future two-host mode but do not fire in
    M1's solo narrator, where every gap is a section boundary. Index 0 is never a boundary.

    Everything is decoded, concatenated, and loudness-normalized in a single concat-filter graph
    (robust to per-clip encode differences), then re-encoded to a mono MP3 at ``audio.bitrate``
    with the supplied ID3 tags. Returns the final MEASURED duration in seconds.
    """
    audio = settings.audio
    out_path = Path(out_path)
    boundary_set = set(boundaries)

    with tempfile.TemporaryDirectory() as tmp:
        section_gap = make_silence(
            audio.gap_section_boundary_ms / 1000.0,
            Path(tmp) / "section_gap.mp3",
            channels=audio.channels,
        )

        # Interleave: a section-boundary clip is preceded by one silence input.
        inputs: list[Path] = []
        for i, clip in enumerate(clips):
            if i != 0 and i in boundary_set:
                inputs.append(section_gap)
            inputs.append(clip)

        cmd: list[str] = ["ffmpeg", "-y"]
        for p in inputs:
            cmd += ["-i", str(p)]
        streams = "".join(f"[{i}:a]" for i in range(len(inputs)))
        filt = (
            f"{streams}concat=n={len(inputs)}:v=0:a=1[cat];"
            f"[cat]loudnorm={audio.loudnorm}[out]"
        )
        cmd += ["-filter_complex", filt, "-map", "[out]"]
        cmd += ["-ac", str(audio.channels), "-b:a", audio.bitrate]
        for key, value in id3.items():
            cmd += ["-metadata", f"{key}={value}"]
        cmd += [str(out_path)]
        _run(cmd)

    return clip_duration_sec(out_path)


__all__ = ["clip_duration_sec", "make_silence", "stitch"]
