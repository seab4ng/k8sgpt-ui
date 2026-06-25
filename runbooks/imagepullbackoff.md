# Pod: ImagePullBackOff / ErrImagePull

## Symptoms
```
STATUS: ImagePullBackOff
Failed to pull image "<image>": ... not found / unauthorized / no such host
```

## Root causes & fixes

### Wrong image name or tag
```bash
kubectl describe pod <pod> -n <ns>   # read the exact image + error
```
Fix the `image:` in the deployment/values. In airgap, tag must point at your
internal registry, not docker.io.

### Airgap: image not mirrored / registry unreachable
- Confirm image exists in your private registry.
- Confirm nodes can reach the registry (`no such host` = DNS/network).
- Re-tag chart values to internal registry host.

### Private registry needs auth
Create + reference an imagePullSecret:
```bash
kubectl create secret docker-registry regcred \
  --docker-server=<registry> --docker-username=<u> --docker-password=<p> -n <ns>
```
```yaml
spec:
  imagePullSecrets:
    - name: regcred
```

## Confirm
```bash
kubectl get pod <pod> -n <ns> -w
```
