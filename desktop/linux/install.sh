#!/bin/sh
# Cynqra for Linux: put the app in your applications menu. Run from the unpacked Cynqra folder:
#   tar xzf Cynqra-*-linux-x64.tar.gz && ./Cynqra/install.sh
# It moves nothing outside your home folder and needs no administrator rights.
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/cynqra-app"
if [ "$SRC" != "$DEST" ]; then
  rm -rf "$DEST.new" && mkdir -p "$(dirname "$DEST")" && cp -a "$SRC" "$DEST.new"
  rm -rf "$DEST" && mv "$DEST.new" "$DEST"
fi
mkdir -p "$HOME/.local/bin" "${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ln -sf "$DEST/cynqra" "$HOME/.local/bin/cynqra"
cat > "${XDG_DATA_HOME:-$HOME/.local/share}/applications/cynqra.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Cynqra
Comment=The organization that builds with you, on an open model on this computer
Exec=$DEST/cynqra
Icon=$DEST/cynqra.png
Terminal=false
Categories=Development;
DESKTOP
echo "Cynqra is installed in $DEST."
echo "Start it from your applications menu, or run: $HOME/.local/bin/cynqra"
echo "Check the installation: $HOME/.local/bin/cynqra --selftest"
