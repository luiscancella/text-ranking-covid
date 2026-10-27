"""Indexação da coleção no Elasticsearch, executada em segundo plano."""

import logging
import threading
import time
from datetime import datetime, timezone

from elasticsearch import helpers

from . import dataset, es
from .config import get_settings

log = logging.getLogger(__name__)

_lock = threading.Lock()
_status: dict = {
    "state": "idle",  # idle | running | done | error
    "indexed": 0,
    "total": None,
    "started_at": None,
    "finished_at": None,
    "elapsed_seconds": None,
    "error": None,
}


def status() -> dict:
    with _lock:
        snapshot = dict(_status)
    if snapshot["state"] == "running" and snapshot["started_at"]:
        snapshot["elapsed_seconds"] = round(time.time() - snapshot["_t0"], 1)
    snapshot.pop("_t0", None)
    return snapshot


def is_running() -> bool:
    with _lock:
        return _status["state"] == "running"


def _actions(index_name: str):
    for doc in dataset.iter_documents():
        yield {
            "_op_type": "index",
            "_index": index_name,
            "_id": doc["docno"],
            "_source": {**doc, "content": f"{doc['title']} {doc['abstract']}".strip()},
        }


def _run() -> None:
    settings = get_settings()
    client = es.get_client()
    t0 = time.time()
    try:
        total = dataset.documents_count()
        with _lock:
            _status["total"] = total
        es.create_index(client, settings.es_index, settings.max_result_window)
        # Desliga o refresh durante a carga para acelerar o bulk.
        client.indices.put_settings(index=settings.es_index, settings={"index.refresh_interval": "-1"})
        indexed = 0
        for ok, item in helpers.streaming_bulk(
            client,
            _actions(settings.es_index),
            chunk_size=settings.index_bulk_size,
            raise_on_error=False,
            max_retries=3,
        ):
            if not ok:
                log.warning("Falha ao indexar documento: %s", item)
                continue
            indexed += 1
            if indexed % settings.index_bulk_size == 0:
                with _lock:
                    _status["indexed"] = indexed
        client.indices.put_settings(index=settings.es_index, settings={"index.refresh_interval": "1s"})
        client.indices.refresh(index=settings.es_index)
        with _lock:
            _status.update(
                state="done",
                indexed=indexed,
                finished_at=datetime.now(timezone.utc).isoformat(),
                elapsed_seconds=round(time.time() - t0, 1),
            )
        log.info("Indexação concluída: %d documentos em %.1fs", indexed, time.time() - t0)
    except Exception as exc:  # noqa: BLE001
        log.exception("Erro na indexação")
        with _lock:
            _status.update(
                state="error",
                error=str(exc),
                finished_at=datetime.now(timezone.utc).isoformat(),
                elapsed_seconds=round(time.time() - t0, 1),
            )


def start() -> bool:
    """Inicia a indexação em uma thread. Retorna False se já estiver rodando."""
    with _lock:
        if _status["state"] == "running":
            return False
        _status.update(
            state="running",
            indexed=0,
            total=None,
            started_at=datetime.now(timezone.utc).isoformat(),
            finished_at=None,
            elapsed_seconds=None,
            error=None,
            _t0=time.time(),
        )
    threading.Thread(target=_run, name="indexer", daemon=True).start()
    return True
