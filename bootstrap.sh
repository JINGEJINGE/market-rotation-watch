#!/usr/bin/env bash
# Market Rotation Watch — fetch the pipeline (code + config + universe lists) from GitHub into ./mrw
# Usage: curl -sSL https://raw.githubusercontent.com/OWNER/REPO/main/bootstrap.sh | bash -s OWNER/REPO [branch]
set -euo pipefail
REPO="${1:?usage: bootstrap.sh OWNER/REPO [branch]}"
BRANCH="${2:-main}"
RAW="https://raw.githubusercontent.com/${REPO}/${BRANCH}"
mkdir -p mrw && cd mrw
curl -sSfL "${RAW}/MANIFEST.txt" -o MANIFEST.txt
n=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  mkdir -p "$(dirname "$f")"
  curl -sSfL "${RAW}/${f}" -o "$f"
  n=$((n+1))
done < MANIFEST.txt
mkdir -p data/prices data/flows data/outputs digests
echo "fetched $n files from ${REPO}@${BRANCH}"
