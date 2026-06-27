# Service has no endpoints (connection refused / empty backend)

## Symptoms
```
# k8sgpt: Service <ns>/<svc> has no endpoints, expected label app=<x>
kubectl get endpoints <svc> -n <ns>
NAME   ENDPOINTS   AGE
<svc>  <none>      5m
```
Clients hitting the Service get connection refused / timeouts — nothing is behind it.

## Triage
```bash
kubectl get svc <svc> -n <ns> -o yaml | grep -A5 selector
kubectl get pods -n <ns> --show-labels                 # do pod labels match the selector?
kubectl get endpoints <svc> -n <ns>
kubectl describe svc <svc> -n <ns>
```

## Common causes & fixes
- **Selector doesn't match pod labels** — the Service `spec.selector` must equal the
  pods' labels exactly. Fix one side so they match.
- **No Ready pods** — pods exist but fail readiness probes, so they're excluded from
  endpoints. Fix the probe / the app (see probe runbook).
- **targetPort mismatch** — Service `targetPort` doesn't match the container's listening
  port; align them.
- **Pods in another namespace** — a Service only selects pods in its own namespace.
- **Headless service expectations** — `clusterIP: None` returns pod IPs directly; verify
  the client handles that.

## Confirm
```bash
kubectl get endpoints <svc> -n <ns>     # now lists pod IP:port
```
