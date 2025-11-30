#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-}"
if [[ -z "${VERSION}" ]]; then
  echo "Usage: $0 <version>" >&2
  exit 1
fi

echo "Preparing release ${VERSION}"

# Use Python helper to bump versions (avoids sed)
python3 scripts/bump_version.py "${VERSION}"

