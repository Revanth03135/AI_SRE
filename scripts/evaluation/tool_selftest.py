"""MCP tool self-test: call every tool of every MCP server once with valid arguments against the live lab.

A call passes when it returns without a protocol error and without the error markers the servers use
(error dictionaries, "Kubernetes API error", "Prometheus connection error", ...). GitHub tools need a token
and are reported as NOT RUN when GITHUB_PAT is unset, rather than counted as passes or failures.
The two mutating Kubernetes tools are exercised on the harmless control deployment sre-lab/lab-healthy
(scale to its current replica count, then a rolling restart).

Usage:  python scripts/evaluation/tool_selftest.py [output.json]
"""

import json
import os
import sys
import time
from pathlib import Path

import anyio

os.environ.setdefault("GROQ_API_KEY", "evaluation-placeholder")
os.environ.setdefault("GEMINI_API_KEY", "evaluation-placeholder")
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

import ai_sre.agents.graph as g  # noqa: E402

NS, CONTROL = "sre-lab", "lab-healthy"
EXPECT = {"namespace": None, "deployment_name": None}


async def run():
    stack, sessions = await g._open_mcp_servers()
    results = []
    try:
        tools, owners = await g._fetch_mcp_tools(sessions)
        owner_name = {tool.name: name for name, s in sessions.items() for tool in (await s.list_tools()).tools}

        async def call(name, args, note=""):
            started = time.perf_counter()
            try:
                raw, tool_call, _ = await g._execute_mcp_tool(name, args, owners, EXPECT)
                ok = not g._is_tool_error(tool_call)
                detail = json.dumps(raw, default=str)[:90]
            except Exception as error:  # a raised protocol error is a failure
                ok, detail = False, f"{type(error).__name__}: {error}"[:90]
            results.append({"server": owner_name.get(name, "?"), "tool": name, "status": "PASS" if ok else "FAIL",
                            "seconds": round(time.perf_counter() - started, 2), "note": note, "detail": detail})
            return ok

        pods = (await g._execute_mcp_tool("list_pods", {"namespace": "online-boutique"}, owners, EXPECT))[0]
        pod = pods[0]["name"] if isinstance(pods, list) and pods else "missing"
        deployments = (await g._execute_mcp_tool("list_deployments", {"namespace": NS}, owners, EXPECT))[0]
        control_replicas = next((d["desired_replicas"] for d in (deployments if isinstance(deployments, list) else []) if d["name"] == CONTROL), 2)

        plan = [
            ("list_pods", {"namespace": "online-boutique"}), ("get_pod_status", {"namespace": "online-boutique", "pod_name": pod}),
            ("get_pod_events", {"namespace": "online-boutique", "pod_name": pod}), ("get_pod_logs", {"namespace": "online-boutique", "pod_name": pod}),
            ("list_deployments", {"namespace": NS}),
            ("scale_deployment", {"namespace": NS, "deployment_name": CONTROL, "replicas": control_replicas}),
            ("restart_deployment", {"namespace": NS, "deployment_name": CONTROL}),
            ("instant_query", {"promql": "count(kube_pod_info)"}),
            ("range_query", {"promql": "count(kube_pod_info)", "start": str(int(time.time()) - 300), "end": str(int(time.time())), "step": "60"}),
            ("list_targets", {}), ("list_alerts", {}),
        ]
        for name, args in plan:
            await call(name, args)
        github_tools = [t for t in owner_name if owner_name[t] == "github"]
        for name in github_tools:
            if os.environ.get("GITHUB_PAT"):
                results.append({"server": "github", "tool": name, "status": "NOT RUN", "seconds": 0, "note": "needs repo arguments", "detail": ""})
            else:
                results.append({"server": "github", "tool": name, "status": "NOT RUN", "seconds": 0, "note": "GITHUB_PAT not set", "detail": ""})
    finally:
        await g._close_mcp_servers(stack, sessions)
    return results


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    results = anyio.run(run)
    run_count = [r for r in results if r["status"] != "NOT RUN"]
    passed = sum(r["status"] == "PASS" for r in run_count)
    by_server = {}
    for r in results:
        s = by_server.setdefault(r["server"], {"tools": 0, "pass": 0, "fail": 0, "not_run": 0})
        s["tools"] += 1
        s[{"PASS": "pass", "FAIL": "fail", "NOT RUN": "not_run"}[r["status"]]] += 1
    print(f"{'server':14s} {'tool':20s} {'status':8s} {'sec':>5s}  detail")
    for r in results:
        print(f"{r['server']:14s} {r['tool']:20s} {r['status']:8s} {r['seconds']:5.2f}  {r['note'] or r['detail']}")
    print(f"\nexercised: {len(run_count)} tools | passed: {passed} | failed: {len(run_count) - passed} | not run: {len(results) - len(run_count)}")
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"tools_total": len(results), "exercised": len(run_count), "passed": passed, "by_server": by_server, "results": results}, indent=2), encoding="utf-8")
        print("saved", out)


main()
