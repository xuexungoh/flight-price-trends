#!/usr/bin/env bash
# Copies the freshly built artifact.html into public/index.html and pushes a
# production deployment to Vercel. Called daily by the flight-price-daily-scrape
# scheduled task and runnable manually:
#
#   bash deploy.sh           # uses .vercel-token from this folder
#   VERCEL_TOKEN=xxx bash deploy.sh
set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Resolve token: env var first, then .vercel-token file
TOKEN="${VERCEL_TOKEN:-}"
if [ -z "$TOKEN" ] && [ -f .vercel-token ]; then
  TOKEN=$(tr -d '[:space:]' < .vercel-token)
fi
if [ -z "$TOKEN" ]; then
  echo "ERROR: no Vercel token found. Set VERCEL_TOKEN env var or write the token to .vercel-token" >&2
  exit 2
fi

# Ensure Vercel CLI is on PATH. Install once per session if needed.
if ! command -v vercel >/dev/null 2>&1; then
  export PATH="/tmp/npm-prefix/bin:$PATH"
  if ! command -v vercel >/dev/null 2>&1; then
    mkdir -p /tmp/npm-prefix
    npm config set prefix /tmp/npm-prefix
    npm install -g vercel >/dev/null 2>&1
    export PATH="/tmp/npm-prefix/bin:$PATH"
  fi
fi

# Stage the freshly built artifact as the site root.
mkdir -p public
cp -f artifact.html public/index.html

# First-time deploy auto-creates the project under the token's owner.
exec vercel deploy --prod --yes --token "$TOKEN" --name flight-price-trends 2>&1
