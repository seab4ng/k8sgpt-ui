# DNS resolution failing in-cluster (CoreDNS)

## Symptoms
```
# from a pod:
Could not resolve host: my-svc.my-ns.svc.cluster.local
dial tcp: lookup ... : no such host / i/o timeout
```
Services can't reach each other by name; intermittent or total DNS failure.

## Triage
```bash
kubectl get pods -n kube-system -l k8s-app=kube-dns         # CoreDNS Running?
kubectl logs -n kube-system -l k8s-app=kube-dns --tail=100
kubectl get svc -n kube-system kube-dns                     # ClusterIP exists
# test from a throwaway pod:
kubectl run dnstest --rm -it --image=busybox:1.36 --restart=Never -- \
  nslookup kubernetes.default
```

## Common causes & fixes
- **CoreDNS pods down / crashlooping** — check logs; common causes are a bad Corefile
  ConfigMap or OOM. Restart: `kubectl rollout restart deploy/coredns -n kube-system`.
- **CoreDNS can't reach upstream** — in airgap, an upstream `forward . /etc/resolv.conf`
  pointing at the internet hangs. Point upstream at your internal resolver, or remove it
  if only cluster names are needed.
- **NetworkPolicy blocks DNS** — a default-deny policy without a DNS egress rule breaks
  resolution; allow UDP/TCP 53 to kube-system (see networkpolicy runbook).
- **Wrong dnsPolicy** — pods with `dnsPolicy: Default` use the node resolver, not
  CoreDNS; use `ClusterFirst` for in-cluster names.
- **kube-dns Service missing/changed ClusterIP** — kubelet `--cluster-dns` must match.

## Confirm
```bash
kubectl run dnstest --rm -it --image=busybox:1.36 --restart=Never -- \
  nslookup my-svc.my-ns.svc.cluster.local
```
