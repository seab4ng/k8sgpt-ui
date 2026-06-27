# Init container failing (Pod stuck Init:Error / Init:CrashLoopBackOff)

## Symptoms
```
STATUS: Init:CrashLoopBackOff    (or Init:Error, Init:0/1)
```
The main containers never start because an init container keeps failing.

## Triage
```bash
kubectl describe pod <pod> -n <ns>                       # which init container, exit code
kubectl logs <pod> -n <ns> -c <init-container>           # current
kubectl logs <pod> -n <ns> -c <init-container> --previous # last crash
```

## Common causes & fixes
- **Waiting on a dependency that never comes** — init container blocks on a DB/service
  that's down or has the wrong address. Fix the dependency or the URL/host it checks.
- **Missing config/secret** — the init step reads a ConfigMap/Secret/volume that isn't
  mounted or has wrong keys (see configmap/secret runbook).
- **Bad command/args or image** — wrong entrypoint; verify `command`/`args` and image.
- **Permissions** — init container can't write its volume (see permission runbook;
  often needs `fsGroup`).
- **Network/DNS in airgap** — init pulls from an unreachable URL; point it at the
  in-cluster/mirror endpoint.

## Confirm
```bash
kubectl get pod <pod> -n <ns> -w     # passes Init and reaches Running
```
