#!/usr/bin/env bash
# Arma el .dmg de Eve para macOS.
#
#   bash packaging/macos/dmg.sh 1.0.0 arm64
#
# En macOS desinstalar ES arrastrar el .app a la Papelera: no hay un registro de
# programas instalados como en Windows o un gestor de paquetes como en Linux. Un
# .pkg no agregaria un desinstalador nativo, solo un instalador sin vuelta atras,
# asi que el .dmg es lo correcto. Para los datos de usuario va el desinstalador
# que se incluye adentro.

set -euo pipefail
VERSION="${1:-1.0.0}"
ARCH="${2:-arm64}"
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP="$RAIZ/dist/Eve.app"
ETAPA="$RAIZ/build/dmg"
NOMBRE="Eve-$([ "$ARCH" = "arm64" ] && echo AppleSilicon || echo Intel)"
SALIDA="$RAIZ/dist/$NOMBRE.dmg"

[ -d "$APP" ] || { echo "Falta $APP. Corre antes: python build.py"; exit 1; }

rm -rf "$ETAPA" "$SALIDA"
mkdir -p "$ETAPA"
cp -R "$APP" "$ETAPA/"
ln -s /Applications "$ETAPA/Applications"

# Desinstalador para los datos: el .app se va a la Papelera, pero la agenda, la
# memoria, el historial y las voces viven aparte y hay que ofrecerlo aparte.
cat > "$ETAPA/Desinstalar Eve.command" <<'EOF'
#!/usr/bin/env bash
DATOS="$HOME/Library/Application Support/LLMJarvis"
echo "Esto borra Eve y tus datos:"
echo "  /Applications/Eve.app"
echo "  $DATOS  (agenda, memoria, historial y voces)"
read -r -p "Seguro? [s/N] " r
[[ "$r" =~ ^[sS]$ ]] || { echo "Cancelado."; exit 0; }
rm -rf "/Applications/Eve.app" "$DATOS"
echo "Listo. Tus claves siguen en el Llavero; borralas ahi si querés."
read -r -p "Enter para cerrar."
EOF
chmod +x "$ETAPA/Desinstalar Eve.command"

# hdiutil falla con "Resource busy" de vez en cuando: Spotlight o el propio
# diskimages-helper todavia tienen tomada la carpeta que se acaba de escribir.
# No es un error del paquete -el intento siguiente arma el mismo dmg-, asi que
# reintentar es la respuesta y no abortar el release entero por eso.
for intento in 1 2 3 4 5; do
    if hdiutil create -volname "Eve $VERSION" -srcfolder "$ETAPA" \
           -ov -format UDZO "$SALIDA"; then
        break
    fi
    if [ "$intento" = 5 ]; then
        echo "hdiutil fallo 5 veces seguidas; esto ya no es el disco ocupado." >&2
        exit 1
    fi
    echo "hdiutil ocupado, reintento $intento de 4 en ${intento}0s..." >&2
    sleep "${intento}0"
    rm -f "$SALIDA"
done
rm -rf "$ETAPA"
echo "Listo: $SALIDA"
echo
echo "Sin firma de Apple, la primera vez hay que abrirlo con boton derecho > Abrir"
echo "(Gatekeeper bloquea el doble clic en apps sin firmar)."
