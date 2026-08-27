"""Un servidor MCP minimo, para probar el cliente sin salir a la red.

No es un mock del cliente: habla el protocolo de verdad --JSON-RPC 2.0, un
mensaje por linea-- asi que lo que se prueba contra el es el transporte
completo. El cliente tambien se comprobo a mano contra un servidor ajeno de
verdad (`npx @playwright/mcp`, 24 herramientas descubiertas); esto es la
version que puede correr en CI todos los dias.

Escribe una linea de log por stdout ANTES de contestar nada, a proposito: hay
servidores reales que lo hacen y el cliente tiene que saltearla en vez de
morirse tratando de parsearla.
"""
import json
import sys

HERRAMIENTAS = [
    {"name": "sumar", "description": "suma dos numeros",
     "inputSchema": {"type": "object",
                     "properties": {"a": {"type": "number"},
                                    "b": {"type": "number"}}}},
    {"name": "saludar", "description": "dice hola",
     "inputSchema": {"type": "object",
                     "properties": {"quien": {"type": "string"}}}},
]


def responder(msg):
    metodo = msg.get("method")
    if metodo == "initialize":
        return {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                "serverInfo": {"name": "falso", "version": "1"}}
    if metodo == "tools/list":
        return {"tools": HERRAMIENTAS}
    if metodo == "tools/call":
        p = msg.get("params") or {}
        args = p.get("arguments") or {}
        if p.get("name") == "sumar":
            return {"content": [{"type": "text",
                                 "text": str(args.get("a", 0) + args.get("b", 0))}]}
        if p.get("name") == "saludar":
            return {"content": [{"type": "text",
                                 "text": "hola " + str(args.get("quien", "nadie"))}]}
        return {"content": [{"type": "text", "text": "no conozco esa"}],
                "isError": True}
    return None


print("servidor falso arrancando", flush=True)

for linea in sys.stdin:
    linea = linea.strip()
    if not linea:
        continue
    try:
        msg = json.loads(linea)
    except ValueError:
        continue
    if "id" not in msg:
        continue   # una notificacion no se contesta
    r = responder(msg)
    salida = {"jsonrpc": "2.0", "id": msg["id"]}
    if r is None:
        salida["error"] = {"code": -32601, "message": "metodo desconocido"}
    else:
        salida["result"] = r
    print(json.dumps(salida), flush=True)
