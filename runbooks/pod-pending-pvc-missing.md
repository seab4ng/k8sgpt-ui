# Pod stuck Pending — PVC missing or unbound

## Symptoms
```
STATUS: Pending
Events:
  Warning  FailedScheduling  persistentvolumeclaim "data" not found
  # or:
  Warning  FailedScheduling  pod has unbound immediate PersistentVolumeClaims
```
The pod references a PVC that doesn't exist, or the PVC exists but never bound.

## Triage
```bash
kubectl describe pod <pod> -n <ns>                 # which PVC it wants
kubectl get pvc -n <ns>                            # does it exist? STATUS Bound?
kubectl describe pvc <pvc> -n <ns>                 # binding events
kubectl get storageclass                           # is there a (default) SC?
```

## Common causes & fixes
- **PVC never created** — the volumeClaimTemplate/PVC manifest wasn't applied. Create it,
  or fix the `claimName` in the pod/Deployment to match an existing PVC.
- **No default StorageClass** — dynamic provisioning can't pick one. Set a default:
  ```bash
  kubectl patch storageclass <sc> -p \
    '{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'
  ```
  or set `storageClassName` explicitly on the PVC.
- **StatefulSet** — PVCs come from `volumeClaimTemplates`; the generated name is
  `<template>-<statefulset>-<ordinal>`. A wrong template name leaves the pod unbound.
- **WaitForFirstConsumer SC** — PVC stays `Pending` until a pod that uses it is scheduled;
  that's normal. If the pod is also Pending, check node/zone/topology constraints.

## Confirm
```bash
kubectl get pvc <pvc> -n <ns>     # Bound
kubectl get pod <pod> -n <ns>     # Running
```
