"""Corre el motor de reglas sobre mensajes_dev.jsonl con los ítems reconstruidos a mano desde
la respuesta esperada (sin modelo). Si no reproduce total, fecha, estado y motivos, el error
es del motor, no del LLM.

Uso: python scripts/verificar_reglas_dev.py [ruta_ges]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from pedidos.consolidacion import ItemPedido
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


def comparar(caso: dict, datos) -> list[str]:
    e = caso["esperado"]
    s = SolicitudPedido(**caso["entrada"])
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
    print(f"{len(casos) - fallos}/{len(casos)} casos reproducidos por el motor de reglas")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1] if len(sys.argv) > 1 else "ges")))
