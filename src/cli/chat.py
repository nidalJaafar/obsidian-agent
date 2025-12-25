import shutil
import uuid

from core.rag_session import create_session
from storage.chat_history_store import create_history_store
from input.chat_input import read_user_input
from sessions.chat_sessions import choose_session, restore_session_history, render_history
from ui.chat_ui import (
    clear_last_lines,
    print_banner,
    render_assistant,
    render_sources,
    set_term_width,
    start_typing_indicator,
)


def main():
    print_banner()
    history_store = create_history_store()
    selected_session_id = choose_session(history_store)
    if selected_session_id:
        session = create_session(session_id=selected_session_id)
        restore_session_history(session, history_store)
        render_history(session)
    else:
        session = create_session(session_id=str(uuid.uuid4()))

    while True:
        set_term_width(shutil.get_terminal_size((80, 20)).columns)
        query = read_user_input()
        if not query:
            continue
        if query.lower() in {"exit", "quit"}:
            break

        typing_stop, typing_thread, typing_lines = start_typing_indicator()
        typing_cleared = False
        last_text, artifacts = session.process_query(query)
        if last_text:
            typing_stop.set()
            typing_thread.join(timeout=0.5)
            clear_last_lines(typing_lines)
            typing_cleared = True
            render_assistant(last_text)
        typing_stop.set()
        typing_thread.join(timeout=0.5)
        if not typing_cleared:
            clear_last_lines(typing_lines)
        if artifacts:
            render_sources(artifacts)


if __name__ == "__main__":
    main()
