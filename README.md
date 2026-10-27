# HO03 — Máquina de busca TREC-COVID

Implementação do trabalho HO03 (comparação entre o modelo Vetorial TF-IDF e o
BM25 na coleção CORD-19 / TREC-COVID round 1) como uma máquina de busca na web,
usando o **Elasticsearch** como indexador no lugar do PyTerrier.

```
backend/   projeto 1: API em FastAPI (main.py) + Elasticsearch  -> backend/docker-compose.yml
frontend/  projeto 2: página HTML com o campo de busca (index.html) -> frontend/docker-compose.yml
HO03(1).ipynb  notebook original
```

São dois projetos independentes, cada um com seu `docker-compose.yml`.

## Rodando localmente

```bash
# terminal 1: Elasticsearch + API
cd backend && docker compose up --build

# terminal 2: frontend
cd frontend && docker compose up --build
```

- Frontend: http://localhost:8080
- API: http://localhost:8000 (documentação em http://localhost:8000/docs)

Na primeira execução a API baixa a coleção (~77 MB) e indexa os 51.078
documentos, o que leva cerca de 1 a 2 minutos. A página mostra o progresso.
Os dados ficam salvos em volumes do Docker, então nas próximas execuções não
é preciso indexar de novo.

## Variáveis de ambiente

Backend (`backend/.env.example`):

| Variável | Padrão | Descrição |
|---|---|---|
| `ELASTICSEARCH_URL` | `http://elasticsearch:9200` | URL de conexão com o Elasticsearch |
| `ES_INDEX` | `trec-covid` | nome do índice |
| `EVAL_DEPTH` | `1000` | documentos por consulta usados na avaliação |

Frontend (`frontend/.env.example`):

| Variável | Padrão | Descrição |
|---|---|---|
| `API_URL` | `http://localhost:8000` | URL da API chamada pelo navegador |

## Deploy no Coolify

Crie dois recursos do tipo *Docker Compose* apontando para este repositório:

1. **Backend**: base directory `/backend`, compose `docker-compose.yml`.
   Exponha a porta 8000 em um domínio (ex.: `https://api.seudominio.com`).
2. **Frontend**: base directory `/frontend`, compose `docker-compose.yml`.
   Defina a variável `API_URL` com a URL pública do backend e exponha a porta 80.

## Rotas da API

| Rota | Descrição |
|---|---|
| `GET /search?q=texto&model=bm25|tfidf&size=10` | busca os artigos |
| `GET /evaluate?depth=1000` | MAP e nDCG (@1, @3, @5, @10) dos dois modelos, como no `pt.Experiment` |
| `GET /health` | estado da indexação |

## Como o notebook foi reproduzido

| Notebook (PyTerrier) | API (Elasticsearch) |
|---|---|
| `ir_datasets.load("cord19/trec-covid/round1")` | mesma coleção, consultas e qrels |
| `IterDictIndexer(text_attrs=["title", "abstract"])` | campo `texto` = título + resumo, analisador `english` |
| `Retriever(wmodel="BM25")` | similaridade BM25 (k1 = 1.2, b = 0.75) |
| `Retriever(wmodel="TF_IDF")` | similaridade *scripted* com a fórmula TF_IDF do Terrier |
| `pt.Experiment(...)` | rota `/evaluate` |

Resultados com `depth=51078` (toda a coleção, como no notebook):

| Métrica | TF-IDF (API) | TF-IDF (notebook) | BM25 (API) | BM25 (notebook) |
|---|---|---|---|---|
| MAP | 0,1810 | 0,1804 | 0,1815 | 0,1817 |
| nDCG | 0,5314 | 0,5279 | 0,5307 | 0,5290 |
| nDCG@10 | 0,3822 | 0,3753 | 0,3778 | 0,3766 |

As diferenças pequenas vêm da tokenização (Terrier × Elasticsearch) e dos 33
`docno` duplicados da coleção, que o Elasticsearch sobrescreve.
