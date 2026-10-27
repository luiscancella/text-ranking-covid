"""Acesso à coleção TREC-COVID (round 1) via ir_datasets, como no HO03."""

from functools import lru_cache
from typing import Iterator

import ir_datasets

from .config import get_settings


@lru_cache
def load_dataset():
    return ir_datasets.load(get_settings().dataset_id)


def _doi_url(doi: str) -> str:
    doi = (doi or "").strip()
    return f"https://doi.org/{doi}" if doi else ""


def iter_documents() -> Iterator[dict]:
    """Mesmo gerador do notebook (docno, title, abstract), com metadados extras."""
    for doc in load_dataset().docs_iter():
        yield {
            "docno": str(doc.doc_id),
            "title": doc.title or "",
            "abstract": doc.abstract or "",
            "doi": doc.doi or "",
            "date": doc.date or "",
            "url": _doi_url(doc.doi),
        }


def documents_count() -> int:
    return load_dataset().docs_count()


@lru_cache
def topics() -> list[dict]:
    """Consultas: título de cada tópico (mais descrição e narrativa)."""
    return [
        {
            "qid": str(q.query_id),
            "query": q.title,
            "description": q.description,
            "narrative": q.narrative,
        }
        for q in load_dataset().queries_iter()
    ]


@lru_cache
def qrels() -> dict[str, dict[str, int]]:
    """Julgamentos de relevância: {qid: {docno: label}}."""
    result: dict[str, dict[str, int]] = {}
    for q in load_dataset().qrels_iter():
        result.setdefault(str(q.query_id), {})[str(q.doc_id)] = int(q.relevance)
    return result
