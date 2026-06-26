# Container fails — permission denied (filesystem / non-root)

## Symptoms
```
... Permission denied
... open /data/...: permission denied
... mkdir /var/lib/app: permission denied
# often paired with CrashLoopBackOff
```
The container runs as a non-root UID (or with a restrictive SecurityContext) and can't
write to a mounted volume or a path it expects to own.

## Triage
```bash
kubectl logs <pod> -n <ns> --previous
kubectl get pod <pod> -n <ns> -o jsonpath='{.spec.securityContext}{"\n"}{.spec.containers[*].securityContext}'
# what UID does the image run as?
kubectl exec <pod> -n <ns> -- id 2>/dev/null
```

## Common causes & fixes
- **Volume owned by root, app runs as non-root** — set `fsGroup` so the kubelet chowns the
  volume to the group the process belongs to:
  ```yaml
  spec:
    securityContext:
      runAsUser: 1000
      runAsNonRoot: true
      fsGroup: 1000          # makes mounted volumes group-writable by 1000
  ```
- **App writes to a read-only path** — if `readOnlyRootFilesystem: true`, mount an
  `emptyDir` at the writable paths (e.g. `/tmp`, cache dirs).
- **OpenShift / restricted SCC** — the assigned UID is random and not in the image's
  passwd. Make group `0` own the writable dirs in the image (`chgrp -R 0 ... && chmod -R g=u`)
  and rely on `fsGroup`.
- **hostPath ownership** — node directory perms don't match the container UID; fix on the
  node or use a proper PVC.
- **subPath skips fsGroup chown** on some versions — mount the whole volume, or pre-create
  with correct ownership.

## Confirm
```bash
kubectl exec <pod> -n <ns> -- sh -c 'touch /data/.w && rm /data/.w && echo writable'
```
