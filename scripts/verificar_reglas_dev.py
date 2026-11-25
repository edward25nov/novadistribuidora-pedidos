"""Verifica el motor de reglas contra mensajes_dev.jsonl, sin modelo:

1. reglas.py (§4–§8) en los 84 casos, con ítems reconstruidos desde la respuesta esperada.
2. consolidacion.py + reglas.py (§2–§8) en los 8 casos "habitual", con las menciones escritas a
   mano a partir del mensaje (MencionHabitual + agregados / exclusiones) y el historial real.

Si no reproduce total, fecha, estado y motivos, el error es del motor, no del LLM.

Uso: python scripts/verificar_reglas_dev.py [ruta_ges]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from decimal import Decimal

from pedidos.consolidacion import Accion, ItemPedido, MencionHabitual, MencionResuelta, consolidar
from pedidos.datos import cargar_datos
from pedidos.esquemas import Motivo, Pendiente, SolicitudPedido
from pedidos.reglas import calcular_pedido


def items_desde_esperado(esp: dict) -> tuple[list[ItemPedido], list[Pendiente]]:
    sust = {s["sku_entregado"]: s for s in esp["sustituciones"]}
    items: list[ItemPedido] = []
    for linea in esp["lineas"]:
        restante = linea["cantidad"]
        if linea["sku"] in sust:
            s = sust[linea["sku"]]
            items.append(ItemPedido(s["sku_solicitado"], s["cantidad"], "sust"))
            restante -= s["cantidad"]
        if restante:
            items.append(ItemPedido(linea["sku"], restante, "linea"))
    pendientes = []
    for p in esp["pendientes"]:
        if p["motivo"] == "agotado_sin_sustituto":
            items.append(ItemPedido(p["opciones"][0], 1, p["texto"]))   # el motor lo marca
        else:
            pendientes.append(Pendiente(**p))
    return items, pendientes


_H = MencionHabitual("lo de siempre")


def _mas(sku: str, n: int) -> MencionResuelta:
    return MencionResuelta(texto=sku, sku=sku, cantidad=Decimal(n))


def _sin(sku: str) -> MencionResuelta:
    return MencionResuelta(texto=sku, sku=sku, accion=Accion.quitar)


# Menciones escritas a mano leyendo cada mensaje "habitual" (lo que debería extraer el LLM).
MENCIONES_HABITUALES = {
    "D012": [_H, _mas("L04", 2)],              # "lo mismo de la otra vez y papel suave 4: 2"
    "D017": [_H],                              # "lo de cada semana"
    "D025": [_H, _sin("A11")],                 # "lo mismo que la vez pasada. quíteme sal pacífico"
    "D030": [_H],
    "D031": [_H, _mas("S03", 5)],              # "de siempre y cinco galletas crac"
    "D033": [_H, _mas("L01", 5)],              # "lo mismo del último pedido y 5 fardos de detergente"
    "D040": [_H, _mas("L06", 2), _sin("P04")], # "... y 2 lavaplatos. pero sin desodorante fresco"
    "D044": [_H, _mas("B01", 1)],              # "pedido de siempre y 1 fardo de kola norte 600"
}


def comparar(caso: dict, datos, con_consolidacion: bool = False) -> list[str]:
    e = caso["esperado"]
    s = SolicitudPedido(**caso["entrada"])
    if con_consolidacion:
        items, pend = consolidar(MENCIONES_HABITUALES[caso["id"]], datos, s.cliente_id)
    else:
        items, pend = items_desde_esperado(e)
    r = calcular_pedido(s.cliente_id, s.recibido, items, pend, datos)
    dif = []
    if r.estado.value != e["estado"]:
        dif.append(f"estado {r.estado.value} != {e['estado']}")
    obtenidas = [l.model_dump() for l in r.lineas]
    if sorted(obtenidas, key=lambda l: l["sku"]) != sorted(e["lineas"], key=lambda l: l["sku"]):
        dif.append(f"lineas {obtenidas} != {e['lineas']}")
    if float(r.total) != e["total"]:
        dif.append(f"total {r.total} != {e['total']}")
    fecha = r.fecha_entrega.isoformat() if r.fecha_entrega else None
    if fecha != e["fecha_entrega"]:
        dif.append(f"fecha {fecha} != {e['fecha_entrega']}")
    if sorted((p.motivo.value, tuple(p.opciones)) for p in r.pendientes) != sorted(
        (p["motivo"], tuple(p["opciones"])) for p in e["pendientes"]
    ):
        dif.append(f"pendientes {r.pendientes} != {e['pendientes']}")
    if sorted(m.value for m in r.motivos_revision) != sorted(e["motivos_revision"]):
        dif.append(f"motivos {[m.value for m in r.motivos_revision]} != {e['motivos_revision']}")
    if [x.model_dump() for x in r.sustituciones] != e["sustituciones"]:
        dif.append(f"sustituciones {r.sustituciones} != {e['sustituciones']}")
    return dif


def main(ruta: Path) -> int:
    datos = cargar_datos(ruta)
    casos = [json.loads(l) for l in (ruta / "ejemplos/mensajes_dev.jsonl").open()]
    fallos = 0
    for c in casos:
        dif = comparar(c, datos)
        if dif:
            fallos += 1
            print(c["id"], c["tipo"], *dif, sep="\n   ")
    print(f"{len(casos) - fallos}/{len(casos)} casos reproducidos por reglas.py (§4–§8)")
    habituales = [c for c in casos if c["id"] in MENCIONES_HABITUALES]
    fallos_h = 0
    for c in habituales:
        dif = comparar(c, datos, con_consolidacion=True)
        if dif:
            fallos_h += 1
            print(c["id"], "(consolidación)", *dif, sep="\n   ")
    print(f"{len(habituales) - fallos_h}/{len(habituales)} casos 'habitual' reproducidos por "
          "consolidacion.py + reglas.py (§2–§8)")
    return 1 if fallos or fallos_h or len(habituales) != len(MENCIONES_HABITUALES) else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "ges")))
