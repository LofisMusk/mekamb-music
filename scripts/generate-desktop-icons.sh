#!/usr/bin/env bash
# Generates desktop app icons from the shared logo.
# Requires: macOS (sips + iconutil) and Python with Pillow for the .ico.
# Outputs are committed to the repo, so this only needs to be re-run when the logo changes.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOGO="$REPO_ROOT/native-android/app/src/main/res/drawable/logo.jpg"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# Square-crop the logo to the largest centered square, as icon masters must be square.
SIZE=$(sips -g pixelWidth -g pixelHeight "$LOGO" | awk '/pixel/ {print $2}' | sort -n | head -1)
MASTER="$TMP_DIR/master.png"
sips -s format png -c "$SIZE" "$SIZE" "$LOGO" --out "$MASTER" >/dev/null

# --- macOS .icns ---
ICONSET="$TMP_DIR/app.iconset"
mkdir -p "$ICONSET"
for s in 16 32 64 128 256 512 1024; do
  sips -z "$s" "$s" "$MASTER" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
done
cp "$ICONSET/icon_32x32.png"     "$ICONSET/icon_16x16@2x.png"
cp "$ICONSET/icon_64x64.png"     "$ICONSET/icon_32x32@2x.png"
cp "$ICONSET/icon_256x256.png"   "$ICONSET/icon_128x128@2x.png"
cp "$ICONSET/icon_512x512.png"   "$ICONSET/icon_256x256@2x.png"
cp "$ICONSET/icon_1024x1024.png" "$ICONSET/icon_512x512@2x.png"
rm "$ICONSET/icon_64x64.png" "$ICONSET/icon_1024x1024.png"
iconutil -c icns "$ICONSET" -o "$REPO_ROOT/native-mac/icons/app.icns"

# --- Linux .png (512px) ---
sips -z 512 512 "$MASTER" --out "$REPO_ROOT/native-linux/icons/app.png" >/dev/null

# --- Windows .ico (via Pillow) ---
python3 - "$MASTER" "$REPO_ROOT/native-windows/icons/app.ico" <<'PY'
import sys
from PIL import Image
master, out = sys.argv[1], sys.argv[2]
img = Image.open(master).convert("RGBA")
img.save(out, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
PY

echo "Icons written:"
ls -la "$REPO_ROOT/native-mac/icons/app.icns" "$REPO_ROOT/native-linux/icons/app.png" "$REPO_ROOT/native-windows/icons/app.ico"
