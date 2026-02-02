import argparse
import curses
from pathlib import Path

from controller import handle_key
from model import AUDIO_EXTS, BrowserState, build_display, clamp_selection, list_entries
from view import get_visible_height, render_browser, show_status
from pydub import AudioSegment
import simpleaudio as sa


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


def file_browser(stdscr, start_path: Path):
    curses.curs_set(0)
    state = BrowserState(current_path=start_path)
    current_playback = None

    while True:
        entries, has_parent = list_entries(state)
        display = build_display(entries, has_parent)
        visible_height = get_visible_height(stdscr)
        state.selected, state.scroll = clamp_selection(
            state.selected, state.scroll, visible_height, entries
        )
        render_browser(
            stdscr,
            state.current_path,
            display,
            state.selected,
            state.scroll,
            entries,
            visible_height,
        )

        key = stdscr.getch()

        if key in (ord('q'), 27):  # q or ESC to quit
            if current_playback is not None:
                current_playback.stop()
            break
        else:
            state.current_path, state.selected, state.scroll, state.show_hidden, action = handle_key(
                key,
                entries,
                state.current_path,
                state.selected,
                state.scroll,
                visible_height,
                state.show_hidden,
                AUDIO_EXTS,
            )
            if action and action[0] == "select_audio":
                chosen = action[1]
                show_status(stdscr, f"Playing preview: {chosen.name}")
                try:
                    if current_playback is not None:
                        current_playback.stop()
                    current_playback = play_audio_preview(chosen)
                except RuntimeError as exc:
                    show_status(stdscr, f"Error: {exc}")
                    stdscr.getch()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Browse directories and preview audio files.",
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=str(Path.home()),
        help="Folder to open (defaults to home directory).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    start_path = Path(args.path).expanduser().resolve()
    curses.wrapper(file_browser, start_path)
