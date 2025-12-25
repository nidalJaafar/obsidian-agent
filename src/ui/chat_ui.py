import json
import os
import re
import shutil
import sys
import textwrap
import threading
import time

try:
    from rich.console import Console
    from rich.markdown import Markdown
except Exception:
    Console = None
    Markdown = None

try:
    from pylatexenc.latex2text import LatexNodes2Text
except Exception:
    LatexNodes2Text = None

_TERM_WIDTH = None
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def set_term_width(width):
    global _TERM_WIDTH
    _TERM_WIDTH = width


def render_markdown_to_text(markdown_text, width=None, color=False):
    if not Markdown:
        return markdown_text
    render_width = max(10, width or 80)
    console = Console(
        width=render_width,
        force_terminal=True if color else False,
        color_system="truecolor" if color else None,
        no_color=not color,
        highlight=False,
    )
    with console.capture() as capture:
        console.print(Markdown(markdown_text))
    return capture.get().rstrip()


def strip_ansi(text):
    return _ANSI_RE.sub("", text)


def truncate_visible(text, width):
    if width <= 0:
        return ""
    visible = 0
    out = []
    i = 0
    while i < len(text):
        if text[i] == "\x1b":
            end = text.find("m", i)
            if end == -1:
                break
            out.append(text[i : end + 1])
            i = end + 1
            continue
        if visible >= width:
            break
        out.append(text[i])
        visible += 1
        i += 1
    return "".join(out)


def pad_visible(text, width):
    visible = len(strip_ansi(text))
    if visible >= width:
        return truncate_visible(text, width)
    return text + (" " * (width - visible))


def render_latex(text):
    if not LatexNodes2Text:
        return text
    def _convert(match):
        expr = match.group(1) or match.group(2) or ""
        return LatexNodes2Text().latex_to_text(expr)
    text = re.sub(r"\$\$(.+?)\$\$", _convert, text, flags=re.DOTALL)
    text = re.sub(r"\$(.+?)\$", _convert, text)
    return text


def bubble_width_ratio(ratio, content_len=None):
    term_width = _TERM_WIDTH or shutil.get_terminal_size((80, 20)).columns
    safe_width = max(20, term_width - 2)
    base = int(term_width * ratio)
    if content_len is not None:
        base = max(base, content_len + 4)
    return max(20, min(safe_width, base))


def format_box_lines(
    label,
    content,
    align="left",
    accent="36",
    content_color=None,
    box_width=None,
    pre_wrapped=False,
):
    term_width = _TERM_WIDTH or shutil.get_terminal_size((80, 20)).columns
    safe_term_width = max(20, term_width - 2)
    if box_width is None:
        box_width = min(bubble_width_ratio(0.7), safe_term_width)
    else:
        box_width = min(box_width, safe_term_width)
    inner_width = max(10, box_width - 4)
    content_text = stringify_content(content).strip() or "(empty)"
    if pre_wrapped:
        wrapped = content_text.splitlines() or [""]
    else:
        wrapped = []
        for line in content_text.splitlines() or [""]:
            if line.strip() == "":
                wrapped.append("")
                continue
            wrapped.extend(textwrap.wrap(line, width=inner_width) or [""])

    label_line = f"{label}"[:inner_width]
    total_width = box_width

    indent = 0
    if align == "right":
        indent = max(0, term_width - total_width)
    pad = " " * indent
    label_block = f" {label_line} "
    available = inner_width - len(label_block)
    if available >= 0:
        left = available // 2
        right = available - left
        top = f"{pad}┌{'─' * left}|{label_block}|{'─' * right}┐"
    else:
        top = f"{pad}┌{'─' * (box_width - 2)}┐"
    top = colorize(top, accent)

    lines = [top]
    for line in wrapped:
        if pre_wrapped:
            text = pad_visible(line, inner_width)
        else:
            text = pad_visible(line[:inner_width], inner_width)
        if content_color:
            text = colorize(text, content_color)
        lines.append(f"{pad}│ {text} │")
    bottom = f"{pad}└{'─' * (box_width - 2)}┘"
    lines.append(colorize(bottom, accent))
    return lines, {
        "pad": pad,
        "inner_width": inner_width,
        "line_count": len(lines),
        "move_up": len(lines) - 1,
    }


def clear_last_lines(count):
    if count <= 0 or not sys.stdout.isatty():
        return
    for _ in range(count):
        sys.stdout.write("\033[2K\033[1A")
    sys.stdout.write("\033[2K\r")
    sys.stdout.flush()


def start_typing_indicator():
    stop_event = threading.Event()
    box_width = bubble_width_ratio(0.2, content_len=len("Typing..."))
    lines, meta = format_box_lines(
        "ASSISTANT",
        "Typing",
        align="left",
        accent="36",
        content_color="2;36",
        box_width=box_width,
    )
    print("\n".join(lines))

    def _run():
        dots = 0
        while not stop_event.is_set():
            text = "Typing" + ("." * dots)
            dots = (dots + 1) % 4
            content = text.ljust(meta["inner_width"])
            line = f"{meta['pad']}│ {content} │"
            line = colorize(line, "2;36")
            if sys.stdout.isatty():
                sys.stdout.write(f"\033[{meta['move_up']}A")
                sys.stdout.write("\r" + line)
                sys.stdout.write(f"\033[{meta['move_up']}B")
                sys.stdout.flush()
            time.sleep(0.4)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return stop_event, thread, meta["line_count"]


def stringify_content(content):
    if isinstance(content, str):
        return render_latex(content)
    if isinstance(content, list):
        parts = []
        for item in content:
            parts.append(stringify_content(item))
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        if "text" in content and isinstance(content["text"], str):
            return content["text"]
        return json.dumps(content, ensure_ascii=False, indent=2)
    return str(content)


def use_color():
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def colorize(text, code):
    if not use_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def render_box(label, content, align="left", accent="36", content_color=None):
    lines, meta = format_box_lines(label, content, align, accent, content_color)
    print("\n".join(lines))
    return meta["line_count"]


def render_assistant(text):
    term_width = _TERM_WIDTH or shutil.get_terminal_size((80, 20)).columns
    safe_term_width = max(20, term_width - 2)
    box_width = min(bubble_width_ratio(0.75), safe_term_width)
    inner_width = max(10, box_width - 4)
    rendered = render_markdown_to_text(render_latex(text), width=inner_width, color=True)
    lines, _ = format_box_lines(
        "ASSISTANT",
        rendered,
        align="left",
        accent="36",
        content_color="2;36",
        box_width=box_width,
        pre_wrapped=True,
    )
    print("\n".join(lines))


def print_banner():
    term_width = shutil.get_terminal_size((80, 20)).columns
    title = "Obsidian Vault Chat"
    max_width = max(20, term_width)
    inner_width = max_width - 4
    top = "┌" + "─" * (max_width - 2) + "┐"
    mid_title = "│ " + title.center(inner_width) + " │"
    mid_hint = "│ " + "Type 'exit' to quit.".center(inner_width) + " │"
    bottom = "└" + "─" * (max_width - 2) + "┘"
    print(colorize(top, "34"))
    print(colorize(mid_title, "1;34"))
    print(mid_hint)
    print(colorize(bottom, "34"))


def render_sources(artifacts):
    if not artifacts:
        return
    sources = []
    def _add_source(value):
        if value and value not in sources:
            sources.append(value)

    def _extract_sources(value):
        if hasattr(value, "metadata"):
            _add_source(value.metadata.get("source"))
            return
        if isinstance(value, dict):
            _add_source(value.get("source"))
            return

    for artifact in artifacts:
        if isinstance(artifact, list):
            for item in artifact:
                _extract_sources(item)
            continue
        _extract_sources(artifact)
    if sources:
        render_box("SOURCES", "\n".join(sources), align="left", accent="33")
