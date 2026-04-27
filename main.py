import argparse
import curses
import random
import time
from pathlib import Path

from controller import handle_action, handle_key
from model import (
    BrowserState,
    build_display,
    clamp_playlist_selection,
    clamp_selection,
    DaemonPlayer,
    ensure_daemon_running,
    list_entries,
    load_persisted_state_into,
    save_state,
)
from view import (
    get_visible_height,
    init_colors,
    render_browser,
    show_info_bar,
    show_status,
    show_error,
)


def file_browser(stdscr, start_path: Path):
    curses.curs_set(0)
    init_colors()
    daemon_ready = ensure_daemon_running()
    init_error_msg = None
    if not daemon_ready:
        init_error_msg = "Could not start or connect to playback daemon."
    last_retry_at = 0.0
    RETRY_INTERVAL_SEC = 3.0
    state = BrowserState(current_path=start_path)
    load_persisted_state_into(state)
    player = DaemonPlayer()
    status_msg = None

    SCROLL_TICK_SEC = 0.2
    SCROLL_END_PAUSE_SEC = 0.5

    while True:
        if not daemon_ready:
            now = time.monotonic()
            if (now - last_retry_at) >= RETRY_INTERVAL_SEC:
                daemon_ready = ensure_daemon_running()
                last_retry_at = now
                if daemon_ready:
                    init_error_msg = None
                    status_msg = "Connected to playback daemon."
                else:
                    init_error_msg = "Could not start or connect to playback daemon."

        entries, has_parent = list_entries(state)
        display = build_display(entries, has_parent)
        visible_height = get_visible_height(stdscr)
        state.selected, state.scroll = clamp_selection(
            state.selected, state.scroll, visible_height, entries
        )

        # ── Update horizontal scroll offsets for long names ─────────────
        now = time.monotonic()
        max_y, max_x = stdscr.getmaxyx()
        divider_col = max(10, max_x // 2)
        browser_width = max(0, divider_col - 2)
        playlist_left = divider_col + 1
        playlist_width = max(0, max_x - playlist_left - 1)

        # Browser pane scrolling
        if (
            state.active_pane == "browser"
            and entries
            and 0 <= state.selected < len(display)
        ):
            label = display[state.selected]
            if len(label) > browser_width and browser_width > 0:
                if now < state.browser_scroll_paused_until:
                    # stay at the end during pause window
                    pass
                elif (now - state.browser_scroll_last_update) >= SCROLL_TICK_SEC:
                    # allow the last character to fully scroll past the visible area
                    max_offset = max(0, len(label))
                    if state.browser_scroll_offset >= max_offset:
                        # after pause, reset to start
                        state.browser_scroll_offset = 0
                        state.browser_scroll_paused_until = 0.0
                    else:
                        state.browser_scroll_offset += 1
                        if state.browser_scroll_offset >= max_offset:
                            # reached end; start pause window
                            state.browser_scroll_paused_until = (
                                now + SCROLL_END_PAUSE_SEC
                            )
                    state.browser_scroll_last_update = now
            else:
                state.browser_scroll_offset = 0
                state.browser_scroll_last_update = 0.0
                state.browser_scroll_paused_until = 0.0
        else:
            state.browser_scroll_offset = 0
            state.browser_scroll_last_update = 0.0
            state.browser_scroll_paused_until = 0.0

        # Playlist pane scrolling
        if (
            state.active_pane == "playlist"
            and state.playlist
            and 0 <= state.playlist_selected < len(state.playlist)
        ):
            name = state.playlist[state.playlist_selected].name
            prefix = f"{state.playlist_selected + 1:>3}. "
            available = max(0, playlist_width - len(prefix))
            if len(name) > available and available > 0:
                if now < state.playlist_scroll_paused_until:
                    # stay at the end during pause window
                    pass
                elif (now - state.playlist_scroll_last_update) >= SCROLL_TICK_SEC:
                    # allow the last character to fully scroll past the visible area
                    max_offset = max(0, len(name))
                    if state.playlist_scroll_offset >= max_offset:
                        # after pause, reset to start
                        state.playlist_scroll_offset = 0
                        state.playlist_scroll_paused_until = 0.0
                    else:
                        state.playlist_scroll_offset += 1
                        if state.playlist_scroll_offset >= max_offset:
                            # reached end; start pause window
                            state.playlist_scroll_paused_until = (
                                now + SCROLL_END_PAUSE_SEC
                            )
                    state.playlist_scroll_last_update = now
            else:
                state.playlist_scroll_offset = 0
                state.playlist_scroll_last_update = 0.0
                state.playlist_scroll_paused_until = 0.0
        else:
            state.playlist_scroll_offset = 0
            state.playlist_scroll_last_update = 0.0
            state.playlist_scroll_paused_until = 0.0

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
            state.browser_scroll_offset,
            state.playlist_scroll_offset,
        )
        if daemon_ready:
            playing_name, time_pos, duration = player.get_playback_info()
        else:
            playing_name, time_pos, duration = (None, None, None)

        # ── Autoplay next item in playlist when one finishes ───────────
        if (
            state.playing_from_playlist
            and state.active_pane == "playlist"
            and state.was_playing
            and playing_name is None
            and state.playlist
        ):
            if state.random_play:
                n = len(state.playlist)
                if n > 1 and state.playing_index >= 0:
                    indices = [i for i in range(n) if i != state.playing_index]
                    next_index = random.choice(indices)
                else:
                    next_index = random.randint(0, n - 1)
            else:
                next_index = state.playing_index + 1
                if next_index >= len(state.playlist):
                    if state.repeat_all and state.playlist:
                        next_index = 0
                    else:
                        # reached end of playlist; stop autoplay
                        state.playing_from_playlist = False
                        state.playing_index = -1
            if 0 <= next_index < len(state.playlist):
                state.playing_index = next_index
                state.playlist_selected = next_index
                clamp_playlist_selection(state, visible_height)
                next_path = state.playlist[next_index]
                state.last_playing_path = next_path
                save_state(state)
                result = handle_action(("select_audio", next_path), player)
                if result:
                    _, status_msg = result

        show_info_bar(
            stdscr,
            playing_name,
            (time_pos, duration),
            state.repeat_all,
            state.random_play,
        )

        if status_msg:
            show_status(stdscr, status_msg)
            status_msg = None

        pending = player.poll_pending() if daemon_ready else None
        if pending:
            level, message = pending
            if level == "error":
                show_error(stdscr, message)
                stdscr.timeout(-1)
                stdscr.getch()
            else:
                show_status(stdscr, message)

        if init_error_msg:
            show_error(stdscr, init_error_msg)

        # remember whether we were playing this frame (for next iteration)
        state.was_playing = playing_name is not None

        stdscr.timeout(200)
        key = stdscr.getch()
        if key == -1:
            continue

        if key == ord("Q"):  # Shift+Q: full quit, stop daemon and playback
            save_state(state)
            if daemon_ready:
                player.quit_daemon()
            break
        if key in (ord("q"), 27):  # q or ESC: exit TUI only, daemon keeps playing
            save_state(state)
            break
        else:
            action = handle_key(key, entries, state, visible_height)
            if action and action[0] == "select_audio":
                state.last_playing_path = action[1]
                save_state(state)
            if action and action[0] in {"select_audio", "toggle_play_pause"} and not daemon_ready:
                result = (
                    "error",
                    "Playback daemon is unavailable. Waiting for reconnection...",
                )
            else:
                result = handle_action(action, player)
            if result:
                level, message = result
                if level == "error":
                    show_error(stdscr, message)
                else:
                    status_msg = message


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
