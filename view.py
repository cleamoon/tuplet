import curses


def get_visible_height(stdscr):
    max_y, _ = stdscr.getmaxyx()
    return max(0, max_y - 2)


def render_browser(stdscr, current_path, display, selected, scroll, entries, visible_height):
    stdscr.clear()
    max_y, max_x = stdscr.getmaxyx()
    stdscr.addstr(0, 0, f"Browsing: {current_path}", curses.A_BOLD)
    if not entries:
        stdscr.addstr(1, 2, "(empty)", curses.A_DIM)
    else:
        start = scroll
        end = min(len(display), scroll + visible_height)
        for row, idx in enumerate(range(start, end), start=1):
            line = display[idx]
            mode = curses.A_REVERSE if idx == selected else curses.A_NORMAL
            stdscr.addstr(row, 2, line[: max_x - 4], mode)
    stdscr.refresh()


def show_audio_selected(stdscr, entries_count, chosen_name):
    stdscr.addstr(entries_count + 2, 0, f"Selected audio file: {chosen_name}")
    stdscr.refresh()
    stdscr.getch()


def show_status(stdscr, message):
    max_y, max_x = stdscr.getmaxyx()
    line = max(0, max_y - 1)
    stdscr.move(line, 0)
    stdscr.clrtoeol()
    if max_x > 0:
        try:
            stdscr.addstr(line, 0, message[: max_x - 1])
        except curses.error:
            pass
    stdscr.refresh()
