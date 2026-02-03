import curses


def handle_key(
    key,
    entries,
    current_path,
    selected,
    scroll,
    visible_height,
    show_hidden,
    audio_exts,
):
    action = None
    if key in (curses.KEY_DOWN, ord('j')):
        if entries:
            selected = min(selected + 1, len(entries) - 1)
    elif key in (curses.KEY_UP, ord('k')):
        if entries:
            selected = max(selected - 1, 0)
    elif key == curses.KEY_NPAGE:
        if entries:
            page_size = max(1, visible_height)
            selected = min(selected + page_size, len(entries) - 1)
            scroll = min(scroll + page_size, max(0, len(entries) - visible_height))
    elif key == curses.KEY_PPAGE:
        if entries:
            page_size = max(1, visible_height)
            selected = max(selected - page_size, 0)
            scroll = max(scroll - page_size, 0)
    elif key in (ord('h'), ord('H')):
        show_hidden = not show_hidden
        selected = 0
        scroll = 0
    elif key in (curses.KEY_ENTER, ord('\n')):
        if entries:
            chosen = entries[selected]
            if chosen.is_dir():
                current_path = chosen
                selected = 0
                scroll = 0
            elif chosen.suffix.lower() in audio_exts:
                action = ("select_audio", chosen)
    elif key == curses.KEY_BACKSPACE or key == 127:
        parent = current_path.parent
        if parent != current_path:
            current_path = parent
            selected = 0
            scroll = 0

    return current_path, selected, scroll, show_hidden, action


def handle_action(action, player):
    if not action:
        return None
    action_type, payload = action
    if action_type == "select_audio":
        try:
            player.play(payload)
        except RuntimeError as exc:
            return ("error", f"Error: {exc}")
        return ("status", f"Playing preview: {payload.name}")
    return None
