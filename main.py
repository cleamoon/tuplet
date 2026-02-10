import argparse
import curses
from pathlib import Path

from controller import handle_action, handle_key
from model import (
    AudioPreviewPlayer,
    BrowserState,
    build_display,
    clamp_playlist_selection,
    clamp_selection,
    list_entries,
)
from view import get_visible_height, init_colors, render_browser, show_info_bar, show_status


def file_browser(stdscr, start_path: Path):
    curses.curs_set(0)
    init_colors()
    state = BrowserState(current_path=start_path)
    player = AudioPreviewPlayer()
    status_msg = None

    while True:
        entries, has_parent = list_entries(state)
        display = build_display(entries, has_parent)
        visible_height = get_visible_height(stdscr)
        state.selected, state.scroll = clamp_selection(
            state.selected, state.scroll, visible_height, entries
        )
        clamp_playlist_selection(state, visible_height)
        render_browser(
            stdscr,
            state.current_path,
            display,
            state.selected,
            state.scroll,
            entries,
            visible_height,
            state.active_pane,
            state.playlist,
            state.playlist_selected,
            state.playlist_scroll,
        )
        playing_name, time_pos, duration = player.get_playback_info()

        # ── Autoplay next item in playlist when one finishes ───────────
        if (
            state.playing_from_playlist
            and state.active_pane == "playlist"
            and state.was_playing
            and playing_name is None
            and state.playlist
        ):
            next_index = state.playing_index + 1
            if 0 <= next_index < len(state.playlist):
                state.playing_index = next_index
                state.playlist_selected = next_index
                clamp_playlist_selection(state, visible_height)
                next_path = state.playlist[next_index]
                result = handle_action(("select_audio", next_path), player)
                if result:
                    _, status_msg = result
            else:
                # reached end of playlist; stop autoplay
                state.playing_from_playlist = False
                state.playing_index = -1

        show_info_bar(stdscr, playing_name, (time_pos, duration))

        if status_msg:
            show_status(stdscr, status_msg)
            status_msg = None

        pending = player.poll_pending()
        if pending:
            level, message = pending
            show_status(stdscr, message)
            if level == "error":
                stdscr.timeout(-1)
                stdscr.getch()

        # remember whether we were playing this frame (for next iteration)
        state.was_playing = playing_name is not None

        stdscr.timeout(200)
        key = stdscr.getch()
        if key == -1:
            continue

        if key in (ord('q'), 27):  # q or ESC to quit
            player.stop()
            break
        else:
            action = handle_key(key, entries, state, visible_height)
            result = handle_action(action, player)
            if result:
                _, status_msg = result


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
