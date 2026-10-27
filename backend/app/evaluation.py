"""Avaliação dos modelos com as métricas do HO03 (MAP, nDCG e cortes @k).

As definições seguem o trec_eval (usado pelo pt.Experiment / ir_measures):

* map / map_cut.k : média das precisões nas posições dos documentos relevantes
  (label > 0), dividida pelo total de relevantes do tópico;
* ndcg / ndcg_cut.k : ganho linear (label) com desconto log2(rank + 1),
  normalizado pelo DCG do ranking ideal.
"""

import math
import threading
from typing import Iterable

from . import dataset, search

CUTS = (1, 3, 5, 10)
METRICS = (
    ["map"]
    + [f"map_cut.{k}" for k in CUTS]
    + ["ndcg"]
    + [f"ndcg_cut.{k}" for k in CUTS]
)

_cache: dict[tuple[str, int], dict] = {}
_cache_lock = threading.Lock()


def average_precision(ranked: list[str], rels: dict[str, int], cutoff: int | None = None) -> float:
    relevant_total = sum(1 for v in rels.values() if v > 0)
    if relevant_total == 0:
        return 0.0
    docs = ranked if cutoff is None else ranked[:cutoff]
    hits = 0
    precision_sum = 0.0
    for i, docno in enumerate(docs, start=1):
        if rels.get(docno, 0) > 0:
            hits += 1
            precision_sum += hits / i
    return precision_sum / relevant_total


def _dcg(gains: Iterable[int]) -> float:
    return sum(g / math.log2(i + 1) for i, g in enumerate(gains, start=1) if g > 0)


def ndcg(ranked: list[str], rels: dict[str, int], cutoff: int | None = None) -> float:
    docs = ranked if cutoff is None else ranked[:cutoff]
    ideal = sorted((v for v in rels.values() if v > 0), reverse=True)
    if cutoff is not None:
        ideal = ideal[:cutoff]
    idcg = _dcg(ideal)
    if idcg == 0:
        return 0.0
    return _dcg(rels.get(d, 0) for d in docs) / idcg


def evaluate_model(model: str, depth: int) -> dict:
    key = (model, depth)
    with _cache_lock:
        if key in _cache:
            return _cache[key]

    all_qrels = dataset.qrels()
    per_topic: list[dict] = []
    for topic in dataset.topics():
        rels = all_qrels.get(topic["qid"], {})
        ranked = search.ranking(topic["query"], model, depth)
        row = {"qid": topic["qid"], "query": topic["query"], "map": average_precision(ranked, rels)}
        for k in CUTS:
            row[f"map_cut.{k}"] = average_precision(ranked, rels, k)
        row["ndcg"] = ndcg(ranked, rels)
        for k in CUTS:
            row[f"ndcg_cut.{k}"] = ndcg(ranked, rels, k)
        per_topic.append(row)

    n = len(per_topic) or 1
    aggregate = {m: round(sum(r[m] for r in per_topic) / n, 4) for m in METRICS}
    result = {
        "model": model,
        "name": "Vetorial TF-IDF" if model == "tfidf" else "BM25",
        "depth": depth,
        "topics": len(per_topic),
        "metrics": aggregate,
        "per_topic": [{**r, **{m: round(r[m], 4) for m in METRICS}} for r in per_topic],
    }
    with _cache_lock:
        _cache[key] = result
    return result


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
