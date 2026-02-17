from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import os
import socket
import subprocess
import sys
import threading
import time
from typing import Literal


lib_dir = Path(__file__).resolve().parent / "libs"
if not lib_dir.is_dir():
    raise RuntimeError("Local mpv library directory not found")
if sys.platform.startswith("win"):
    os.add_dll_directory(str(lib_dir))
else:
    var = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
    existing = os.environ.get(var, "")
    os.environ[var] = f"{str(lib_dir)}:{existing}" if existing else str(lib_dir)
import mpv


DAEMON_SOCKET_PATH = Path.home() / ".tuplet_tui_audio_player.sock"


def ensure_daemon_running():
    for _ in range(2):
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(1.0)
            s.connect(str(DAEMON_SOCKET_PATH))
            s.sendall(b"GET_INFO\n")
            s.recv(4096)
            s.close()
            return True
        except (socket.error, OSError):
            pass

        root = Path(__file__).resolve().parent
        daemon_script = root / "daemon.py"
        if not daemon_script.is_file():
            return False
        try:
            subprocess.Popen(
                [sys.executable, str(daemon_script)],
                cwd=str(root),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            return False

        time.sleep(0.5)
    return False


STATE_FILE = Path.home() / ".tuplet_tui_audio_player.json"


@dataclass
class BrowserState:
    current_path: Path
    selected: int = 0
    scroll: int = 0
    show_hidden: bool = False
    playlist: list = None
    playlist_selected: int = 0
    playlist_scroll: int = 0
    active_pane: Literal["browser", "playlist"] = "browser"
    playing_from_playlist: bool = False
    playing_index: int = -1
    was_playing: bool = False
    last_playing_path: Path | None = None

    def __post_init__(self):
        if self.playlist is None:
            self.playlist = []


class AudioPreviewPlayer:
    def __init__(self):
        self.player = mpv.MPV(video=False)
        self.current_path = None
        self._pending_result = None
        self._probe_lock = threading.Lock()

    def stop(self):
        try:
            self.player.stop()
        except Exception:
            pass
        self.current_path = None

    def toggle_pause(self):
        """Pause if playing, resume if paused. No-op if nothing loaded."""
        if not self.current_path:
            return
        try:
            self.player.pause = not self.player.pause
        except Exception:
            pass

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

    def try_play(self, file_path, start_seconds=0):
        file_path = Path(file_path)
        with self._probe_lock:
            self._pending_result = None

        def _probe():
            probe = mpv.MPV(video=False, vo="null", ao="null")
            try:
                probe.play(str(file_path))
                probe.wait_until_playing(timeout=3)
            except Exception as exc:
                with self._probe_lock:
                    self._pending_result = (
                        "error",
                        f"Cannot play {file_path.name}: {exc}",
                    )
                return
            finally:
                try:
                    probe.terminate()
                except Exception:
                    pass
            try:
                self.play(file_path, start_seconds=start_seconds)
                with self._probe_lock:
                    self._pending_result = (
                        "status",
                        f"Playing preview: {file_path.name}",
                    )
            except Exception as exc:
                with self._probe_lock:
                    self._pending_result = ("error", f"Error: {exc}")

        thread = threading.Thread(target=_probe, daemon=True)
        thread.start()

    def poll_pending(self):
        with self._probe_lock:
            result = self._pending_result
            self._pending_result = None
        return result

    def get_playback_info(self):
        if not self.current_path:
            return None, None, None
        try:
            time_pos = self.player.time_pos
            duration = self.player.duration
            idle = self.player.idle_active
        except Exception:
            return self.current_path.name, None, None
        if idle:
            self.current_path = None
            return None, None, None
        return self.current_path.name, time_pos, duration


class DaemonPlayer:
    """Proxy to the background daemon so playback continues after the TUI exits."""

    def __init__(self):
        self._pending_result = None  # ("status"|"error", message)
        self._lock = threading.Lock()

    def _send(self, msg: str) -> str:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(3.0)
            s.connect(str(DAEMON_SOCKET_PATH))
            s.sendall((msg + "\n").encode("utf-8"))
            buf = b""
            while b"\n" not in buf and len(buf) < 8192:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
            s.close()
            return buf.decode("utf-8", errors="replace").split("\n")[0].strip()
        except Exception as e:
            return f"ERROR {e}"

    def stop(self):
        self._send("STOP")

    def quit_daemon(self):
        """Tell the daemon to exit and stop playback (full quit)."""
        self._send("QUIT")

    def toggle_pause(self):
        self._send("PAUSE")

    def play(self, audio_path, start_seconds=0):
        path = str(Path(audio_path).resolve())
        reply = self._send(f"PLAY\t{path}\t{start_seconds}")
        if reply.startswith("ERROR"):
            raise RuntimeError(reply[6:].strip())
        return None

    def try_play(self, file_path, start_seconds=0):
        file_path = Path(file_path)
        with self._lock:
            self._pending_result = None
        reply = self._send(f"PLAY\t{file_path.resolve()}\t{start_seconds}")
        with self._lock:
            if reply == "OK":
                self._pending_result = ("status", f"Playing preview: {file_path.name}")
            elif reply.startswith("ERROR"):
                self._pending_result = ("error", reply[6:].strip())

    def poll_pending(self):
        with self._lock:
            result = self._pending_result
            self._pending_result = None
        return result

    def get_playback_info(self):
        reply = self._send("GET_INFO")
        if reply == "NONE" or reply.startswith("ERROR"):
            return None, None, None
        if reply.startswith("INFO\t"):
            parts = reply.split("\t", 3)
            if len(parts) >= 4:
                name, time_pos_s, duration_s = parts[1], parts[2], parts[3]
                try:
                    time_pos = float(time_pos_s) if time_pos_s else None
                    duration = float(duration_s) if duration_s else None
                except ValueError:
                    time_pos = duration = None
                return name, time_pos, duration
        return None, None, None


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


def clamp_playlist_selection(state, visible_height):
    if not state.playlist:
        state.playlist_selected = 0
        state.playlist_scroll = 0
        return
    state.playlist_selected = min(state.playlist_selected, len(state.playlist) - 1)
    if state.playlist_selected < state.playlist_scroll:
        state.playlist_scroll = state.playlist_selected
    elif state.playlist_selected >= state.playlist_scroll + visible_height:
        state.playlist_scroll = max(0, state.playlist_selected - visible_height + 1)


def load_persisted_state_into(state: BrowserState) -> None:
    """Load previously saved state (playlist, current directory, last playing file) into *state*."""
    if not STATE_FILE.exists():
        return
    try:
        data = json.loads(STATE_FILE.read_text())
    except Exception:
        # Corrupt or unreadable state file; ignore
        return

    # Restore last open directory
    saved_dir = data.get("current_directory")
    if isinstance(saved_dir, str):
        dir_path = Path(saved_dir).expanduser().resolve()
        if dir_path.is_dir():
            state.current_path = dir_path

    # Restore browser position (clamped when entries are known in main loop)
    saved_selected = data.get("browser_selected")
    if isinstance(saved_selected, int) and saved_selected >= 0:
        state.selected = saved_selected
    saved_scroll = data.get("browser_scroll")
    if isinstance(saved_scroll, int) and saved_scroll >= 0:
        state.scroll = saved_scroll

    # Restore last playing file path (for display/consistency; no auto-resume)
    saved_playing = data.get("current_playing_file")
    if isinstance(saved_playing, str):
        playing_path = Path(saved_playing).expanduser()
        if playing_path.exists():
            state.last_playing_path = playing_path

    playlist_paths = data.get("playlist", [])
    if not isinstance(playlist_paths, list):
        return

    playlist = []
    for item in playlist_paths:
        if not isinstance(item, str):
            continue
        path = Path(item).expanduser()
        if path.exists():
            playlist.append(path)

    if playlist:
        state.playlist = playlist
        state.playlist_selected = min(
            data.get("playlist_selected", 0), max(0, len(playlist) - 1)
        )
        state.playlist_scroll = min(
            data.get("playlist_scroll", 0), max(0, len(playlist) - 1)
        )


def save_state(state: BrowserState) -> None:
    """Persist current state (playlist, current directory, current playing file) to the hidden JSON file."""
    try:
        data = {
            "playlist": [str(p) for p in state.playlist],
            "current_directory": str(state.current_path.resolve()),
            "current_playing_file": (
                str(state.last_playing_path) if state.last_playing_path else None
            ),
            "browser_selected": state.selected,
            "browser_scroll": state.scroll,
            "playlist_selected": state.playlist_selected,
            "playlist_scroll": state.playlist_scroll,
        }
        STATE_FILE.write_text(json.dumps(data))
    except Exception:
        # Never let persistence errors crash the TUI
        pass
