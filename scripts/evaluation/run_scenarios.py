"""End-to-end evaluation: run the full agent pipeline on each injected fault and score it against a written expectation.

Prerequisite: the lab is up and infra/faults/broken-workloads.yaml is applied (kubectl apply -f ...).
For each scenario the four pipeline stages are run in order (the same sequence LangGraph executes) and timed.

Scoring (automatic, so it is reproducible and cannot be tuned by hand per run):
  diagnosis_correct  - the diagnosis names the true root cause (all `must` patterns match, case-insensitive)
  action_correct     - the recommended action is one of the acceptable actions for that fault
  runbook_hit        - the expected runbook is among the retrieved chunks (RAG top-3)
  correct            - diagnosis_correct AND action_correct (the headline "diagnostic accuracy")
For the healthy control the correct outcome is: no fault claimed and no action.

Usage:  python scripts/evaluation/run_scenarios.py [output.json] [--only name1,name2] [--pause 20]
"""

import json
import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

TAIL = "Investigate the real cluster state."
EXEC = {"restart_deployment", "scale_deployment"}

SCENARIOS = [
    {"name": "lab-oom-killed", "fault": "Container exceeds its memory limit (OOMKilled)",
     "alert": f"Deployment lab-oom-killed in namespace sre-lab keeps restarting and its pod is not staying up. {TAIL}",
     "must": [r"OOMKilled|out[- ]of[- ]memory|exit code[: ]*137|memory limit"],
     "actions": {"restart_deployment", "none"}, "runbook": "team_oomkilled-memory-limit.txt"},
    {"name": "lab-crashloop", "fault": "App exits at startup (database unreachable)",
     "alert": f"Deployment lab-crashloop in namespace sre-lab is crash-looping and never becomes ready. {TAIL}",
     "must": [r"CrashLoopBackOff|crash[- ]?loop", r"orders-db|database|connection refused|exit(ed)? (with )?(code )?1|non-zero"],
     "actions": {"none"}, "runbook": "team_crashloopbackoff-application-error.txt"},
    {"name": "lab-image-pull", "fault": "Image does not exist (ImagePullBackOff)",
     "alert": f"Deployment lab-image-pull in namespace sre-lab has no running pods and never becomes available. {TAIL}",
     "must": [r"ImagePullBackOff|ErrImagePull|failed to pull|pull image"],
     "actions": {"none"}, "runbook": "team_imagepullbackoff-bad-image.txt"},
    {"name": "lab-pending", "fault": "Requests more memory than the node has (FailedScheduling)",
     "alert": f"Deployment lab-pending in namespace sre-lab has a pod that never starts. {TAIL}",
     "must": [r"Pending", r"FailedScheduling|Insufficient|unschedulable|cannot be scheduled|not be scheduled"],
     "actions": {"none"}, "runbook": "team_pending-insufficient-resources.txt"},
    {"name": "lab-readiness-fail", "fault": "Readiness probe path returns 404",
     "alert": f"Deployment lab-readiness-fail in namespace sre-lab is running but never becomes ready. {TAIL}",
     "must": [r"readiness", r"probe|404|not ready|0/1"],
     "actions": {"none"}, "runbook": "team_readiness-probe-failing.txt"},
    {"name": "lab-scaled-to-zero", "fault": "Deployment scaled to 0 replicas",
     "alert": f"Deployment lab-scaled-to-zero in namespace sre-lab has no running pods and the service it backs is returning errors. {TAIL}",
     "must": [r"replicas\W{0,6}(=|:|is|of)?\W{0,3}0|scaled[- ](down )?to[- ](zero|0)|zero replicas|no (running )?pods"],
     "actions": {"scale_deployment"}, "runbook": "team_deployment-under-replicated-scale.txt"},
    {"name": "lab-missing-config", "fault": "References a ConfigMap that does not exist",
     "alert": f"Deployment lab-missing-config in namespace sre-lab cannot start its container. {TAIL}",
     "must": [r"CreateContainerConfigError|config ?map|configuration"],
     "actions": {"none"}, "runbook": "team_missing-configmap-secret.txt"},
    {"name": "lab-healthy", "fault": "Nothing is wrong (control)",
     "alert": f"Monitoring flagged deployment lab-healthy in namespace sre-lab for a possible problem. {TAIL}",
     "must": [r"healthy|no (issue|problem|fault|action)|false positive|operating normally|running (normally|fine)|no (actionable|real) "],
     "forbid": [r"CrashLoopBackOff|OOMKilled|ImagePullBackOff|CreateContainerConfigError|FailedScheduling"],
     "actions": {"none"}, "runbook": None},
]


def score(sc, state):
    diagnosis = state.get("diagnosis") or ""
    action = state.get("recommended_action") or "none"
    must_ok = all(re.search(p, diagnosis, re.I) for p in sc["must"])
    forbid_ok = not any(re.search(p, diagnosis, re.I) for p in sc.get("forbid", []))
    chunks = [c["source_file"] for c in state.get("retrieved_chunks") or []]
    return {
        "diagnosis_correct": bool(must_ok and forbid_ok),
        "action_correct": action in sc["actions"],
        "runbook_hit": (sc["runbook"] in chunks) if sc["runbook"] else None,
        "runbook_top1": (bool(chunks) and chunks[0] == sc["runbook"]) if sc["runbook"] else None,
    }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(args[0]) if args else None
    only = None
    pause = 20
    for i, a in enumerate(sys.argv):
        if a == "--only":
            only = set(sys.argv[i + 1].split(","))
        if a == "--pause":
            pause = int(sys.argv[i + 1])

    from ai_sre.agents import graph as g
    from ai_sre.agents.runner import _initial_graph_state

    done = {}
    if out and out.exists():  # resume: keep scenarios that already finished
        for r in json.loads(out.read_text(encoding="utf-8")).get("runs", []):
            done[r["name"]] = r
    runs = dict(done)

    for sc in SCENARIOS:
        if only and sc["name"] not in only:
            continue
        if sc["name"] in done and not only:
            print(f"skip {sc['name']} (already in {out})")
            continue
        print(f"\n=== {sc['name']}: {sc['fault']}", flush=True)
        state = _initial_graph_state(sc["alert"])
        timings = {}
        error = None
        try:
            for label, node in (("planner", g.planner_node), ("log_analysis", g.log_analysis_node), ("fix_proposer", g.fix_proposer_node), ("verifier", g.verifier_node)):
                started = time.perf_counter()
                state = node(state)
                timings[label] = round(time.perf_counter() - started, 1)
        except Exception as exc:  # record the failure; do not abort the whole evaluation
            error = f"{type(exc).__name__}: {exc}"[:300]
        calls = state.get("tool_calls") or []
        tool_errors = sum(1 for c in calls if g._is_tool_error(c))
        run = {
            "name": sc["name"], "fault": sc["fault"], "error": error, "timings_s": timings, "total_s": round(sum(timings.values()), 1),
            "tool_calls": len(calls), "tool_call_errors": tool_errors, "tools_used": sorted({c["tool"] for c in calls}),
            "models": state.get("model_used"), "degraded": state.get("diagnosis_degraded"),
            "recommended_action": state.get("recommended_action"), "action_target": f"{state.get('action_namespace')}/{state.get('action_deployment_name')}" if state.get("action_deployment_name") else None,
            "action_replicas": state.get("action_replicas"), "classification": state.get("classification"), "trust_score": state.get("trust_score"),
            "top_runbooks": [(c["source_file"], round(c["score"], 3)) for c in (state.get("retrieved_chunks") or [])],
            "diagnosis": (state.get("diagnosis") or "")[:1500], **(score(sc, state) if not error else {"diagnosis_correct": False, "action_correct": False, "runbook_hit": None, "runbook_top1": None}),
        }
        run["correct"] = bool(run["diagnosis_correct"] and run["action_correct"])
        runs[sc["name"]] = run
        print(f"  total {run['total_s']}s {timings} | tools {run['tool_calls']} (errors {tool_errors}) | models {run['models']}")
        print(f"  action={run['recommended_action']} verdict={run['classification']} trust={run['trust_score']} runbook_hit={run['runbook_hit']}")
        print(f"  diagnosis_correct={run['diagnosis_correct']} action_correct={run['action_correct']} -> CORRECT={run['correct']}" + (f"  ERROR {error}" if error else ""), flush=True)
        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({"runs": [runs[s["name"]] for s in SCENARIOS if s["name"] in runs]}, indent=2), encoding="utf-8")
        time.sleep(pause)

    finished = [runs[s["name"]] for s in SCENARIOS if s["name"] in runs]
    n = len(finished)
    if n:
        print(f"\nSUMMARY over {n} scenarios: correct {sum(r['correct'] for r in finished)}/{n} | diagnosis {sum(r['diagnosis_correct'] for r in finished)}/{n} | action {sum(r['action_correct'] for r in finished)}/{n}"
              f" | mean latency {sum(r['total_s'] for r in finished) / n:.0f}s")


main()
