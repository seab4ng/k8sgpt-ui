# Helm: pre-install hook Job already exists

## Symptoms / error text
```
Error: INSTALLATION FAILED: ... pre-install hooks failed:
warning: Hook pre-install ... failed:
jobs.batch "<name>" already exists
```
Also seen on `helm upgrade --install`. Often after a previous failed install
left the hook Job behind (Job ran, was not deleted).

## Root cause
A Helm hook resource (usually a `Job`) from a prior release attempt is still in
the namespace. Helm tries to create it again, the API server rejects it because
the object already exists.

## Fix

### Option A — delete the leftover Job, then reinstall
```bash
kubectl get jobs -n <namespace>
kubectl delete job <name> -n <namespace>
helm install <release> <chart> -n <namespace>
```

### Option B (preferred, permanent) — add a hook-delete-policy
Annotate the hook resource so Helm cleans it up automatically. In the Job's
metadata:
```yaml
metadata:
  annotations:
    "helm.sh/hook": pre-install
    "helm.sh/hook-delete-policy": before-hook-creation,hook-succeeded
```
- `before-hook-creation` — delete any prior instance before creating the new one (kills this error).
- `hook-succeeded` — clean up after success.

### If the whole release is stuck
```bash
helm status <release> -n <namespace>
helm uninstall <release> -n <namespace>   # if appropriate
# then reinstall
```

## Confirm
```bash
helm install <release> <chart> -n <namespace> --dry-run --debug   # render check
kubectl get jobs -n <namespace>                                   # no leftover
```
