# OOMKilled (container/node out of memory)

## Symptoms
```
kubectl get pod <pod> -o jsonpath='{.status.containerStatuses[0].lastState.terminated.reason}'
OOMKilled
# exit code 137; often paired with CrashLoopBackOff
```
The kernel killed the container for exceeding its memory limit (or the node ran out).

## Triage
```bash
kubectl describe pod <pod> -n <ns>     # Last State: Terminated, Reason: OOMKilled
kubectl top pod <pod> -n <ns>          # needs metrics-server
kubectl describe node <node> | grep -A6 Allocated
```

## Common causes & fixes
- **Memory limit too low** — the app legitimately needs more. Raise it:
  ```yaml
  resources:
    requests: { memory: "256Mi" }
    limits:   { memory: "512Mi" }
  ```
- **Memory leak** — usage climbs until the limit; fix the app or add a periodic restart
  as a stopgap.
- **JVM/runtime not limit-aware** — set heap from the cgroup limit (e.g. JVM
  `-XX:MaxRAMPercentage=75`), don't hardcode larger than the limit.
- **Node-level OOM (no pod limit)** — a limitless pod ate the node; set limits and
  `requests` so the scheduler accounts for it, preventing node memory pressure/eviction.

## Confirm
```bash
kubectl get pod <pod> -n <ns> -w                       # stays Running, restarts stop
kubectl top pod <pod> -n <ns>                          # usage below the limit
```
