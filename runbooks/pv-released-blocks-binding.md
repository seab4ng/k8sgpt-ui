# PVC stuck Pending — old PV with same name/claim is "Released"

## Symptoms
```
PVC STATUS: Pending
PV  STATUS: Released        # a leftover PV from a deleted PVC
```
A previous PVC was deleted but its PV has `persistentVolumeReclaimPolicy: Retain`, so the
PV went to **Released** instead of being reused. A new PVC won't bind to a Released PV
because it still carries the old `claimRef`.

## Triage
```bash
kubectl get pv | grep -i released
kubectl get pv <pv> -o jsonpath='{.spec.claimRef}{"\n"}'   # points at the OLD pvc uid
kubectl describe pvc <pvc> -n <ns>
```

## Common causes & fixes
- **Reuse the Released PV** — clear the stale `claimRef` so it returns to `Available`:
  ```bash
  kubectl patch pv <pv> --type=json -p='[{"op":"remove","path":"/spec/claimRef"}]'
  # PV -> Available, then the matching PVC binds to it
  ```
  (Data on the PV is preserved — this is the right move when you want the old data.)
- **Don't need the old data** — delete the leftover PV (and its backing disk if any),
  then recreate the PVC so it provisions fresh:
  ```bash
  kubectl delete pv <pv>
  ```
- **Name collision on a static PV** — you recreated a PV with a name that still exists in
  Released state. Delete or rename the old one first.
- **Prevent recurrence** — for ephemeral data use `reclaimPolicy: Delete`; keep `Retain`
  only where you intend to recover the disk manually.

## Confirm
```bash
kubectl get pv <pv>          # Available, then Bound
kubectl get pvc <pvc> -n <ns>  # Bound
```
