import shutil
import textwrap

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

from ui.chat_ui import bubble_width_ratio, set_term_width


def read_user_input():
    if not Application:
        set_term_width(shutil.get_terminal_size((80, 20)).columns)
        return input("").strip()

    term_size = shutil.get_terminal_size((80, 20))
    term_width = term_size.columns
    set_term_width(term_width)
    term_height = term_size.lines
    min_height_needed = 3  # frame border + 1 line
    min_width_needed = 20
    if term_width < min_width_needed or term_height < min_height_needed:
        return input("").strip()

    frame_width = min(bubble_width_ratio(0.5), max(20, term_width - 2))
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
