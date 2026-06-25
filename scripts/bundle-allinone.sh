#!/usr/bin/env bash
# OUTSIDE airgap: build the single all-in-one image and save to one tar.
# Model is baked into the image, so the tar is the ONLY thing you carry in.
set -euo pipefail

MODEL="${MODEL:-qwen2.5-coder:7b}"
K8SGPT_VERSION="${K8SGPT_VERSION:-0.3.48}"
TAG="${TAG:-k8sgpt-ui:allinone}"
OUT="${OUT:-k8sgpt-ui-allinone.tar}"

cd "$(dirname "$0")/.."

echo "==> Building ${TAG} (model ${MODEL} baked in — this is slow + large)"
docker build -f Dockerfile.allinone \
    --build-arg MODEL="${MODEL}" \
    --build-arg K8SGPT_VERSION="${K8SGPT_VERSION}" \
    -t "${TAG}" .

echo "==> Saving image -> ${OUT}"
docker save "${TAG}" -o "${OUT}"

echo
echo "DONE. Carry ONE file into the airgap:  ${OUT}"
du -sh "${OUT}"
echo
echo "Inside airgap:"
echo "  docker load -i ${OUT}"
echo "  docker run -d -p 8080:8080 \\"
echo "    -e KUBECONFIG_B64=\"\$(base64 -w0 ~/.kube/config)\" \\"
echo "    --name k8sgpt-ui ${TAG}"
echo "  open http://localhost:8080"
