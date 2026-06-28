#!/usr/bin/env bash
# OUTSIDE airgap: build an all-in-one image (model BAKED IN) and save to one tar.
# The tar is the ONLY thing you carry into the airgap — at runtime nothing is
# downloaded, so the container works with zero internet.
#
# Usage:
#   scripts/bundle-allinone.sh                       # default model gemma3:4b
#   MODEL=gemma2:9b scripts/bundle-allinone.sh
set -euo pipefail

# pick the model: gemma3:4b (default, smaller/faster) or gemma2:9b
MODEL="${MODEL:-gemma3:4b}"
K8SGPT_VERSION="${K8SGPT_VERSION:-0.3.48}"
VERSION="${VERSION:-local}"

case "$MODEL" in
    gemma3:4b) DOCKERFILE=Dockerfile.gemma3-4b; SUFFIX=gemma3-4b ;;
    gemma2:9b) DOCKERFILE=Dockerfile.gemma2-9b; SUFFIX=gemma2-9b ;;
    *) echo "Unsupported MODEL '$MODEL' (use gemma3:4b or gemma2:9b)"; exit 1 ;;
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
