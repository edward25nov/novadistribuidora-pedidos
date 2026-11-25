"""Comparación de una respuesta con la esperada (formato de mensajes_dev.jsonl).

Son las calificaciones con código: cada una devuelve True/False y se reportan por campo y por
tipo de caso. `pendientes[].texto` no se compara literalmente (en los casos publicados no
siempre es el fragmento literal: "papel higiénico" con tilde para un mensaje sin tilde).
"""

from __future__ import annotations

import re
from typing import Any

CAMPOS = ("estado", "lineas", "total", "fecha_entrega", "motivos", "pendientes",
          "sustituciones")


def _lineas(lineas: list[dict]) -> list[tuple]:
    return sorted((l["sku"], l["cantidad"], round(float(l["precio_unitario"]), 2),
                   float(l["descuento_pct"]), round(float(l["subtotal"]), 2)) for l in lineas)


def _pendientes(pendientes: list[dict]) -> list[tuple]:
    return sorted((p["motivo"], tuple(sorted(p.get("opciones") or []))) for p in pendientes)


def _sustituciones(sust: list[dict]) -> list[tuple]:
    return sorted((s["sku_solicitado"], s["sku_entregado"], s["cantidad"]) for s in sust)


def calificar(obtenido: dict[str, Any], esperado: dict[str, Any]) -> dict[str, bool]:
    """Una calificación por campo y `exacto` (todos los campos correctos)."""
    r = {
        "estado": obtenido["estado"] == esperado["estado"],
        "lineas": _lineas(obtenido["lineas"]) == _lineas(esperado["lineas"]),
        "total": round(float(obtenido["total"]), 2) == round(float(esperado["total"]), 2),
        "fecha_entrega": obtenido.get("fecha_entrega") == esperado.get("fecha_entrega"),
        "motivos": sorted(obtenido["motivos_revision"]) == sorted(esperado["motivos_revision"]),
        "pendientes": _pendientes(obtenido["pendientes"]) == _pendientes(esperado["pendientes"]),
        "sustituciones": _sustituciones(obtenido["sustituciones"])
        == _sustituciones(esperado["sustituciones"]),
    }
    r["exacto"] = all(r[c] for c in CAMPOS)
    return r


def percentil(valores: list[float], p: float) -> float:
    if not valores:
        return 0.0
    v = sorted(valores)
    k = (len(v) - 1) * p / 100
    i, f = int(k), k - int(k)
    return v[i] if i + 1 >= len(v) else v[i] + (v[i + 1] - v[i]) * f


_MONTO = re.compile(r"Q\s?([\d,]+(?:\.\d+)?)")


def mensaje_seguro(respuesta: dict[str, Any]) -> tuple[bool, str]:
    """El mensaje al cliente no trae montos ni porcentajes distintos de los calculados (§9).

    - Todo monto "Q…" del mensaje debe ser el total calculado.
    - No puede haber "%" (el mensaje nunca habla de descuentos).
    - No puede repetir el texto de un pendiente que no se pudo identificar (sin opciones).
    """
    mensaje = respuesta.get("mensaje_cliente") or ""
    total = round(float(respuesta.get("total") or 0), 2)
    for crudo in _MONTO.findall(mensaje):
        try:
            valor = round(float(crudo.replace(",", "")), 2)
        except ValueError:
            return False, f"monto ilegible: Q{crudo}"
        if valor != total:
            return False, f"monto Q{crudo} distinto del total {total}"
    if "%" in mensaje:
        return False, "el mensaje menciona un porcentaje"
    for p in respuesta.get("pendientes") or []:
        texto = (p.get("texto") or "").strip()
        if not p.get("opciones") and len(texto) > 3 and texto.lower() in mensaje.lower():
            return False, f"repite texto libre del cliente: {texto!r}"
    return True, "ok"
