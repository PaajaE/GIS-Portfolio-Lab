#!/usr/bin/env bash
# Pack or restore a project's data bundle via the private release repository (GIS-Portfolio-Lab-data).
#   scripts/data_bundle.sh pack    <project>          -> new release <project>-YYYY-MM-DD
#   scripts/data_bundle.sh restore <project> [tag]    -> latest (or given) release into projects/<project>/data/
# The paths in a bundle are listed in projects/<project>/data_bundle.txt (relative to data/). Needs: gh (logged in
# with access to the private repo), tar, gzip, shasum or sha256sum.
set -euo pipefail
REPO="${GIS_DATA_REPO:-PaajaE/GIS-Portfolio-Lab-data}"
cmd="${1:?pack|restore}"; proj="${2:?project name}"
root="$(git rev-parse --show-toplevel)"; pdir="$root/projects/$proj"; data="$pdir/data"
sha() { if command -v shasum >/dev/null; then shasum -a 256 "$@"; else sha256sum "$@"; fi; }
[[ -d "$pdir" ]] || { echo "no project $proj" >&2; exit 1; }

case "$cmd" in
  pack)
    spec="$pdir/data_bundle.txt"; [[ -f "$spec" ]] || { echo "missing $spec" >&2; exit 1; }
    tag="$proj-$(date +%Y-%m-%d)"; out="$(mktemp -d)"
    while IFS= read -r p; do
      [[ -z "$p" || "$p" == \#* ]] && continue
      echo "packing $p"; tar -czf "$out/${p//\//__}.tar.gz" -C "$data" "$p"
    done < "$spec"
    [[ -f "$pdir/provenance/harvest_manifest.json" ]] && cp "$pdir/provenance/harvest_manifest.json" "$out/"
    (cd "$out" && sha ./*.tar.gz > SHA256SUMS)
    commit="$(git -C "$root" rev-parse --short HEAD)"
    gh release create "$tag" --repo "$REPO" --title "$tag" \
      --notes "Data bundle of projects/$proj at main-repo commit $commit. Paths: $(grep -v '^#' "$spec" | xargs)." \
      "$out"/*
    rm -rf "$out"; echo "released $tag" ;;
  restore)
    tag="${3:-$(gh release list --repo "$REPO" --limit 100 --json tagName,createdAt \
      -q "[.[] | select(.tagName | startswith(\"$proj-\"))] | sort_by(.createdAt) | last | .tagName")}"
    [[ -n "$tag" && "$tag" != null ]] || { echo "no release for $proj" >&2; exit 1; }
    tmp="$(mktemp -d)"; gh release download "$tag" --repo "$REPO" --dir "$tmp"
    (cd "$tmp" && sha -c SHA256SUMS)
    mkdir -p "$data"; for f in "$tmp"/*.tar.gz; do echo "restoring $(basename "$f")"; tar -xzf "$f" -C "$data"; done
    rm -rf "$tmp"; echo "restored $tag into $data" ;;
  *) echo "usage: $0 pack|restore <project> [tag]" >&2; exit 2 ;;
esac
