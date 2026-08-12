#!/usr/bin/env bash
# Arma el .deb de Eve.
#
#   bash packaging/linux/build_deb.sh 1.0.0 x64
#
# A mano con dpkg-deb, sin fpm: fpm exige Ruby y aca alcanza con un control file
# y dos scripts. Instalado aparece en el gestor de paquetes y se quita con
# `apt remove eve`, que es lo que se pidio: desinstalacion nativa del sistema.

set -euo pipefail
VERSION="${1:-1.0.0}"
ARCH_IN="${2:-x64}"
DEB_ARCH="$([ "$ARCH_IN" = "arm64" ] && echo arm64 || echo amd64)"

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST="$RAIZ/dist/Eve"
ETAPA="$RAIZ/build/deb"
SALIDA="$RAIZ/dist/eve_${VERSION}_${DEB_ARCH}.deb"

[ -d "$DIST" ] || { echo "Falta $DIST. Corre antes: python build.py"; exit 1; }

rm -rf "$ETAPA"
mkdir -p "$ETAPA/DEBIAN" \
         "$ETAPA/opt/LLMJarvis" \
         "$ETAPA/usr/bin" \
         "$ETAPA/usr/share/applications" \
         "$ETAPA/usr/share/icons/hicolor/256x256/apps"

cp -R "$DIST/." "$ETAPA/opt/LLMJarvis/"
cp "$RAIZ/packaging/linux/eve.desktop" "$ETAPA/usr/share/applications/eve.desktop"
[ -f "$HOME/.config/LLMJarvis/assets/eve.png" ] && \
    cp "$HOME/.config/LLMJarvis/assets/eve.png" \
       "$ETAPA/usr/share/icons/hicolor/256x256/apps/eve.png" || true

ln -sf /opt/LLMJarvis/Eve "$ETAPA/usr/bin/eve"

TAM="$(du -sk "$ETAPA" | cut -f1)"
cat > "$ETAPA/DEBIAN/control" <<EOF
Package: eve
Version: $VERSION
Section: utils
Priority: optional
Architecture: $DEB_ARCH
Maintainer: EvanPalac1 <evanpalaciosa@outlook.com>
Installed-Size: $TAM
Depends: libc6, libasound2 | libasound2t64, libx11-6, libportaudio2
Recommends: xclip, libayatana-appindicator3-1
Homepage: https://github.com/EvanPalac1/LLMJarvis
Description: Asistente de voz local con IA
 Manten presionada una tecla, habla, y la IA ejecuta la instruccion en tu PC.
 Funciona con un modelo local (Ollama) sin mandar nada a la nube, o contra la
 API de Anthropic. Reconocimiento de voz y sintesis tambien offline.
EOF

cat > "$ETAPA/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && \
    gtk-update-icon-cache -q /usr/share/icons/hicolor || true
cat <<'AVISO'

Eve instalado. Antes de usarlo:

  1. El atajo global necesita leer el teclado:
       sudo usermod -aG input "$USER"     (y volver a iniciar sesion)
     Bajo Wayland solo llegan eventos de apps sobre Xwayland.
  2. Configuralo:  eve --panel
  3. Arrancalo:    eve

Tus datos van a ~/.config/LLMJarvis y NO se borran al desinstalar.
AVISO
EOF

cat > "$ETAPA/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database -q || true
if [ "$1" = "purge" ]; then
    # Solo con `apt purge` se tocan los datos del usuario: `apt remove` los deja,
    # que es lo que espera quien esta reinstalando o actualizando.
    for h in /home/*; do
        [ -d "$h/.config/LLMJarvis" ] && rm -rf "$h/.config/LLMJarvis"
    done
    true
fi
EOF

chmod 755 "$ETAPA/DEBIAN/postinst" "$ETAPA/DEBIAN/postrm"
# -Zxz y no el zstd por defecto: zstd necesita dpkg >= 1.21, asi que un .deb
# armado en Ubuntu 24 no se instala en Debian 11 ni en Ubuntu 20.04. xz lo lee
# cualquier version a cambio de comprimir mas lento.
dpkg-deb -Zxz --build --root-owner-group "$ETAPA" "$SALIDA"
rm -rf "$ETAPA"
echo "Listo: $SALIDA"
