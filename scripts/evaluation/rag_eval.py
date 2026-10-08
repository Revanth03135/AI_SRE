"""Retrieval-quality evaluation of the runbook index (Qdrant + all-MiniLM-L6-v2).

Test set: one natural-language symptom description per team runbook, written in different words than the
runbook itself. A query is a hit at rank k when its expected runbook is among the top-k retrieved chunks.
Metrics: Hit@1, Hit@3, Hit@5, MRR, and Precision@5 (reported because it was the Review 1 target; with a single
relevant runbook per query it cannot exceed 0.20, which is why Hit@k and MRR are the meaningful measures here).

Usage:  python scripts/evaluation/rag_eval.py [output.json]
Needs Qdrant at QDRANT_URL with the runbook_chunks collection loaded.
"""

import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from qdrant_client import QdrantClient  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION = "runbook_chunks"
TOP_K = 5

TEST_SET = [
    ("Container keeps getting killed with exit code 137 because it reaches its memory limit", "team_oomkilled-memory-limit.txt"),
    ("Pod in CrashLoopBackOff: the application exits at startup with a stack trace about a failed dependency connection", "team_crashloopbackoff-application-error.txt"),
    ("Pods stuck in ErrImagePull then ImagePullBackOff, manifest unknown for the image tag", "team_imagepullbackoff-bad-image.txt"),
    ("Pod is Pending and the scheduler reports 0/1 nodes are available: Insufficient memory", "team_pending-insufficient-resources.txt"),
    ("Pod is Running but 0/1 containers are ready, readiness probe failed with connection refused, zero restarts", "team_readiness-probe-failing.txt"),
    ("Container restarts at regular intervals because its liveness probe fails, exit code 143 from the kubelet", "team_liveness-probe-restart-loop.txt"),
    ("Deployment has only one replica available when three are needed after being scaled down by mistake, pods are healthy", "team_deployment-under-replicated-scale.txt"),
    ("Container cannot start: CreateContainerConfigError, configmap not found", "team_missing-configmap-secret.txt"),
    ("cartservice cannot reach redis-cart, add to cart returns 500 errors", "team_redis-cache-dependency-down.txt"),
    ("Service has an empty endpoints list because its selector matches no pods even though the pods are Ready", "team_service-no-endpoints.txt"),
    ("Services fail with no such host and temporary failure in name resolution, coredns pods are unhealthy", "team_dns-resolution-failure.txt"),
    ("Requests are slow although nothing crashes, container CPU is pinned at its limit with heavy throttling", "team_cpu-throttling-high-latency.txt"),
    ("Deployment rollout never completes: ProgressDeadlineExceeded and the new ReplicaSet pods are not ready", "team_rollout-stuck-progress-deadline.txt"),
    ("Pods show Evicted: the node was low on resource memory and reports MemoryPressure", "team_evicted-pods-node-pressure.txt"),
    ("checkoutservice returns rpc error code Unavailable when it calls paymentservice", "team_downstream-grpc-dependency-unavailable.txt"),
    ("A chaos experiment killed a pod and a replacement pod appeared; error rate spiked briefly", "team_chaos-pod-kill-self-healing.txt"),
]


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    model = SentenceTransformer("all-MiniLM-L6-v2")
    client = QdrantClient(url=QDRANT_URL)
    total_chunks = client.count(COLLECTION, exact=True).count

    rows = []
    for query, expected in TEST_SET:
        vector = model.encode([query], convert_to_numpy=True, show_progress_bar=False)[0].tolist()
        points = client.query_points(COLLECTION, query=vector, limit=TOP_K, with_payload=True).points
        files = [p.payload["source_file"] for p in points]
        rank = files.index(expected) + 1 if expected in files else None
        rows.append({"query": query, "expected": expected, "rank": rank, "top1": files[0], "top1_score": round(points[0].score, 3),
                     "expected_score": round(next((p.score for p in points if p.payload["source_file"] == expected), 0.0), 3)})

    n = len(rows)
    hit = lambda k: sum(1 for r in rows if r["rank"] and r["rank"] <= k)
    result = {
        "queries": n, "corpus_chunks": total_chunks,
        "hit_at_1": round(hit(1) / n, 3), "hit_at_3": round(hit(3) / n, 3), "hit_at_5": round(hit(5) / n, 3),
        "mrr": round(sum(1 / r["rank"] for r in rows if r["rank"]) / n, 3),
        "precision_at_5": round(sum(1 for r in rows if r["rank"]) / (n * TOP_K), 3),
        "mean_top1_score": round(sum(r["top1_score"] for r in rows) / n, 3),
        "misses": [r for r in rows if not r["rank"] or r["rank"] > 1], "rows": rows,
    }
    print(f"corpus: {total_chunks} chunks | queries: {n}")
    for r in rows:
        mark = "OK " if r["rank"] == 1 else ("~  " if r["rank"] else "MISS")
        print(f"  {mark} rank={r['rank']}  top1={r['top1_score']:.3f}  {r['expected']}" + ("" if r["rank"] == 1 else f"   (top1 was {r['top1']})"))
    print(f"Hit@1 {result['hit_at_1']:.1%} | Hit@3 {result['hit_at_3']:.1%} | Hit@5 {result['hit_at_5']:.1%} | MRR {result['mrr']:.3f} | P@5 {result['precision_at_5']:.3f}")
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print("saved", out)


main()
