# HN Pipeline

Scrapes Hacker News top stories, summarizes them with a local LLM (Ollama),
stores results in SQLite, and serves them via a FastAPI endpoint.

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Install Ollama and pull the model
ollama pull llama3.2
```

## Usage

### Run the pipeline (scrape + summarize + save)

```bash
python -m app.pipeline
```

Options:
```bash
python -m app.pipeline --limit 50       # Fetch 50 stories instead of 30
python -m app.pipeline --no-summary     # Skip LLM summarization
```

### Serve the API

```bash
uvicorn app.api:app --reload --host 0.0.0.0 --port 8000
```

- API docs: http://localhost:8000/docs
- Stories endpoint: `GET /stories?limit=30`

## Project Structure

```
hn-pipeline/
├── app/
│   ├── __init__.py
│   ├── scraper.py      # HN API client (async)
│   ├── summarizer.py   # Ollama LLM summarizer
│   ├── database.py     # SQLite storage layer
│   ├── api.py          # FastAPI endpoints
│   └── pipeline.py     # Orchestrator script
├── data/
│   └── hn_stories.db   # SQLite database (auto-created)
├── requirements.txt
└── README.md
```
