#!/usr/bin/env bash
# Run OUTSIDE the airgap (internet-connected box).
# Builds everything, pulls the model, and packs it all into ONE folder to carry in.
set -euo pipefail

MODEL="${MODEL:-qwen2.5-coder:7b}"
OUT="${OUT:-airgap-bundle}"

cd "$(dirname "$0")/.."

echo "==> Building UI image (downloads k8sgpt binary)"
docker compose build ui

echo "==> Pulling base images"
docker compose pull ollama

echo "==> Starting ollama to pull the model into ./ollama-data"
docker compose up -d ollama
sleep 5
docker exec ollama ollama pull "$MODEL"
docker compose down

echo "==> Saving images to tar"
mkdir -p "$OUT"
docker save ollama/ollama:latest k8sgpt-ui:local -o "$OUT/images.tar"

echo "==> Copying model blobs + project files"
cp -r ollama-data "$OUT/ollama-data"
cp docker-compose.yml "$OUT/"
cp -r runbooks "$OUT/runbooks"
cp scripts/load.sh "$OUT/"

echo
echo "DONE. Carry the '$OUT/' folder into the airgap."
echo "Size:"
du -sh "$OUT"
