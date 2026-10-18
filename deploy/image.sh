#!/usr/bin/env bash
# P3: build the API image from a clean export of a commit and push it to GHCR.
#   deploy/image.sh [ref]        # default: origin/main; the tag is the commit's short SHA
# Docker must be logged in to ghcr.io with write:packages, for example:
#   gh auth token | docker login ghcr.io -u <github user> --password-stdin
# The export holds only committed files, so no .env or local build output reaches the image.
set -euo pipefail
cd "$(dirname "$0")/.."

REPO=ghcr.io/alined-labs/alinka-api
SOURCE=https://github.com/alined-labs/alinka
sha="$(git rev-parse --verify "${1:-origin/main}^{commit}")"
image="$REPO:${sha:0:7}"

src="$(mktemp -d)"
trap 'rm -rf "$src"' EXIT
git archive "$sha" | tar -x -C "$src"

docker build -f "$src/docker/Dockerfile.api" -t "$image" \
  --label "org.opencontainers.image.source=$SOURCE" \
  --label "org.opencontainers.image.revision=$sha" \
  --label "org.opencontainers.image.description=Alinka API (accounts-payable agent, Blinka challenge)" \
  "$src"
docker push "$image"
echo "pushed $image"
