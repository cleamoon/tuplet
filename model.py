from dataclasses import dataclass
from pathlib import Path
import ctypes
import os
import sys
import threading


def _load_local_mpv():
    lib_dir = Path(__file__).resolve().parent / "libs"
    if not lib_dir.is_dir():
        return
    if sys.platform.startswith("win"):
        os.add_dll_directory(str(lib_dir))
    else:
        var = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
        existing = os.environ.get(var, "")
        os.environ[var] = f"{str(lib_dir)}:{existing}" if existing else str(lib_dir)


_load_local_mpv()

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
        self.current_path = None

    def stop(self):
        try:
            self.player.stop()
        except Exception:
            pass
        self.current_path = None

    def play(self, audio_path, start_seconds=0):
        self.stop()
        self.current_path = Path(audio_path)
        audio_path = str(audio_path)
        try:
            self.player.play(audio_path)
            if start_seconds:
                self.player.seek(max(0, float(start_seconds)), reference="absolute")
        except Exception as exc:
            raise RuntimeError(str(exc)) from exc
        return self.player

    def get_playback_info(self):
        if not self.current_path:
            return None, None, None
        try:
            eof_reached = self.player.eof_reached
            playback_active = self.player.playback_active
            time_pos = self.player.time_pos
            duration = self.player.duration
        except Exception:
            eof_reached = None
            playback_active = None
            time_pos = None
            duration = None
        if eof_reached or (playback_active is False and time_pos is None):
            self.current_path = None
            return None, None, None
        return self.current_path.name, time_pos, duration


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
