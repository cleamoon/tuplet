import curses
from model import save_state
from view import MEDIA_EXTENSIONS


def handle_key(key, entries, state, visible_height):
    action = None

    # ── Media keys / Space: play-pause toggle ─────────────────────────
    if key == ord(" "):
        return ("toggle_play_pause",)

    # ── 'r': toggle Repeat All mode ────────────────────────────────────
    if key == ord("r"):
        state.repeat_all = not state.repeat_all
        save_state(state)
        status = "Repeat all: ON" if state.repeat_all else "Repeat all: OFF"
        return ("status", status)

    # ── 's': toggle Random play (shuffle) mode ─────────────────────────
    if key == ord("s"):
        state.random_play = not state.random_play
        save_state(state)
        status = "Random play: ON" if state.random_play else "Random play: OFF"
        return ("status", status)

    # ── Tab: switch pane ──────────────────────────────────────────────
    if key == ord("\t"):
        # reset scroll state when switching panes
        state.browser_scroll_offset = 0
        state.browser_scroll_last_update = 0.0
        state.browser_scroll_paused_until = 0.0
        state.playlist_scroll_offset = 0
        state.playlist_scroll_last_update = 0.0
        state.playlist_scroll_paused_until = 0.0
        if state.active_pane == "browser":
            state.active_pane = "playlist"
        else:
            state.active_pane = "browser"
        return action

    # ── 'a': add file to playlist (only from browser pane) ───────────
    if key == ord("a") and state.active_pane == "browser":
        if entries:
            chosen = entries[state.selected]
            if chosen.is_file() and chosen.suffix.lower() in MEDIA_EXTENSIONS:
                if chosen not in state.playlist:
                    state.playlist.append(chosen)
                    save_state(state)
                    action = ("status", f"Added to playlist: {chosen.name}")
                else:
                    action = ("status", f"Already in playlist: {chosen.name}")
            else:
                action = ("status", "Not an audio file")
        return action

    # ── 'd' / DEL: remove item from playlist (only in playlist pane) ─
    if key in (ord("d"), ord("x"), curses.KEY_DC) and state.active_pane == "playlist":
        if state.playlist:
            removed_index = state.playlist_selected
            removed = state.playlist.pop(removed_index)
            if state.playlist_selected >= len(state.playlist) and state.playlist:
                state.playlist_selected = len(state.playlist) - 1

            # keep autoplay state consistent with removals
            if not state.playlist:
                state.playing_from_playlist = False
                state.playing_index = -1
            elif state.playing_from_playlist:
                if removed_index < state.playing_index:
                    state.playing_index -= 1
                elif removed_index == state.playing_index:
                    state.playing_from_playlist = False
                    state.playing_index = -1

            save_state(state)
            action = ("status", f"Removed: {removed.name}")
        return action

    # ── Navigation ────────────────────────────────────────────────────
    if state.active_pane == "browser":
        action = _handle_browser_nav(key, entries, state, visible_height)
    else:
        action = _handle_playlist_nav(key, state, visible_height)

    return action


def _handle_browser_nav(key, entries, state, visible_height):
    action = None
    count = len(entries)
    max_index = max(0, count - 1)

    old_selected = state.selected

    if key in (curses.KEY_DOWN, ord("j")):
        if entries:
            state.selected = min(state.selected + 1, max_index)
            save_state(state)
    elif key in (curses.KEY_UP, ord("k")):
        if entries:
            state.selected = max(state.selected - 1, 0)
            save_state(state)
    elif key == curses.KEY_NPAGE:
        if entries:
            page_size = max(1, visible_height)
            state.selected = min(state.selected + page_size, max_index)
            state.scroll = min(state.scroll + page_size, max(0, count - visible_height))
            save_state(state)
    elif key == curses.KEY_PPAGE:
        if entries:
            page_size = max(1, visible_height)
            state.selected = max(state.selected - page_size, 0)
            state.scroll = max(state.scroll - page_size, 0)
            save_state(state)
    elif key == curses.KEY_HOME:
        if entries:
            state.selected = 0
            state.scroll = 0
            save_state(state)
    elif key == curses.KEY_END:
        if entries:
            state.selected = max_index
            state.scroll = max(0, count - visible_height)
            save_state(state)
    elif key in (ord("h"), ord("H")):
        state.show_hidden = not state.show_hidden
        state.selected = 0
        state.scroll = 0
    elif key in (curses.KEY_ENTER, ord("\n")):
        if entries:
            chosen = entries[state.selected]
            if chosen.is_dir():
                state.current_path = chosen
                state.selected = 0
                state.scroll = 0
                save_state(state)
            elif chosen.is_file():
                state.playing_from_playlist = False
                state.playing_index = -1
                action = ("select_audio", chosen)
    elif key == curses.KEY_RIGHT:
        if entries:
            chosen = entries[state.selected]
            if chosen.is_dir():
                state.current_path = chosen
                state.selected = 0
                state.scroll = 0
                save_state(state)
    elif key == curses.KEY_BACKSPACE or key == 127:
        parent = state.current_path.parent
        if parent != state.current_path:
            state.current_path = parent
            state.selected = 0
            state.scroll = 0
            save_state(state)
    elif key == curses.KEY_LEFT:
        parent = state.current_path.parent
        if parent != state.current_path:
            state.current_path = parent
            state.selected = 0
            state.scroll = 0
            save_state(state)
    if state.selected != old_selected:
        state.browser_scroll_offset = 0
        state.browser_scroll_last_update = 0.0
        state.browser_scroll_paused_until = 0.0
    return action


def _handle_playlist_nav(key, state, visible_height):
    action = None
    count = len(state.playlist)
    if not count:
        return action

    old_selected = state.playlist_selected

    if key in (curses.KEY_DOWN, ord("j")):
        state.playlist_selected = min(state.playlist_selected + 1, count - 1)
    elif key in (curses.KEY_UP, ord("k")):
        state.playlist_selected = max(state.playlist_selected - 1, 0)
    elif key == curses.KEY_NPAGE:
        page_size = max(1, visible_height)
        state.playlist_selected = min(state.playlist_selected + page_size, count - 1)
        state.playlist_scroll = min(
            state.playlist_scroll + page_size, max(0, count - visible_height)
        )
    elif key == curses.KEY_PPAGE:
        page_size = max(1, visible_height)
        state.playlist_selected = max(state.playlist_selected - page_size, 0)
        state.playlist_scroll = max(state.playlist_scroll - page_size, 0)
    elif key == curses.KEY_HOME:
        state.playlist_selected = 0
        state.playlist_scroll = 0
    elif key == curses.KEY_END:
        state.playlist_selected = count - 1
        state.playlist_scroll = max(0, count - visible_height)
    elif key in (curses.KEY_ENTER, ord("\n")):
        state.playing_from_playlist = True
        state.playing_index = state.playlist_selected
        chosen = state.playlist[state.playlist_selected]
        action = ("select_audio", chosen)

    if state.playlist_selected != old_selected:
        state.playlist_scroll_offset = 0
        state.playlist_scroll_last_update = 0.0
        state.playlist_scroll_paused_until = 0.0

    return action


def handle_action(action, player):
    if not action:
        return None
    action_type = action[0]
    payload = action[1] if len(action) > 1 else None
    if action_type == "select_audio":
        path = payload
        if path.suffix.lower() not in MEDIA_EXTENSIONS:
            return ("error", "Not an audio file")
        try:
            player.play(path)
            return ("status", f"Loading: {path.name}")
        except Exception as exc:
            return ("error", f"Cannot play: {exc}")
    if action_type == "toggle_play_pause":
        player.toggle_pause()
        return None
    if action_type == "status":
        return ("status", payload)
    return None
