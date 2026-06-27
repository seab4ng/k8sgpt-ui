# Readiness / Liveness probe failures

## Symptoms
```
Events:
  Warning  Unhealthy  Readiness probe failed: HTTP probe failed with statuscode: 503
  Warning  Unhealthy  Liveness probe failed: ... ; Container will be restarted
```
Pod never becomes Ready (kept out of Service endpoints), or is repeatedly restarted by a
failing liveness probe (can look like CrashLoopBackOff).

## Triage
```bash
kubectl describe pod <pod> -n <ns>      # which probe, last message
kubectl logs <pod> -n <ns>
kubectl get pod <pod> -n <ns> -o jsonpath='{.spec.containers[0].readinessProbe}{"\n"}{.spec.containers[0].livenessProbe}'
```

## Common causes & fixes
- **Probe path/port wrong** — `httpGet.path`/`port` doesn't match what the app serves;
  fix to a real health endpoint.
- **Slow startup killed by liveness** — app needs time to boot; add a `startupProbe`
  (or raise `initialDelaySeconds`) so liveness doesn't restart it mid-boot.
- **Thresholds too tight** — raise `timeoutSeconds`/`failureThreshold`/`periodSeconds`
  for a slow endpoint.
- **App genuinely unhealthy** — readiness is correctly reporting a dependency failure;
  fix the dependency (DB/config) — see relevant runbook.
- **TCP vs HTTP mismatch** — use `tcpSocket` for non-HTTP servers; `httpGet` 4xx/5xx
  counts as failure.

## Confirm
```bash
kubectl get pod <pod> -n <ns>      # READY 1/1, no more restarts
```
