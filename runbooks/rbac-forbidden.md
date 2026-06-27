# RBAC "Forbidden" / insufficient permissions

## Symptoms
```
Error from server (Forbidden): <resource> is forbidden:
  User "system:serviceaccount:<ns>:<sa>" cannot <verb> resource "<res>"
  in API group "<group>" at the cluster scope
```
An app, controller, or Helm release fails because its ServiceAccount lacks rights.

## Triage
```bash
# does the SA have the permission?
kubectl auth can-i <verb> <resource> --as=system:serviceaccount:<ns>:<sa> -n <ns>
kubectl get rolebinding,clusterrolebinding -A | grep <sa>
kubectl describe clusterrole <role>
```

## Common causes & fixes
- **No (Cluster)RoleBinding for the SA** — bind a Role granting just what's needed:
  ```bash
  kubectl create rolebinding <name> --role=<role> \
    --serviceaccount=<ns>:<sa> -n <ns>
  ```
- **Wrong scope** — namespaced RoleBinding but the resource is cluster-scoped (needs a
  ClusterRoleBinding), or vice-versa.
- **Verb/apiGroup/resource mismatch** — the Role must list the exact `verbs`,
  `apiGroups`, and `resources` from the error.
- **Helm needs broader rights** — the SA running Helm can't create the chart's objects;
  grant a matching Role (avoid blanket `cluster-admin` in production).
- **Wrong ServiceAccount** — pod uses `default` SA with no rights; set
  `serviceAccountName:` to the intended one.

## Confirm
```bash
kubectl auth can-i <verb> <resource> --as=system:serviceaccount:<ns>:<sa> -n <ns>  # yes
```
