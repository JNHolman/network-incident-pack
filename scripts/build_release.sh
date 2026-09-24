#!/usr/bin/env bash
set -euo pipefail

# Build a source archive from the tracked Git tree, never from the working directory.
# This prevents local .git/.venv/cache/build artifacts from leaking into release ZIPs.

ref="${1:-HEAD}"
out_dir="${2:-dist}"
repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  echo "error: working tree has tracked or untracked changes; commit/stash them before packaging" >&2
  exit 1
fi

version="$(git show "$ref:pyproject.toml" | sed -n 's/^version = "\([^"]*\)"/\1/p' | head -1)"
if [[ -z "$version" ]]; then
  echo "error: could not read project version from pyproject.toml at $ref" >&2
  exit 1
fi

mkdir -p "$out_dir"
archive="$out_dir/network-incident-pack-v${version}.zip"
prefix="network-incident-pack-v${version}/"

git archive --format=zip --prefix="$prefix" --output="$archive" "$ref"
python3 scripts/verify_release.py "$archive"

echo "Created $archive"
echo "Archive contents come only from files tracked at Git ref: $ref"
