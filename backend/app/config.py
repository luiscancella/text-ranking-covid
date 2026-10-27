"""Configuração da API lida a partir de variáveis de ambiente."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # URL de conexão com o Elasticsearch (indexador).
    elasticsearch_url: str = "http://localhost:9200"
    # Nome do índice no Elasticsearch.
    es_index: str = "trec-covid-round1"
    # Coleção do ir_datasets usada no HO03.
    dataset_id: str = "cord19/trec-covid/round1"
    # Indexa automaticamente na subida da API caso o índice não exista.
    auto_index: bool = True
    # Tamanho de cada lote enviado ao Elasticsearch durante a indexação.
    index_bulk_size: int = 500
    # Quantidade máxima de documentos recuperados por consulta (from + size).
    max_result_window: int = 60000
    # Profundidade padrão do ranking usada na avaliação (MAP, nDCG).
    eval_depth: int = 1000
    # Origens permitidas no CORS, separadas por vírgula ("*" libera todas).
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
