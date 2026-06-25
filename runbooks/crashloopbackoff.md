# Pod: CrashLoopBackOff

## Symptoms
```
STATUS: CrashLoopBackOff
RESTARTS: <climbing>
```
Container starts, exits, k8s restarts it, repeat with backoff.

## Triage
```bash
kubectl describe pod <pod> -n <ns>          # events, last state, exit code
kubectl logs <pod> -n <ns> --previous       # logs from the crashed container
```

## Common causes & fixes
- **App error on startup** — read `--previous` logs. Fix config/env/secret it needs.
- **Bad command/args** — wrong entrypoint; check `command`/`args` in spec.
- **Missing config/secret** — mount exists? key names match?
- **Liveness probe too aggressive** — probe kills slow-starting app. Raise
  `initialDelaySeconds` / use `startupProbe`.
- **OOMKilled** (exit 137) — raise memory limits:
  ```yaml
  resources:
    limits:
      memory: "512Mi"
  ```
- **Exit code 1/2** — app-level failure, logs tell why.

## Confirm
```bash
kubectl get pod <pod> -n <ns> -w
```
