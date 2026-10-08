# scripts

Run these from the repository root.

| Script | Purpose |
|---|---|
| `up.ps1` | Build the lab: Qdrant, a kind cluster, and everything in it (`-Full`, `-LoadRag`). Safe to re-run. |
| `down.ps1` | Remove the lab cluster (`-Qdrant` also removes Qdrant). |
| `analyze_alert.py` | Run one alert through the whole pipeline and print each stage. `--persist` saves the incident for the dashboard. |
| `live_retests/` | Live acceptance scenarios against a real cluster; each one creates a broken workload, runs the agent, and prints what happened. |

```powershell
python scripts/analyze_alert.py "Deployment lab-oom-killed in namespace sre-lab keeps restarting"
python scripts/live_retests/not_found.py
```
