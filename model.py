from dataclasses import dataclass
from pathlib import Path

from pydub import AudioSegment
import simpleaudio as sa

AUDIO_EXTS = {".mp3", ".flac", ".ogg", ".wav", ".m4a"}


@dataclass
class BrowserState:
    current_path: Path
    selected: int = 0
    scroll: int = 0
    show_hidden: bool = False


class AudioPreviewPlayer:
    def __init__(self):
        self.current_playback = None

    def stop(self):
        if self.current_playback is not None:
            self.current_playback.stop()
            self.current_playback = None

    def play(self, audio_path):
        self.stop()
        self.current_playback = play_audio_preview(audio_path)
        return self.current_playback


def play_audio_preview(audio_path, start_seconds=0, duration_seconds=5):
    audio_path = str(audio_path)
    try:
        segment = AudioSegment.from_file(audio_path)
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc

    try:
        playback = sa.play_buffer(
            segment.raw_data,
            num_channels=segment.channels,
            bytes_per_sample=segment.sample_width,
            sample_rate=segment.frame_rate,
        )
        return playback
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


def list_entries(state: BrowserState):
    entries = list(state.current_path.iterdir())
    if not state.show_hidden:
        entries = [entry for entry in entries if not entry.name.startswith(".")]
    entries.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
    parent = state.current_path.parent
    has_parent = parent != state.current_path
    if has_parent:
        entries = [parent] + entries
    return entries, has_parent


def build_display(entries, has_parent):
    display = []
    for idx, entry in enumerate(entries):
        if has_parent and idx == 0:
            display.append("[DIR] ..")
        else:
            display.append(
                f"[DIR] {entry.name}" if entry.is_dir() else f"     {entry.name}"
            )
    return display


def clamp_selection(selected, scroll, visible_height, entries):
    if not entries:
        return 0, 0
    selected = min(selected, len(entries) - 1)
    if selected < scroll:
        scroll = selected
    elif selected >= scroll + visible_height:
        scroll = max(0, selected - visible_height + 1)
    return selected, scroll
