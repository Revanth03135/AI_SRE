# Local lab

A practice Kubernetes cluster on your laptop for the agent to investigate. Built by Terraform and Helm
(see [../infra/README.md](../infra/README.md)).

```
Windows -> Docker Desktop -+- container "qdrant"                (runbook index; not Kubernetes)
                           +- container "ai-sre-control-plane"  (kind: a whole Kubernetes cluster in one container)
                                +- namespace online-boutique   the demo shop (10 services)
                                +- namespace monitoring        Prometheus + kube-state-metrics
                                +- namespace chaos-mesh        fault injection
                                +- namespace sre-lab           broken workloads (kubectl apply, not Terraform)
```

## Start and stop

```powershell
.\scripts\up.ps1 -LoadRag     # first run: 10-15 minutes, pulls ~1.5 GB of images
.\scripts\down.ps1            # remove the cluster
```

After Docker Desktop restarts, bring the existing lab back instead of rebuilding it:

```powershell
docker start qdrant ai-sre-control-plane
kind export kubeconfig --name ai-sre      # only if kubectl cannot connect
kubectl get nodes                         # ai-sre-control-plane   Ready
```

Both containers use `--restart unless-stopped`, so they normally come back on their own. The default profile fits in
about 3.5 GB of Docker memory; `-Full` needs about 6 GB. If `kind`, `helm` or `terraform` are not found, reopen the terminal.

## Where to look

| What | Address |
|---|---|
| Demo shop | http://127.0.0.1:8081 (use 127.0.0.1, not `localhost`) |
| Prometheus | http://localhost:9090 |
| Qdrant | http://localhost:6333/dashboard |
| API docs | http://127.0.0.1:8000/docs |
| Review dashboard | http://localhost:3000 |

```powershell
kubectl get ns                                       # namespaces
kubectl get pods -A                                  # every pod with its status
kubectl get pods -n sre-lab                          # the broken workloads and how each is failing
kubectl describe pod <pod> -n sre-lab                # details; the Events list at the bottom is what the agent reads
kubectl logs <pod> -n online-boutique                # what a pod printed
kubectl get events -n sre-lab --sort-by=.lastTimestamp

terraform -chdir=infra/terraform state list          # the resources Terraform manages
helm list -A                                         # installed Helm releases
docker exec -it ai-sre-control-plane bash            # a shell inside the cluster node
```

The agent's MCP tools (`list_pods`, `get_pod_status`, `get_pod_events`, `get_pod_logs`, `list_deployments`) are these
same queries made available to the LLM. `k9s` (`winget install k9s`) is a friendlier terminal UI.

## Break things and watch the agent

```powershell
kubectl apply -f infra/faults/broken-workloads.yaml                       # 8 broken workloads
kubectl apply -f infra/faults/chaos-mesh/pod-kill-cartservice.yaml        # kill a shop pod
python scripts/analyze_alert.py "Deployment lab-oom-killed in namespace sre-lab keeps restarting"
```

| Workload | Failure | Expected action |
|---|---|---|
| `lab-oom-killed` | Exceeds its memory limit (OOMKilled) | restart as a stopgap, or none |
| `lab-crashloop` | Exits at startup | none |
| `lab-image-pull` | Image does not exist | none |
| `lab-pending` | Requests more memory than the node has | none |
| `lab-readiness-fail` | Readiness probe path returns 404 | none |
| `lab-scaled-to-zero` | Scaled to 0 replicas | scale to 1-3 |
| `lab-missing-config` | References a missing ConfigMap | none |
| `lab-healthy` | Nothing wrong (control) | none |

## Troubleshooting

- **First install fails with `etcdserver: request timed out`:** the cluster was overloaded by parallel installs.
  Re-run `terraform -chdir=infra/terraform apply -parallelism=1`.
- **`emailservice` / `recommendationservice` restart in a loop:** their 1-second probes need more CPU than the chart
  default; `infra/helm/values/online-boutique.yaml` already raises it.
- **Analysis fails with a connection error:** Qdrant is not running (`docker start qdrant`).
