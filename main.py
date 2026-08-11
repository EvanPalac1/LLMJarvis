"""LLMJarvis - arranca el listener del keypad y el icono de bandeja."""

import sys

from eve import listener as listener_mod
from eve import store, tray


def main() -> int:
    cfg = store.load_config()
    try:
        lis = listener_mod.Listener(cfg)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        print("Abriendo el panel de configuracion...")
        tray.open_panel()
        return 1

    lis.start()
    icono = tray.build(lis)
    # El panel corre aparte; al guardar cambia config.json y el listener se rearma
    # solo. El icono actualiza su tooltip para que se note que paso.
    lis.watch_config(on_reload=lambda l: setattr(icono, "title", tray._title(l)))
    icono.run()  # bloquea hasta 'Salir'
    return 0


if __name__ == "__main__":
    sys.exit(main())
