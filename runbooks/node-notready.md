# Node NotReady

## Symptoms
```
kubectl get nodes
NAME       STATUS     ROLES    AGE   VERSION
worker-1   NotReady   <none>   30d   v1.30.2
```
Pods on the node go Unknown/Terminating; new pods won't schedule there.

## Triage
```bash
kubectl describe node <node>                 # Conditions + events (MemoryPressure, DiskPressure, PIDPressure)
kubectl get node <node> -o wide
# on the node itself:
systemctl status kubelet
journalctl -u kubelet -n 200 --no-pager
```

## Common causes & fixes
- **kubelet down / crashing** — restart and read its logs: `systemctl restart kubelet`.
- **DiskPressure** — node disk full (often image/log buildup). Free space, prune
  unused images: `crictl rmi --prune`.
- **MemoryPressure / PIDPressure** — node exhausted; evict/limit workloads or add capacity.
- **Container runtime down** — check `systemctl status containerd` (or crio/docker).
- **Network plugin (CNI) not ready** — node stays NotReady until CNI pods are Running
  (see CNI/DNS runbooks).
- **Clock skew / expired kubelet cert** — verify node time; renew the kubelet client cert.

## Confirm
```bash
kubectl get node <node> -w     # returns to Ready
```
