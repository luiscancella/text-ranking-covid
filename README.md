# TREC-COVID Search — HO03 como máquina de busca

Implementação do trabalho **HO03** (recuperação de informação sobre a coleção
CORD-19 / TREC-COVID round 1, comparando o modelo **Vetorial TF-IDF** com o
**BM25**) como uma máquina de busca com acesso web:

| Componente | Tecnologia | Função |
|---|---|---|
| `frontend/` | HTML/JS estático servido por nginx | Página com campo de busca que lista os artigos |
| `backend/` | FastAPI (Python) | API que indexa a coleção, executa as consultas e reproduz a avaliação do notebook |
| Elasticsearch 8 | indexador | Índice invertido com os dois modelos de ranqueamento |

O notebook original está em [`HO03(1).ipynb`](<HO03(1).ipynb>).

## Como rodar

Pré-requisitos: Docker e Docker Compose.

```bash
cp .env.example .env        # opcional: ajuste portas e URLs
docker compose up --build
```

Na primeira subida a API baixa a coleção (≈ 77 MB, via `ir_datasets`) e indexa
os 51.078 documentos no Elasticsearch automaticamente. O progresso aparece em
`GET /index/status` e na própria página. Os dados ficam em volumes Docker
(`esdata` e `irdatasets`), então subidas posteriores são imediatas.

| Serviço | URL padrão |
|---|---|
| Frontend | http://localhost:8080 |
| API (Swagger em `/docs`) | http://localhost:8000 |
| Elasticsearch | http://localhost:9200 |

## Variáveis de ambiente

Todas as URLs de conexão são configuráveis por variável de ambiente
(ver [`.env.example`](.env.example)):

| Variável | Serviço | Padrão | Descrição |
|---|---|---|---|
| `ELASTICSEARCH_URL` | api | `http://elasticsearch:9200` | URL de conexão da API com o Elasticsearch |
| `ES_INDEX` | api | `trec-covid-round1` | Nome do índice |
| `DATASET_ID` | api | `cord19/trec-covid/round1` | Coleção do `ir_datasets` |
| `AUTO_INDEX` | api | `true` | Indexa na subida se o índice não existir |
| `EVAL_DEPTH` | api | `1000` | Profundidade padrão do ranking na avaliação |
| `CORS_ORIGINS` | api | `*` | Origens permitidas (separadas por vírgula) |
| `API_URL` | frontend | `http://localhost:8000` | URL da API usada pelo navegador |
| `ES_PORT`, `API_PORT`, `FRONTEND_PORT` | compose | `9200`, `8000`, `8080` | Portas expostas no host |
| `ES_JAVA_OPTS` | elasticsearch | `-Xms1g -Xmx1g` | Heap da JVM |

No frontend, `API_URL` é injetada em tempo de execução: o container gera
`config.js` ao iniciar, então a mesma imagem serve para qualquer ambiente.

## API

| Método | Rota | Descrição |
|---|---|---|
| `GET` | `/search?q=&model=bm25\|tfidf&size=10&offset=0` | Busca com destaque de trechos e paginação |
| `GET` | `/documents/{docno}` | Documento completo |
| `GET` | `/topics` | As 30 consultas (tópicos) do TREC-COVID round 1 |
| `GET` | `/evaluate?model=all&depth=1000` | MAP, nDCG e cortes @1/@3/@5/@10 por modelo (equivalente ao `pt.Experiment`) |
| `POST` | `/index` | (Re)indexa a coleção em segundo plano |
| `GET` | `/index/status` | Progresso da indexação |
| `GET` | `/health` | Estado da API, do Elasticsearch e do índice |

O contrato OpenAPI exportado está em [`docs/openapi.json`](docs/openapi.json)
(também disponível ao vivo em `/openapi.json`).

Exemplo:

```bash
curl "http://localhost:8000/search?q=coronavirus%20origin&model=tfidf&size=3"
```

## Correspondência com o notebook

| Notebook (PyTerrier) | API (Elasticsearch) |
|---|---|
| `ir_datasets.load("cord19/trec-covid/round1")` | `backend/app/dataset.py` (mesma coleção, mesmos tópicos e qrels) |
| `IterDictIndexer(text_attrs=["title", "abstract"])` | campo `content` = título + resumo, analisador `english` (Porter + stopwords), 1 shard |
| `Retriever(wmodel="BM25")` | similaridade `BM25` (k1 = 1.2, b = 0.75, padrões do Terrier) no campo `content` |
| `Retriever(wmodel="TF_IDF")` | similaridade *scripted* com a fórmula `TF_IDF` do Terrier (tf de Robertson × idf) no subcampo `content.tfidf` |
| `pt.Experiment(..., eval_metrics=[map, ndcg, *_cut.k])` | `GET /evaluate` (métricas calculadas com as definições do `trec_eval`) |

Resultados obtidos com `GET /evaluate?depth=51078` (mesma profundidade do
notebook, que recuperava toda a coleção), comparados aos do HO03:

| Métrica | BM25 (API) | BM25 (notebook) | TF-IDF (API) | TF-IDF (notebook) |
|---|---|---|---|---|
| MAP | 0,1815 | 0,1817 | 0,1810 | 0,1804 |
| nDCG | 0,5307 | 0,5290 | 0,5314 | 0,5279 |
| nDCG@10 | 0,3778 | 0,3766 | 0,3822 | 0,3753 |
| MAP@10 | 0,0541 | 0,0544 | 0,0550 | 0,0537 |

As pequenas diferenças vêm da tokenização (Terrier × analisador `english` do
Elasticsearch) e dos 33 `docno` duplicados na coleção, que o Elasticsearch
sobrescreve (51.045 documentos únicos) e que no notebook geraram o erro
`Key 0klupmep is not unique` do Terrier. O padrão `EVAL_DEPTH=1000` torna a
avaliação mais rápida (≈ 2 s); MAP@k e nDCG@k não mudam com a profundidade.

## Deploy

As três imagens são independentes e podem ser publicadas em qualquer
plataforma que rode containers (Railway, Render, Fly.io, VM com Docker etc.):

1. suba um Elasticsearch (container ou serviço gerenciado) e aponte
   `ELASTICSEARCH_URL` da API para ele;
2. publique a API (`backend/`) e configure `CORS_ORIGINS` com o domínio do
   frontend;
3. publique o frontend (`frontend/`) com `API_URL` apontando para a URL pública
   da API.

Para persistência entre deploys mantenha o volume do Elasticsearch; caso
contrário a API reindexa a coleção na próxima subida (`AUTO_INDEX=true`).

## Desenvolvimento local sem Docker (apenas a API)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
ELASTICSEARCH_URL=http://localhost:9200 uvicorn app.main:app --reload
```
