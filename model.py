from dataclasses import dataclass
from pathlib import Path
import threading

import mpv

AUDIO_EXTS = {".mp3", ".flac", ".ogg", ".wav", ".m4a"}


@dataclass
class BrowserState:
    current_path: Path
    selected: int = 0
    scroll: int = 0
    show_hidden: bool = False


class AudioPreviewPlayer:
    def __init__(self):
        self.player = mpv.MPV(video=False)
        self.stop_timer = None

    def stop(self):
        if self.stop_timer is not None:
            self.stop_timer.cancel()
            self.stop_timer = None
        try:
            self.player.stop()
        except Exception:
            pass

    def play(self, audio_path, start_seconds=0, duration_seconds=5):
        self.stop()
        audio_path = str(audio_path)
        try:
            self.player.play(audio_path)
            if start_seconds:
                self.player.seek(max(0, float(start_seconds)), reference="absolute")
            if duration_seconds is not None:
                duration = max(0, float(duration_seconds))
                self.stop_timer = threading.Timer(duration, self.stop)
                self.stop_timer.daemon = True
                self.stop_timer.start()
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc
        return self.player


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
