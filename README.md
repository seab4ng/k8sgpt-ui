# k8sgpt-ui

Airgap troubleshooting assistant for **Helm** and **Kubernetes**. A web UI where
you paste an error (or scan a cluster) and a **local** LLM suggests the fix —
grounded in your own runbooks, with conversation context kept. **No internet at
runtime.**

Everything (Ollama + the model + `k8sgpt` + the UI + runbooks) is baked into a
**single image** at build time. You carry one image into the airgap and run one
container — nothing is downloaded when it runs.

## What it does

Two modes, one chat thread (context kept across both):

| Mode | When | How |
|------|------|-----|
| **Paste error** | You already have the error text (e.g. failed `helm install`) | Text → local model (+ matching runbook) → fix. Vague wording works. |
| **Scan cluster** | "Something's broken, no error in hand" | `k8sgpt` detects problems in the cluster (JSON) → model explains + fixes. |

```
Browser → Streamlit UI ──┬─ paste error → model (+ runbooks) → fix
                         └─ Scan cluster → k8sgpt (detect) → model → explain
         context kept in session
```

- **Model:** `qwen2.5-coder:3b` (default) or `qwen2.5-coder:7b`, via a local
  **Ollama** baked into the image (strong on YAML / Helm / k8s).
- **k8sgpt:** binary baked in, used as a pure detector (no AI backend wired into
  it — the UI's model does all explaining + holds context). Supports scanning all
  namespaces or specific ones.
- **Runbooks:** markdown in [`runbooks/`](runbooks/). BM25 keyword retrieval
  (airgap-friendly, no embeddings) optionally grounds answers; browse them in the
  UI. Add your own — see below.

## Which image / model?

Each release publishes **two** images — pick by your speed/quality trade-off:

| Image tag | Model | Image size | Speed (CPU) | Use when |
|-----------|-------|-----------|-------------|----------|
| `…-qwen2.5-coder-3b` | 3B (Q4) | ~4 GB | ~2× faster | **default** — great for "explain + fix this error" |
| `…-qwen2.5-coder-7b` | 7B (Q4) | ~7 GB | baseline | you want higher-quality reasoning |

Runs CPU-only. **8 vCPU recommended** for responsive answers (4 works but is slow);
RAM need is ~3 GB (3B) / ~6 GB (7B) resident. A GPU is the only way to make it
genuinely fast.

## Run it (connected box)

With Docker Compose ([`docker-compose-files/`](docker-compose-files/) — works the
same on Windows and Linux):

```bash
cd docker-compose-files
docker compose up -d
# open http://localhost:8080
```

Provide cluster access by clicking **Upload kubeconfig** in the sidebar, or use
`docker-compose.with-kubeconfig.yml` to bind-mount one. See
[`docker-compose-files/README.md`](docker-compose-files/README.md).

Or with plain `docker run`:
```bash
docker run -d -p 8080:8080 \
  -e KUBECONFIG_B64="$(base64 -w0 ~/.kube/config)" \
  --name k8sgpt-ui sokushinbutsu/k8sgpt-ui:1.0.0-qwen2.5-coder-3b
```

### Passing the kubeconfig (pick one)
| Method | How |
|--------|-----|
| **upload in UI** (simplest) | sidebar → **Upload kubeconfig** → used immediately |
| base64 env | `-e KUBECONFIG_B64="$(base64 -w0 ~/.kube/config)"` |
| raw env | `-e KUBECONFIG_CONTENT="$(cat ~/.kube/config)"` |
| mount file | `-v /path/to/kubeconfig:/root/.kube/config:ro` |
| none | paste-error mode still works |

The box running this must reach the cluster API server (`server:` URL in the
kubeconfig). **GKE note:** a kubeconfig using the `gke-gcloud-auth-plugin` exec
auth won't work inside the container (no `gcloud` there) — use a static/token
kubeconfig, or upload through the UI. Paste-error mode needs no kubeconfig.

## Airgap deploy (single file, zero runtime internet)

The model is baked at **build time**; at **runtime nothing is pulled or
downloaded**. Carry one tar in.

```bash
# OUTSIDE the airgap (internet) — build + save one tar (default model 3b)
bash scripts/bundle-allinone.sh
#   -> k8sgpt-ui-local-qwen2.5-coder-3b.tar
# (for 7B:  MODEL=qwen2.5-coder:7b bash scripts/bundle-allinone.sh)

# carry the .tar in, then INSIDE the airgap:
docker load -i k8sgpt-ui-local-qwen2.5-coder-3b.tar
docker run -d -p 8080:8080 \
  -e KUBECONFIG_B64="$(base64 -w0 ~/.kube/config)" \
  --name k8sgpt-ui k8sgpt-ui:local-qwen2.5-coder-3b
# open http://localhost:8080
```

If you build via CI instead, pull the published image on a connected box and
`docker save` it to a tar the same way.

> ⚠️ Do **not** mount a volume over `/root/.ollama` — that would hide the baked-in
> model, and the container refuses to start (it never pulls at runtime, by design).

## Build the image yourself

Two Dockerfiles, identical except the baked model:
```bash
docker build -f Dockerfile.qwen2.5-coder-3b -t k8sgpt-ui:3b .   # ~4 GB
docker build -f Dockerfile.qwen2.5-coder-7b -t k8sgpt-ui:7b .   # ~7 GB
```
Build needs internet (it pulls the model into the image). After that the image
runs fully offline.

## CI — release builds (GitHub Actions)

[`.github/workflows/build-allinone.yml`](.github/workflows/build-allinone.yml)
runs **only on a tag** (a plain branch push builds nothing). Each tag builds and
pushes **both** images to Docker Hub `sokushinbutsu/k8sgpt-ui`:

```
git tag 1.0.0 && git push origin 1.0.0
#  -> sokushinbutsu/k8sgpt-ui:1.0.0-qwen2.5-coder-3b
#  -> sokushinbutsu/k8sgpt-ui:1.0.0-qwen2.5-coder-7b
```
(A leading `v` is stripped: `v1.0.0` → `1.0.0-…`. No `latest` tag is published.)

### Required repo secrets
Settings → Secrets and variables → Actions:
| Secret | Value |
|--------|-------|
| `DOCKERHUB_USERNAME` | `sokushinbutsu` |
| `DOCKERHUB_TOKEN` | Docker Hub access token (Account Settings → Security → New Access Token) |

## Config (runtime env vars)

Most settings are baked into the image. These are the ones you may set at runtime:

| Var | Default | Meaning |
|-----|---------|---------|
| `KUBECONFIG_B64` / `KUBECONFIG_CONTENT` | – | inject a kubeconfig at startup |
| `OLLAMA_KEEP_ALIVE` | `30m` | keep the model warm between queries |
| `OLLAMA_NUM_CTX` | `8192` | model context window |
| `MAX_SCAN_CHARS` | `9000` | cap on scan text fed to the model (trade completeness for speed) |
| `STREAMLIT_SERVER_ENABLE_CORS` / `…_XSRF_PROTECTION` | – | set `false` behind a reverse proxy so the UI connects |

> Do **not** set `MODEL` at runtime — it must match the model baked into the image
> (the 3B image bakes 3B, the 7B image bakes 7B). Pick the model by choosing the
> image tag.

## Add your own runbooks

Drop more `*.md` files into [`runbooks/`](runbooks/). One error per file:
symptom → triage → root cause → fix → confirm, then rebuild the image. Seeded
examples include CrashLoopBackOff, ImagePullBackOff, Helm hook/lock conflicts,
stale admission webhooks, missing/duplicate CRDs, PVC/PV binding issues,
ContainerCreating subPath, and container permission errors.

## Notes / limits

- `k8sgpt` reads **cluster state**, not your terminal. A pure helm *client* error
  (e.g. hook conflict) may leave nothing in the cluster → use **paste** mode.
  Scan mode shines for broken pods/jobs/configs already live.
- Chat history resets on browser refresh (kept only within a session) — use the
  **Export chat** button (Markdown or PDF) to save a conversation.
- `K8SGPT_VERSION` is pinned in the Dockerfiles; verify/bump against
  <https://github.com/k8sgpt-ai/k8sgpt/releases>.
