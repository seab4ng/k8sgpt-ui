#!/usr/bin/env bash
# OUTSIDE airgap: build an all-in-one image (model BAKED IN) and save to one tar.
# The tar is the ONLY thing you carry into the airgap — at runtime nothing is
# downloaded, so the container works with zero internet.
#
# Usage:
#   scripts/bundle-allinone.sh                       # default model qwen2.5-coder:3b
#   MODEL=qwen2.5-coder:7b scripts/bundle-allinone.sh
set -euo pipefail

# pick the model: qwen2.5-coder:3b (default, smaller/faster) or qwen2.5-coder:7b
MODEL="${MODEL:-qwen2.5-coder:3b}"
K8SGPT_VERSION="${K8SGPT_VERSION:-0.3.48}"
VERSION="${VERSION:-local}"

case "$MODEL" in
    qwen2.5-coder:3b) DOCKERFILE=Dockerfile.qwen2.5-coder-3b; SUFFIX=qwen2.5-coder-3b ;;
    qwen2.5-coder:7b) DOCKERFILE=Dockerfile.qwen2.5-coder-7b; SUFFIX=qwen2.5-coder-7b ;;
    *) echo "Unsupported MODEL '$MODEL' (use qwen2.5-coder:3b or qwen2.5-coder:7b)"; exit 1 ;;
esac

TAG="${TAG:-k8sgpt-ui:${VERSION}-${SUFFIX}}"
OUT="${OUT:-k8sgpt-ui-${VERSION}-${SUFFIX}.tar}"

cd "$(dirname "$0")/.."

echo "==> Building ${TAG} from ${DOCKERFILE} (model ${MODEL} baked in — slow + large)"
docker build -f "${DOCKERFILE}" \
    --build-arg MODEL="${MODEL}" \
    --build-arg K8SGPT_VERSION="${K8SGPT_VERSION}" \
    --build-arg APP_VERSION="${VERSION}" \
    -t "${TAG}" .

echo "==> Saving image -> ${OUT}"
docker save "${TAG}" -o "${OUT}"

echo
echo "DONE. Carry ONE file into the airgap:  ${OUT}"
du -sh "${OUT}"
echo
echo "Inside airgap (no internet needed):"
echo "  docker load -i ${OUT}"
echo "  docker run -d -p 8080:8080 \\"
echo "    -e KUBECONFIG_B64=\"\$(base64 -w0 ~/.kube/config)\" \\"
echo "    --name k8sgpt-ui ${TAG}"
echo "  open http://localhost:8080"
