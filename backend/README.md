# backend

The Python service. The import root is this folder, so the package is imported as `ai_sre`
(`pytest.ini` and the commands below add it to the path).

```
backend/
├── ai_sre/
│   ├── agents/        graph.py   planner -> log analysis -> fix proposer -> verifier (LangGraph)
│   │                  runner.py  runs the graph for an alert and saves the incident
│   ├── api/           main.py    FastAPI app: incidents, approve, reject, execute, analyze (SQLite)
│   ├── executor/      executor.py  runs an approved restart/scale and verifies the rollout
│   ├── mcp_servers/   kubernetes/  github/  observability/   tool servers the agent calls over MCP
│   └── rag/           chunk_runbooks.py -> embed_runbooks.py -> load_qdrant.py, evaluate_retrieval.py
├── tests/             pytest suite (tests marked `live` need a cluster, Qdrant, and LLM keys)
├── requirements.txt   full dependencies: agents, RAG, ML libraries
├── requirements-api.txt  slim set for the Docker image
├── Dockerfile         API-only image, built with backend/ as the context (see ../render.yaml)
└── .dockerignore
```

## Run

From the repository root:

```powershell
uvicorn ai_sre.api.main:app --app-dir backend --port 8000 --env-file .env
```

The incident database is created at `backend/ai_sre/api/ai_sre.db` (git-ignored); set `AI_SRE_DB_PATH` to move it.

## Build the runbook index

Reads `data/runbooks/void/` (public postmortems, not committed) and `knowledge/runbooks/` (team runbooks):

```powershell
python backend/ai_sre/rag/chunk_runbooks.py
python backend/ai_sre/rag/embed_runbooks.py
python backend/ai_sre/rag/load_qdrant.py       # needs Qdrant at QDRANT_URL
```

## Notes

- All the agent logic currently lives in `agents/graph.py` (one function per stage: `planner_node`,
  `log_analysis_node`, `fix_proposer_node`, `verifier_node`).
- The Docker image serves the API only. `/incidents/analyze` imports the agent lazily and needs the full
  `requirements.txt`, Qdrant, and a kubeconfig, so it does not work on the slim image.
- The anomaly model is loaded from `ml/models/lightgbm_final_classifier.joblib` (override with `ANOMALY_MODEL_PATH`).
