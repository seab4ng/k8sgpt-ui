# Helm install fails — CRD already exists / ownership conflict

## Symptoms
```
Error: INSTALLATION FAILED: rendered manifests contain a resource that already exists.
Unable to continue with install: CustomResourceDefinition "foos.example.com" in namespace ""
exists and cannot be imported into the current release: invalid ownership metadata;
label validation error: missing key "app.kubernetes.io/managed-by": must be set to "Helm"
```
The CRD is already in the cluster (installed manually, by an operator, or by another
chart), and the chart you're installing also ships that CRD as a template.

## Triage
```bash
kubectl get crd foos.example.com -o jsonpath='{.metadata.labels}{"\n"}{.metadata.annotations}'
helm list -A | grep -i foo            # is another release already managing it?
```

## Common causes & fixes
- **CRD already managed elsewhere** — don't let this chart own it. Skip CRDs at install:
  ```bash
  helm install rel ./chart --skip-crds
  ```
- **Chart templates the CRD instead of using `crds/`** — CRDs in Helm's `crds/` dir are
  install-only and never templated/owned. Move CRD manifests there to avoid conflicts.
- **Adopt the existing CRD into the release** (Helm 3) — add the ownership metadata so
  Helm imports it instead of erroring:
  ```bash
  kubectl label crd foos.example.com app.kubernetes.io/managed-by=Helm --overwrite
  kubectl annotate crd foos.example.com \
    meta.helm.sh/release-name=rel meta.helm.sh/release-namespace=ns --overwrite
  ```
- **Two charts both ship the CRD** — pick one owner; disable the CRD in the other
  (e.g. `--set crds.enabled=false` if the chart supports it).

## Confirm
```bash
helm upgrade --install rel ./chart -n ns      # completes without ownership errors
```
