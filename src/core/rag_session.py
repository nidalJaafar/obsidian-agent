import json
import uuid

from core.config import get_setting
from core.rag_agent import agent, summarize_messages
from storage.chat_history_store import create_history_store

try:
    import redis
except Exception:
    redis = None


class InMemorySessionStore:
    def __init__(self):
        self._data = {}

    def load(self, session_id):
        return self._data.get(session_id, {"history": [], "summary": ""})

    def save(self, session_id, state):
        self._data[session_id] = state


class RedisSessionStore:
    def __init__(
            self,
            host="localhost",
            port=6379,
            db=0,
            prefix="rag:session:",
    ):
        self._client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        self._prefix = prefix


    def load(self, session_id):
        key = self._key(session_id)
        raw = self._client.get(key)
        if not raw:
            return {"history": [], "summary": ""}
        try:
            return json.loads(raw)
        except Exception:
            return {"history": [], "summary": ""}


    def save(self, session_id, state):
        key = self._key(session_id)
        payload = json.dumps(state)
        self._client.set(key, payload)


    def _key(self, session_id):
        return f"{self._prefix}{session_id}"


class RAGSession:
    def __init__(
            self,
            session_id="default",
            store=None,
            history_store=None,
            history_max_messages=30,
    ):
        self._session_id = session_id
        self._store = store or InMemorySessionStore()
        self._history_store = history_store
        self._history_max_messages = history_max_messages

    def process_query(self, query):
        state = self._load_state()
        history = state["history"]
        summary = state["summary"]

        history.append({"role": "user", "content": query})
        self._persist_message("user", query)
        history, summary = self._maybe_summarize(history, summary)

        messages = []
        if summary:
            messages.append(
                {
                    "role": "system",
                    "content": f"Conversation summary:\n{summary}",
                }
            )
        messages.extend(history)

        last_text = None
        artifacts = []
        for event in agent.stream(
                {"messages": messages},
                stream_mode="values",
        ):
            message = event["messages"][-1]
            content = getattr(message, "content", message)
            if hasattr(message, "tool_calls") and message.tool_calls:
                artifacts.extend(message.tool_calls)
            if hasattr(message, "artifact") and message.artifact:
                artifacts.append(message.artifact)
            role = getattr(message, "type", None) or getattr(message, "role", "assistant")
            role_key = role.lower() if isinstance(role, str) else str(role).lower()
            if role_key in {"ai", "assistant"} and content:
                text = _extract_text(content).strip()
                if text:
                    last_text = text
        if last_text:
            history.append({"role": "assistant", "content": last_text})
            self._persist_message("assistant", last_text)
            history, summary = self._maybe_summarize(history, summary)

        self._save_state(history, summary)
        return last_text or "", artifacts

    def _load_state(self):
        state = self._store.load(self._session_id)
        history = list(state.get("history", []))
        summary = state.get("summary", "")
        return {"history": history, "summary": summary}

    def _save_state(self, history, summary):
        self._store.save(self._session_id, {"history": history, "summary": summary})

    def _maybe_summarize(self, history, summary):
        if len(history) <= self._history_max_messages:
            return history, summary
        to_summarize = history[:-self._history_max_messages]
        summary = summarize_messages(summary, to_summarize)
        history = history[-self._history_max_messages:]
        return history, summary

    def _persist_message(self, role, content):
        if not self._history_store:
            return
        self._history_store.append_message(self._session_id, role, content)


def _extract_text(content):
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
                continue
            if isinstance(part, dict):
                text = part.get("text")
                if text:
                    parts.append(str(text))
        return "".join(parts)
    if isinstance(content, dict):
        text = content.get("text")
        if text:
            return str(text)
    return str(content)


def create_session(session_id=str(uuid.uuid4())):
    history_max_messages = get_setting("history_max_messages", default=30)
    store_type = get_setting("session_store", default="memory")
    if store_type == "redis":
        store = RedisSessionStore(
            host=get_setting("redis_host", default="localhost"),
            port=get_setting("redis_port", default=6379),
            db=get_setting("redis_db", default=0),
            prefix=get_setting("redis_prefix", default="rag:session:"),
        )
    else:
        store = InMemorySessionStore()
    history_store = create_history_store()
    return RAGSession(
        session_id=session_id,
        store=store,
        history_store=history_store,
        history_max_messages=history_max_messages,
    )
