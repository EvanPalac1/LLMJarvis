#!/usr/bin/env bash
# Arma el .rpm de Eve.
#
#   bash packaging/linux/build_rpm.sh 1.0.0 x64
#
# Con rpmbuild directo, sin fpm (que exige Ruby). Instalado aparece en
# `dnf list installed` y se quita con `dnf remove eve`.

set -euo pipefail
VERSION="${1:-1.0.0}"
ARCH_IN="${2:-x64}"
RPM_ARCH="$([ "$ARCH_IN" = "arm64" ] && echo aarch64 || echo x86_64)"

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST="$RAIZ/dist/Eve"
TOP="$RAIZ/build/rpm"

[ -d "$DIST" ] || { echo "Falta $DIST. Corre antes: python build.py"; exit 1; }
command -v rpmbuild >/dev/null || { echo "Falta rpmbuild (rpm-build)."; exit 1; }

rm -rf "$TOP"
mkdir -p "$TOP"/{BUILD,RPMS,SOURCES,SPECS,BUILDROOT}

BR="$TOP/BUILDROOT/eve-$VERSION-1.$RPM_ARCH"
mkdir -p "$BR/opt/LLMJarvis" "$BR/usr/bin" "$BR/usr/share/applications" \
         "$BR/usr/share/icons/hicolor/256x256/apps"
cp -R "$DIST/." "$BR/opt/LLMJarvis/"
cp "$RAIZ/packaging/linux/eve.desktop" "$BR/usr/share/applications/eve.desktop"
[ -f "$HOME/.config/LLMJarvis/assets/eve.png" ] && \
    cp "$HOME/.config/LLMJarvis/assets/eve.png" \
       "$BR/usr/share/icons/hicolor/256x256/apps/eve.png" || true
ln -sf /opt/LLMJarvis/Eve "$BR/usr/bin/eve"

cat > "$TOP/SPECS/eve.spec" <<EOF
Name:           eve
Version:        $VERSION
Release:        1
Summary:        Asistente de voz local con IA
License:        MIT
URL:            https://github.com/EvanPalac1/LLMJarvis
BuildArch:      $RPM_ARCH
Requires:       alsa-lib, libX11, portaudio
Recommends:     xclip, libappindicator-gtk3
AutoReqProv:    no

%description
Manten presionada una tecla, habla, y la IA ejecuta la instruccion en tu PC.
Funciona con un modelo local (Ollama) sin mandar nada a la nube, o contra la
API de Anthropic. Reconocimiento de voz y sintesis tambien offline.

%files
/opt/LLMJarvis
/usr/bin/eve
/usr/share/applications/eve.desktop
/usr/share/icons/hicolor/256x256/apps/eve.png

%post
update-desktop-database -q 2>/dev/null || true
gtk-update-icon-cache -q /usr/share/icons/hicolor 2>/dev/null || true
cat <<'AVISO'

Eve instalado. El atajo global necesita leer el teclado:
    sudo usermod -aG input "\$USER"     (y volver a iniciar sesion)

Configuralo con:  eve --panel
Tus datos van a ~/.config/LLMJarvis y NO se borran al desinstalar.
AVISO

%postun
update-desktop-database -q 2>/dev/null || true
EOF

rpmbuild --define "_topdir $TOP" --buildroot "$BR" -bb "$TOP/SPECS/eve.spec"
mkdir -p "$RAIZ/dist"
find "$TOP/RPMS" -name '*.rpm' -exec cp {} "$RAIZ/dist/" \;
rm -rf "$TOP"
echo "Listo: $RAIZ/dist/eve-$VERSION-1.$RPM_ARCH.rpm"
