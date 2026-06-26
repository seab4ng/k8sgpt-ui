# Running k8sgpt-ui with Docker Compose

The all-in-one image (Ollama + model + k8sgpt + UI + runbooks) is built and pushed
by CI, so you don't build anything locally — Compose just pulls and runs it.

Both files below run **identically on Windows and Linux** (Docker Desktop or Docker
Engine + the `docker compose` plugin).

> Images are published **per release** as `<version>-<model>` (there is no `latest`
> tag). The compose files default to `1.0.0-qwen2.5-coder-3b`; if you tagged a
> different version, set `K8SGPT_UI_IMAGE` (see "Common tweaks") so the tag exists
> on Docker Hub.

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
| Pick model / version | Images are published per release as `<version>-<model>`. Choose one: `K8SGPT_UI_IMAGE=sokushinbutsu/k8sgpt-ui:1.0.0-qwen2.5-coder-7b docker compose up -d` (default is the `-qwen2.5-coder-3b` build — smaller & ~2× faster on CPU) |
| Limit CPU/RAM | uncomment `cpus:` / `mem_limit:` (default = use all host cores/RAM) |
| Change the port | edit `"8080:8080"` → `"<host>:8080"` |

## Notes on speed
Inference here is CPU-bound. The default **3B** image is ~2× faster than the 7B and
is plenty for "explain + fix this error." **≥ 8 vCPU** is recommended for responsive
answers (4 works but is slow); RAM need is ~3 GB (3B) / ~6 GB (7B). The container
uses all host cores by default — don't set `cpus:` unless you want to cap it. A GPU
is the only way to make it genuinely fast.
