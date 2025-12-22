RAG with Gemini and ChromaDB for Obsidian notes with a TUI interface

Step-by-step setup
1) Create config and env files:
   - Copy `config.example.json` to `config.json`.
   - Copy `.env.example` to `.env`.
2) Edit `config.json`:
   - `vault_path`: absolute path to your Obsidian vault.
   - `chroma_persist_dir`: where to store the local Chroma DB (default `./chroma-data`).
   - `embedding_model` and `chat_model`: keep defaults or change as needed.
3) Edit `.env` and set `GOOGLE_API_KEY`.
4) (Optional) Set `RAG_CONFIG_PATH` to point to a different config file:
   - Example: `export RAG_CONFIG_PATH=/path/to/config.json`
5) Install dependencies:
   - `uv sync`

Indexing behavior
- Incremental by default: only new or changed chunks are embedded.
- Stale chunks are removed automatically if a file changes or is deleted.
- Full rebuild: `uv run build_index.py --reindex` deletes the collection and reindexes everything.

Typical workflow
1) Build or update the index:
   - `uv run build_index.py`
2) Run the TUI chat:
   - `uv run chat.py`

Notes
- Chroma runs in embedded mode using `./chroma-data`.
