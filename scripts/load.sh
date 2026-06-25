#!/usr/bin/env bash
# Run INSIDE the airgap, from the carried-in bundle folder.
set -euo pipefail

echo "==> Loading images"
docker load -i images.tar

echo "==> Place your cluster kubeconfig at ./kubeconfig (for cluster-scan mode)"
if [ ! -f kubeconfig ]; then
  echo "    (no ./kubeconfig found — paste-error mode still works without it)"
fi

echo "==> Starting stack"
docker compose up -d

echo
echo "DONE. Open the UI:  http://localhost:8501"
echo "Ollama API:         http://localhost:11434"
