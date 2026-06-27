# Pod stuck in Terminating

## Symptoms
```
kubectl get pod <pod> -n <ns>
NAME    READY   STATUS        RESTARTS   AGE
<pod>   1/1     Terminating   0          20m   # never goes away
```

## Triage
```bash
kubectl describe pod <pod> -n <ns>
kubectl get pod <pod> -n <ns> -o jsonpath='{.metadata.finalizers}{"\n"}{.metadata.deletionTimestamp}'
```

## Common causes & fixes
- **Finalizer never clears** — an operator/controller that owns the finalizer is gone or
  failing, so deletion blocks forever. Fix/restore the controller, or remove the stuck
  finalizer as a last resort:
  ```bash
  kubectl patch pod <pod> -n <ns> -p '{"metadata":{"finalizers":null}}' --type=merge
  ```
- **Graceful shutdown hangs** — the process ignores SIGTERM. It deletes after
  `terminationGracePeriodSeconds`; to force now:
  ```bash
  kubectl delete pod <pod> -n <ns> --grace-period=0 --force
  ```
- **Node is NotReady/unreachable** — the kubelet can't confirm deletion. Recover the
  node (see node-notready), or after confirming the node is truly dead, force-delete.
- **Volume won't unmount** — a stuck mount (e.g. NFS) blocks teardown; check kubelet logs
  on the node.

## Confirm
```bash
kubectl get pod <pod> -n <ns>     # gone
```
