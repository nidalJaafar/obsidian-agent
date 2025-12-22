import os.path

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.tools import tool

from config import get_setting, load_env
from rag_store import get_vector_store

load_env()
model = init_chat_model(get_setting("chat_model", required=True))
vector_store = get_vector_store()
vault_path = get_setting("vault_path", required=True)


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
    "You have access to a tool that retrieves context from a personal vault, and a tool that writes notes to the vault. "
    "Use the retrieve_context tool to help answer user queries, and the write_to_vault tool to create new notes as needed. "
)
agent = create_agent(model, tools, system_prompt=prompt)
