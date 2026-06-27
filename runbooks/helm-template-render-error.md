# Helm chart rendering / validation errors

## Symptoms
```
Error: UPGRADE FAILED: error validating "": error validating data:
  ValidationError(Deployment.spec): unknown field "..."
# or: template: <chart>/templates/x.yaml:12:14: executing ... <.Values.foo>: nil pointer
# or: YAML parse error on <chart>/templates/x.yaml
```
The chart produces invalid Kubernetes manifests, or templating fails.

## Triage
```bash
helm lint <chart>
helm template <release> <chart> -f values.yaml | less     # see exactly what's rendered
helm template <release> <chart> -f values.yaml | kubectl apply --dry-run=server -f -
```

## Common causes & fixes
- **Unknown/typo field** — a manifest key is misspelled or for the wrong apiVersion. Fix
  the template/field to match the resource schema.
- **Nil value / missing key** — `.Values.x` is undefined for the current values. Provide
  it, or guard with `default`: `{{ .Values.x | default "..." }}`.
- **Bad indentation from `toYaml`** — pipe through `nindent`: `{{ toYaml .Values.x | nindent 8 }}`.
- **Wrong apiVersion for the cluster** — e.g. a removed/older API; bump to the version the
  cluster serves (`kubectl api-resources`).
- **values.yaml type mismatch** — a string where a list/map is expected; align with the
  chart's expectations.

## Confirm
```bash
helm template <release> <chart> -f values.yaml | kubectl apply --dry-run=server -f -   # passes
```
