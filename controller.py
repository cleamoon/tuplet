import curses
from model import save_state
from view import AUDIO_EXTENSIONS

def handle_key(key, entries, state, visible_height):
    """Process a key press and return an action (or None).

    Mutates *state* in place (selected, scroll, show_hidden, playlist, active_pane …).
    Returns an optional action tuple, e.g. ("select_audio", path).
    """
    action = None

    # ── Media keys / Space: play-pause toggle ─────────────────────────
    if key == ord(' '):
        return ("toggle_play_pause",)

    # ── Tab: switch pane ──────────────────────────────────────────────
    if key == ord('\t'):
        if state.active_pane == "browser":
            state.active_pane = "playlist"
        else:
            state.active_pane = "browser"
        return action

    # ── 'a': add file to playlist (only from browser pane) ───────────
    if key == ord('a') and state.active_pane == "browser":
        if entries:
            chosen = entries[state.selected]
            if chosen.is_file() and chosen.suffix.lower() in AUDIO_EXTENSIONS:
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
    if key in (ord('d'), ord('x'), curses.KEY_DC) and state.active_pane == "playlist":
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
    if key in (curses.KEY_DOWN, ord('j')):
        if entries:
            state.selected = min(state.selected + 1, len(entries) - 1)
    elif key in (curses.KEY_UP, ord('k')):
        if entries:
            state.selected = max(state.selected - 1, 0)
    elif key == curses.KEY_NPAGE:
        if entries:
            page_size = max(1, visible_height)
            state.selected = min(state.selected + page_size, len(entries) - 1)
            state.scroll = min(state.scroll + page_size, max(0, len(entries) - visible_height))
    elif key == curses.KEY_PPAGE:
        if entries:
            page_size = max(1, visible_height)
            state.selected = max(state.selected - page_size, 0)
            state.scroll = max(state.scroll - page_size, 0)
    elif key in (ord('h'), ord('H')):
        state.show_hidden = not state.show_hidden
        state.selected = 0
        state.scroll = 0
    elif key in (curses.KEY_ENTER, ord('\n')):
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
    elif key == curses.KEY_BACKSPACE or key == 127:
        parent = state.current_path.parent
        if parent != state.current_path:
            state.current_path = parent
            state.selected = 0
            state.scroll = 0
            save_state(state)
    return action


def _handle_playlist_nav(key, state, visible_height):
    action = None
    count = len(state.playlist)
    if not count:
        return action

    if key in (curses.KEY_DOWN, ord('j')):
        state.playlist_selected = min(state.playlist_selected + 1, count - 1)
    elif key in (curses.KEY_UP, ord('k')):
        state.playlist_selected = max(state.playlist_selected - 1, 0)
    elif key == curses.KEY_NPAGE:
        page_size = max(1, visible_height)
        state.playlist_selected = min(state.playlist_selected + page_size, count - 1)
        state.playlist_scroll = min(state.playlist_scroll + page_size, max(0, count - visible_height))
    elif key == curses.KEY_PPAGE:
        page_size = max(1, visible_height)
        state.playlist_selected = max(state.playlist_selected - page_size, 0)
        state.playlist_scroll = max(state.playlist_scroll - page_size, 0)
    elif key in (curses.KEY_ENTER, ord('\n')):
        state.playing_from_playlist = True
        state.playing_index = state.playlist_selected
        chosen = state.playlist[state.playlist_selected]
        action = ("select_audio", chosen)

    return action


def handle_action(action, player):
    if not action:
        return None
    action_type = action[0]
    payload = action[1] if len(action) > 1 else None
    if action_type == "select_audio":
        player.try_play(payload)
        return ("status", f"Loading: {payload.name}")
    if action_type == "toggle_play_pause":
        player.toggle_pause()
        return None  # status shown via playback info bar
    if action_type == "status":
        return ("status", payload)
    return None
