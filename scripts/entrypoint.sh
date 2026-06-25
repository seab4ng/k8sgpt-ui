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

# --- ensure model present (baked at build; pull as fallback if volume wiped it) ---
if ! ollama list 2>/dev/null | grep -q "${MODEL%%:*}"; then
    echo "[entrypoint] model ${MODEL} missing, pulling (needs network)..."
    ollama pull "${MODEL}" || echo "[entrypoint] WARN: model pull failed (airgap?)"
fi

# --- run the UI in foreground on UI_PORT ---
echo "[entrypoint] starting UI on :${UI_PORT}"
exec python3 -m streamlit run /app/app.py \
    --server.port="${UI_PORT}" \
    --server.address=0.0.0.0 \
    --server.headless=true
