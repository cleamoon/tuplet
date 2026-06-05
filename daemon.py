from __future__ import annotations

import os
import socket
import sys
from ctypes import CDLL
from pathlib import Path


def _mpv_lib_names() -> tuple[str, ...]:
    if sys.platform.startswith("win"):
        return ("mpv-2.dll", "libmpv-2.dll", "mpv-1.dll")
    if sys.platform == "darwin":
        return ("libmpv.dylib", "libmpv.2.dylib")
    return ("libmpv.so", "libmpv.so.2", "libmpv.so.1")


def _mpv_lib_candidates() -> list[Path]:
    root = Path(__file__).resolve().parent
    candidates: list[Path] = []

    bundled = root / "libs"
    if bundled.is_dir():
        candidates.append(bundled)

    if sys.platform == "darwin":
        brew_prefix = Path(os.environ.get("HOMEBREW_PREFIX", "/opt/homebrew"))
        for rel in ("lib", "opt/mpv/lib"):
            path = brew_prefix / rel
            if path.is_dir():
                candidates.append(path)
    elif not sys.platform.startswith("win"):
        for path in (Path("/usr/local/lib"), Path("/usr/lib")):
            if path.is_dir():
                candidates.append(path)

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def _try_load_mpv_lib(lib_dir: Path) -> Path | None:
    for name in _mpv_lib_names():
        lib_file = lib_dir / name
        if not lib_file.is_file():
            continue
        try:
            CDLL(str(lib_file))
            return lib_file
        except OSError:
            continue
    return None


def _setup_mpv_library() -> None:
    if sys.platform.startswith("win"):
        lib_dir = Path(__file__).resolve().parent / "libs"
        if not lib_dir.is_dir():
            raise RuntimeError(
                "Local mpv library directory not found. "
                "Place mpv DLLs in libs/ or install mpv."
            )
        os.add_dll_directory(str(lib_dir))
        return

    var = "DYLD_LIBRARY_PATH" if sys.platform == "darwin" else "LD_LIBRARY_PATH"
    for lib_dir in _mpv_lib_candidates():
        lib_file = _try_load_mpv_lib(lib_dir)
        if lib_file is None:
            continue
        existing = os.environ.get(var, "")
        os.environ[var] = (
            f"{lib_dir}:{existing}" if existing else str(lib_dir)
        )
        return

    hint = (
        "Try: brew install mpv"
        if sys.platform == "darwin"
        else "Install mpv and libmpv development libraries for your distro."
    )
    raise RuntimeError(f"Cannot load libmpv from any known location. {hint}")


_setup_mpv_library()
import mpv

CONFIG_DIR = Path.home() / ".tuplet_tui_audio_player"
SOCKET_PATH = CONFIG_DIR / "socket"


def _run_daemon():
    player = mpv.MPV(video=False)
    current_path = None

    def get_info():
        nonlocal current_path
        if not current_path:
            return "NONE"
        try:
            time_pos = player.time_pos
            duration = player.duration
            idle = player.idle_active
        except Exception:
            return f"INFO\t{current_path.name}\t\t"
        if idle:
            # When playback has finished, clear current_path so subsequent
            # GET_INFO calls reliably report that nothing is playing.
            current_path = None
            return "NONE"
        return f"INFO\t{current_path.name}\t{time_pos}\t{duration}"

    def handle_play(args):
        nonlocal current_path
        if not args:
            return "ERROR missing path"
        path = args[0].strip()
        start_sec = float(args[1].strip()) if len(args) > 1 else 0
        try:
            player.play(path)
            current_path = Path(path)
            if start_sec > 0:
                player.seek(max(0, start_sec), reference="absolute")
            return "OK"
        except Exception as e:
            return f"ERROR {e}"

    def handle_stop():
        nonlocal current_path
        try:
            player.stop()
        except Exception:
            pass
        current_path = None
        return "OK"

    def handle_pause():
        try:
            player.pause = not player.pause
            return "OK"
        except Exception as e:
            return f"ERROR {e}"

    def handle_seek(args):
        if not args:
            return "ERROR missing seconds"
        try:
            sec = float(args[0].strip())
            player.seek(max(0, sec), reference="absolute")
            return "OK"
        except Exception as e:
            return f"ERROR {e}"

    SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SOCKET_PATH.exists():
        try:
            SOCKET_PATH.unlink()
        except Exception:
            pass

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(str(SOCKET_PATH))
    server.listen(4)

    try:
        while True:
            conn, _ = server.accept()
            try:
                buf = b""
                while b"\n" not in buf and len(buf) < 8192:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                line = buf.decode("utf-8", errors="replace").split("\n")[0].strip()
                parts = line.split("\t", 2)  # CMD, path, optional start
                cmd = (parts[0].upper() if parts else "").strip()
                rest = (parts[1] if len(parts) > 1 else "").strip()
                rest2 = (parts[2] if len(parts) > 2 else "").strip()

                if cmd == "QUIT":
                    reply = "OK"
                    conn.sendall((reply + "\n").encode("utf-8"))
                    conn.close()
                    break
                elif cmd == "PLAY":
                    reply = handle_play([rest, rest2] if rest2 else [rest])
                elif cmd == "STOP":
                    reply = handle_stop()
                elif cmd == "PAUSE":
                    reply = handle_pause()
                elif cmd == "SEEK":
                    # SEEK expects the new absolute position in seconds as the
                    # next argument (e.g. "SEEK\t123.4").
                    reply = handle_seek([rest2] if rest2 else [rest])
                elif cmd == "GET_INFO":
                    reply = get_info()
                else:
                    reply = "ERROR unknown command"

                conn.sendall((reply + "\n").encode("utf-8"))
            except Exception as e:
                try:
                    conn.sendall(f"ERROR {e}\n".encode("utf-8"))
                except Exception:
                    pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
        # QUIT received
    finally:
        try:
            player.terminate()
        except Exception:
            pass
        try:
            server.close()
        except Exception:
            pass
        if SOCKET_PATH.exists():
            try:
                SOCKET_PATH.unlink()
            except Exception:
                pass


if __name__ == "__main__":
    _run_daemon()
