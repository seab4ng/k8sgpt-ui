# Admission webhook blocking everything (stale/orphaned webhook)

## Symptoms
```
Error from server (InternalError): Internal error occurred: failed calling webhook
"xxx.yyy.svc": failed to call webhook: Post "https://xxx.svc:443/...": dial tcp ... connect: connection refused
```
Operator/chart was uninstalled but its `ValidatingWebhookConfiguration` /
`MutatingWebhookConfiguration` stayed behind. The webhook points at a Service/pod
that no longer exists, so the API server rejects create/update of matching objects.

## Triage
```bash
kubectl get validatingwebhookconfigurations
kubectl get mutatingwebhookconfigurations
# find the one whose clientConfig.service points at a gone namespace/service
kubectl get validatingwebhookconfiguration <name> -o yaml | grep -A6 clientConfig
```

## Common causes & fixes
- **Orphaned webhook after uninstall** — delete the dangling config:
  ```bash
  kubectl delete validatingwebhookconfiguration <name>
  kubectl delete mutatingwebhookconfiguration <name>
  ```
- **Webhook pod down but should exist** — fix the backing Deployment/Service instead
  of deleting the webhook (check pods in its namespace).
- **`failurePolicy: Fail`** makes an unreachable webhook block the whole resource type.
  For first-party webhooks that should tolerate downtime, consider `failurePolicy: Ignore`.
- **Namespace stuck Terminating** because a webhook intercepts the finalizer — delete
  the webhook config first, then the namespace finishes.

## Confirm
```bash
kubectl apply -f <thing-that-was-blocked>.yaml   # should now succeed
```
