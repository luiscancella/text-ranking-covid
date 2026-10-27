"""Cliente e definição do índice no Elasticsearch.

O índice reproduz o processo do HO03: título e resumo são concatenados em um
único campo textual (``content``), com stemming de Porter e remoção de
stopwords (analisador ``english``), e dois modelos de ranqueamento:

* ``bm25``  -> similaridade BM25 nativa (k1 = 1.2, b = 0.75, como no Terrier);
* ``tfidf`` -> similaridade *scripted* com a fórmula do modelo TF_IDF do
  Terrier (tf de Robertson x idf), aplicada ao subcampo ``content.tfidf``.

Um único shard garante estatísticas globais de coleção (idf, avgdl), como em
um índice Terrier.
"""

from functools import lru_cache

from elasticsearch import Elasticsearch

from .config import get_settings

MODELS = {"bm25": "content", "tfidf": "content.tfidf"}

# Fórmula do org.terrier.matching.models.TF_IDF (k_1 = 1.2, b = 0.75):
#   Robertson_tf = k_1 * tf / (tf + k_1 * (1 - b + b * dl / avgdl))
#   idf          = log(N / df + 1)
#   score        = keyFrequency * Robertson_tf * idf
TERRIER_TFIDF_SCRIPT = """
double k1 = 1.2;
double b = 0.75;
double tf = doc.freq;
double dl = doc.length;
double avgdl = (double) field.sumTotalTermFreq / (double) field.docCount;
double robertsonTf = k1 * tf / (tf + k1 * (1.0 - b + b * dl / avgdl));
double idf = Math.log((double) field.docCount / (double) term.docFreq + 1.0);
return query.boost * robertsonTf * idf;
"""


def index_definition(max_result_window: int) -> dict:
    return {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "index": {"max_result_window": max_result_window},
            "similarity": {
                "terrier_bm25": {"type": "BM25", "k1": 1.2, "b": 0.75},
                "terrier_tfidf": {
                    "type": "scripted",
                    "script": {"source": TERRIER_TFIDF_SCRIPT},
                },
            },
        },
        "mappings": {
            "properties": {
                "docno": {"type": "keyword"},
                "title": {"type": "text", "analyzer": "english"},
                "abstract": {"type": "text", "analyzer": "english"},
                "doi": {"type": "keyword"},
                "date": {"type": "keyword"},
                "url": {"type": "keyword"},
                "content": {
                    "type": "text",
                    "analyzer": "english",
                    "similarity": "terrier_bm25",
                    "fields": {
                        "tfidf": {
                            "type": "text",
                            "analyzer": "english",
                            "similarity": "terrier_tfidf",
                        }
                    },
                },
            }
        },
    }


@lru_cache
def get_client() -> Elasticsearch:
    settings = get_settings()
    return Elasticsearch(settings.elasticsearch_url, request_timeout=120)


def index_exists(client: Elasticsearch, name: str) -> bool:
    return bool(client.indices.exists(index=name))


def create_index(client: Elasticsearch, name: str, max_result_window: int) -> None:
    if index_exists(client, name):
        client.indices.delete(index=name)
    client.indices.create(index=name, **index_definition(max_result_window))


def doc_count(client: Elasticsearch, name: str) -> int:
    if not index_exists(client, name):
        return 0
    client.indices.refresh(index=name)
    return int(client.count(index=name)["count"])
