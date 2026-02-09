import curses

AUDIO_EXTENSIONS = {
    ".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac",
    ".wma", ".opus", ".aiff", ".ape", ".alac", 
    ".mp4", ".mkv", ".webm", ".avi", ".mov", ".mpg", ".mpeg",
}

CP_HEADER = 1
CP_DIR = 2
CP_SELECTED = 3
CP_GREEN = 4
CP_STATUS = 5
CP_SONGNAME = 6
CP_BAR = 7


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(CP_HEADER, curses.COLOR_CYAN, -1)
    curses.init_pair(CP_DIR, curses.COLOR_BLUE, -1)
    curses.init_pair(CP_SELECTED, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(CP_GREEN, curses.COLOR_GREEN, -1)
    curses.init_pair(CP_STATUS, curses.COLOR_YELLOW, -1)
    curses.init_pair(CP_SONGNAME, curses.COLOR_MAGENTA, -1)
    curses.init_pair(CP_BAR, curses.COLOR_BLACK, curses.COLOR_GREEN)


def _cp(pair, extra=0):
    return curses.color_pair(pair) | extra


def _write_segments(stdscr, line, max_x, segments):
    """Write [(text, attr), ...] segments sequentially on *line*."""
    col = 0
    for text, attr in segments:
        if col >= max_x:
            break
        stdscr.addstr(line, col, text[: max_x - col], attr)
        col += len(text)
    return col


def get_visible_height(stdscr):
    max_y, _ = stdscr.getmaxyx()
    return max(0, max_y - 3)


def render_browser(stdscr, current_path, display, selected, scroll, entries, visible_height):
    stdscr.clear()
    max_y, max_x = stdscr.getmaxyx()

    header = f" Browsing: {current_path} "
    stdscr.addstr(0, 0, header[: max_x - 1], _cp(CP_HEADER, curses.A_BOLD))

    if not entries:
        stdscr.addstr(1, 2, "(empty)", curses.A_DIM)
    else:
        end = min(len(display), scroll + visible_height)
        for row, idx in enumerate(range(scroll, end), start=1):
            text = display[idx][: max_x - 4]
            entry = entries[idx]

            if idx == selected:
                text = text.ljust(max_x - 4)
                attr = _cp(CP_SELECTED, curses.A_BOLD)
            elif entry.is_dir():
                attr = _cp(CP_DIR, curses.A_BOLD)
            elif entry.suffix.lower() in AUDIO_EXTENSIONS:
                attr = _cp(CP_GREEN)
            else:
                attr = curses.A_NORMAL

            stdscr.addstr(row, 2, text, attr)

    stdscr.refresh()


def show_audio_selected(stdscr, entries_count, chosen_name):
    stdscr.addstr(
        entries_count + 2, 0,
        f"Selected audio file: {chosen_name}",
        _cp(CP_SONGNAME, curses.A_BOLD),
    )
    stdscr.refresh()
    stdscr.getch()


def show_status(stdscr, message):
    max_y, max_x = stdscr.getmaxyx()
    line = max(0, max_y - 1)
    stdscr.move(line, 0)
    stdscr.clrtoeol()
    if max_x > 0:
        try:
            stdscr.addstr(line, 0, message[: max_x - 1], _cp(CP_STATUS, curses.A_BOLD))
        except curses.error:
            pass
    stdscr.refresh()


def _format_time(seconds):
    if seconds is None:
        return "--:--"
    seconds = max(0, int(seconds))
    minutes, secs = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def show_info_bar(stdscr, playing_name=None, progress=None):
    max_y, max_x = stdscr.getmaxyx()
    line = max(0, max_y - 2)
    stdscr.move(line, 0)
    stdscr.clrtoeol()
    if max_x <= 0:
        return

    time_pos = duration = None
    if progress:
        time_pos, duration = progress

    label = "> Now playing: " if playing_name else "  Stopped: "
    name = playing_name or "(none)"

    time_text = f"  {_format_time(time_pos)} / {_format_time(duration)}"
    percent = None
    if duration and time_pos is not None and duration > 0:
        percent = int(max(0, min(100, (time_pos / duration) * 100)))
    if percent is not None:
        time_text += f" ({percent:3d}%)"

    bold = curses.A_BOLD
    segments = [
        (label, _cp(CP_GREEN, bold)),
        (name, _cp(CP_SONGNAME, bold)),
        (time_text, _cp(CP_HEADER)),
    ]

    try:
        col = _write_segments(stdscr, line, max_x, segments)

        if percent is not None and col + 4 < max_x:
            bar_w = min(20, max_x - col - 2)
            if bar_w > 2:
                filled = max(0, int(bar_w * percent / 100))
                stdscr.addstr(line, col, " ", curses.A_NORMAL)
                col += 1
                if filled:
                    stdscr.addstr(line, col, " " * filled, _cp(CP_BAR))
    except curses.error:
        pass
