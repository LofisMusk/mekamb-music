#!/usr/bin/env bash
# Wraps the jpackage app-image produced by `:native-linux:createDistributable`
# into a portable AppImage. Run on Linux (CI: ubuntu-latest) after the gradle task.
# Usage: package-appimage.sh <tag>   (e.g. v1.0.0)
set -euo pipefail

TAG="${1:?usage: package-appimage.sh <tag>}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_SRC="$REPO_ROOT/native-linux/build/compose/binaries/main/app/mekamb-music"
OUT="$REPO_ROOT/native-linux/build/mekamb-music-desktop-${TAG}-linux-x86_64.AppImage"

if [ ! -d "$APP_SRC" ]; then
  echo "::error::jpackage app-image not found at $APP_SRC — run :native-linux:createDistributable first" >&2
  exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
APPDIR="$WORK/AppDir"
mkdir -p "$APPDIR"
cp -r "$APP_SRC"/. "$APPDIR/"

cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/bin/mekamb-music" "$@"
RUN
chmod +x "$APPDIR/AppRun"

cat > "$APPDIR/mekamb-music.desktop" <<'DESK'
[Desktop Entry]
Type=Application
Name=Mekamb Music
Exec=mekamb-music
Icon=mekamb-music
Categories=Audio;Music;Player;
Comment=Mekamb Music desktop client
DESK

cp "$REPO_ROOT/native-linux/icons/app.png" "$APPDIR/mekamb-music.png"
cp "$REPO_ROOT/native-linux/icons/app.png" "$APPDIR/.DirIcon"

TOOL="$WORK/appimagetool"
curl -fsSL -o "$TOOL" \
  "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
chmod +x "$TOOL"

# --appimage-extract-and-run avoids needing FUSE on CI runners.
ARCH=x86_64 "$TOOL" --appimage-extract-and-run "$APPDIR" "$OUT"
echo "AppImage created: $OUT"
