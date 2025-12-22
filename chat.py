from rag_agent import agent

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

try:
    from prompt_toolkit import Application
    from prompt_toolkit.application import get_app_or_none
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout.dimension import Dimension
    from prompt_toolkit.layout import Layout, Window, VSplit, DynamicContainer
    from prompt_toolkit.widgets import Frame
    from prompt_toolkit.layout.controls import DummyControl, BufferControl
except Exception:
    Application = None
    get_app_or_none = None
    Buffer = None
    KeyBindings = None
    Dimension = None
    Layout = None
    Frame = None
    Window = None
    VSplit = None
    DummyControl = None
    DynamicContainer = None
    BufferControl = None

_console = Console() if Console else None
_TERM_WIDTH = None
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _render_markdown_to_text(markdown_text, width=None, color=False):
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


def _strip_ansi(text):
    return _ANSI_RE.sub("", text)


def _truncate_visible(text, width):
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


def _pad_visible(text, width):
    visible = len(_strip_ansi(text))
    if visible >= width:
        return _truncate_visible(text, width)
    return text + (" " * (width - visible))


def _render_latex(text):
    if not LatexNodes2Text:
        return text
    def _convert(match):
        expr = match.group(1) or match.group(2) or ""
        return LatexNodes2Text().latex_to_text(expr)
    text = re.sub(r"\$\$(.+?)\$\$", _convert, text, flags=re.DOTALL)
    text = re.sub(r"\$(.+?)\$", _convert, text)
    return text


def _bubble_width_ratio(ratio, content_len=None):
    term_width = _TERM_WIDTH or shutil.get_terminal_size((80, 20)).columns
    safe_width = max(20, term_width - 2)
    base = int(term_width * ratio)
    if content_len is not None:
        base = max(base, content_len + 4)
    return max(20, min(safe_width, base))


def _format_box_lines(
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
        box_width = min(_bubble_width_ratio(0.7), safe_term_width)
    else:
        box_width = min(box_width, safe_term_width)
    inner_width = max(10, box_width - 4)
    content_text = _stringify_content(content).strip() or "(empty)"
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
    top = _colorize(top, accent)

    lines = [top]
    for line in wrapped:
        if pre_wrapped:
            text = _pad_visible(line, inner_width)
        else:
            text = _pad_visible(line[:inner_width], inner_width)
        if content_color:
            text = _colorize(text, content_color)
        lines.append(f"{pad}│ {text} │")
    bottom = f"{pad}└{'─' * (box_width - 2)}┘"
    lines.append(_colorize(bottom, accent))
    return lines, {
        "pad": pad,
        "inner_width": inner_width,
        "line_count": len(lines),
        "move_up": len(lines) - 1,
    }


def _clear_last_lines(count):
    if count <= 0 or not sys.stdout.isatty():
        return
    for _ in range(count):
        sys.stdout.write("\033[2K\033[1A")
    sys.stdout.write("\033[2K\r")
    sys.stdout.flush()


def _start_typing_indicator():
    stop_event = threading.Event()
    box_width = _bubble_width_ratio(0.2, content_len=len("Typing..."))
    lines, meta = _format_box_lines(
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
            line = _colorize(line, "2;36")
            if sys.stdout.isatty():
                sys.stdout.write(f"\033[{meta['move_up']}A")
                sys.stdout.write("\r" + line)
                sys.stdout.write(f"\033[{meta['move_up']}B")
                sys.stdout.flush()
            time.sleep(0.4)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return stop_event, thread, meta["line_count"]


def _read_user_input():
    global _TERM_WIDTH
    if not Application:
        _TERM_WIDTH = shutil.get_terminal_size((80, 20)).columns
        return input("").strip()

    term_size = shutil.get_terminal_size((80, 20))
    term_width = term_size.columns
    _TERM_WIDTH = term_width
    term_height = term_size.lines
    min_height_needed = 3  # frame border + 1 line
    min_width_needed = 20
    if term_width < min_width_needed or term_height < min_height_needed:
        return input("").strip()

    frame_width = min(_bubble_width_ratio(0.5), max(20, term_width - 2))
    content_width = max(10, frame_width - 2)
    max_rows = max(1, min(6, term_height - 6))
    height_state = {"rows": 1, "max_rows": max_rows}

    required_height = height_state["rows"] + 3
    if term_height < required_height:
        return input("").strip()

    buffer = Buffer(multiline=True)
    buffer_control = BufferControl(
        buffer=buffer,
        focusable=True,
    )
    kb = KeyBindings()

    def _count_wrapped_lines(text, width):
        wrap_width = max(10, width - 2)
        lines = text.splitlines() or [""]
        total = 0
        for line in lines:
            if not line:
                total += 1
                continue
            total += max(1, len(textwrap.wrap(line, width=wrap_width)))
        return max(1, total)

    def _calc_rows():
        rows = min(height_state["max_rows"], _count_wrapped_lines(buffer.text, content_width))
        height_state["rows"] = rows
        return rows

    def _input_frame():
        rows = _calc_rows()
        input_window = Window(
            content=buffer_control,
            width=Dimension.exact(content_width),
            height=Dimension.exact(rows),
            wrap_lines=True,
        )
        return Frame(
            input_window,
            title="YOU",
            width=Dimension.exact(frame_width),
            height=Dimension.exact(rows + 2),
        )

    def _on_change(_):
        app = get_app_or_none() if get_app_or_none else None
        if app:
            app.layout.reset()
            app.invalidate()

    buffer.on_text_changed += _on_change

    @kb.add("enter")
    def _submit(event):
        event.app.exit(result=buffer.text)

    @kb.add("escape", "enter")
    def _newline_alt(event):
        buffer.insert_text("\n")
        _on_change(None)

    @kb.add("c-j")
    def _newline(event):
        buffer.insert_text("\n")
        _on_change(None)

    pad_width = max(0, term_width - frame_width)
    pad = Window(
        content=DummyControl(),
        width=Dimension.exact(pad_width),
    )
    if DynamicContainer:
        input_container = DynamicContainer(_input_frame)
    else:
        input_container = _input_frame()
    layout = Layout(VSplit([pad, input_container]), focused_element=buffer_control)
    app = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
    )
    try:
        return (app.run() or "").strip()
    except Exception:
        return input("").strip()

def _stringify_content(content):
    if isinstance(content, str):
        return _render_latex(content)
    if isinstance(content, list):
        parts = []
        for item in content:
            parts.append(_stringify_content(item))
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        if "text" in content and isinstance(content["text"], str):
            return content["text"]
        return json.dumps(content, ensure_ascii=False, indent=2)
    return str(content)


def _use_color():
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def _colorize(text, code):
    if not _use_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def _render_box(label, content, align="left", accent="36", content_color=None):
    lines, meta = _format_box_lines(label, content, align, accent, content_color)
    print("\n".join(lines))
    return meta["line_count"]


def _render_assistant(text):
    term_width = _TERM_WIDTH or shutil.get_terminal_size((80, 20)).columns
    safe_term_width = max(20, term_width - 2)
    box_width = min(_bubble_width_ratio(0.75), safe_term_width)
    inner_width = max(10, box_width - 4)
    rendered = _render_markdown_to_text(_render_latex(text), width=inner_width, color=True)
    lines, meta = _format_box_lines(
        "ASSISTANT",
        rendered,
        align="left",
        accent="36",
        content_color="2;36",
        box_width=box_width,
        pre_wrapped=True,
    )
    print("\n".join(lines))


def _print_banner():
    term_width = shutil.get_terminal_size((80, 20)).columns
    title = "Obsidian Vault Chat"
    max_width = max(20, term_width)
    inner_width = max_width - 4
    top = "┌" + "─" * (max_width - 2) + "┐"
    mid_title = "│ " + title.center(inner_width) + " │"
    mid_hint = "│ " + "Type 'exit' to quit.".center(inner_width) + " │"
    bottom = "└" + "─" * (max_width - 2) + "┘"
    print(_colorize(top, "34"))
    print(_colorize(mid_title, "1;34"))
    print(mid_hint)
    print(_colorize(bottom, "34"))

def main():
    _print_banner()
    while True:
        global _TERM_WIDTH
        _TERM_WIDTH = shutil.get_terminal_size((80, 20)).columns
        query = _read_user_input()
        if not query:
            continue
        if query.lower() in {"exit", "quit"}:
            break

        typing_stop, typing_thread, typing_lines = _start_typing_indicator()
        typing_cleared = False
        last_text = None
        for event in agent.stream(
                {"messages": [{"role": "user", "content": query}]},
                stream_mode="values",
        ):
            message = event["messages"][-1]
            role = getattr(message, "type", None) or getattr(message, "role", "assistant")
            content = getattr(message, "content", message)
            role_key = role.lower() if isinstance(role, str) else str(role).lower()
            if role_key in {"ai", "assistant"}:
                text = _stringify_content(content).strip()
                if text and text != last_text:
                    last_text = text
                    typing_stop.set()
                    typing_thread.join(timeout=0.5)
                    _clear_last_lines(typing_lines)
                    typing_cleared = True
                    _render_assistant(text)
        typing_stop.set()
        typing_thread.join(timeout=0.5)
        if not typing_cleared:
            _clear_last_lines(typing_lines)


if __name__ == "__main__":
    main()
