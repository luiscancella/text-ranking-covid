"""API de busca sobre a coleção TREC-COVID (HO03) usando Elasticsearch."""

import logging
import time
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import dataset, es, evaluation, indexer, search
from .config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")
logging.getLogger("elastic_transport.transport").setLevel(logging.WARNING)

Model = Literal["bm25", "tfidf"]


def _wait_for_elasticsearch(retries: int = 30, delay: float = 2.0) -> bool:
    client = es.get_client()
    for attempt in range(1, retries + 1):
        try:
            if client.ping():
                return True
        except Exception:  # noqa: BLE001
            pass
        log.info("Aguardando Elasticsearch (%d/%d)...", attempt, retries)
        time.sleep(delay)
    return False


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    if settings.auto_index:
        if _wait_for_elasticsearch():
            client = es.get_client()
            if not es.index_exists(client, settings.es_index) or es.doc_count(client, settings.es_index) == 0:
                log.info("Índice '%s' ausente: iniciando indexação automática", settings.es_index)
                indexer.start()
            else:
                log.info("Índice '%s' já existe (%d docs)", settings.es_index, es.doc_count(client, settings.es_index))
        else:
            log.error("Elasticsearch indisponível em %s", settings.elasticsearch_url)
    yield


app = FastAPI(
    title="TREC-COVID Search API",
    description=(
        "Máquina de busca sobre a coleção CORD-19 / TREC-COVID (round 1), "
        "com os modelos Vetorial TF-IDF e BM25 do HO03 indexados no Elasticsearch."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_index() -> None:
    settings = get_settings()
    if not es.index_exists(es.get_client(), settings.es_index):
        raise HTTPException(
            status_code=503,
            detail="Índice ainda não disponível. Consulte GET /index/status ou dispare POST /index.",
        )


@app.get("/", tags=["info"])
def root():
    settings = get_settings()
    return {
        "name": app.title,
        "dataset": settings.dataset_id,
        "index": settings.es_index,
        "models": list(es.MODELS),
        "docs": "/docs",
    }


@app.get("/health", tags=["info"])
def health():
    settings = get_settings()
    client = es.get_client()
    try:
        es_ok = bool(client.ping())
    except Exception:  # noqa: BLE001
        es_ok = False
    exists = es_ok and es.index_exists(client, settings.es_index)
    return {
        "status": "ok" if es_ok else "degraded",
        "elasticsearch": {"url": settings.elasticsearch_url, "reachable": es_ok},
        "index": {
            "name": settings.es_index,
            "exists": exists,
            "docs": es.doc_count(client, settings.es_index) if exists else 0,
        },
        "indexing": indexer.status(),
    }


@app.get("/search", tags=["busca"])
def search_endpoint(
    q: str = Query(..., min_length=1, description="Texto da consulta"),
    model: Model = Query("bm25", description="Modelo de ranqueamento"),
    size: int = Query(10, ge=1, le=100, description="Resultados por página"),
    offset: int = Query(0, ge=0, description="Deslocamento (paginação)"),
    highlight: bool = Query(True, description="Retorna trechos destacados"),
):
    _require_index()
    settings = get_settings()
    if offset + size > settings.max_result_window:
        raise HTTPException(status_code=400, detail=f"offset + size deve ser <= {settings.max_result_window}")
    return search.search(q, model, size, offset, highlight)


@app.get("/documents/{docno}", tags=["busca"])
def document(docno: str):
    _require_index()
    doc = search.get_document(docno)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return doc


@app.get("/topics", tags=["avaliação"])
def topics():
    return {"count": len(dataset.topics()), "topics": dataset.topics()}


@app.get("/evaluate", tags=["avaliação"])
def evaluate(
    model: Literal["bm25", "tfidf", "all"] = Query("all"),
    depth: int = Query(None, ge=1, description="Profundidade do ranking avaliado"),
):
    """Reproduz o pt.Experiment do HO03: MAP, nDCG e cortes @1, @3, @5, @10."""
    _require_index()
    settings = get_settings()
    depth = depth or settings.eval_depth
    if depth > settings.max_result_window:
        raise HTTPException(status_code=400, detail=f"depth deve ser <= {settings.max_result_window}")
    models = list(es.MODELS) if model == "all" else [model]
    results = [evaluation.evaluate_model(m, depth) for m in models]
    return {
        "depth": depth,
        "metrics": evaluation.METRICS,
        "results": [{k: v for k, v in r.items() if k != "per_topic"} for r in results],
        "per_topic": {r["model"]: r["per_topic"] for r in results},
    }


@app.post("/index", status_code=202, tags=["indexação"])
def start_indexing():
    """(Re)indexa toda a coleção em segundo plano."""
    if not indexer.start():
        raise HTTPException(status_code=409, detail="Indexação já em andamento")
    evaluation.clear_cache()
    return {"message": "Indexação iniciada", "status": indexer.status()}


@app.get("/index/status", tags=["indexação"])
def indexing_status():
    settings = get_settings()
    client = es.get_client()
    st = indexer.status()
    try:
        st["docs_in_index"] = es.doc_count(client, settings.es_index)
    except Exception:  # noqa: BLE001
        st["docs_in_index"] = None
    return st
