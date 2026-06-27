# Pod Pending — unschedulable (insufficient resources / taints / affinity)

## Symptoms
```
STATUS: Pending
Events:
  Warning  FailedScheduling  0/3 nodes are available: 3 Insufficient cpu.
  # or: had untolerated taint, didn't match node affinity/selector, too many pods
```
The scheduler can't place the pod on any node.

## Triage
```bash
kubectl describe pod <pod> -n <ns>        # the FailedScheduling reason is explicit
kubectl describe nodes | grep -A5 Allocated   # free cpu/mem per node
kubectl get nodes --show-labels
```

## Common causes & fixes
- **Insufficient CPU/memory** — requests exceed free capacity. Lower
  `resources.requests`, or free/add node capacity.
- **Untolerated taint** — node has a taint (e.g. `NoSchedule`). Add a matching
  `tolerations:` to the pod, or remove the taint: `kubectl taint nodes <n> key-`.
- **nodeSelector / nodeAffinity mismatch** — required label not on any node. Fix the
  selector or label the node: `kubectl label node <n> <key>=<val>`.
- **Pod anti-affinity / topology spread** — constraints can't be satisfied with current
  nodes; relax them or add nodes.
- **Max pods per node reached** — kubelet `--max-pods` cap hit; add nodes.

## Confirm
```bash
kubectl get pod <pod> -n <ns> -w     # moves Pending -> Running
```
