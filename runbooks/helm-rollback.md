# Helm rollback (a bad release / failed upgrade)

## Symptoms
```
# an upgrade broke things and you need the previous working state back,
# or: helm rollback fails / doesn't restore as expected
```

## Triage
```bash
helm history <release> -n <ns>        # revisions + status; find the last DEPLOYED one
helm status <release> -n <ns>
kubectl get pods -n <ns>
```

## Common causes & fixes
- **Roll back to the last good revision:**
  ```bash
  helm rollback <release> <revision> -n <ns> --wait --timeout 5m
  ```
- **Rollback fails because resources were changed by hand** — Helm's view and the live
  state diverged. Reconcile, then force:
  ```bash
  helm rollback <release> <revision> -n <ns> --force
  ```
- **Rollback hangs on a failing workload** — the target revision's pods don't become
  ready (image/probe/resource). Fix the workload first (see pod runbooks).
- **Prevent next time** — use `helm upgrade --install --atomic --timeout 10m` so a failed
  upgrade auto-rolls-back instead of leaving a broken/pending release.
- **History gone / single revision** — nothing to roll back to; redeploy a known-good
  chart+values.

## Confirm
```bash
helm history <release> -n <ns>     # newest revision STATUS deployed
kubectl get pods -n <ns>           # workloads healthy
```
