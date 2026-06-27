# NetworkPolicy blocking traffic (connection timeouts)

## Symptoms
```
# pod-to-pod or pod-to-DNS connections time out (not "refused")
dial tcp <ip>:<port>: i/o timeout
```
Connectivity that should work silently times out after a NetworkPolicy was added.

## Triage
```bash
kubectl get networkpolicy -A
kubectl describe networkpolicy <name> -n <ns>
kubectl get pods -n <ns> --show-labels       # do podSelectors match intended pods?
```

## Common causes & fixes
- **Default-deny with no allow rule** — once any policy selects a pod, all non-matching
  traffic is denied. Add explicit `ingress`/`egress` allow rules for the flows you need.
- **DNS egress forgotten** — a default-deny egress breaks name resolution. Allow egress
  to kube-system DNS on UDP+TCP **53**.
- **Wrong podSelector / namespaceSelector** — labels don't match the real pods/namespaces;
  fix the selectors (remember an empty selector means "all").
- **Policy in the wrong namespace** — NetworkPolicies are namespaced; they only affect
  pods in their own namespace.
- **CNI doesn't enforce NetworkPolicy** — some CNIs ignore them; if a policy "isn't
  working" at all, confirm the CNI supports enforcement.

## Confirm
```bash
kubectl exec <src-pod> -n <ns> -- nc -z -w3 <dst-svc> <port> && echo ok
```
