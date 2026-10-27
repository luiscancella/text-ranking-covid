"""Consultas ao índice (modelo vetorial TF-IDF e BM25)."""

from . import es
from .config import get_settings

SOURCE_FIELDS = ["docno", "title", "abstract", "doi", "date", "url"]


def _query(q: str, model: str) -> dict:
    return {"match": {es.MODELS[model]: {"query": q, "operator": "or"}}}


def search(q: str, model: str, size: int, offset: int, highlight: bool = True) -> dict:
    settings = get_settings()
    client = es.get_client()
    body: dict = {
        "query": _query(q, model),
        "from": offset,
        "size": size,
        "track_total_hits": True,
        "_source": SOURCE_FIELDS,
    }
    if highlight:
        body["highlight"] = {
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
            "require_field_match": False,
            "fields": {
                "title": {"number_of_fragments": 0},
                "abstract": {"fragment_size": 220, "number_of_fragments": 2},
            },
        }
    resp = client.search(index=settings.es_index, **body)
    hits = resp["hits"]
    results = []
    for rank, hit in enumerate(hits["hits"], start=offset + 1):
        src = hit["_source"]
        hl = hit.get("highlight", {})
        results.append(
            {
                "rank": rank,
                "score": hit["_score"],
                "docno": src["docno"],
                "title": src.get("title", ""),
                "abstract": src.get("abstract", ""),
                "doi": src.get("doi", ""),
                "date": src.get("date", ""),
                "url": src.get("url", ""),
                "highlight": {
                    "title": hl.get("title", [None])[0],
                    "abstract": hl.get("abstract", []),
                },
            }
        )
    return {
        "query": q,
        "model": model,
        "total": hits["total"]["value"],
        "offset": offset,
        "size": size,
        "took_ms": resp["took"],
        "results": results,
    }


def ranking(q: str, model: str, depth: int) -> list[str]:
    """Retorna apenas os docnos ranqueados (usado na avaliação)."""
    settings = get_settings()
    client = es.get_client()
    resp = client.search(
        index=settings.es_index,
        query=_query(q, model),
        size=depth,
        _source=False,
        track_total_hits=False,
    )
    return [hit["_id"] for hit in resp["hits"]["hits"]]


def get_document(docno: str) -> dict | None:
    settings = get_settings()
    client = es.get_client()
    if not client.exists(index=settings.es_index, id=docno):
        return None
    doc = client.get(index=settings.es_index, id=docno, source_includes=SOURCE_FIELDS)
    return doc["_source"]
