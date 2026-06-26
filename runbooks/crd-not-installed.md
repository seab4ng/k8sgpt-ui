# CRD not installed — "no matches for kind" when creating a CR

## Symptoms
```
error: unable to recognize "cr.yaml": no matches for kind "Foo" in version "example.com/v1"
# or from a controller/helm:
no kind "Foo" is registered for version "example.com/v1"
```
You tried to create a custom resource (CR) before its CustomResourceDefinition (CRD)
exists in the cluster.

## Triage
```bash
kubectl get crd | grep -i foo                       # is the CRD present?
kubectl api-resources | grep -i foo                 # is the kind served?
kubectl get crd foos.example.com -o jsonpath='{.status.conditions}'
```

## Common causes & fixes
- **CRD never applied** — install it first, then the CR:
  ```bash
  kubectl apply -f crds/                  # CRDs
  kubectl wait --for condition=established crd/foos.example.com --timeout=60s
  kubectl apply -f cr.yaml                # then the custom resource
  ```
- **Helm ordering** — Helm installs files in `crds/` before templates, but CRDs created
  by a *separate* chart/operator must be installed and Established first. Split into two
  releases or add the operator as a dependency.
- **Wrong apiVersion** — the CRD serves a different `group/version` than the CR uses.
  Match `kubectl get crd foos.example.com -o jsonpath='{.spec.versions[*].name}'`.
- **CRD not yet Established** — newly applied; wait for the `Established` condition.

## Confirm
```bash
kubectl get foo -A
```
