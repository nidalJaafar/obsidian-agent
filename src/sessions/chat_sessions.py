import shutil

from ui.chat_ui import (
    bubble_width_ratio,
    format_box_lines,
    render_assistant,
    render_box,
    render_latex,
    render_markdown_to_text,
)


def render_session_menu(sessions):
    lines = ["0) New chat"]
    for idx, row in enumerate(sessions, start=1):
        session_id = row[0]
        last_at = row[2] if len(row) > 2 else ""
        title = row[3] if len(row) > 3 else ""
        label = format_session_label(title, session_id)
        lines.append(f"{idx}) {label} (last: {last_at})")
    render_box("SESSIONS", "\n".join(lines), align="left", accent="35")


def choose_session(history_store, limit=10):
    if not history_store:
        return None
    sessions = history_store.list_sessions(limit=limit, offset=0)
    if not sessions:
        return None
    render_session_menu(sessions)
    choice = input("Select session number (or Enter for new): ").strip().lower()
    if not choice or choice in {"0", "n", "new"}:
        return None
    if choice.isdigit():
        index = int(choice) - 1
        if 0 <= index < len(sessions):
            return sessions[index][0]
        return None
    return choice


def format_session_label(title, session_id, max_len=48):
    text = (title or "").strip()
    if not text:
        return session_id
    text = " ".join(text.split())
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def restore_session_history(session, history_store):
    if not history_store:
        return
    state = session._load_state()
    if state.get("history"):
        return
    limit = getattr(session, "_history_max_messages", 30)
    if hasattr(history_store, "get_recent_messages"):
        rows = history_store.get_recent_messages(session._session_id, limit=limit)
    else:
        rows = history_store.get_messages(session._session_id, limit=limit, offset=0)
    history = [{"role": role, "content": content} for role, content, _ in rows]
    if history:
        session._save_state(history, state.get("summary", ""))


def render_history(session):
    state = session._load_state()
    history = state.get("history", [])
    if not history:
        return
    render_box("HISTORY", f"{len(history)} messages", align="left", accent="90")
    for entry in history:
        role = entry.get("role", "")
        content = entry.get("content", "")
        if role == "assistant":
            render_assistant(content)
        elif role == "user":
            term_width = shutil.get_terminal_size((80, 20)).columns
            safe_term_width = max(20, term_width - 2)
            box_width = min(bubble_width_ratio(0.6), safe_term_width)
            inner_width = max(10, box_width - 4)
            rendered = render_markdown_to_text(
                render_latex(content),
                width=inner_width,
                color=False,
            )
            lines, _ = format_box_lines(
                "YOU",
                rendered,
                align="right",
                accent="35",
                content_color=None,
                box_width=box_width,
                pre_wrapped=True,
            )
            print("\n".join(lines))
