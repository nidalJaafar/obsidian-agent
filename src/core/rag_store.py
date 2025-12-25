from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from core.config import get_setting, load_env


def get_vector_store(persist_directory: str | None = None):
    load_env()
    if persist_directory is None:
        persist_directory = get_setting("chroma_persist_dir", required=True)
    embeddings = GoogleGenerativeAIEmbeddings(
        model=get_setting("embedding_model", required=True)
    )
    return Chroma(
        collection_name="personal_vault",
        embedding_function=embeddings,
        persist_directory=persist_directory,
    )
