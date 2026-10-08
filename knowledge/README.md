# knowledge

The runbooks the agent searches when it proposes a fix (retrieval-augmented generation).

```
knowledge/
└── runbooks/   16 team-written runbooks for pod-level Kubernetes failures (committed)
```

The index is built from two sources:

| Source | Location | In git |
|---|---|---|
| Team runbooks | `knowledge/runbooks/*.txt` | yes |
| Public incident postmortems (VOID database) | `data/runbooks/void/*.txt` | no (download separately) |

## Runbook format

One plain-text file per failure type, named `team_<topic>.txt`:

```
Title: Team runbook: <what goes wrong>
Category: Kubernetes / <area>

Symptoms: ...as they appear in pod status, events, and logs...
Diagnosis: ...what to check...
Remediation: ...what fixes it, and whether a restart or scale helps or not...
Verification: ...how to confirm it worked...
```

State clearly whether restarting or scaling helps. The agent can only restart or scale, so a runbook that says
"a restart does NOT fix this" is what steers it to recommend no action for, say, a bad image.

## Add or change a runbook

```powershell
python backend/ai_sre/rag/chunk_runbooks.py     # splits both folders into data/processed/runbook_chunks.parquet
python backend/ai_sre/rag/embed_runbooks.py     # embeds with all-MiniLM-L6-v2
python backend/ai_sre/rag/load_qdrant.py        # (re)creates the Qdrant collection `runbook_chunks`
```

Or run `.\scripts\up.ps1 -LoadRag`. File names must be unique across both folders.
