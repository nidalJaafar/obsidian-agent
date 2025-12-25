import os.path

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.tools import tool

from core.config import get_setting, load_env
from core.rag_store import get_vector_store

load_env()
model = init_chat_model(get_setting("chat_model", required=True))
vector_store = get_vector_store()
vault_path = get_setting("vault_path", required=True)


def summarize_messages(existing_summary, messages):
    """Summarize a list of chat messages into a compact running summary."""
    if not messages:
        return existing_summary

    lines = []
    for message in messages:
        role = message.get("role", "unknown").upper()
        content = message.get("content", "")
        if content:
            lines.append(f"{role}: {content}")
    if not lines:
        return existing_summary

    prompt_text = (
        "You are summarizing a conversation for future context.\n"
        "Keep it concise (under 300 words) and focus on user goals, decisions, "
        "constraints, and key facts.\n\n"
        f"Existing summary:\n{existing_summary or 'None'}\n\n"
        "New conversation excerpt:\n"
        f"{chr(10).join(lines)}\n\n"
        "Updated summary:"
    )
    try:
        response = model.invoke(prompt_text)
    except Exception:
        return existing_summary
    content = getattr(response, "content", response)
    return str(content).strip() or existing_summary



@tool(response_format="content_and_artifact")
def retrieve_context(query: str):
    """Retrieve information to help answer a query by reading full files."""
    retrieved_docs = vector_store.similarity_search(query, k=10)

    unique_paths = set()
    context_parts = []

    for doc in retrieved_docs:
        source_path = doc.metadata.get("source")

        if source_path and source_path not in unique_paths:
            unique_paths.add(source_path)

            try:
                with open(os.path.join(vault_path, source_path), "r", encoding="utf-8") as f:
                    full_content = f.read()

                context_parts.append(
                    f"FILE SOURCE: {source_path}\n"
                    f"{'=' * 30}\n"
                    f"{full_content}\n"
                    f"{'=' * 30}"
                )
            except Exception as e:
                print(f"Error reading file {source_path}: {e}")

    if not context_parts:
        serialized = "No relevant documents found in the vault."
    else:
        serialized = "\n\n".join(context_parts)

    return serialized, retrieved_docs

@tool(response_format="content_and_artifact")
def write_to_vault(file_name: str, content: str):
    """Write content to a specified file in the vault. File name should include spaces if needed and end with .md"""
    full_path = os.path.join(vault_path, "AI Generated", file_name)
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    full_note = ""

    with open(full_path, "w", encoding="utf-8") as f:
        full_note = f"""

Tags: [[AI Generated]]

#🌱

---

{content}

---

        """.strip()
        f.write(full_note)

    return f"Content written to {full_path}", full_note


tools = [retrieve_context, write_to_vault]
prompt = (
    "You are a helpful assistant that has access to a personal vault of notes. "
    "Your primary goal is to answer the user's questions and help them with their tasks. "
    "You have access to two tools:\n"
    "1. `retrieve_context`: Use this tool to find relevant information from the vault. "
    "When you use this tool, you should inform the user that you are searching for information. "
    "2. `write_to_vault`: Use this tool to write new notes to the vault. "
    "You should use this tool when the user asks you to create a new note or when you think it would be helpful to save information for later.\n\n"
    "When answering a question, you should use the following process:\n"
    "1. First, consider if the user's question can be answered from the conversation history. "
    "2. If the question cannot be answered from the history, use the `retrieve_context` tool to find relevant information. "
    "When you use the `retrieve_context` tool, you should generate a search query that is relevant to the user's question and the conversation history. "
    "3. If you are still unable to answer the question, you should inform the user that you were unable to find an answer.\n\n"
    "You should be proactive and ask clarifying questions if the user's query is ambiguous. "
    "Remember to use the conversation history to provide context-aware responses."
)
agent = create_agent(model, tools, system_prompt=prompt)
