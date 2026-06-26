#!/usr/bin/env bash
# All-in-one entrypoint: start Ollama in background, wire kubeconfig, run UI.
set -e

# --- kubeconfig: accept base64 env, raw env, or mounted file ---
mkdir -p "$(dirname "${KUBECONFIG:-/root/.kube/config}")"
if [ -n "${KUBECONFIG_B64:-}" ]; then
    echo "[entrypoint] decoding KUBECONFIG_B64 -> ${KUBECONFIG}"
    echo "${KUBECONFIG_B64}" | base64 -d > "${KUBECONFIG}"
elif [ -n "${KUBECONFIG_CONTENT:-}" ]; then
    echo "[entrypoint] writing KUBECONFIG_CONTENT -> ${KUBECONFIG}"
    printf '%s' "${KUBECONFIG_CONTENT}" > "${KUBECONFIG}"
elif [ -f "${KUBECONFIG}" ]; then
    echo "[entrypoint] using mounted kubeconfig at ${KUBECONFIG}"
else
    echo "[entrypoint] no kubeconfig -> cluster scan disabled, paste-error mode still works"
fi

# --- start ollama in background ---
echo "[entrypoint] starting ollama..."
ollama serve &
OLLAMA_PID=$!

# --- wait for ollama to be ready ---
for i in $(seq 1 30); do
    if curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "[entrypoint] ollama up"
        break
    fi
    sleep 1
done

# --- verify the baked-in model is present (AIRGAP: never pull at runtime) ---
# The model is baked into the image at build time. At runtime nothing is downloaded,
# so the container works with zero internet. If the model is missing it means the
# image was built wrong (or a volume was mounted over /root/.ollama) — fail loudly.
if ! ollama list 2>/dev/null | grep -q "${MODEL%%:*}"; then
    echo "[entrypoint] FATAL: model '${MODEL}' is not baked into this image."
    echo "[entrypoint] This image must run fully offline; the model is included at"
    echo "[entrypoint] build time. Do NOT mount a volume over /root/.ollama, and"
    echo "[entrypoint] rebuild the image if the model is genuinely missing."
    exit 1
fi
echo "[entrypoint] model ${MODEL} present (baked at build, no download needed)"

# --- warm the model in the background so the first user query isn't a cold load ---
# (runs in parallel; UI comes up immediately, model loads into RAM meanwhile)
(
    curl -fsS http://localhost:11434/api/generate \
        -d "{\"model\":\"${MODEL}\",\"prompt\":\"ok\",\"stream\":false,\"keep_alive\":\"30m\"}" \
        >/dev/null 2>&1 \
        && echo "[entrypoint] model warm" \
        || echo "[entrypoint] model warm-up skipped/failed (non-fatal)"
) &

# --- run the UI in foreground on UI_PORT ---
echo "[entrypoint] starting UI on :${UI_PORT}"
exec python3 -m streamlit run /app/app.py \
    --server.port="${UI_PORT}" \
    --server.address=0.0.0.0 \
    --server.headless=true
