#!/bin/bash
# Build the browser z3 assets for ARDiff-lite into DEST (default: ./z3-assets):
#   z3-built.js / .wasm / .worker.js (z3-solver 4.13.0), z3lite-bundle.js (window.Z3Lite), coi-serviceworker.min.js
# The page must be cross-origin isolated (SharedArrayBuffer); on GitHub Pages coi-serviceworker provides that.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DEST=$(mkdir -p "${1:-$HERE/z3-assets}" && cd "${1:-$HERE/z3-assets}" && pwd)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
cd "$TMP"
npm init -y >/dev/null
npm install --silent --no-audit --no-fund z3-solver@4.13.0 esbuild@0.20.2 coi-serviceworker@0.1.7
cp "$HERE/z3entry.js" entry.js
./node_modules/.bin/esbuild entry.js --bundle --format=iife --platform=browser --define:global=window --minify --outfile="$DEST/z3lite-bundle.js"
cp node_modules/z3-solver/build/z3-built.js node_modules/z3-solver/build/z3-built.wasm node_modules/z3-solver/build/z3-built.worker.js "$DEST/"
cp node_modules/coi-serviceworker/coi-serviceworker.min.js "$DEST/"
ls -la "$DEST"
