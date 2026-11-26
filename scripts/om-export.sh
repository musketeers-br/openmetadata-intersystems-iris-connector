#!/usr/bin/env bash
# Write the changes made in .om/ back into overlay/ (new files) and patches/ (edits to existing files).
# OUT=<dir> writes there instead of the repository (om-import uses it to detect unexported work).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
OM=".om"
OUT="${OUT:-$ROOT}"
[ -d "$OM/.git" ] || { echo "om-export: $OM not found; run 'make om-import'" >&2; exit 1; }

STAGE="$ROOT/.cache/export"
mkdir -p "$STAGE/overlay" "$STAGE/patches"
find "$STAGE/overlay" "$STAGE/patches" -mindepth 1 -delete

while IFS= read -r -d '' entry; do
  st="${entry:0:2}"; path="${entry:3}"
  if grep -qEf <(grep -v '^#' scripts/om-export-ignore) <<<"$path"; then continue; fi
  case "$st" in
    '??') mkdir -p "$STAGE/overlay/$(dirname "$path")"; cp -p "$OM/$path" "$STAGE/overlay/$path" ;;
    *D*)  echo "om-export: tracked file deleted: $path (deleting OpenMetadata files is not supported)" >&2; exit 1 ;;
    R*|C*) echo "om-export: unsupported rename/copy: $path" >&2; exit 1 ;;
    *)    git -C "$OM" diff --binary HEAD -- "$path" > "$STAGE/patches/$(printf '%s' "$path" | sed 's#/#__#g').patch" ;;
  esac
done < <(git -C "$OM" status --porcelain=v1 -z --untracked-files=all)

# Files the repository carries verbatim although OpenMetadata already has them (licence text).
while IFS= read -r path; do
  case "$path" in ''|'#'*) continue ;; esac
  mkdir -p "$STAGE/overlay/$(dirname "$path")"
  cp -p "$OM/$path" "$STAGE/overlay/$path"
done < scripts/om-export-always

for d in overlay patches; do
  mkdir -p "$OUT/$d"
  rsync -a --delete --checksum "$STAGE/$d/" "$OUT/$d/"
done
echo "om-export: overlay/ and patches/ updated"
