# Enterprise Knowledge Copilot

Enterprise Knowledge Copilot is a multi-tenant RAG platform for enterprise knowledge assistants.

It includes:

- Platform admin console
- Tenant admin console
- Front chat workspace
- Multi-tenant knowledge isolation
- Hybrid retrieval with BM25 + vector search
- Rerank and retrieval trace explanation
- Session-based chat history
- Model routing, key pool rotation, and fallback
- Guardrails, logs, evaluations, and scheduler

## Tech Stack

- Python
- FastAPI
- SQLite
- Qdrant
- LangGraph
- HTML / TailwindCSS / SSE

## Local Run

1. Create and activate a virtual environment
2. Install dependencies from `requirements.txt`
3. Configure API keys with `.env` or `config/api_keys.txt`
4. Start the app:

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 6090
```

## Notes

- Runtime secrets are not committed.
- Local database, vector store, and tenant private data are ignored by git.
- Tenant knowledge and API keys should be configured locally before testing.
