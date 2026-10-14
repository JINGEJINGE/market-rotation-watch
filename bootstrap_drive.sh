#!/usr/bin/env bash
# Market Rotation Watch — fetch the pipeline zip from a public Google Drive file into ./mrw
# Usage: bash bootstrap_drive.sh <DRIVE_FILE_ID>
set -euo pipefail
ID="${1:?usage: bootstrap_drive.sh DRIVE_FILE_ID}"
curl -sSL -o mrw-pipeline.zip "https://drive.google.com/uc?export=download&id=${ID}"
if ! unzip -tq mrw-pipeline.zip >/dev/null 2>&1; then
  # large-file interstitial: fetch again with the confirm token
  curl -sSL -c cookies.txt "https://drive.google.com/uc?export=download&id=${ID}" > page.html
  TOKEN=$(grep -o 'confirm=[^&"]*' page.html | head -1 | cut -d= -f2)
  curl -sSL -b cookies.txt -o mrw-pipeline.zip "https://drive.google.com/uc?export=download&confirm=${TOKEN:-t}&id=${ID}"
fi
mkdir -p mrw && unzip -oq mrw-pipeline.zip -d mrw
mkdir -p mrw/data/prices mrw/data/flows mrw/data/outputs mrw/digests
echo "unpacked $(find mrw -type f | wc -l) files"
