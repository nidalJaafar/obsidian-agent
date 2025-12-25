from langchain_community.document_loaders import (
    DirectoryLoader,
    UnstructuredMarkdownLoader, TextLoader,
)
from langchain_text_splitters import RecursiveCharacterTextSplitter, MarkdownHeaderTextSplitter

import argparse
import hashlib
from collections import defaultdict

from core.config import get_setting, load_env
from core.rag_store import get_vector_store


def _doc_id(doc) -> str:
    source = doc.metadata.get("source", "")
    start = doc.metadata.get("start_index", "")
    payload = f"{source}:{start}:{doc.page_content}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def main():
    parser = argparse.ArgumentParser(description="Index vault documents into Chroma.")
    parser.add_argument(
        "--reindex",
        action="store_true",
        help="Delete the existing collection and rebuild from scratch.",
    )
    args = parser.parse_args()

    load_env()
    vault_path = get_setting("vault_path", required=True)
    loader = DirectoryLoader(
        vault_path,
        glob="**/*.md",
        loader_cls=TextLoader,
        recursive=True,
        show_progress=True,
    )
    docs = loader.load()

    markdown_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=[("##", "Header 2"), ("###", "Header 3")])

    markdown_splits = []
    for doc in docs:
        markdown_split = markdown_splitter.split_text(doc.page_content)
        for split in markdown_split:
            split.metadata.update(doc.metadata)
        markdown_splits.extend(markdown_split)


    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        add_start_index=True,
    )
    all_splits = text_splitter.split_documents(markdown_splits)

    vector_store = get_vector_store()
    if args.reindex:
        vector_store.delete_collection()
        vector_store = get_vector_store()

    existing_ids = set()
    existing_by_source = defaultdict(set)
    if vector_store._collection.count() > 0:
        result = vector_store._collection.get(include=["metadatas"])
        ids = result.get("ids", [])
        metadatas = result.get("metadatas", [])
        for doc_id, metadata in zip(ids, metadatas):
            existing_ids.add(doc_id)
            source = None
            if metadata:
                source = metadata.get("source")
            existing_by_source[source].add(doc_id)

    new_docs = []
    new_ids = []
    new_by_source = defaultdict(set)
    for doc in all_splits:
        doc_id = _doc_id(doc)
        source = doc.metadata.get("source")
        new_by_source[source].add(doc_id)
        if doc_id not in existing_ids and doc_id not in new_ids:
            new_docs.append(doc)
            new_ids.append(doc_id)

    stale_ids = []
    for source, ids in existing_by_source.items():
        current_ids = new_by_source.get(source)
        if not current_ids:
            stale_ids.extend(ids)
            continue
        stale_ids.extend(list(ids - current_ids))

    deleted_count = 0
    if stale_ids:
        for batch in _chunked(stale_ids, 200):
            vector_store._collection.delete(ids=batch)
            deleted_count += len(batch)

    if not new_docs:
        if deleted_count == 0:
            print("No changes detected.")
        else:
            print(f"Removed {deleted_count} stale chunks from Chroma.")
        return

    document_ids = vector_store.add_documents(documents=new_docs, ids=new_ids)
    print(f"Added {len(document_ids)} chunks to Chroma.")
    if deleted_count:
        print(f"Removed {deleted_count} stale chunks from Chroma.")


if __name__ == "__main__":
    main()
