/* El interprete del registro, del lado del HTML.
 *
 * Es el gemelo de `gui.py::_pintar_registro`, y tiene la misma regla: aca no
 * se dibuja nada nuevo. Cada tipo de nodo va a su funcion y nada mas. Si un
 * control necesita logica propia, se declara `Propio` en el registro y se
 * escribe aparte -- que es exactamente por lo que existe ese tipo.
 *
 * Todo lo que se muestra llega ya resuelto desde Python: los rotulos
 * traducidos, los valores de la config, los tipos, las listas que se arman al
 * abrir, la paleta y las dos tablas sueltas (las siete piezas de un fondo y
 * los ocho roles de color). Este archivo no sabe ni un rotulo ni un color.
 */

"use strict";

let ESQ = null;               // el esquema entero, como lo sirve panel_api
let PENDIENTES = new Map();   // clave -> valor editado y todavia sin guardar
let PESTANA = "General";
let SUB = null;               // sub-pestana activa, solo en Apariencia

const $ = (sel, raiz = document) => raiz.querySelector(sel);

function el(tag, props = {}, hijos = []) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) n.setAttribute(k, v);
  }
  for (const h of [].concat(hijos)) if (h) n.appendChild(h);
  return n;
}

/* --- el puente ---------------------------------------------------------- */

// pywebview inyecta `pywebview.api` cuando la ventana esta lista. Fuera de esa
// ventana --abriendo el archivo en un navegador para mirar el diseno-- no
// existe, y en vez de reventar se dibuja con lo que haya: es la unica forma de
// poder ver la pantalla sin arrancar el programa entero.
async function api(metodo, ...args) {
  if (!window.pywebview || !window.pywebview.api) {
    throw new Error("sin puente: el panel no esta corriendo dentro de Eve");
  }
  return window.pywebview.api[metodo](...args);
}

/* --- la paleta ---------------------------------------------------------- */

function aplicarTema(esq) {
  const r = document.documentElement.style;
  const mapa = {
    fondo: "--fondo", panel: "--panel", texto: "--texto",
    texto_tenue: "--texto-tenue", acento: "--acento", acento2: "--acento2",
    borde: "--borde", alerta: "--alerta",
  };
  for (const [rol, variable] of Object.entries(mapa)) {
    if (esq.paleta && esq.paleta[rol]) r.setProperty(variable, esq.paleta[rol]);
  }
  // La escala viene en PUNTOS, que es como la declara `tema.ESCALA`. A pixeles
  // con el 4/3 de siempre: es lo mismo que hace tk al pasar puntos a pantalla.
  if (esq.escala && esq.escala.cuerpo) {
    document.body.style.fontSize = Math.round(esq.escala.cuerpo * 4 / 3) + "px";
  }
  (esq.espacio || []).forEach((px, i) => r.setProperty(`--e${i + 1}`, px + "px"));
}

/* --- valores ------------------------------------------------------------ */

function valor(clave) {
  if (PENDIENTES.has(clave)) return PENDIENTES.get(clave);
  const v = ESQ.valores[clave];
  return v === undefined || v === null ? "" : v;
}

function editar(clave, nuevo) {
  // Volver al valor que tiene el disco NO es un cambio pendiente: sin esto,
  // tocar un campo y deshacerlo dejaba una escritura fantasma en la cola.
  const original = ESQ.valores[clave];
  const igual = Array.isArray(original)
    ? original.join("\n") === String(nuevo)
    : String(original) === String(nuevo) || original === nuevo;
  if (igual) PENDIENTES.delete(clave); else PENDIENTES.set(clave, nuevo);
  pintarPie();
}

/* --- los nodos ---------------------------------------------------------- */

function nodo(item) {
  switch (item.tipo) {
    case "Seccion": return seccion(item);
    case "Fila": return fila(item);
    case "Campo": return campo(item);
    case "Interruptor": return interruptor(item);
    case "Ayuda": return el("p", { class: "ayuda", text: item.texto });
    case "Boton": return botonera([item]);
    // Una `Salida` arranca con lo que Python haya puesto para ella, si puso
    // algo. Algunas tienen algo que decir apenas se abre el panel --que motor
    // de dibujo quedo activo, si el modelo de fin de turno esta bajado-- y sin
    // esto se dibujaban vacias hasta que alguien apretara un boton que ni
    // siquiera existe para ellas.
    case "Salida": return el("p", { class: "salida", id: "sal-" + item.atributo,
                                    text: (ESQ.salidas || {})[item.atributo] || "" });
    // Una `Clave` no es un `Campo`: su valor vive en el llavero del sistema y
    // nunca en la config, asi que no entra a los cambios pendientes ni al
    // Guardar de abajo. Se guarda sola, con su propio boton.
    case "Clave": return campoDeClave({
      id: item.proveedor, clave: item.proveedor, rotulo: item.etiqueta,
      etiqueta: item.etiqueta, necesita_clave: true,
      tiene_clave: (ESQ.con_clave || []).includes(item.proveedor),
    });
    case "Colores": return colores(item);
    case "Fondo": return fondo(item);
    // `Vivo` no dibuja: declara que claves repintan la vista previa. Cuando la
    // previa exista, se engancha aca. Devolver null y no un hueco es correcto
    // -- en tkinter tampoco se ve.
    case "Vivo": return null;
    case "Propio": return propio(item);
    default: throw new Error("el registro trae algo que no se dibujar: " + item.tipo);
  }
}

function seccion(item) {
  // En modo "esencial" las avanzadas arrancan cerradas, igual que en el panel
  // de tkinter. Se pliegan TODAS, no solo las avanzadas: un mecanismo es mas
  // facil de aprender que dos, y ver que la de al lado se pliega es lo que
  // ensena que esta tambien puede.
  const abierta = item.nivel === "basico" || ESQ.modo !== "esencial";
  const cuerpo = el("div", { class: "cuerpo-seccion" },
                    item.hijos.map(nodo).filter(Boolean));
  const flecha = el("span", { class: "flecha", "aria-hidden": "true", text: "▾" });
  const titulo = el("button", {
    class: "titulo", type: "button", "aria-expanded": String(abierta),
    onclick: (ev) => {
      const b = ev.currentTarget;
      b.setAttribute("aria-expanded", b.getAttribute("aria-expanded") === "false" ? "true" : "false");
    },
  }, [flecha, el("span", { text: item.titulo })]);
  if (item.nivel === "avanzado") {
    titulo.appendChild(el("span", { class: "nivel", text: "avanzado" }));
  }
  return el("section", { class: "seccion" }, [titulo, cuerpo]);
}

function fila(item) {
  return el("div", { class: "botones" }, item.hijos.map(nodo).filter(Boolean));
}

function campo(item) {
  const id = "c-" + item.clave;
  const tipo = (ESQ.tipos || {})[item.clave] || "str";
  const lista = ESQ.opciones[item.clave] !== undefined
    ? ESQ.opciones[item.clave]     // la que armo Python al abrir
    : item.opciones;               // la escrita en el registro
  let control;

  if (tipo === "lista") {
    // La unica clave que no es un escalar: una por renglon, que es como la
    // escribe el cuadro de rutas permitidas del panel de tkinter.
    const v = valor(item.clave);
    control = el("textarea", { id, rows: "4" });
    control.value = Array.isArray(v) ? v.join("\n") : String(v);
    control.addEventListener("input", () => editar(item.clave, control.value));
  } else if (Array.isArray(lista) && lista.length && !item.abierto) {
    control = el("select", { id });
    const actual = String(valor(item.clave));
    let esta = false;
    for (const op of lista) {
      // Una opcion puede ser un par [valor, rotulo]: lo que se guarda no
      // siempre es lo que se lee --el idioma guarda `es` y muestra "Espanol"--
      // y con dos variables paralelas hay que acordarse de mover las dos.
      const val = Array.isArray(op) ? String(op[0]) : String(op);
      const txt = Array.isArray(op) ? String(op[1]) : (val === "" ? "(sin elegir)" : val);
      control.appendChild(el("option", { value: val, text: txt }));
      if (val === actual) esta = true;
    }
    // Un valor guardado que ya no esta en la lista NO se pisa en silencio: se
    // agrega marcado. Perderlo cambiaria un ajuste sin que nadie lo pida --y
    // es justo lo que pasa cuando un proveedor retira un modelo.
    if (!esta && actual !== "") {
      control.appendChild(el("option", { value: actual, text: actual + "  (guardado, ya no esta en la lista)" }));
    }
    control.value = actual;
    control.addEventListener("change", () => editar(item.clave, control.value));
  } else {
    control = el("input", { type: "text", id });
    control.value = String(valor(item.clave));
    if (Array.isArray(lista) && lista.length) {
      // `abierto`: las opciones son SUGERENCIAS y se puede escribir otra cosa.
      const dl = el("datalist", { id: id + "-op" });
      for (const op of lista) dl.appendChild(el("option", { value: String(op) }));
      control.setAttribute("list", id + "-op");
      control.appendChild(dl);
    }
    if (item.ancho) control.style.maxWidth = (item.ancho + 2) + "ch";
    control.addEventListener("input", () => editar(item.clave, control.value));
  }
  return el("div", { class: "campo" },
            [el("label", { for: id, text: item.etiqueta }), control]);
}

function interruptor(item) {
  const casilla = el("input", { type: "checkbox" });
  casilla.checked = Boolean(valor(item.clave));
  casilla.addEventListener("change", () => editar(item.clave, casilla.checked));
  return el("label", { class: "interruptor" },
            [casilla, el("span", { text: item.etiqueta })]);
}

function colores(item) {
  const filas = ESQ.roles.map(([rol, etiqueta]) => {
    const clave = `${item.prefijo}_color_${rol}`;
    const id = "c-" + clave;
    const texto = el("input", { type: "text", id, maxlength: "9" });
    const muestra = el("input", { type: "color", "aria-label": etiqueta });
    const actual = String(valor(clave) || "");
    texto.value = actual;
    if (/^#[0-9a-fA-F]{6}$/.test(actual)) muestra.value = actual;
    texto.addEventListener("input", () => {
      editar(clave, texto.value);
      if (/^#[0-9a-fA-F]{6}$/.test(texto.value)) muestra.value = texto.value;
    });
    muestra.addEventListener("input", () => {
      texto.value = muestra.value;
      editar(clave, muestra.value);
    });
    return el("div", { class: "color-fila" },
              [el("label", { for: id, text: etiqueta }), muestra, texto]);
  });
  return el("div", { class: "cuerpo-seccion" }, filas);
}

function fondo(item) {
  // Los siete rotulos llegan servidos y no escritos aca: ya se desfasaron una
  // vez de lo que el panel dibuja, y el buscador te llevaba a otro ajuste.
  const filas = ESQ.partes_fondo.map(([sufijo, etiqueta]) =>
    campo({ tipo: "Campo", clave: item.prefijo + sufijo, etiqueta, opciones: null, ancho: 44, abierto: false }));
  return el("div", { class: "cuerpo-seccion" }, filas);
}

/* --- las acciones -------------------------------------------------------- */

// Lo que el usuario tiene EN PANTALLA: el disco con los cambios sin guardar
// encima. Va con cada accion porque uno cambia el proveedor y aprieta Probar
// sin guardar, y probar el anterior seria mentir.
function cfgDePantalla() {
  return Object.assign({}, ESQ.valores, Object.fromEntries(PENDIENTES));
}

// Donde escribe cada accion. La tabla la sirve Python; lo que no este ahi va a
// la linea de estado del pie, que es donde iba en el panel viejo.
function decir(nombre, texto) {
  const attr = (ESQ.salida_de || {})[nombre];
  const destino = attr ? document.getElementById("sal-" + attr) : null;
  if (destino) destino.textContent = texto;
  else avisar(texto, "");
}

function avisar(texto, clase) {
  const a = $(".pie .aviso");
  a.className = "aviso " + (clase || "");
  a.textContent = texto;
}

// Cada accion es bloqueante del lado de Python --pywebview la atiende en un
// hilo propio-- asi que lo unico que hace falta de este lado es apagar el
// boton mientras corre. Sin eso, dos clics seguidos abren dos veces el
// microfono.
async function correr(nombre, args, boton) {
  if (boton) { boton.disabled = true; boton.dataset.antes = boton.textContent; }
  decir(nombre, "...");
  let r;
  try {
    r = await api("accion", nombre, cfgDePantalla(), args || {});
  } catch (exc) {
    r = { ok: false, salida: String(exc.message || exc), valores: {} };
  }
  if (boton) { boton.disabled = false; boton.textContent = boton.dataset.antes; }
  if (r.salida) decir(nombre, r.salida);
  // Lo que la accion decidio NO se escribe: queda como cambio pendiente y el
  // usuario aprieta Guardar. Escribirlo solo seria la app poseida que el
  // ajuste de autoridad existe para evitar.
  for (const [clave, valor] of Object.entries(r.valores || {})) editar(clave, valor);
  if (Object.keys(r.valores || {}).length) pintar();
  // Una accion puede PEDIR que se elija un archivo: Python no abre el cuadro
  // del sistema --no tiene ventana-- asi que declara que hay que elegir y para
  // que clave, y esto lo hace.
  if (r.elegir_archivo) {
    const pedido = r.elegir_archivo;
    const arch = await api("elegir_archivo", pedido.filtros || [], false);
    if (arch.ok && arch.rutas.length) { editar(pedido.clave, arch.rutas[0]); pintar(); }
  }
  // Las dos del cartel SI escriben en el disco --el cartel es otro proceso y
  // lee del archivo-- asi que hay que releer o el panel muestra lo viejo.
  if (r.recargar) await recargar();
  return r;
}

async function recargar() {
  const pendientes = new Map(PENDIENTES);
  ESQ = await api("esquema");
  PENDIENTES = pendientes;
  pintar();
}

function botonera(items) {
  return el("div", { class: "botones" }, items.map((b) => {
    const boton = el("button", { class: "boton", type: "button", text: b.etiqueta });
    if (b.metodo === "probar_tecla") {
      // La unica que necesita al navegador: la tecla la captura el, y Python
      // dice si es la configurada y si alguien la esta escuchando.
      boton.addEventListener("click", () => {
        decir("probar_tecla", "presiona una tecla ahora...");
        const una = (ev) => {
          ev.preventDefault();
          window.removeEventListener("keydown", una, true);
          correr("probar_tecla", { recibida: ev.key }, boton);
        };
        window.addEventListener("keydown", una, true);
      });
    } else if (b.metodo === "compat_buscar_modelos") {
      boton.addEventListener("click", async () => {
        const r = await correr("compat_buscar_modelos", {}, boton);
        if (r.ok && r.modelos && r.modelos.length) elegirDeLista(r.modelos, "compat_modelo");
      });
    } else if (b.metodo === "hotkey_capturar") {
      boton.addEventListener("click", () => {
        decir("hotkey_capturar", "presiona la tecla que quieras...  (Escape cancela)");
        correr("hotkey_capturar", {}, boton);
      });
    } else {
      boton.addEventListener("click", () => correr(b.metodo, {}, boton));
    }
    return boton;
  }));
}

/* --- los huecos declarados ----------------------------------------------- */

function propio(item) {
  const datos = (ESQ.huecos || {})[item.metodo];
  if (!datos) return hueco(item.metodo, "no llegaron sus datos");
  const dibuja = COMPONENTES[datos.componente];
  if (!dibuja) return hueco(item.metodo, "no se dibujar un " + datos.componente);
  return dibuja(datos, item);
}

// El hueco visible es lo unico honesto para lo que no esta: esconderlo daria
// una pestana que se ve completa y no lo esta.
function hueco(metodo, razon) {
  return el("div", { class: "propio" }, [
    el("code", { text: metodo }), el("span", { text: "  — " + razon }),
  ]);
}

function compRutas(d) {
  const control = el("textarea", { id: "c-" + d.clave, rows: "5" });
  const v = valor(d.clave);
  control.value = Array.isArray(v) ? v.join("\n") : String(v);
  control.addEventListener("input", () => editar(d.clave, control.value));
  return el("div", { class: "campo alto" },
            [el("label", { for: "c-" + d.clave, text: d.etiqueta }), control]);
}

function compPermisos(d) {
  // Guarda la NEGACION de su clave: el desplegable dice "permitir todo" y la
  // clave se llama `confirm_destructive`. Por eso no es una fila normal.
  const sel = el("select", { id: "c-" + d.clave });
  for (const op of d.opciones) sel.appendChild(el("option", { value: op, text: op }));
  sel.value = Boolean(valor(d.clave)) ? d.opciones[0] : d.opciones[1];
  sel.addEventListener("change", () => editar(d.clave, sel.value === d.opciones[0]));
  return el("div", { class: "campo" },
            [el("label", { for: "c-" + d.clave, text: d.etiqueta }), sel]);
}

function compProveedores(d) {
  // El pedido que motivo la mudanza: cada proveedor con su modelo y su clave a
  // la vista, en vez de dos controles en dos secciones y una pared de nueve
  // campos de clave sin ninguna senal de cual estaba en uso.
  const elegido = String(valor("engine")) === "compat"
    ? String(valor("compat_proveedor") || d.elegido) : String(valor("engine"));
  const filas = d.lista.map((p) => {
    const radio = el("input", { type: "radio", name: "proveedor", value: p.id });
    radio.checked = p.id === elegido;
    radio.addEventListener("change", async () => {
      const r = await correr("elegir_proveedor", { id: p.id });
      if (r.ok) { avisar(r.salida, "hecho"); pintar(); }
    });
    const estado = p.necesita_clave
      ? (p.tiene_clave ? "clave cargada" : "sin clave")
      : "no necesita clave";
    return el("label", { class: "prov " + (p.id === elegido ? "activo" : "") }, [
      radio,
      el("span", { class: "prov-nombre", text: p.rotulo }),
      el("span", { class: "prov-donde", text: p.donde }),
      el("span", { class: "prov-clave " + (p.necesita_clave && !p.tiene_clave ? "falta" : ""),
                   text: estado }),
    ]);
  });
  return el("div", { class: "proveedores" },
            [...filas, campoDeClave(d.lista.find((p) => p.id === elegido))]);
}

// La clave del proveedor ELEGIDO, y solo la de ese. Es la mitad del pedido:
// antes estaban las nueve juntas en otra pestana, una abajo de la otra, sin
// ninguna senal de cual estaba en uso.
//
// La clave no viaja de vuelta nunca: el campo arranca con asteriscos si ya hay
// una guardada, y si no lo reescribis, no se toca. Traerla al HTML para
// dibujar los asteriscos seria dejarla leible desde la consola.
function campoDeClave(p) {
  if (!p || !p.necesita_clave) return null;
  const id = "clave-" + p.id;
  const control = el("input", { type: "password", id, autocomplete: "off" });
  control.value = p.tiene_clave ? "************" : "";
  const guardar = el("button", { class: "boton", type: "button", text: "Guardar clave" });
  const eco = el("span", { class: "salida" });
  guardar.addEventListener("click", async () => {
    const r = await api("accion", "guardar_clave", cfgDePantalla(),
                        { proveedor: p.clave, valor: control.value });
    eco.textContent = r.salida;
    eco.className = "salida " + (r.ok ? "" : "error");
  });
  return el("div", { class: "campo clave" }, [
    el("label", { for: id, text: p.etiqueta || ("Clave de " + p.rotulo) }),
    control, guardar, eco,
  ]);
}

function compAyuda(d) {
  return el("p", { class: "ayuda", text: d.texto });
}

function compArchivo(d) {
  const id = "c-" + d.clave;
  const control = el("input", { type: "text", id });
  control.value = String(valor(d.clave));
  control.addEventListener("input", () => editar(d.clave, control.value));
  const elegir = el("button", { class: "boton", type: "button", text: "Elegir..." });
  elegir.addEventListener("click", async () => {
    // El cuadro del sistema y no un `<input type=file>`: ese entrega el
    // CONTENIDO y lo que Eve guarda es la RUTA, porque la imagen se relee cada
    // vez que se dibuja.
    const r = await api("elegir_archivo", d.filtros || [], false);
    if (r.ok && r.rutas.length) { control.value = r.rutas[0]; editar(d.clave, r.rutas[0]); }
  });
  const quitar = el("button", { class: "boton", type: "button", text: "Quitar" });
  quitar.addEventListener("click", () => { control.value = ""; editar(d.clave, ""); });
  return el("div", { class: "campo" }, [
    el("label", { for: id, text: d.etiqueta }), control, elegir, quitar,
  ]);
}

function compFormas(d) {
  // No guarda una clave: LLENA otras cuatro. Elegir "hexagono" escribe lados,
  // giro y redondeo de un saque.
  const sel = el("select", { id: "c-forma" });
  sel.appendChild(el("option", { value: "", text: "(elegir)" }));
  for (const op of d.opciones) sel.appendChild(el("option", { value: op, text: op }));
  sel.addEventListener("change", async () => {
    if (!sel.value) return;
    await correr("_forma_elegida", { forma: sel.value });
  });
  return el("div", { class: "campo" },
            [el("label", { for: "c-forma", text: d.etiqueta }), sel]);
}

function compSalida(d) {
  return el("p", { class: "salida", id: "sal-" + d.atributo, text: d.texto });
}

function compSinPortar(d) {
  return el("div", { class: "propio" }, [
    el("code", { text: d.metodo }), el("span", { text: "  — " + d.razon }),
  ]);
}

function compError(d) {
  return el("div", { class: "propio error", text: d.metodo + ": " + d.texto });
}

/* --- skills -------------------------------------------------------------- */

function compSkills(d) {
  const caja = el("div", { class: "lista-caja" });
  const lista = el("ul", { class: "lista" });
  const estado = el("p", { class: "salida" });

  const pintarLista = (items) => {
    lista.replaceChildren(...(items.length ? items.map((s) => {
      const quitar = el("button", { class: "boton chico", type: "button", text: "Quitar" });
      quitar.addEventListener("click", async () => {
        if (!confirm("Borrar " + s.nombre + "?")) return;
        const r = await api("accion", "skills_borrar", cfgDePantalla(), { nombre: s.nombre });
        estado.textContent = r.salida;
        if (r.skills) pintarLista(r.skills);
      });
      return el("li", {}, [
        el("span", { class: "lista-nombre", text: s.nombre }),
        el("span", { class: "lista-resumen", text: s.resumen || "" }),
        quitar,
      ]);
    }) : [el("li", { class: "vacio", text: "(ninguna todavia)" })]));
  };
  pintarLista(d.lista || []);

  const importar = el("button", { class: "boton", type: "button", text: "Importar skill..." });
  importar.addEventListener("click", async () => {
    const arch = await api("elegir_archivo", ["Texto (*.md;*.markdown;*.txt)", "*"], true);
    if (!arch.ok || !arch.rutas.length) return;
    const r = await api("accion", "skills_importar", cfgDePantalla(), { rutas: arch.rutas });
    estado.textContent = r.salida;
    if (r.skills) pintarLista(r.skills);
  });

  caja.append(lista, el("div", { class: "botones" }, [importar]), estado);
  return caja;
}

/* --- comandos ------------------------------------------------------------ */

function compComandos(d) {
  const caja = el("div", { class: "lista-caja" });
  const tabla = el("table", { class: "tabla" });
  const cuerpo = el("tbody");
  const estado = el("p", { class: "salida" });
  const aprobacion = el("div", { class: "aprobacion", hidden: "hidden" });
  let elegido = null;
  let datos = d;

  tabla.appendChild(el("thead", {}, [el("tr", {},
    datos.columnas.map((c) => el("th", { text: c })))]));
  tabla.appendChild(cuerpo);

  const seleccionar = (fila, cmd) => {
    for (const tr of cuerpo.querySelectorAll("tr")) tr.removeAttribute("aria-selected");
    fila.setAttribute("aria-selected", "true");
    elegido = cmd;
  };

  const pintarFilas = () => {
    elegido = null;
    aprobacion.hidden = true;
    cuerpo.replaceChildren(...datos.lista.map((c) => {
      const fila = el("tr", { tabindex: "0" }, [
        el("td", { text: c.frases.join(" | ") }),
        el("td", { text: c.tipo }),
        el("td", { class: "mono", text: c.valor }),
        el("td", { class: c.aprobado ? "" : "falta", text: c.estado }),
      ]);
      fila.addEventListener("click", () => seleccionar(fila, c));
      fila.addEventListener("dblclick", () => { seleccionar(fila, c); editor(c); });
      return fila;
    }));
    estado.textContent = datos.resumen;
  };

  const refrescar = (r) => { if (r && r.comandos) { datos = r.comandos; pintarFilas(); } };

  const pedir = async (nombre, args) => {
    const r = await api("accion", nombre, cfgDePantalla(), args || {});
    if (r.salida) estado.textContent = r.salida;
    refrescar(r);
    return r;
  };

  // El cartel de aprobar va DENTRO del panel y no en un cuadro del sistema: ese
  // recorta el texto largo sin decirlo --y lo que se aprueba ES el texto--, no
  // se puede copiar, y tapa la lista, asi que no se ve cual de todos era.
  const revTitulo = el("p", { class: "ayuda" });
  const revTexto = el("textarea", { rows: "3", readonly: "readonly",
                                    "aria-label": "El comando que se va a aprobar" });
  const aprobarYa = el("button", { class: "boton primario", type: "button", text: "Aprobar" });
  const cancelar = el("button", { class: "boton", type: "button", text: "Cancelar" });
  cancelar.addEventListener("click", () => { aprobacion.hidden = true; });
  aprobarYa.addEventListener("click", async () => {
    if (!elegido) return;
    await pedir("comandos_aprobar", elegido);
  });
  aprobacion.append(revTitulo, revTexto, el("div", { class: "botones" }, [
    aprobarYa, cancelar,
    el("span", { class: "ayuda", text: "Se aprueba ESTE texto: si despues lo editas, vuelve a quedar frenado." }),
  ]));

  const revisar = () => {
    if (!elegido) { estado.textContent = "Elige uno de la lista."; return; }
    if (elegido.tipo !== "sistema") {
      estado.textContent = "Ese no corre nada: no hace falta aprobarlo.";
      return;
    }
    revTitulo.textContent = 'Al decir "' + elegido.frases[0] + '" se va a correr:';
    revTexto.value = elegido.valor;
    aprobacion.hidden = false;
  };

  function editor(cmd) {
    const frases = el("input", { type: "text", id: "cmd-frases" });
    const tipo = el("select", { id: "cmd-tipo" });
    for (const t of datos.tipos) tipo.appendChild(el("option", { value: t, text: t }));
    const valorTxt = el("textarea", { id: "cmd-valor", rows: "3" });
    const aviso = el("p", { class: "salida" });
    if (cmd) { frases.value = cmd.frases.join(" | "); tipo.value = cmd.tipo; valorTxt.value = cmd.valor; }

    const guardarCmd = el("button", { class: "boton primario", type: "button", text: "Guardar" });
    const cerrar = el("button", { class: "boton", type: "button", text: "Cancelar" });
    const dlg = el("dialog", { class: "cuadro" }, [
      el("h2", { text: cmd ? "Editar comando" : "Comando nuevo" }),
      el("div", { class: "campo" }, [el("label", { for: "cmd-frases", text: "Frases" }), frases]),
      el("div", { class: "campo" }, [el("label", { for: "cmd-tipo", text: "Tipo" }), tipo]),
      el("div", { class: "campo alto" }, [el("label", { for: "cmd-valor", text: "Hace" }), valorTxt]),
      // La lista de acciones va con el texto, no adentro de una traduccion: un
      // `tr` con una variable adentro es invisible para el chequeo, y esos son
      // justo los textos que se quedan en espanol con el panel en ingles.
      el("p", { class: "ayuda", text:
        "Varias formas de decir lo mismo, separadas por |.\n"
        + "accion: una de estas, con su argumento: " + datos.acciones.join(", ") + "\n"
        + "prompt: el texto largo que se le manda al modelo.\n"
        + "sistema: el comando que corre. Hay que aprobarlo despues." }),
      aviso,
      el("div", { class: "botones" }, [guardarCmd, cerrar]),
    ]);
    cerrar.addEventListener("click", () => dlg.close());
    dlg.addEventListener("close", () => dlg.remove());
    guardarCmd.addEventListener("click", async () => {
      const r = await pedir("comandos_guardar", {
        frases: frases.value, tipo: tipo.value, valor: valorTxt.value,
        anterior: cmd || null,
      });
      if (r.ok) dlg.close(); else aviso.textContent = r.salida;
    });
    document.body.appendChild(dlg);
    dlg.showModal();
  }

  const conElegido = (fn) => () => {
    if (!elegido) { estado.textContent = "Elige uno de la lista."; return; }
    fn();
  };

  const botones = [
    ["Nuevo", () => editor(null)],
    ["Editar", conElegido(() => editor(elegido))],
    ["Borrar", conElegido(async () => {
      if (!confirm('Borrar el comando "' + elegido.frases[0] + '"?')) return;
      await pedir("comandos_borrar", elegido);
    })],
    ["Revisar y aprobar", revisar],
    ["Probar", conElegido(async () => {
      const r = await pedir("comandos_probar", elegido);
      // Un `sistema` sin aprobar NO se corre, ni siquiera desde aca: probar
      // seria el atajo perfecto para saltear el freno.
      if (r.aprobar) { revisar(); return; }
      if (r.cuerpo) ventanaTexto(r.titulo, r.cuerpo);
    })],
    ["Abrir Comandos.md", () => pedir("comandos_abrir_archivo")],
    ["Recargar", () => pedir("comandos_listar")],
  ].map(([txt, fn]) => {
    const b = el("button", { class: "boton", type: "button", text: txt });
    b.addEventListener("click", fn);
    return b;
  });

  pintarFilas();
  caja.append(tabla, el("div", { class: "botones" }, botones), aprobacion, estado);
  return caja;
}

// Una ventana con texto que se puede leer entero y copiar. Existe porque el
// cuadro del sistema recorta el texto largo sin avisar y no deja seleccionarlo,
// que son las dos cosas que uno necesita cuando algo fallo.
function ventanaTexto(titulo, cuerpo) {
  const cerrar = el("button", { class: "boton", type: "button", text: "Cerrar" });
  const dlg = el("dialog", { class: "cuadro ancho" }, [
    el("h2", { text: titulo }),
    el("pre", { class: "volcado", text: cuerpo }),
    el("div", { class: "botones" }, [cerrar]),
  ]);
  cerrar.addEventListener("click", () => dlg.close());
  dlg.addEventListener("close", () => dlg.remove());
  document.body.appendChild(dlg);
  dlg.showModal();
}

// Elegir uno de una lista que llego de la red, sin desplegable: son cientos en
// OpenRouter y un `<select>` de trescientos es peor que una lista con buscador.
function elegirDeLista(lista, clave) {
  const filtro = el("input", { type: "search", placeholder: "filtrar...", "aria-label": "filtrar" });
  const ul = el("ul", { class: "lista elegible" });
  const cerrar = el("button", { class: "boton", type: "button", text: "Cancelar" });
  const dlg = el("dialog", { class: "cuadro" }, [
    el("h2", { text: lista.length + " modelos" }), filtro, ul,
    el("div", { class: "botones" }, [cerrar]),
  ]);
  const pintarOpciones = () => {
    const q = filtro.value.trim().toLowerCase();
    ul.replaceChildren(...lista.filter((m) => !q || m.toLowerCase().includes(q))
      .slice(0, 300).map((m) => {
        const b = el("button", { class: "boton chico", type: "button", text: m });
        b.addEventListener("click", () => { editar(clave, m); dlg.close(); pintar(); });
        return el("li", {}, [b]);
      }));
  };
  filtro.addEventListener("input", pintarOpciones);
  cerrar.addEventListener("click", () => dlg.close());
  dlg.addEventListener("close", () => dlg.remove());
  pintarOpciones();
  document.body.appendChild(dlg);
  dlg.showModal();
}

/* --- los componentes de las cuatro ultimas pestanas ---------------------- */

// Pide una accion y refresca lo que devuelva. Las listas --contactos, addons,
// MCP, actividad-- vuelven enteras con cada respuesta, para no tener que
// recargar el esquema completo por agregar un contacto.
async function pedir(nombre, args, eco) {
  let r;
  try {
    r = await api("accion", nombre, cfgDePantalla(), args || {});
  } catch (exc) {
    r = { ok: false, salida: String(exc.message || exc), valores: {} };
  }
  // Una accion puede pedir confirmacion en vez de hacerse. Aca no hay cuadros
  // del sistema: pregunta el navegador y se reintenta con la marca puesta.
  if (r.confirmar) {
    if (!confirm(r.confirmar)) return { ok: false, salida: "", valores: {} };
    return pedir(nombre, Object.assign({}, args, { confirmado: true }), eco);
  }
  if (eco && r.salida !== undefined) {
    eco.textContent = r.salida;
    eco.className = "salida " + (r.ok === false ? "error" : "");
  }
  for (const [clave, valor] of Object.entries(r.valores || {})) editar(clave, valor);
  // Guardar un archivo tambien es del sistema: Python dice QUE guardar y con
  // que nombre, el cuadro lo abre la ventana, y se vuelve con el destino.
  if (r.guardar_archivo) {
    const g = r.guardar_archivo;
    const d = await api("guardar_archivo", g.nombre, g.filtros || []);
    if (d.ok && d.ruta) {
      return pedir(g.accion, Object.assign({}, g.args, { destino: d.ruta }), eco);
    }
    return r;
  }
  if (r.recargar) await recargar();
  return r;
}

function caja(hijos) {
  return el("div", { class: "lista-caja" }, hijos.filter(Boolean));
}

/* --- Cuentas: el SteamID autodetectado ---------------------------------- */

function compAutodetectado(d) {
  // Un campo comun, con una diferencia: si la config esta vacia el valor que
  // se muestra salio de mirar el disco, y hay que dejarlo como cambio
  // pendiente o se pierde al guardar.
  const id = "c-" + d.clave;
  const control = el("input", { type: "text", id });
  control.value = String(valor(d.clave) || d.valor || "");
  if (!String(valor(d.clave)) && d.valor) editar(d.clave, d.valor);
  control.addEventListener("input", () => editar(d.clave, control.value));
  return el("div", { class: "campo" },
            [el("label", { for: id, text: d.etiqueta }), control]);
}

/* --- Contactos ----------------------------------------------------------- */

function compContactos(d) {
  // Son datos de personas reales. Se dibujan y se editan; no salen de aca.
  let datos = d;
  let elegido = null;
  const tabla = el("table", { class: "tabla" });
  const cuerpo = el("tbody");
  const eco = el("p", { class: "salida" });
  const campos = {};

  tabla.appendChild(el("thead", {}, [el("tr", {},
    datos.columnas.map((c) => el("th", { text: c })))]));
  tabla.appendChild(cuerpo);

  const cargar = (c) => {
    elegido = c;
    for (const col of datos.columnas) campos[col].value = c ? (c[col] || "") : "";
  };

  const pintarFilas = () => {
    cuerpo.replaceChildren(...datos.lista.map((c) => {
      const fila = el("tr", { tabindex: "0" },
                      datos.columnas.map((col) => el("td", { text: c[col] || "" })));
      fila.addEventListener("click", () => {
        for (const tr of cuerpo.querySelectorAll("tr")) tr.removeAttribute("aria-selected");
        fila.setAttribute("aria-selected", "true");
        cargar(c);
      });
      return fila;
    }));
  };

  // El formulario, con el nombre CRUDO de cada columna: `discord_dm` y no
  // "Mensaje directo de Discord", porque la ayuda de arriba los nombra asi.
  const form = el("div", { class: "form-agenda" }, datos.columnas.map((col) => {
    const id = "contacto-" + col;
    campos[col] = el("input", { type: "text", id });
    return el("div", { class: "campo chico" },
              [el("label", { for: id, text: col }), campos[col]]);
  }));

  const refrescar = (r) => {
    if (r && r.contactos) { datos = r.contactos; pintarFilas(); }
  };

  const conNombre = () => campos.nombre.value.trim();

  const botones = [
    ["Agregar / actualizar", async () => {
      const args = {};
      for (const col of datos.columnas) args[col] = campos[col].value;
      refrescar(await pedir("contacto_guardar", args, eco));
      cargar(null);
    }],
    ["Borrar", async () => {
      const nombre = conNombre();
      if (!nombre) { eco.textContent = "Elige un contacto de la lista primero."; return; }
      if (!confirm('Borrar el contacto "' + nombre + '"?')) return;
      refrescar(await pedir("contacto_borrar", { nombre }, eco));
      cargar(null);
    }],
    ["Limpiar campos", () => cargar(null)],
    ["Exportar", () => pedir("contacto_exportar", { nombre: conNombre() }, eco)],
    ["Importar", async () => {
      const arch = await api("elegir_archivo",
                             ["Contacto de Eve (*.evecontact)", "JSON (*.json)", "*"], true);
      if (!arch.ok || !arch.rutas.length) return;
      const r = await pedir("contacto_importar", { rutas: arch.rutas }, eco);
      refrescar(r);
      // Pisar la agenda de alguien en silencio no se hace: si el archivo trae
      // nombres que ya tenias, se pregunta antes de reemplazarlos.
      if (r.conflictos && r.conflictos.length) {
        const si = confirm("Estos contactos ya estan en tu agenda:\n\n  "
          + r.conflictos.join("\n  ") + "\n\nReemplazarlos con los del archivo?");
        if (si) {
          refrescar(await pedir("contacto_importar",
                                { rutas: arch.rutas, reemplazar: r.conflictos }, eco));
        }
      }
    }],
  ].map(([txt, fn]) => {
    const b = el("button", { class: "boton", type: "button", text: txt });
    b.addEventListener("click", fn);
    return b;
  });

  pintarFilas();
  return caja([tabla, form, el("div", { class: "botones" }, botones), eco]);
}

/* --- Addons -------------------------------------------------------------- */

function compAddons(d) {
  const eco = el("p", { class: "salida" });
  if (!d.lista.length) return caja([el("p", { class: "ayuda", text: d.vacio }), eco]);
  const filas = d.lista.map((a) => {
    const casilla = el("input", { type: "checkbox" });
    casilla.checked = a.activo;
    casilla.addEventListener("change", () =>
      pedir("addons_activar", { nombre: a.nombre, activo: casilla.checked }, eco));
    const cabeza = el("label", { class: "interruptor" }, [
      casilla,
      el("span", { text: a.nombre }),
      el("span", { class: "ayuda", text: a.descripcion
        + (a.disponible ? "" : "  —  no disponible: " + a.motivo) }),
    ]);
    // Cada addon dice que claves necesita y el panel las dibuja: agregar uno
    // no obliga a tocar esta pantalla.
    const claves = a.claves.map((k) => campoDeClave({
      id: a.nombre + "-" + k.proveedor, rotulo: k.etiqueta, clave: k.proveedor,
      necesita_clave: true, tiene_clave: k.tiene,
    }));
    return el("div", { class: "addon" }, [cabeza, ...claves]);
  });
  return caja([...filas, eco]);
}

function compAddonsPendientes(d) {
  const eco = el("p", { class: "salida" });
  if (!d.lista.length) return el("p", { class: "ayuda", text: "(ninguno)" });
  const filas = d.lista.map((a) => {
    const ver = el("button", { class: "boton chico", type: "button", text: "Ver el codigo" });
    ver.addEventListener("click", async () => {
      const r = await pedir("addon_ver", { ruta: a.ruta }, eco);
      if (r.cuerpo) ventanaTexto(r.titulo, r.cuerpo);
    });
    const aprobar = el("button", { class: "boton chico", type: "button", text: "Aprobar" });
    aprobar.addEventListener("click", () =>
      pedir("addon_aprobar", { nombre: a.nombre, marca: a.marca }, eco));
    return el("li", {}, [
      el("span", { class: "lista-nombre", text: a.nombre + ".py" }),
      el("span", { class: "lista-resumen" }), ver, aprobar,
    ]);
  });
  return caja([el("ul", { class: "lista" }, filas), eco]);
}

function compAddonsAprobados(d) {
  const eco = el("p", { class: "salida" });
  if (!d.lista.length) return el("p", { class: "ayuda", text: "(ninguno)" });
  const filas = d.lista.map((nombre) => {
    const revocar = el("button", { class: "boton chico", type: "button", text: "Revocar" });
    revocar.addEventListener("click", () => pedir("addon_revocar", { nombre }, eco));
    return el("li", {}, [
      el("span", { class: "lista-nombre", text: nombre + ".py" }),
      el("span", { class: "lista-resumen" }), revocar,
    ]);
  });
  return caja([el("ul", { class: "lista" }, filas), eco]);
}

/* --- MCP ----------------------------------------------------------------- */

function compMcp(d) {
  let datos = d;
  let elegido = "";
  const eco = el("p", { class: "salida" });
  const lista = el("div", { class: "mcp-lista" });

  const pintarLista = () => {
    if (!datos.lista.length) {
      lista.replaceChildren(el("p", { class: "ayuda", text: datos.vacio }));
      return;
    }
    lista.replaceChildren(...datos.lista.map((s) => {
      const radio = el("input", { type: "radio", name: "mcp", value: s.nombre });
      radio.checked = s.nombre === elegido;
      radio.addEventListener("change", () => { elegido = s.nombre; });
      const casilla = el("input", { type: "checkbox" });
      casilla.checked = s.activo;
      // Encender uno es autorizar que corra en tu maquina, asi que se escribe
      // al toque y no queda como cambio pendiente: vive en el archivo de MCP,
      // no en la config.
      casilla.addEventListener("change", async () => {
        const r = await pedir("mcp_activar",
                              { nombre: s.nombre, activo: casilla.checked }, eco);
        if (r.mcp) { datos = r.mcp; pintarLista(); }
      });
      const detalle = s.comando.slice(0, 60)
        + (s.de ? "   (de " + s.de + ")" : "")
        + (s.vistas ? "   " + s.vistas + " herramientas" : "");
      return el("label", { class: "mcp-fila" }, [
        radio, casilla,
        el("span", { class: "lista-nombre", text: s.nombre }),
        el("span", { class: "lista-resumen", text: detalle }),
      ]);
    }));
  };

  const conElegido = (fn) => async () => {
    if (!elegido) { eco.textContent = "Elige un servidor de la lista."; return; }
    await fn();
  };

  const botones = [
    ["Buscar los que ya tienes", async () => {
      const r = await pedir("mcp_importar", {}, eco);
      if (r.hallados) elegirServidores(r, async (elegidos) => {
        const r2 = await pedir("mcp_importar", { elegidos }, eco);
        if (r2.mcp) { datos = r2.mcp; pintarLista(); }
      });
    }],
    ["Agregar a mano", () => editorMcp(async (args) => {
      const r = await pedir("mcp_agregar", args, eco);
      if (r.mcp) { datos = r.mcp; pintarLista(); }
      return r;
    })],
    ["Ver herramientas", conElegido(async () => {
      const r = await pedir("mcp_herramientas", { nombre: elegido }, eco);
      if (r.herramientas) ventanaHerramientas(r, eco);
    })],
    ["Quitar", conElegido(async () => {
      if (!confirm('Quitar el servidor "' + elegido + '"?')) return;
      const r = await pedir("mcp_quitar", { nombre: elegido }, eco);
      if (r.mcp) { datos = r.mcp; elegido = ""; pintarLista(); }
    })],
  ].map(([txt, fn]) => {
    const b = el("button", { class: "boton", type: "button", text: txt });
    b.addEventListener("click", fn);
    return b;
  });

  pintarLista();
  return caja([el("div", { class: "botones" }, botones), lista, eco]);
}

function elegirServidores(r, alAceptar) {
  const casillas = r.hallados.map((h) => {
    const c = el("input", { type: "checkbox" });
    c.checked = !h.ya;
    c.dataset.nombre = h.nombre;
    return el("label", { class: "interruptor" }, [
      c, el("span", { class: "lista-nombre", text: h.nombre }),
      el("span", { class: "lista-resumen", text: h.de + "   " + h.comando.slice(0, 60) }),
    ]);
  });
  const aceptar = el("button", { class: "boton primario", type: "button", text: "Agregar" });
  const cerrar = el("button", { class: "boton", type: "button", text: "Cancelar" });
  const dlg = el("dialog", { class: "cuadro" }, [
    el("h2", { text: "Servidores encontrados" }),
    ...casillas,
    el("p", { class: "ayuda", text: r.aviso }),
    el("div", { class: "botones" }, [aceptar, cerrar]),
  ]);
  aceptar.addEventListener("click", () => {
    const elegidos = [...dlg.querySelectorAll("input:checked")].map((c) => c.dataset.nombre);
    dlg.close();
    alAceptar(elegidos);
  });
  cerrar.addEventListener("click", () => dlg.close());
  dlg.addEventListener("close", () => dlg.remove());
  document.body.appendChild(dlg);
  dlg.showModal();
}

function editorMcp(alGuardar) {
  const campos = {};
  const filas = [["nombre", "Nombre"], ["comando", "Comando"], ["args", "Argumentos"]]
    .map(([k, rotulo]) => {
      campos[k] = el("input", { type: "text", id: "mcp-" + k });
      return el("div", { class: "campo" },
                [el("label", { for: "mcp-" + k, text: rotulo }), campos[k]]);
    });
  const aviso = el("p", { class: "ayuda", text: "Los argumentos van separados por espacios." });
  const guardarBtn = el("button", { class: "boton primario", type: "button", text: "Guardar" });
  const cerrar = el("button", { class: "boton", type: "button", text: "Cancelar" });
  const dlg = el("dialog", { class: "cuadro" }, [
    el("h2", { text: "Servidor MCP" }), ...filas, aviso,
    el("div", { class: "botones" }, [guardarBtn, cerrar]),
  ]);
  guardarBtn.addEventListener("click", async () => {
    const r = await alGuardar({ nombre: campos.nombre.value, comando: campos.comando.value,
                                args: campos.args.value });
    if (r.ok) dlg.close(); else aviso.textContent = r.salida;
  });
  cerrar.addEventListener("click", () => dlg.close());
  dlg.addEventListener("close", () => dlg.remove());
  document.body.appendChild(dlg);
  dlg.showModal();
}

function ventanaHerramientas(r, eco) {
  const filas = r.herramientas.map((h) => {
    const activa = el("input", { type: "checkbox" });
    activa.checked = h.activa;
    activa.addEventListener("change", () => pedir("mcp_herramienta",
      { servidor: r.servidor, nombre: h.nombre, activa: activa.checked }, eco));
    const confiada = el("input", { type: "checkbox" });
    confiada.checked = h.confiada;
    confiada.addEventListener("change", () => pedir("mcp_herramienta",
      { servidor: r.servidor, nombre: h.nombre, confiada: confiada.checked }, eco));
    return el("li", {}, [
      el("label", { class: "interruptor" }, [activa, el("span", { class: "lista-nombre", text: h.nombre })]),
      el("label", { class: "interruptor" }, [confiada, el("span", { text: "sin preguntar" })]),
      el("span", { class: "lista-resumen", text: h.descripcion }),
    ]);
  });
  const cerrar = el("button", { class: "boton", type: "button", text: "Cerrar" });
  const dlg = el("dialog", { class: "cuadro ancho" }, [
    el("h2", { text: "Herramientas: " + r.servidor }),
    el("p", { class: "ayuda", text: r.aviso }),
    el("ul", { class: "lista" }, filas),
    el("div", { class: "botones" }, [cerrar]),
  ]);
  cerrar.addEventListener("click", () => dlg.close());
  dlg.addEventListener("close", () => dlg.remove());
  document.body.appendChild(dlg);
  dlg.showModal();
}

/* --- Actividad ----------------------------------------------------------- */

function compHistorial(d) {
  let datos = d;
  const eco = el("p", { class: "salida" });
  const cuantos = el("span", { class: "ayuda", text: datos.cuantos });
  const caja_ = el("div", { class: "historial" });

  const pintarTurnos = () => {
    cuantos.textContent = datos.cuantos;
    caja_.replaceChildren(...datos.lista.map((t) => el("div", { class: "turno" }, [
      el("span", { class: "turno-hora", text: "[" + t.hora + "]" }),
      el("span", { class: "turno-quien", text: t.quien }),
      el("span", { class: "turno-texto", text: t.texto }),
    ])));
  };

  const limpiar = el("button", { class: "boton", type: "button", text: "Limpiar historial" });
  limpiar.addEventListener("click", async () => {
    const r = await pedir("historial_limpiar", {}, eco);
    if (r.historial) { datos = r.historial; pintarTurnos(); }
  });

  pintarTurnos();
  return caja([el("div", { class: "botones" }, [limpiar, cuantos]), caja_, eco]);
}

function compAcciones(d) {
  // Muestra lo que Eve ejecuto Y lo que el usuario freno. Las dos mitades: una
  // tabla llena solo de operaciones exitosas venderia una idea equivocada de
  // para que esta.
  const tabla = el("table", { class: "tabla" }, [
    el("thead", {}, [el("tr", {}, d.columnas.map((c) => el("th", { text: c })))]),
    el("tbody", {}, d.lista.map((f) => el("tr", {}, f.map((v, i) =>
      el("td", { class: i === 2 ? "mono" : "", text: String(v) }))))),
  ]);
  return caja([tabla]);
}

/* --- Perfiles ------------------------------------------------------------ */

function compPerfiles(d) {
  const eco = el("p", { class: "salida" });
  let elegido = d.activo;

  // Cada muestra pinta el panel arriba y el cartel abajo. Con el cartel solo,
  // Claro y Oscuro se veian identicos: lo que cambia entre esos dos es
  // `ui_tema`, que es justamente la mitad de arriba.
  const galeria = el("div", { class: "galeria" }, d.lista.map((p) => {
    const muestra = el("button", {
      class: "muestra" + (p.nombre === elegido ? " activa" : ""),
      type: "button", "aria-pressed": String(p.nombre === elegido),
    }, [
      el("span", { class: "muestra-panel" }, [
        el("span", { class: "muestra-riel" }),
        el("span", { class: "muestra-tarjeta" }),
      ]),
      el("span", { class: "muestra-cartel" }, [
        el("span", { class: "muestra-punto" }),
        el("span", { class: "muestra-titulo", text: p.titulo }),
      ]),
      el("span", { class: "muestra-nombre", text: p.etiqueta }),
    ]);
    const s = muestra.style;
    s.setProperty("--m-fondo", p.ui.fondo);
    s.setProperty("--m-panel", p.ui.panel);
    s.setProperty("--m-texto", p.ui.texto);
    s.setProperty("--m-acento", p.ui.acento);
    s.setProperty("--m-borde", p.ui.borde);
    s.setProperty("--m-hud-fondo", p.hud.fondo);
    s.setProperty("--m-hud-texto", p.hud.texto);
    s.setProperty("--m-hud-acento", p.hud.acento);
    muestra.addEventListener("click", () => {
      elegido = p.nombre;
      combo.value = p.nombre;
      for (const m of galeria.querySelectorAll(".muestra")) {
        m.classList.remove("activa");
        m.setAttribute("aria-pressed", "false");
      }
      muestra.classList.add("activa");
      muestra.setAttribute("aria-pressed", "true");
    });
    // Dos clics para aplicarlo, uno para elegirlo: es lo que dice la ayuda.
    muestra.addEventListener("dblclick", () => pedir("perfil_cargar", { nombre: p.nombre }, eco));
    return muestra;
  }));

  const combo = el("select", { id: "c-perfil_activo" });
  combo.appendChild(el("option", { value: "", text: "(sin elegir)" }));
  for (const p of d.lista) combo.appendChild(el("option", { value: p.nombre, text: p.etiqueta }));
  combo.value = elegido;
  combo.addEventListener("change", () => { elegido = combo.value; });

  const botones = [
    ["Cargar", () => pedir("perfil_cargar", { nombre: elegido }, eco)],
    ["Guardar como...", () => {
      const nombre = prompt("Nombre del perfil:", elegido || "nuevo");
      if (!nombre) return;
      // Lo pendiente viaja con el pedido: un perfil que sale de la config del
      // disco no incluye lo que acabas de cambiar, que es lo que querias guardar.
      return pedir("perfil_guardar",
                   { nombre, pendientes: Object.fromEntries(PENDIENTES) }, eco);
    }],
    ["Borrar", () => pedir("perfil_borrar", { nombre: elegido }, eco)],
    ["Exportar...", () => pedir("perfil_exportar", { nombre: elegido }, eco)],
    ["Importar...", async () => {
      const arch = await api("elegir_archivo", ["Perfil de Eve (*.eveperfil)", "*"], true);
      if (!arch.ok || !arch.rutas.length) return;
      const r = await pedir("perfil_importar", { rutas: arch.rutas }, eco);
      if (r.conflictos && r.conflictos.length) {
        const si = confirm("Ya hay perfiles con estos nombres:\n\n  "
          + r.conflictos.join("\n  ") + "\n\nSe reemplazan?");
        if (si) await pedir("perfil_importar",
                            { rutas: arch.rutas, reemplazar: r.conflictos }, eco);
      }
    }],
  ].map(([txt, fn]) => {
    const b = el("button", { class: "boton", type: "button", text: txt });
    b.addEventListener("click", fn);
    return b;
  });

  return caja([
    galeria,
    el("p", { class: "ayuda", text:
      "Un clic para elegirlo, dos para aplicarlo. Los que dicen (de fabrica)\n"
      + "no se borran: guardar uno propio con el mismo nombre no los pisa." }),
    el("div", { class: "campo" }, [
      el("label", { for: "c-perfil_activo", text: d.etiqueta }), combo]),
    el("div", { class: "botones" }, botones),
    eco,
  ]);
}

const COMPONENTES = {
  rutas: compRutas,
  permisos: compPermisos,
  proveedores: compProveedores,
  ayuda: compAyuda,
  archivo: compArchivo,
  formas: compFormas,
  skills: compSkills,
  comandos: compComandos,
  salida: compSalida,
  sin_portar: compSinPortar,
  error: compError,
  autodetectado: compAutodetectado,
  contactos: compContactos,
  addons: compAddons,
  addons_pendientes: compAddonsPendientes,
  addons_aprobados: compAddonsAprobados,
  mcp: compMcp,
  historial: compHistorial,
  acciones: compAcciones,
  perfiles: compPerfiles,
};

/* --- las pestanas ------------------------------------------------------- */

function pestanaActual() {
  return ESQ.pestanas.find((p) => p.clave === PESTANA) || ESQ.pestanas[0];
}

function pintarRiel() {
  const riel = $(".riel");
  riel.replaceChildren(...ESQ.pestanas.map((p) => el("button", {
    type: "button", text: p.rotulo,
    "aria-current": p.clave === PESTANA ? "page" : null,
    onclick: () => { PESTANA = p.clave; SUB = null; pintar(); },
  })));
}

function pintarContenido() {
  const p = pestanaActual();
  const cont = $(".contenido");
  const cabecera = el("div", { class: "cabecera" }, [
    el("h1", { text: p.rotulo }),
    p.subtitulo ? el("p", { text: p.subtitulo }) : null,
  ]);
  cont.replaceChildren(cabecera);

  if (!p.tablas.length) {
    cont.appendChild(el("div", { class: "vacia", text:
      "Esta pestana no sale del registro: esta escrita a mano en gui.py." }));
    return;
  }

  // Apariencia es la unica con sub-pestanas, y es porque son cuatro tablas del
  // registro. Una tabla sola no las necesita.
  // Varias tablas se muestran UNA ABAJO DE LA OTRA, que es como las compone el
  // panel viejo. Solo se parten en sub-pestanas las que Python declara como
  // tales --las cuatro de Apariencia-- y eso lo dice `subpestanas`, que ya las
  // nombra: dos listas para lo mismo es la copia que se desfasa.
  const parte = p.tablas.every((t) => ESQ.subpestanas[t]);
  let tablas = p.tablas;
  if (parte && p.tablas.length > 1) {
    if (!p.tablas.includes(SUB)) SUB = p.tablas[0];
    tablas = [SUB];
    cont.appendChild(el("div", { class: "subpestanas", role: "tablist" },
      p.tablas.map((t) => el("button", {
        type: "button", role: "tab", text: ESQ.subpestanas[t] || t,
        "aria-selected": String(t === SUB),
        onclick: () => { SUB = t; pintar(); },
      }))));
  }
  const nodos = [];
  for (const t of tablas) nodos.push(...ESQ.tablas[t].map(nodo).filter(Boolean));
  cont.appendChild(el("div", { class: "tablero" }, nodos));
}

function pintarPie() {
  const n = PENDIENTES.size;
  const txt = $(".pendientes");
  txt.replaceChildren(...(n === 0
    ? [document.createTextNode("Sin cambios sin guardar")]
    : [el("b", { text: String(n) }),
       document.createTextNode(n === 1 ? " cambio sin guardar: " : " cambios sin guardar: "),
       document.createTextNode([...PENDIENTES.keys()].join(", "))]));
  $(".pie .boton.primario").disabled = n === 0;
}

function pintar() {
  // La pestana, marcada en el documento. `tokens.css` la usa para darle a cada
  // una la columna de rotulos que tiene en SU artboard: el dibujo no usa la
  // misma en las nueve --150 en casi todas, 200 en General, 220 en Cuentas--
  // y seguirlo pestana por pestana es lo unico que da diferencia cero contra
  // cada dibujo. Unificar seria elegir por el diseno, no implementarlo.
  document.body.dataset.pestana = PESTANA;
  pintarRiel();
  pintarContenido();
  pintarPie();
}

/* --- guardar ------------------------------------------------------------ */

async function guardar() {
  const aviso = $(".pie .aviso");
  aviso.className = "aviso";
  aviso.textContent = "";
  let r;
  try {
    r = await api("guardar", Object.fromEntries(PENDIENTES));
  } catch (exc) {
    aviso.className = "aviso error";
    aviso.textContent = String(exc.message || exc);
    return;
  }
  if (!r.ok) {
    aviso.className = "aviso error";
    aviso.textContent = r.error;
    return;
  }
  // Lo que quedo escrito pasa a ser el valor de referencia. Sin esto, "7,5"
  // seguiria mostrandose asi despues de guardarse como 7.5, y el proximo
  // guardado lo volveria a mandar.
  Object.assign(ESQ.valores, r.valores);
  PENDIENTES.clear();
  aviso.className = "aviso hecho";
  aviso.textContent = "Guardado";
  pintar();
}

/* --- arranque ----------------------------------------------------------- */

async function arrancar() {
  try {
    ESQ = await api("esquema");
  } catch (exc) {
    $(".contenido").replaceChildren(el("div", { class: "vacia",
      text: "No se pudo leer la configuracion: " + (exc.message || exc) }));
    return;
  }
  aplicarTema(ESQ);
  $(".version").textContent = "v" + (ESQ.version || "?");
  // El par de botones arranca donde diga la config, no donde diga el HTML: si
  // el usuario dejo el panel en "Todo", abrirlo mostrando "Lo esencial"
  // marcado y las avanzadas cerradas seria decirle que su ajuste no se guardo.
  document.querySelectorAll(".modo").forEach(
    (b) => b.setAttribute("aria-pressed", String(b.dataset.modo === ESQ.modo)));
  pintar();
  // Estas dos salen a hablar con otro programa --Outlook por COM, el CLI de
  // Claude-- y tardan segundos. Van DESPUES de dibujar: esperarlas antes
  // dejaria la ventana en blanco mientras tanto.
  for (const nombre of ESQ.salidas_al_abrir || []) correr(nombre, {});
}

$(".pie .boton.primario").addEventListener("click", guardar);
$(".buscador").addEventListener("input", (ev) => {
  // Filtrado en vivo sobre lo que ya esta dibujado: esconde las secciones que
  // no tienen ninguna coincidencia. El buscador de verdad --el que salta a la
  // pestana correcta-- usa `registro.buscar()` y se porta despues.
  const q = ev.target.value.trim().toLowerCase();
  for (const sec of document.querySelectorAll(".contenido .seccion")) {
    sec.hidden = q !== "" && !sec.textContent.toLowerCase().includes(q);
  }
});
document.querySelectorAll(".modo").forEach((b) => b.addEventListener("click", () => {
  ESQ.modo = b.dataset.modo;
  // Es un ajuste como cualquier otro --`ui_modo_panel`-- y por eso queda como
  // cambio pendiente en vez de vivir solo en la pantalla. Si no, abrir el
  // panel te devolvia siempre a "Lo esencial" sin decir por que.
  editar("ui_modo_panel", b.dataset.modo);
  document.querySelectorAll(".modo").forEach(
    (o) => o.setAttribute("aria-pressed", String(o === b)));
  pintar();
}));

// pywebview avisa cuando el puente esta listo. Si ya lo esta --recarga-- el
// evento no vuelve a salir, asi que se prueba tambien de una.
window.addEventListener("pywebviewready", arrancar);
if (window.pywebview && window.pywebview.api) arrancar();
