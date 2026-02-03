import argparse
import curses
from pathlib import Path

from controller import handle_action, handle_key
from model import (
    AUDIO_EXTS,
    AudioPreviewPlayer,
    BrowserState,
    build_display,
    clamp_selection,
    list_entries,
)
from view import get_visible_height, render_browser, show_status


def file_browser(stdscr, start_path: Path):
    curses.curs_set(0)
    state = BrowserState(current_path=start_path)
    player = AudioPreviewPlayer()

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
            player.stop()
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
            result = handle_action(action, player)
            if result:
                level, message = result
                show_status(stdscr, message)
                if level == "error":
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
