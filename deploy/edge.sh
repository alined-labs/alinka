#!/usr/bin/env bash
# P5: the Worker alinka-edge on https://alinka.alinedlabs.co: the built front end, and the frozen
# API, /api/* answered from the recorded responses in web/public/snapshot/ (edge/src/frozen.ts).
#   deploy/edge.sh [ref]          # default: origin/main
# Builds web/ from a git archive of the ref (only committed files ship, so the snapshot must be
# committed) and deploys edge/ from the same export. No secret: the Worker calls nothing.
set -euo pipefail
cd "$(dirname "$0")/.."

WRANGLER=(pnpm dlx wrangler@4.151.0)
URL=https://alinka.alinedlabs.co

sha="$(git rev-parse --verify "${1:-origin/main}^{commit}")"
src="$(mktemp -d)"
trap 'rm -rf "$src"' EXIT
git archive "$sha" | tar -x -C "$src"
[ -f "$src/web/public/snapshot/manifest.json" ] || {
  echo "edge.sh: ${sha:0:7} has no web/public/snapshot/manifest.json, so /api would answer nothing" >&2
  exit 1
}
echo "building web/ at ${sha:0:7}"
(cd "$src" && pnpm install --frozen-lockfile --silent && pnpm --filter ./web run build >/dev/null)

cd "$src/edge" # no .env here, so wrangler loads none
"${WRANGLER[@]}" deploy

code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
for _ in $(seq 1 30); do
  [ "$(code "$URL/api/health")" = 200 ] && break
  sleep 2
done
echo "health:  $(curl -s -w ' (HTTP %{http_code})' "$URL/api/health")"
echo "page /:  HTTP $(code "$URL/")"
echo "board through the Worker: HTTP $(code "$URL/api/board?view=canonical") (200 expected)"
# Only the frozen Worker sends this header: its absence means the old one still answers.
echo "snapshot: $(curl -s -o /dev/null -D - "$URL/api/health" | tr -d '\r' | grep -i '^x-alinka-snapshot:' || echo 'missing')"
