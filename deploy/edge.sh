#!/usr/bin/env bash
# P5: the Worker alinka-edge on https://alinka.alinedlabs.co: the built front end, and /api/*
# forwarded to the API on Azure with the edge secret.
#   deploy/edge.sh [ref]          # default: origin/main
# Builds web/ from a git archive of the ref (only committed files ship), deploys edge/ from the
# same export, then pipes EDGE_SECRET (.env, read through the API's settings) into
# wrangler secret put. Nothing echoes it.
set -euo pipefail
cd "$(dirname "$0")/.."

WRANGLER=(pnpm dlx wrangler@4.151.0)
URL=https://alinka.alinedlabs.co
[ -f .env ] || { echo "edge.sh: no .env in $(pwd)" >&2; exit 1; }
secret="$(env -u EDGE_SECRET uv run --quiet python -c '
import sys
from alinka.settings import Settings
value = Settings().edge_secret
sys.stdout.write(value.get_secret_value() if value else "")')"
[ -n "$secret" ] || { echo "edge.sh: EDGE_SECRET is empty in .env" >&2; exit 1; }

sha="$(git rev-parse --verify "${1:-origin/main}^{commit}")"
src="$(mktemp -d)"
trap 'rm -rf "$src"' EXIT
git archive "$sha" | tar -x -C "$src"
echo "building web/ at ${sha:0:7}"
(cd "$src" && pnpm install --frozen-lockfile --silent && pnpm --filter ./web run build >/dev/null)

cd "$src/edge" # no .env here, so wrangler loads none
"${WRANGLER[@]}" deploy
printf '%s' "$secret" | "${WRANGLER[@]}" secret put EDGE_SECRET

code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
for _ in $(seq 1 30); do
  [ "$(code "$URL/api/health")" = 200 ] && break
  sleep 2
done
echo "health:  $(curl -s -w ' (HTTP %{http_code})' "$URL/api/health")"
echo "page /:  HTTP $(code "$URL/")"
echo "board through the Worker: HTTP $(code "$URL/api/board?view=canonical") (200 expected)"
