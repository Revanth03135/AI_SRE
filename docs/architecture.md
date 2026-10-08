# Architecture

AI-SRE automates what an on-call engineer does at 3 a.m.: decide what to check, look at the cluster, remember
how a similar problem was fixed, propose a fix, and ask a senior engineer before touching production.

## Parts

| Part | Role | Where |
|---|---|---|
| Dashboard | Submit alerts; review, approve, reject, and execute | `dashboard/` |
| API | Stores incidents (SQLite) and enforces the approval rules | `backend/ai_sre/api/main.py` |
| Agent pipeline | Four stages run in order: planner, log analysis, fix proposer, verifier | `backend/ai_sre/agents/graph.py` |
| MCP servers | Small programs that expose tools (list pods, read logs, query Prometheus) | `backend/ai_sre/mcp_servers/` |
| LLMs | Groq `gpt-oss-20b` does the reasoning; Gemini is the fallback when Groq is rate-limited | `graph.py` |
| Runbook index | Qdrant holds embedded runbooks and postmortems | `backend/ai_sre/rag/`, `knowledge/` |
| Executor | Runs an approved restart or scale and verifies the rollout | `backend/ai_sre/executor/` |

## One alert, step by step

Alert: *"Deployment cartservice in namespace online-boutique is crash-looping."*

1. **Submit.** The dashboard posts to `/api/sre/incidents/analyze`; its server-side relay adds the API key and
   forwards to the API, which calls `run_alert_and_persist` ([runner.py](../backend/ai_sre/agents/runner.py)).
2. **State.** One dictionary flows through the pipeline. Each stage reads it and adds fields (`plan`, `diagnosis`,
   `tool_calls`, `retrieved_chunks`, `recommended_action`, `trust_score`, `classification`, ...).
3. **Planner.** One LLM call turns the alert into an investigation plan.
4. **Log analysis.** The three MCP servers are started and the LLM is given their tools. It cannot run anything
   itself: it replies with *"call `get_pod_status` for this pod"*, the code runs that tool against the real cluster,
   and the answer goes back to the LLM. This repeats for up to five rounds. Namespaces and deployment names the
   LLM invents are replaced with the ones in the alert, and tool error results do not count as evidence.
   Output: `diagnosis` and `tool_calls` (the evidence).
5. **Fix proposer.** The diagnosis is embedded and matched against the runbook index (cosine similarity, 0 to 1).
   The LLM writes a `proposed_fix` using the matches, then picks one safe action as strict JSON:
   `restart_deployment`, `scale_deployment`, or `none`. The action is rejected (forced to `none`) unless the target
   deployment appeared in a real `list_deployments` result from this run.
6. **Verifier.** A plain rule, not an LLM, sets the label from the best runbook score and the tool evidence:

   | Condition | Verdict |
   |---|---|
   | No real tool evidence and no runbook match | REJECT |
   | Real tool evidence and runbook score at least 0.80 | ACCEPT |
   | Anything else | REVIEW |

   The LLM only explains that verdict in words.
7. **Save.** One row in the `incidents` table with the diagnosis, fix, verdict, trust score, and the action.
   Nothing in the cluster has changed.
8. **Review.** A human opens the incident in the dashboard and approves or rejects it.
9. **Execute.** After approval, **Execute** claims the incident (so it can only run once), snapshots the deployment,
   calls the Kubernetes MCP tool, polls up to 30 seconds for the rollout, and stores the before and after states.

## Not part of the live pipeline

- **Anomaly model** (`ml/`): a LightGBM classifier trained on the GAIA dataset. It is meant to raise alerts
  automatically; today a person types the alert.
- **MLflow** (`mlflow.db`): records of the training experiments.
