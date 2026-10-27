"""
API de busca do HO03 (TREC-COVID round 1) usando Elasticsearch como indexador.

Mesmos passos do notebook:
  1. carrega a coleção com ir_datasets (documentos, consultas e qrels);
  2. indexa título + resumo;
  3. recupera documentos com o modelo vetorial TF-IDF e com o BM25;
  4. avalia os dois modelos com MAP e nDCG (@1, @3, @5, @10).
"""

import math
import os
import threading
import time

import ir_datasets
from elasticsearch import Elasticsearch, helpers
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ----- configuração por variáveis de ambiente -----
ELASTICSEARCH_URL = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
INDEX = os.getenv("ES_INDEX", "trec-covid")
DATASET = os.getenv("DATASET_ID", "cord19/trec-covid/round1")
EVAL_DEPTH = int(os.getenv("EVAL_DEPTH", "1000"))

# Campo usado por cada modelo de ranqueamento.
MODELOS = {"bm25": "texto", "tfidf": "texto.tfidf"}

# Fórmula do TF_IDF do Terrier (tf de Robertson * idf), usada no notebook.
TFIDF_SCRIPT = """
double k1 = 1.2; double b = 0.75;
double avgdl = (double) field.sumTotalTermFreq / field.docCount;
double tf = k1 * doc.freq / (doc.freq + k1 * (1 - b + b * doc.length / avgdl));
double idf = Math.log((double) field.docCount / term.docFreq + 1);
return query.boost * tf * idf;
"""

MAPEAMENTO = {
    "settings": {
        "number_of_shards": 1,
        "index.max_result_window": 60000,
        "similarity": {
            "bm25": {"type": "BM25", "k1": 1.2, "b": 0.75},
            "tfidf": {"type": "scripted", "script": {"source": TFIDF_SCRIPT}},
        },
    },
    "mappings": {
        "properties": {
            "docno": {"type": "keyword"},
            "title": {"type": "text"},
            "abstract": {"type": "text"},
            "doi": {"type": "keyword"},
            "date": {"type": "keyword"},
            # título + resumo, com stemming e stopwords (analisador english),
            # indexado duas vezes: uma com BM25 e outra com TF-IDF.
            "texto": {
                "type": "text",
                "analyzer": "english",
                "similarity": "bm25",
                "fields": {"tfidf": {"type": "text", "analyzer": "english", "similarity": "tfidf"}},
            },
        }
    },
}

app = FastAPI(title="TREC-COVID Search API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

es = Elasticsearch(ELASTICSEARCH_URL, request_timeout=120)
dataset = ir_datasets.load(DATASET)
status = {"estado": "aguardando", "indexados": 0, "total": 0}


# ----- indexação -----
def documentos():
    for doc in dataset.docs_iter():
        yield {
            "_index": INDEX,
            "_id": doc.doc_id,
            "docno": doc.doc_id,
            "title": doc.title or "",
            "abstract": doc.abstract or "",
            "doi": doc.doi or "",
            "date": doc.date or "",
            "texto": f"{doc.title or ''} {doc.abstract or ''}",
        }


def indexar():
    status.update(estado="indexando", indexados=0, total=dataset.docs_count())
    if es.indices.exists(index=INDEX):
        es.indices.delete(index=INDEX)
    es.indices.create(index=INDEX, **MAPEAMENTO)
    for ok, _ in helpers.streaming_bulk(es, documentos(), chunk_size=500):
        status["indexados"] += int(ok)
    es.indices.refresh(index=INDEX)
    status["estado"] = "pronto"


@app.on_event("startup")
def startup():
    # espera o Elasticsearch subir e indexa a coleção caso o índice não exista
    for _ in range(60):
        if es.ping():
            break
        time.sleep(2)
    if es.indices.exists(index=INDEX) and es.count(index=INDEX)["count"] > 0:
        total = es.count(index=INDEX)["count"]
        status.update(estado="pronto", indexados=total, total=total)
    else:
        threading.Thread(target=indexar, daemon=True).start()


# ----- rotas -----
@app.get("/health")
def health():
    return {"elasticsearch": ELASTICSEARCH_URL, "indice": INDEX, **status}


@app.get("/search")
def search(q: str, model: str = "bm25", size: int = 10):
    if model not in MODELOS:
        raise HTTPException(400, "model deve ser 'bm25' ou 'tfidf'")
    if status["estado"] != "pronto":
        raise HTTPException(503, "Índice ainda não está pronto")
    resp = es.search(index=INDEX, query={"match": {MODELOS[model]: q}}, size=size, track_total_hits=True)
    return {
        "query": q,
        "model": model,
        "total": resp["hits"]["total"]["value"],
        "results": [
            {
                "rank": i,
                "score": hit["_score"],
                "docno": hit["_source"]["docno"],
                "title": hit["_source"]["title"],
                "abstract": hit["_source"]["abstract"],
                "date": hit["_source"]["date"],
                "url": f"https://doi.org/{hit['_source']['doi']}" if hit["_source"]["doi"] else "",
            }
            for i, hit in enumerate(resp["hits"]["hits"], start=1)
        ],
    }


# ----- avaliação (mesmas métricas do pt.Experiment do notebook) -----
def precisao_media(ranking, rels, k=None):
    docs = ranking[:k] if k else ranking
    relevantes = sum(1 for v in rels.values() if v > 0)
    acertos, soma = 0, 0.0
    for i, d in enumerate(docs, start=1):
        if rels.get(d, 0) > 0:
            acertos += 1
            soma += acertos / i
    return soma / relevantes if relevantes else 0.0


def ndcg(ranking, rels, k=None):
    docs = ranking[:k] if k else ranking
    ideal = sorted(rels.values(), reverse=True)
    ideal = ideal[:k] if k else ideal
    dcg = sum(rels.get(d, 0) / math.log2(i + 1) for i, d in enumerate(docs, start=1))
    idcg = sum(g / math.log2(i + 1) for i, g in enumerate(ideal, start=1))
    return dcg / idcg if idcg else 0.0


@app.get("/evaluate")
def evaluate(depth: int = EVAL_DEPTH):
    if status["estado"] != "pronto":
        raise HTTPException(503, "Índice ainda não está pronto")
    topics = [(q.query_id, q.title) for q in dataset.queries_iter()]
    qrels = {}
    for qrel in dataset.qrels_iter():
        qrels.setdefault(qrel.query_id, {})[qrel.doc_id] = qrel.relevance

    resultados = {}
    for model, campo in MODELOS.items():
        metricas = {m: 0.0 for m in ["map", "ndcg"] + [f"{m}@{k}" for m in ("map", "ndcg") for k in (1, 3, 5, 10)]}
        for qid, query in topics:
            resp = es.search(index=INDEX, query={"match": {campo: query}}, size=depth, source=False)
            ranking = [hit["_id"] for hit in resp["hits"]["hits"]]
            rels = qrels.get(qid, {})
            metricas["map"] += precisao_media(ranking, rels)
            metricas["ndcg"] += ndcg(ranking, rels)
            for k in (1, 3, 5, 10):
                metricas[f"map@{k}"] += precisao_media(ranking, rels, k)
                metricas[f"ndcg@{k}"] += ndcg(ranking, rels, k)
        resultados[model] = {m: round(v / len(topics), 4) for m, v in metricas.items()}
    return {"depth": depth, "topics": len(topics), "resultados": resultados}
