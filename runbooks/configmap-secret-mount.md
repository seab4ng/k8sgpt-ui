# ConfigMap / Secret mount issues

## Symptoms
```
Events:
  Warning  FailedMount  MountVolume.SetUp failed for volume "cfg":
           configmap "app-config" not found
  # or: secret "app-secret" not found / references non-existent key
```
Pod stuck ContainerCreating, or app crashes because expected config/env is absent.

## Triage
```bash
kubectl describe pod <pod> -n <ns>                 # the FailedMount reason
kubectl get configmap,secret -n <ns>               # do they exist?
kubectl get configmap <name> -n <ns> -o yaml       # key names present?
```

## Common causes & fixes
- **ConfigMap/Secret doesn't exist** — create it, or fix the name referenced in the
  pod/Deployment. Watch the **namespace** (must be the same as the pod).
- **Wrong key name** — `items`/`key` in the volume or `secretKeyRef.key` must match an
  existing key exactly (case-sensitive).
- **subPath of a missing key** — see the ContainerCreating/subPath runbook.
- **Updated value not picked up** — env/`subPath` mounts don't auto-update; whole-volume
  mounts update with a delay. Roll the pod to force a re-read.
- **Immutable Secret/ConfigMap** — you can't edit it in place; recreate it.

## Confirm
```bash
kubectl exec <pod> -n <ns> -- env | grep <VAR>          # env present
kubectl exec <pod> -n <ns> -- ls /etc/config            # files mounted
```
