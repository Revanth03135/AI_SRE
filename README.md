# AI-SRE

An agentic incident-response assistant for Kubernetes. Give it an alert; it plans an investigation, reads the
live cluster through MCP tool servers, searches runbooks (RAG), proposes a fix, and scores how much to trust it.
A human approves in a dashboard before anything is executed, and the executor verifies the result.

```
alert ─► planner ─► log analysis ─► fix proposer ─► verifier ─► incident ─► dashboard ─► approve ─► execute
          (LLM)     (MCP tools)     (RAG + LLM)     (rules)      (SQLite)               (human)     (verified)
```

New here? Read [docs/architecture.md](docs/architecture.md) for a walk-through of one alert, and
[docs/local-lab.md](docs/local-lab.md) for the practice cluster.

## Repository map

```
AI_SRE/
├── backend/        Python service (package `ai_sre`): agents, API, MCP servers, executor, RAG, tests
├── dashboard/      Next.js review console (approve, reject, execute)
├── ml/             Anomaly-detection research: GAIA data loaders, experiments, trained models
├── infra/          Local lab: Terraform + Helm values + fault injection (broken workloads, Chaos Mesh)
├── knowledge/      Team-written runbooks that the RAG index is built from
├── scripts/        up.ps1 / down.ps1 (lab), analyze_alert.py (run one alert), live retests
├── docs/           Architecture and lab guides
├── .github/        CI (backend + ml tests, dashboard lint and build)
├── pytest.ini      Test configuration (run from here)
├── render.yaml     Deployment of the API image (backend/Dockerfile)
└── .env.example    Every setting the project reads
```

Generated and git-ignored: `data/` (datasets and RAG parquet files), `ml/models/` (trained artifacts),
`mlruns/` and `mlflow.db` (MLflow), `.venv/`.

Each folder has its own README with the details.

## Where do I find...?

| I want to... | Go to |
|---|---|
| Change how the agent investigates or decides | `backend/ai_sre/agents/graph.py` |
| Add or change an API endpoint | `backend/ai_sre/api/main.py` |
| Add a tool the agent can call | `backend/ai_sre/mcp_servers/` |
| Add a runbook | `knowledge/runbooks/` (then rebuild the index, see its README) |
| Add a broken workload or chaos experiment | `infra/faults/` |
| Change what the practice cluster runs | `infra/terraform/` and `infra/helm/values/` |
| Change the dashboard UI | `dashboard/app/components/` |
| Retrain or evaluate the anomaly model | `ml/experiments/` |
| Run a single alert end to end | `scripts/analyze_alert.py` |

## Quick start

Run everything from the repository root.

```powershell
# 1. Python environment
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt pytest
copy .env.example .env            # then fill in GROQ_API_KEY, GEMINI_API_KEY, AI_SRE_API_KEY

# 2. Backend API (http://127.0.0.1:8000, docs at /docs)
uvicorn ai_sre.api.main:app --app-dir backend --port 8000 --env-file .env

# 3. Dashboard (http://localhost:3000) - put AI_SRE_API_URL and AI_SRE_API_KEY in dashboard/.env.local
cd dashboard
npm install
npm run build; npm start          # or: npm run dev

# 4. Practice cluster + Qdrant (needs Docker Desktop, kind, helm, terraform)
.\scripts\up.ps1 -LoadRag

# 5. Try it
python scripts/analyze_alert.py "Deployment lab-oom-killed in namespace sre-lab keeps restarting"
```

Without a cluster the API, dashboard and tests still run; only live analysis needs the lab.

## Tests

```powershell
python -m pytest -m "not live"    # backend/tests and ml/tests; tests marked `live` need a cluster, Qdrant, and LLM keys
```

## Security model

- Every state-changing endpoint (`/incidents/analyze`, `POST /incidents`, `approve`, `reject`, `execute`)
  requires the `X-API-Key` header when `AI_SRE_API_KEY` is set. Always set it outside local development.
- The dashboard never sees that key: the browser calls `dashboard/app/api/sre/*`, a server-side relay that adds
  it. Set `AI_SRE_API_URL` and `AI_SRE_API_KEY` in the dashboard's server environment, and `DASHBOARD_PASSWORD`
  to put the dashboard behind HTTP Basic auth.
- Execution requires human approval (unless `AUTO_EXECUTE_ON_ACCEPT=true`), is claimed atomically so an
  incident can run at most once, and REJECT-classified incidents cannot be approved.
