# Helm install fails — resource already exists

## Symptoms
```
Error: INSTALLATION FAILED: rendered manifests contain a resource that already
exists. Unable to continue with install: <Kind> "<name>" in namespace "<ns>"
exists and cannot be imported into the current release: invalid ownership metadata
```
A non-CRD object the chart wants to create is already in the cluster (created manually
or by another release). (For CRDs specifically, see the CRD/helm ownership runbook.)

## Triage
```bash
kubectl get <kind> <name> -n <ns> -o jsonpath='{.metadata.labels}{"\n"}{.metadata.annotations}'
helm list -A | grep <name>          # is another release already managing it?
```

## Common causes & fixes
- **Leftover from a manual `kubectl apply`** — delete it, then install:
  ```bash
  kubectl delete <kind> <name> -n <ns>
  helm install <release> <chart> -n <ns>
  ```
- **Adopt it into the release** — add Helm ownership metadata so Helm imports instead of
  erroring:
  ```bash
  kubectl label <kind> <name> -n <ns> app.kubernetes.io/managed-by=Helm --overwrite
  kubectl annotate <kind> <name> -n <ns> \
    meta.helm.sh/release-name=<release> meta.helm.sh/release-namespace=<ns> --overwrite
  ```
- **Two charts ship the same object** — pick one owner; disable it in the other.
- **Previous failed install left orphans** — clean them up, or use `--atomic` next time
  so a failed install rolls back automatically:
  ```bash
  helm upgrade --install <release> <chart> -n <ns> --atomic
  ```

## Confirm
```bash
helm status <release> -n <ns>      # deployed
```
