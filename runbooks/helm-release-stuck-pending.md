# Helm release stuck in pending-install / pending-upgrade

## Symptoms
```
helm list -A
NAME    STATUS              ...
myrel   pending-upgrade     # or pending-install / pending-rollback
# new upgrades fail: another operation (install/upgrade/rollback) is in progress
```
A previous Helm operation was interrupted (timeout, Ctrl-C, crashed CI) and left the
release locked.

## Triage
```bash
helm status <release> -n <ns>
helm history <release> -n <ns>           # see the stuck revision
kubectl get pods -n <ns>                 # is the underlying rollout actually failing?
```

## Common causes & fixes
- **Interrupted operation** — roll back to the last good revision to clear the lock:
  ```bash
  helm rollback <release> <last-deployed-revision> -n <ns>
  ```
- **First-ever install left pending-install** — there's no good revision to roll back to;
  uninstall and reinstall:
  ```bash
  helm uninstall <release> -n <ns>
  helm install <release> <chart> -n <ns>
  ```
- **Underlying rollout is the real problem** — pods are failing (image, probes,
  resources), so the operation never completes. Fix the workload (see the relevant pod
  runbook), then retry; use `--atomic --timeout 10m` so failures auto-roll-back instead
  of hanging.
- **Stuck Helm release secret** — as a last resort, inspect/clean the
  `sh.helm.release.v1.<release>.v<n>` Secret in the namespace.

## Confirm
```bash
helm status <release> -n <ns>      # deployed
```
