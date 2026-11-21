#!/usr/bin/env bash
# Build the ZIP uploaded to the OpenAI Platform dashboard (ChatGPT and Codex
# plugin directory).
#
# The directory package leaves out the lightsage-cli skill. It covers setting
# up API keys for the terminal, and OpenAI's plugin review treats skills that
# deal with access credentials as soliciting restricted data. The other client
# packages (Claude Code, Cursor, Grok) still ship it.
#
# Usage: scripts/build-openai-zip.sh   -> dist/lightsage-<version>-openai.zip
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"

version="$(python3 -c 'import json; print(json.load(open("plugin.json"))["version"])')"
out="$root/dist/lightsage-${version}-openai.zip"

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT

cp plugin.json mcp.json LICENSE "$stage/"
mkdir -p "$stage/.codex-plugin"
cp .codex-plugin/plugin.json "$stage/.codex-plugin/"
cp .mcp.json "$stage/"
cp -R assets "$stage/"
mkdir -p "$stage/skills"
for skill in skills/*/; do
  name="$(basename "$skill")"
  [ "$name" = "lightsage-cli" ] && continue
  cp -R "$skill" "$stage/skills/$name"
done
find "$stage" -name .DS_Store -delete

# Review details for OpenAI (test cases, demo video URL) are kept out of this
# public repo, and out of the plugin users install from it, in the gitignored
# review.private.json at the repo root. They go only into this ZIP, under
# extensions.com.openai.review. Without the file the ZIP has no review section,
# and the dashboard keeps the test cases it already has.
if [ -f review.private.json ]; then
  python3 - "$stage/plugin.json" review.private.json <<'PY'
import json, sys
manifest_path, review_path = sys.argv[1], sys.argv[2]
manifest = json.load(open(manifest_path))
openai = manifest["extensions"]["com.openai"]
publication = openai.pop("publication", None)
openai["review"] = json.load(open(review_path))
if publication is not None:
    openai["publication"] = publication
with open(manifest_path, "w") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY
else
  echo "No review.private.json: building without review details" >&2
fi

# Every skill a packaged skill points to must be in the package.
if grep -rq "lightsage-cli" "$stage/skills"; then
  echo "A packaged skill still refers to lightsage-cli" >&2
  exit 1
fi

mkdir -p "$root/dist"
rm -f "$out"
(cd "$stage" && zip -qr "$out" .)
echo "$out"
