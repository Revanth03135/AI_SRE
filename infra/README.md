# infra

Everything for the local practice cluster the agent investigates. See [../docs/local-lab.md](../docs/local-lab.md)
for how to look around inside it.

```
infra/
├── terraform/   Creates a kind cluster and installs the Helm releases below (state stays local, git-ignored)
├── helm/
│   ├── values/      Settings for each release: online-boutique, prometheus, chaos-mesh, grafana
│   └── dashboards/  Grafana dashboards as JSON (ai-sre-lab.json), loaded automatically
└── faults/      Things that break the cluster on purpose
    ├── broken-workloads.yaml   8 broken deployments in namespace sre-lab (OOM, bad image, crash loop, ...)
    └── chaos-mesh/             Chaos Mesh experiments against Online Boutique (pod kill, CPU stress, ...)
```

## Use

```powershell
.\scripts\up.ps1                                  # build everything (idempotent); -Full adds ad service, load generator, Grafana
.\scripts\down.ps1                                # remove the cluster

kubectl apply -f infra/faults/broken-workloads.yaml
kubectl apply -f infra/faults/chaos-mesh/pod-kill-cartservice.yaml
kubectl delete -f infra/faults/chaos-mesh/pod-kill-cartservice.yaml
```

## What Terraform manages

| Resource | Purpose |
|---|---|
| `kind_cluster.this` | One-node Kubernetes cluster `ai-sre` |
| `helm_release.online_boutique` | The demo shop (namespace `online-boutique`) |
| `helm_release.prometheus` | Metrics, with kube-state-metrics (namespace `monitoring`) |
| `helm_release.chaos_mesh` | Fault injection (namespace `chaos-mesh`) |
| `helm_release.grafana` | Dashboards on `http://localhost:3300`, with the AI-SRE Lab dashboard (`enable_grafana`, on by default) |
| `kubernetes_service_v1.frontend_nodeport` | Storefront on `http://127.0.0.1:8081` |
| `kubernetes_namespace_v1.sre_lab` | Home for the broken workloads |
