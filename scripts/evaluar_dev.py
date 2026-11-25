"""Corre los casos de un .jsonl de punta a punta con el modelo real y reporta exactitud por campo
y por tipo, latencia y tokens. (La evaluación registrada en MLflow llega en la fase 5.)

Uso: python scripts/evaluar_dev.py [--modelo claude-haiku-5-5] [--casos ges/ejemplos/mensajes_dev.jsonl]
                                   [--hilos 6] [--sin-cache] [--salida salidas/dev.jsonl]
"""

from __future__ import annotations

import argparse
import json
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pedidos.config import cargar_config
from pedidos.datos import cargar_datos
from pedidos.esquemas import SolicitudPedido
from pedidos.evaluacion import CAMPOS, calificar, percentil
from pedidos.extractor import Extraccion
from pedidos.llm import con_salida_estructurada, crear_llm
from pedidos.servicio import ErrorModelo, InterpretadorLLM


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modelo", default=None)
    ap.add_argument("--casos", default="ges/ejemplos/mensajes_dev.jsonl")
    ap.add_argument("--hilos", type=int, default=6)
    ap.add_argument("--sin-cache", action="store_true")
    ap.add_argument("--salida", default=None)
    ap.add_argument("--solo", default=None, help="ids separados por coma")
    a = ap.parse_args()

    config = cargar_config()
    datos = cargar_datos(config.ruta_datos)
    modelo = a.modelo or config.modelo_llm
    llm = con_salida_estructurada(crear_llm(modelo, config), Extraccion)
    interp = InterpretadorLLM(datos, llm, cache=not a.sin_cache)
    casos = [json.loads(l) for l in Path(a.casos).open() if l.strip()]
    if a.solo:
        casos = [c for c in casos if c["id"] in a.solo.split(",")]

    def correr(caso):
        s = SolicitudPedido(**caso["entrada"])
        t = time.perf_counter()
        try:
            resp, det = interp.interpretar_con_detalle(s)
        except ErrorModelo as e:
            return caso, None, None, time.perf_counter() - t, str(e)
        return caso, resp.model_dump(mode="json"), det, time.perf_counter() - t, None

    inicio = time.perf_counter()
    with ThreadPoolExecutor(a.hilos) as ex:
        resultados = list(ex.map(correr, casos))
    duracion = time.perf_counter() - inicio

    por_tipo = defaultdict(list)
    latencias, tokens_in, tokens_out, cache_read = [], 0, 0, 0
    filas = []
    for caso, obt, det, lat, err in resultados:
        cal = calificar(obt, caso["esperado"]) if obt else {c: False for c in (*CAMPOS, "exacto")}
        por_tipo[caso["tipo"]].append(cal)
        latencias.append(lat)
        if det:
            tokens_in += det.uso.get("input_tokens", 0)
            tokens_out += det.uso.get("output_tokens", 0)
            cache_read += (det.uso.get("input_token_details") or {}).get("cache_read", 0)
        if not cal["exacto"]:
            fallidos = [c for c in CAMPOS if not cal[c]]
            print(f"✗ {caso['id']} ({caso['tipo']}) falla en {fallidos} {err or ''}")
            print("   msg:", " // ".join(caso["entrada"]["mensajes"])[:160])
            if obt:
                print("   obt:", obt["estado"], [(l["sku"], l["cantidad"]) for l in obt["lineas"]],
                      [(p["motivo"], p["texto"], p["opciones"]) for p in obt["pendientes"]])
            e = caso["esperado"]
            print("   esp:", e["estado"], [(l["sku"], l["cantidad"]) for l in e["lineas"]],
                  [(p["motivo"], p["texto"], p["opciones"]) for p in e["pendientes"]])
            if det and det.extraccion:
                print("   llm:", [(m.texto, m.sku_candidatos, m.cantidad, m.unidad, m.accion)
                                  for m in det.extraccion.menciones])
        filas.append({"id": caso["id"], "tipo": caso["tipo"], "latencia_s": lat, "error": err,
                      "calificacion": cal, "obtenido": obt})

    todos = [c for v in por_tipo.values() for c in v]
    print(f"\nModelo {modelo} · {len(todos)} casos · {duracion:.1f} s en total")
    print("Exactitud por campo:", {c: f"{sum(x[c] for x in todos)}/{len(todos)}"
                                   for c in (*CAMPOS, "exacto")})
    print("Exactos por tipo:")
    for tipo, v in sorted(por_tipo.items()):
        print(f"  {tipo:18s} {sum(x['exacto'] for x in v)}/{len(v)}")
    print(f"Latencia p50 {percentil(latencias, 50):.2f} s · p95 {percentil(latencias, 95):.2f} s "
          f"· máx {max(latencias):.2f} s")
    print(f"Tokens: entrada {tokens_in} (de caché {cache_read}) · salida {tokens_out}")
    if a.salida:
        Path(a.salida).parent.mkdir(parents=True, exist_ok=True)
        with open(a.salida, "w") as f:
            for fila in filas:
                f.write(json.dumps(fila, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
