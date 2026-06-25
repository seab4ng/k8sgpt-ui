# k8sgpt-ui

Airgap troubleshooting assistant for **Helm** and **Kubernetes**. A web UI where
you paste an error (or scan a cluster) and a **local** LLM suggests the fix —
grounded in your own runbooks, with conversation context kept. No internet at
runtime.

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

- **Model:** `qwen2.5-coder:7b` via local **Ollama** (strong on YAML / Helm / k8s).
- **k8sgpt:** binary baked into the UI image, used as a pure detector (no AI
  backend wired into it — the UI's model does all explaining + holds context).
- **Runbooks:** markdown in [`runbooks/`](runbooks/). Naive keyword retrieval
  injects the best match as context (airgap-friendly, no embeddings needed).

## Components

| Container | Image | Role |
|-----------|-------|------|
| `ollama`  | `ollama/ollama` | runs the model |
| `ui`      | built from [`ui/`](ui/) | Streamlit UI + `k8sgpt` binary |

## Size budget (airgap transfer)

| Item | Size |
|------|------|
| ollama image | ~1.5 GB |
| ui image (python + k8sgpt) | ~0.4 GB |
| model `qwen2.5-coder:7b` (Q4) | ~4.7 GB |
| **Total** | **~6.5 GB** |

Runs fine on a **16 GB RAM CPU-only** box (model uses ~6–7 GB; answers in
~20–60 s).

## Deploy

### 1. Outside the airgap — build + pull + pack
```bash
bash scripts/bundle.sh
# produces ./airgap-bundle/ (images.tar + ollama-data + compose + runbooks + load.sh)
```

### 2. Carry `airgap-bundle/` in (USB, ~6.5 GB).

### 3. Inside the airgap — load + run
```bash
cd airgap-bundle
# optional: drop your cluster kubeconfig here as ./kubeconfig (for scan mode)
bash load.sh
```

Open **http://localhost:8501**.

## Cluster scan setup (optional)

Scan mode needs a read-only kubeconfig for the target cluster. Put it at
`./kubeconfig`. The box running this must reach the cluster API server
(`server:` URL in the kubeconfig, usually port 6443). One UI can scan many
clusters — swap the kubeconfig.

Paste-error mode needs **no** kubeconfig.

## Config (env vars on the `ui` service)

| Var | Default | Meaning |
|-----|---------|---------|
| `OLLAMA_URL` | `http://ollama:11434` | Ollama endpoint |
| `MODEL` | `qwen2.5-coder:7b` | model name (must be pulled) |
| `KUBECONFIG` | `/root/.kube/config` | kubeconfig path inside container |

## Add your own runbooks

Drop more `*.md` files into [`runbooks/`](runbooks/). One error per file:
symptom → root cause → fix → confirm. Rebuild the UI image (or bind-mount the
folder). Seeded examples: Helm pre-install hook conflict, Helm "another
operation in progress", ImagePullBackOff, CrashLoopBackOff.

## All-in-one single image (one container, no compose)

Everything — Ollama + model + k8sgpt + UI — baked into **one** image. Run one
container, open `http://localhost:8080`. Carry a single tar into the airgap.

### Build (outside airgap)
```bash
bash scripts/bundle-allinone.sh        # -> k8sgpt-ui-allinone.tar (~6.5 GB)
# or directly:
docker build -f Dockerfile.allinone -t k8sgpt-ui:allinone .
```

### Run
```bash
docker run -d -p 8080:8080 \
  -e KUBECONFIG_B64="$(base64 -w0 ~/.kube/config)" \
  --name k8sgpt-ui k8sgpt-ui:allinone
```
Open **http://localhost:8080**.

### Passing the kubeconfig (pick one)
| Method | How |
|--------|-----|
| **base64 env** (recommended) | `-e KUBECONFIG_B64="$(base64 -w0 ~/.kube/config)"` |
| raw env | `-e KUBECONFIG_CONTENT="$(cat ~/.kube/config)"` |
| mount file | `-v /path/to/kubeconfig:/root/.kube/config:ro` |
| none | paste-error mode still works |

### Airgap transfer (single file)
```bash
# outside
bash scripts/bundle-allinone.sh
# carry k8sgpt-ui-allinone.tar in, then inside:
docker load -i k8sgpt-ui-allinone.tar
docker run -d -p 8080:8080 -e KUBECONFIG_B64="$(base64 -w0 ~/.kube/config)" \
  --name k8sgpt-ui k8sgpt-ui:allinone
```

Inside the container: `entrypoint.sh` starts `ollama serve`, wires the
kubeconfig from env, then launches the UI on `:8080`. Model is already baked in
— no runtime pull.

## CI — auto-build the image (GitHub Actions)

[`.github/workflows/build-allinone.yml`](.github/workflows/build-allinone.yml)
builds the all-in-one image (model baked in) and pushes it to **Docker Hub**
`sokushinbutsu/k8sgpt-ui` on every push to `main`, on `v*` tags, or manually
(Actions → build-allinone → Run).

Override model / k8sgpt version when running manually (workflow inputs).

### Required repo secrets
Settings → Secrets and variables → Actions:
| Secret | Value |
|--------|-------|
| `DOCKERHUB_USERNAME` | `sokushinbutsu` |
| `DOCKERHUB_TOKEN` | Docker Hub access token (Account Settings → Security → New Access Token) |

### Pull + run (connected box)
```bash
docker pull sokushinbutsu/k8sgpt-ui:allinone
docker run -d -p 8080:8080 \
  -e KUBECONFIG_B64="$(base64 -w0 ~/.kube/config)" \
  sokushinbutsu/k8sgpt-ui:allinone
```
Open **http://localhost:8080**.

### Get it into the airgap
Docker Hub is unreachable from the airgap. On a connected box:
```bash
docker pull sokushinbutsu/k8sgpt-ui:allinone
docker save sokushinbutsu/k8sgpt-ui:allinone -o k8sgpt-ui.tar
# carry k8sgpt-ui.tar in, then inside:
docker load -i k8sgpt-ui.tar
docker run -d -p 8080:8080 -e KUBECONFIG_B64="$(base64 -w0 ~/.kube/config)" \
  sokushinbutsu/k8sgpt-ui:allinone
```

### Notes
- Image is ~6.5 GB; the workflow frees runner disk before building.
- Tags pushed: `allinone`, `latest` (on main), `allinone-<sha>`, and the git tag on `v*`.

## Notes / limits

- `k8sgpt` reads **cluster state**, not your terminal. A pure helm *client*
  error (e.g. hook conflict) may leave nothing in the cluster → use **paste**
  mode for those. Scan mode shines for broken pods/jobs/configs already live.
- `K8SGPT_VERSION` is pinned in [`ui/Dockerfile`](ui/Dockerfile) and
  [`docker-compose.yml`](docker-compose.yml). Verify/bump against
  <https://github.com/k8sgpt-ai/k8sgpt/releases>.
- Bigger model? Set `MODEL=qwen2.5-coder:14b` (~9 GB, tighter on 16 GB RAM).
