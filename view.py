import curses
import unicodedata

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
CP_AUDIO_NAME = 6
CP_BAR = 7
CP_INACTIVE_SEL = 8


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(CP_HEADER, curses.COLOR_CYAN, -1)
    curses.init_pair(CP_DIR, curses.COLOR_BLUE, -1)
    curses.init_pair(CP_SELECTED, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(CP_GREEN, curses.COLOR_GREEN, -1)
    curses.init_pair(CP_STATUS, curses.COLOR_YELLOW, -1)
    curses.init_pair(CP_AUDIO_NAME, curses.COLOR_MAGENTA, -1)
    curses.init_pair(CP_BAR, curses.COLOR_BLACK, curses.COLOR_GREEN)
    curses.init_pair(CP_INACTIVE_SEL, curses.COLOR_WHITE, curses.COLOR_BLACK)


def color_pair(pair, extra=0):
    return curses.color_pair(pair) | extra


def _cell_width(c: str) -> int:
    """Return terminal cell width for one character (1 for narrow, 2 for wide/CJK)."""
    if not c:
        return 0
    ea = unicodedata.east_asian_width(c)
    return 2 if ea in ("F", "W") else 1


def _truncate_to_width(s: str, max_width: int) -> str:
    """Truncate string so its terminal display width is at most max_width."""
    w = 0
    for i, c in enumerate(s):
        cw = _cell_width(c)
        if w + cw > max_width:
            return s[:i]
        w += cw
    return s


def get_visible_height(stdscr):
    max_y, _ = stdscr.getmaxyx()
    return max(0, max_y - 3)


def render_browser(stdscr, current_path, display, selected, scroll, entries,
                   visible_height, active_pane, playlist, playlist_selected,
                   playlist_scroll):
    """Render the split-pane view: file browser on the left, playlist on the right."""
    stdscr.clear()
    max_y, max_x = stdscr.getmaxyx()

    # ── Column widths ─────────────────────────────────────────────────
    divider_col = max(10, (max_x * 2) // 3)
    browser_width = divider_col - 2          # usable text width in browser pane
    playlist_left = divider_col + 1          # starting x for playlist text
    playlist_width = max(0, max_x - playlist_left - 1)  # usable text width in playlist pane

    browser_is_active = active_pane == "browser"

    # ── Headers ───────────────────────────────────────────────────────
    browser_header = f" Browsing: {current_path} "
    playlist_header = f" Playlist ({len(playlist)} items) "
    br_attr = color_pair(CP_HEADER, curses.A_BOLD | (curses.A_UNDERLINE if browser_is_active else 0))
    pl_attr = color_pair(CP_HEADER, curses.A_BOLD | (curses.A_UNDERLINE if not browser_is_active else 0))

    stdscr.addstr(0, 0, _truncate_to_width(browser_header, browser_width + 2), br_attr)
    if playlist_left < max_x:
        stdscr.addstr(0, playlist_left, _truncate_to_width(playlist_header, playlist_width), pl_attr)

    # ── Divider line ──────────────────────────────────────────────────
    for row in range(0, max_y - 2):
        if divider_col < max_x:
            try:
                stdscr.addch(row, divider_col, curses.ACS_VLINE, curses.A_DIM)
            except curses.error:
                pass

    # ── Browser pane ──────────────────────────────────────────────────
    if not entries:
        stdscr.addstr(1, 2, "(empty)", curses.A_DIM)
    else:
        end = min(len(display), scroll + visible_height)
        for row, idx in enumerate(range(scroll, end), start=1):
            text = _truncate_to_width(display[idx], browser_width)
            entry = entries[idx]

            if idx == selected:
                if browser_is_active:
                    attr = color_pair(CP_SELECTED, curses.A_BOLD)
                else:
                    attr = color_pair(CP_INACTIVE_SEL)
            elif entry.is_dir():
                attr = color_pair(CP_DIR, curses.A_BOLD)
            elif entry.suffix.lower() in AUDIO_EXTENSIONS:
                attr = color_pair(CP_GREEN)
            else:
                attr = curses.A_NORMAL

            try:
                stdscr.addstr(row, 2, text, attr)
            except curses.error:
                pass

    # ── Playlist pane ─────────────────────────────────────────────────
    if not playlist:
        if playlist_left + 2 < max_x:
            try:
                stdscr.addstr(1, playlist_left, "(empty)"[: playlist_width], curses.A_DIM)
            except curses.error:
                pass
    else:
        end = min(len(playlist), playlist_scroll + visible_height)
        for row, idx in enumerate(range(playlist_scroll, end), start=1):
            num = f"{idx + 1:>3}. "
            name = playlist[idx].name
            text = _truncate_to_width(num + name, playlist_width)

            if idx == playlist_selected:
                if not browser_is_active:
                    attr = color_pair(CP_SELECTED, curses.A_BOLD)
                else:
                    attr = color_pair(CP_INACTIVE_SEL)
            elif playlist[idx].suffix.lower() in AUDIO_EXTENSIONS:
                attr = color_pair(CP_GREEN)
            else:
                attr = curses.A_NORMAL

            try:
                stdscr.addstr(row, playlist_left, text, attr)
            except curses.error:
                pass

    stdscr.refresh()


def show_audio_selected(stdscr, entries_count, chosen_name):
    stdscr.addstr(
        entries_count + 2, 0,
        f"Selected audio file: {chosen_name}",
        color_pair(CP_AUDIO_NAME, curses.A_BOLD),
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
            stdscr.addstr(line, 0, message[: max_x - 1], color_pair(CP_STATUS, curses.A_BOLD))
        except curses.error:
            pass
    stdscr.refresh()


def _format_time(seconds):
    if seconds is None:
        return "--:--"
    try:
        total = max(0, int(float(seconds)))
    except (ValueError, TypeError, OverflowError):
        return "--:--"
    minutes, secs = divmod(total, 60)
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
        (label, color_pair(CP_GREEN, bold)),
        (name, color_pair(CP_AUDIO_NAME, bold)),
        (time_text, color_pair(CP_HEADER)),
    ]

    try:
        col = 0
        for text, attr in segments:
            if col >= max_x:
                break
            stdscr.addstr(line, col, text[: max_x - col], attr)
            col += len(text)

        if percent is not None and col + 4 < max_x:
            bar_w = min(20, max_x - col - 2)
            if bar_w > 2:
                filled = max(0, int(bar_w * percent / 100))
                stdscr.addstr(line, col, " ", curses.A_NORMAL)
                col += 1
                if filled:
                    stdscr.addstr(line, col, " " * filled, color_pair(CP_BAR))
    except curses.error:
        pass
