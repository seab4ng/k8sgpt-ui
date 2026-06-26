# Running k8sgpt-ui with Docker Compose

The all-in-one image (Ollama + model + k8sgpt + UI + runbooks) is built and pushed
by CI, so you don't build anything locally — Compose just pulls and runs it.

Both files below run **identically on Windows and Linux** (Docker Desktop or Docker
Engine + the `docker compose` plugin).

## Option 1 — recommended (no host paths, zero OS quirks)

```bash
docker compose up -d
```
Open <http://localhost:8080>, then click **Upload kubeconfig** in the sidebar to scan
a cluster. Stop with `docker compose down`.

This is the most foolproof option because it mounts nothing from the host.

## Option 2 — bind-mount a kubeconfig from disk

Use this if you'd rather not upload through the UI.

1. Put your kubeconfig file in **this folder**, named exactly `kubeconfig`, **or**
   set the `KUBECONFIG_HOST` variable to its full path (see comments in the file).
2. Run:
   ```bash
   docker compose -f docker-compose.with-kubeconfig.yml up -d
   ```

> The path must be an **existing file**, otherwise Docker creates an empty directory
> there and the scan fails.
>
> **GKE:** kubeconfigs using `gke-gcloud-auth-plugin` won't work inside the container
> (no `gcloud` there). Use a static/token-based kubeconfig, or just use Option 1.

## Common tweaks

| Want to… | Do this |
|---|---|
| Use a specific image tag | `K8SGPT_UI_IMAGE=sokushinbutsu/k8sgpt-ui:v1.2.3 docker compose up -d` |
| Change the model | edit `MODEL:` (e.g. `qwen2.5-coder:3b` for ~2× speed on CPU) |
| Limit CPU/RAM | uncomment `cpus:` / `mem_limit:` (default = use all host cores/RAM) |
| Change the port | edit `"8080:8080"` → `"<host>:8080"` |

## Notes on speed
Inference here is CPU-bound. A 7B model wants **≥ 8 vCPU** for usable speed; RAM
need is ~6 GB. The container uses all host cores by default — don't set `cpus:`
unless you want to cap it. A GPU is the only way to make 7B genuinely fast.
