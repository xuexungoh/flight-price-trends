#!/usr/bin/env bash
# Publishes the freshly built artifact to the xuexungoh/flight-price-trends
# GitHub repo so GitHub Pages re-serves it at
#   https://xuexungoh.github.io/flight-price-trends/
#
# The Cowork sandbox mount has flaky atomic-write semantics for .git, so we
# clone into /tmp, copy the artifact in, commit, and push.
#
# Reads the GitHub PAT from .github-token in this folder (or $GITHUB_TOKEN).

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

REPO_OWNER="xuexungoh"
REPO_NAME="flight-price-trends"
BRANCH="main"

TOKEN="${GITHUB_TOKEN:-}"
if [ -z "$TOKEN" ] && [ -f .github-token ]; then
  TOKEN=$(tr -d '[:space:]' < .github-token)
fi
if [ -z "$TOKEN" ]; then
  echo "ERROR: no GitHub token. Set GITHUB_TOKEN or write to .github-token" >&2
  exit 2
fi

WORK="/tmp/${REPO_NAME}-work"
rm -rf "$WORK"
git clone --quiet --depth 1 \
  "https://${TOKEN}@github.com/${REPO_OWNER}/${REPO_NAME}.git" "$WORK"

# Refresh the published file tree: artifact + raw data + scripts, no secrets.
# Skip the source's .git (workspace mount has a stale one), skip secrets and caches.
rsync -a \
  --exclude='.git/' \
  --exclude='.github-token' --exclude='.vercel-token' \
  --exclude='.DS_Store' --exclude='.vercel' \
  --exclude='tmp/' --exclude='__pycache__/' --exclude='*.pyc' \
  ./ "$WORK/"

# GitHub Pages serves /index.html from the branch root, so make a copy there.
cp -f artifact.html "$WORK/index.html"

cd "$WORK"
git config user.email "xuexun@eogspecialist.com"
git config user.name "flight-price-bot"

git add -A
if git diff --cached --quiet; then
  echo "no changes to deploy"
  exit 0
fi

STAMP=$(date -u +%Y-%m-%dT%H:%MZ)
git commit -m "Daily update ${STAMP}" --quiet
git push --quiet origin "$BRANCH"

echo "deployed at $(date -u +%FT%TZ) — https://${REPO_OWNER}.github.io/${REPO_NAME}/"
