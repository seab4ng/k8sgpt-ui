# Pod stuck ContainerCreating — subPath does not exist

## Symptoms
```
STATUS: ContainerCreating   (never progresses)
Events:
  Warning  Failed  ... failed to create subPath directory ...
  # or a silent hang with a mount that references subPath:
  MountVolume.SetUp failed for volume "v": ... no such file or directory
```
The volume mounts a `subPath` (or `subPathExpr`) pointing at a directory that doesn't
exist on the volume yet, so the kubelet can't set up the mount.

## Triage
```bash
kubectl describe pod <pod> -n <ns>            # look for subPath in the mount + events
kubectl get pod <pod> -n <ns> -o jsonpath='{.spec.containers[*].volumeMounts}'
```

## Common causes & fixes
- **subPath dir missing on the volume** — the referenced subdirectory must pre-exist on
  the PV/volume. Create it (mount the volume in a throwaway pod and `mkdir`), or drop the
  `subPath` and mount the whole volume.
- **Typo / wrong case in subPath** — must match the on-disk path exactly.
- **subPathExpr with empty variable** — an unresolved env var yields a bad path; verify
  the env exists in the container.
- **Read-only or wrong-fs-perms volume** — kubelet can't auto-create the subdir; create it
  manually or fix volume permissions.
- **ConfigMap/Secret as subPath** — those don't auto-update and the key must exist; confirm
  the key name matches the subPath.

## Confirm
```bash
kubectl get pod <pod> -n <ns> -w    # moves past ContainerCreating to Running
```
