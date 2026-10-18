#!/usr/bin/env bash
# P4: the API on Azure Container Apps (East US 2), from the public GHCR image.
#   deploy/azure.sh <tag>        # an image pushed by deploy/image.sh, e.g. 9b94b98
# The first run creates alinka-rg, alinka-env and alinka-api; later runs refresh the secrets
# and roll a new revision on the given image. One replica stays warm (1 CPU, 2 GiB).
# Secret values come from .env through the API's own settings and become Container Apps
# secrets that the environment variables reference with secretref:. Nothing echoes them.
set -euo pipefail
cd "$(dirname "$0")/.."

RG=alinka-rg
LOCATION=eastus2
ENVIRONMENT=alinka-env
APP=alinka-api
REPO=ghcr.io/alined-labs/alinka-api
TAG="${1:?usage: deploy/azure.sh <image tag>}"
IMAGE="$REPO:$TAG"
# VARIABLE=secret-name: what the API reads, and the Container Apps secret behind it.
SECRETS=(
  ANTHROPIC_API_KEY=anthropic-api-key
  OPENROUTER_API_KEY=openrouter-api-key
  DATABASE_URL=database-url
  EDGE_SECRET=edge-secret
  ADMIN_TOKEN=admin-token
)

[ -f .env ] || { echo "azure.sh: no .env in $(pwd)" >&2; exit 1; }

setting() { # the value the API's settings read for $1 from .env (a shell export can't override)
  env -u "$1" uv run --quiet python -c '
import sys
from alinka.settings import Settings
value = getattr(Settings(), sys.argv[1].lower())
value = value.get_secret_value() if hasattr(value, "get_secret_value") else value
sys.stdout.write("" if value is None else str(value))' "$1"
}

values=() secret_args=() env_args=(CACHE_MODE=replay)
for pair in "${SECRETS[@]}"; do
  var="${pair%%=*}" name="${pair#*=}"
  value="$(setting "$var")"
  [ -n "$value" ] || { echo "azure.sh: $var is empty in .env" >&2; exit 1; }
  values+=("$value")
  secret_args+=("$name=$value")
  env_args+=("$var=secretref:$name")
done

az_quiet() { # az with no output; on failure, its message with every secret value masked
  local err v
  if ! err="$(az "$@" --only-show-errors -o none 2>&1)"; then
    for v in "${values[@]}"; do err="${err//"$v"/***}"; done
    printf 'azure.sh: az %s %s failed:\n%s\n' "$1" "$2" "$err" >&2
    exit 1
  fi
}

# Container Apps pulls without credentials, so the package must be public.
path="${REPO#ghcr.io/}"
token="$(curl -fs "https://ghcr.io/token?scope=repository:$path:pull" | jq -r .token)" || token=""
accept="application/vnd.oci.image.index.v1+json,application/vnd.oci.image.manifest.v1+json"
accept+=",application/vnd.docker.distribution.manifest.v2+json"
if ! curl -fs -o /dev/null -H "Authorization: Bearer $token" -H "Accept: $accept" \
  "https://ghcr.io/v2/$path/manifests/$TAG"; then
  echo "azure.sh: $IMAGE is not publicly pullable; push it and make the package public" >&2
  exit 1
fi

az_quiet group create -n "$RG" -l "$LOCATION"
if ! az containerapp env show -n "$ENVIRONMENT" -g "$RG" -o none 2>/dev/null; then
  echo "creating $ENVIRONMENT (a few minutes)"
  az_quiet containerapp env create -n "$ENVIRONMENT" -g "$RG" -l "$LOCATION"
fi

common=(--image "$IMAGE" --cpu 1.0 --memory 2.0Gi --min-replicas 1 --max-replicas 2
  --revision-suffix "r$TAG-$(date -u +%H%M%S)")
if az containerapp show -n "$APP" -g "$RG" -o none 2>/dev/null; then
  echo "updating $APP to $IMAGE"
  az_quiet containerapp secret set -n "$APP" -g "$RG" --secrets "${secret_args[@]}"
  az_quiet containerapp update -n "$APP" -g "$RG" "${common[@]}" --set-env-vars "${env_args[@]}"
else
  echo "creating $APP on $IMAGE"
  az_quiet containerapp create -n "$APP" -g "$RG" --environment "$ENVIRONMENT" "${common[@]}" \
    --target-port 8000 --ingress external --secrets "${secret_args[@]}" --env-vars "${env_args[@]}"
fi

fqdn="$(az containerapp show -n "$APP" -g "$RG" --query properties.configuration.ingress.fqdn -o tsv)"
url="https://$fqdn"
for _ in $(seq 1 40); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' "$url/api/health")" = 200 ] && break
  sleep 3
done
echo "image:  $IMAGE"
echo "url:    $url"
echo "health: $(curl -s "$url/api/health")"
echo "board without the edge secret: HTTP $(curl -s -o /dev/null -w '%{http_code}' \
  "$url/api/board?view=canonical") (403 expected)"
