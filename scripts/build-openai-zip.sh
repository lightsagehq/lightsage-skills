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

# Every skill a packaged skill points to must be in the package.
if grep -rq "lightsage-cli" "$stage/skills"; then
  echo "A packaged skill still refers to lightsage-cli" >&2
  exit 1
fi

mkdir -p "$root/dist"
rm -f "$out"
(cd "$stage" && zip -qr "$out" .)
echo "$out"
