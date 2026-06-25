# Helm: another operation (install/upgrade) is in progress

## Symptoms
```
Error: UPGRADE FAILED: another operation (install/upgrade/rollback) is in progress
```

## Root cause
A previous helm operation crashed or was killed, leaving the release stuck in a
`pending-install` / `pending-upgrade` state in its release secret.

## Fix

### Check state
```bash
helm status <release> -n <ns>
helm history <release> -n <ns>
```

### Roll back to last good revision
```bash
helm rollback <release> <last-good-revision> -n <ns>
```

### If never successfully installed (pending-install, no good revision)
```bash
helm uninstall <release> -n <ns>
helm install <release> <chart> -n <ns>
```

### Manual unstick (last resort)
Delete the stuck release secret (Helm 3 stores state in secrets):
```bash
kubectl get secret -n <ns> -l owner=helm,name=<release>
kubectl delete secret sh.helm.release.v1.<release>.v<rev> -n <ns>
```

## Confirm
```bash
helm history <release> -n <ns>
```
