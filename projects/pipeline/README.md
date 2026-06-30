# HN Summary Pipeline

A data pipeline that scrapes Hacker News top stories, summarizes them with a local LLM (Ollama), stores results in SQLite, and serves them via a FastAPI endpoint.

## Architecture

```
Hacker News API → hn_client.py → pipeline.py → SQLite (stories.db)
                                                         ↑
                                              llm_client.py (Ollama)
                                                         ↓
                                              FastAPI → GET /stories
```

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Install and start [Ollama](https://ollama.com/):
   ```bash
   ollama serve
   ollama pull llama3.2
   ```

3. Run the API server:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

4. Trigger the pipeline:
   ```bash
   curl -X POST http://localhost:8000/pipeline/run
   ```

5. View stories:
   ```bash
   curl http://localhost:8000/stories
   ```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API info |
| GET | `/health` | Health check |
| GET | `/stories` | List top stories (query: `limit`) |
| GET | `/stories/{id}` | Get a single story |
| POST | `/pipeline/run` | Trigger fetch + summarize pipeline |

## Configuration

Environment variables (optional):

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3.2` | Model to use for summarization |

## Project Structure

```
projects/pipeline/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app & lifespan
│   ├── models.py            # Pydantic schemas
│   ├── database.py          # SQLite connection & CRUD
│   ├── routers/
│   │   └── stories.py       # /stories endpoints
│   └── services/
│       ├── hn_client.py     # Hacker News API client
│       ├── llm_client.py    # Ollama LLM client
│       └── pipeline.py      # Pipeline orchestrator
├── data/
│   └── stories.db           # SQLite database (auto-created)
├── requirements.txt
└── README.md
```
