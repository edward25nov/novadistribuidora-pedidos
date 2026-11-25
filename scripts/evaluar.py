"""Evaluación reproducible en MLflow (mlflow.genai.evaluate).

- Dataset registrado en MLflow: casos publicados (ges/ejemplos/mensajes_dev.jsonl) + casos
  propios (ejemplos/casos_propios.jsonl), con `caso` y `tipo` en las entradas.
- Calificaciones con código, una por campo: estado, lineas, total, fecha_entrega, motivos,
  pendientes, sustituciones, exacto, y mensaje_seguro (sin montos ni % ajenos en la
  confirmación). Más latencia y costo por solicitud.
- Métricas por tipo de caso, p50/p95 de latencia y costo total se registran en la misma corrida
  y en evidencia/ (CSV).
- Estabilidad: los casos de inyección se repiten N veces (por defecto 3).
- Las trazas de la evaluación llevan origen=evaluacion, caso, tipo y corrida (separadas de las
  de la API, que llevan origen=api).

Uso:
  python scripts/evaluar.py --nombre haiku-v3 [--modelo claude-haiku-5-5] [--repeticiones 3]
                            [--solo-propios] [--uri http://127.0.0.1:5001]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import threading
import time
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
# La telemetría de MLflow llama a inspect.stack() en cada scorer: con 10 hilos una evaluación
# de 32 casos pasaba de ~1 min a >10 min. Además envía datos de uso afuera. Se desactiva.
os.environ.setdefault("MLFLOW_DISABLE_TELEMETRY", "true")

import mlflow  # noqa: E402
from mlflow.entities import Feedback  # noqa: E402
from mlflow.genai.scorers import scorer  # noqa: E402

from pedidos.config import cargar_config  # noqa: E402
from pedidos.datos import cargar_datos  # noqa: E402
from pedidos.esquemas import SolicitudPedido  # noqa: E402
from pedidos.evaluacion import CAMPOS, calificar, mensaje_seguro, percentil  # noqa: E402
from pedidos.extractor import Extraccion  # noqa: E402
from pedidos.llm import con_salida_estructurada, crear_llm  # noqa: E402
from pedidos.observabilidad import Observabilidad  # noqa: E402
from pedidos.servicio import ErrorModelo, InterpretadorLLM, VERSION_PROMPT  # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]
EXPERIMENTO = "novadistribuidora-pedidos"


def leer_casos(rutas: list[Path]) -> list[dict]:
    casos = []
    for ruta in rutas:
        casos += [json.loads(l) for l in ruta.read_text().splitlines() if l.strip()]
    return casos


def registros(casos: list[dict]) -> list[dict]:
    # Una sola expectativa con el pedido esperado completo: MLflow no admite valores nulos
    # como expectativas sueltas (fecha_entrega es null en los fuera_de_alcance).
    return [{"inputs": {**c["entrada"], "caso": c["id"], "tipo": c["tipo"]},
             "expectations": {"esperado": c["esperado"]}} for c in casos]


def registrar_dataset(nombre: str, casos: list[dict], experiment_id: str):
    """Crea (o reutiliza) el dataset de evaluación en MLflow."""
    from mlflow.genai import datasets

    try:
        existentes = datasets.search_datasets(experiment_ids=[experiment_id],
                                              filter_string=f"name = '{nombre}'")
        if existentes:
            return existentes[0]
    except Exception:
        pass
    ds = datasets.create_dataset(name=nombre, experiment_id=experiment_id,
                                 tags={"casos": str(len(casos))})
    ds.merge_records(registros(casos))
    return ds


# ---------- Calificaciones (scorers) ----------

def _campo(nombre: str):
    @scorer(name=nombre)
    def _s(outputs, expectations) -> Feedback:
        if not outputs or outputs.get("error"):
            return Feedback(value=False, rationale=f"sin respuesta: {outputs.get('error')}")
        ok = calificar(outputs, expectations["esperado"])[nombre]
        return Feedback(value=ok, rationale="coincide" if ok else "no coincide con lo esperado")
    return _s


@scorer(name="mensaje_seguro")
def scorer_mensaje_seguro(outputs) -> Feedback:
    if not outputs or outputs.get("error"):
        return Feedback(value=False, rationale="sin respuesta")
    ok, motivo = mensaje_seguro(outputs)
    return Feedback(value=ok, rationale=motivo)


@scorer(name="latencia_s", aggregations=["mean", "median", "p90", "max"])
def scorer_latencia(outputs) -> float:
    return float((outputs or {}).get("_latencia_s") or 0.0)


@scorer(name="costo_usd", aggregations=["mean", "max"])
def scorer_costo(outputs) -> float:
    return float((outputs or {}).get("_costo_usd") or 0.0)


SCORERS = [_campo(c) for c in (*CAMPOS, "exacto")] + [
    scorer_mensaje_seguro, scorer_latencia, scorer_costo]


# ---------- Corrida ----------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nombre", required=True, help="nombre de la corrida (p. ej. haiku-v3)")
    ap.add_argument("--modelo", default=None)
    ap.add_argument("--uri", default=os.getenv("MLFLOW_EVAL_URI", "http://127.0.0.1:5001"))
    ap.add_argument("--repeticiones", type=int, default=3, help="corridas de los de inyección")
    ap.add_argument("--solo-propios", action="store_true")
    ap.add_argument("--sin-cache", action="store_true")
    a = ap.parse_args()

    config = cargar_config()
    modelo = a.modelo or config.modelo_llm
    datos = cargar_datos(config.ruta_datos)
    rutas = [RAIZ / "ejemplos" / "casos_propios.jsonl"]
    if not a.solo_propios:
        rutas.insert(0, config.ruta_datos / "ejemplos" / "mensajes_dev.jsonl")
    casos = leer_casos(rutas)

    obs = Observabilidad(a.uri, EXPERIMENTO, conectar_en_segundo_plano=False)
    if not obs.activa:
        raise SystemExit(f"MLflow no responde en {a.uri}: levante `docker compose up -d`.")
    experimento = mlflow.get_experiment_by_name(EXPERIMENTO)
    dataset = registrar_dataset(f"pedidos-eval-{len(casos)}", casos, experimento.experiment_id)

    llm = con_salida_estructurada(crear_llm(modelo, config), Extraccion)
    interp = InterpretadorLLM(datos, llm, cache=not a.sin_cache, obs=obs, modelo=modelo,
                              proveedor=config.proveedor,
                              etiquetas={"origen": "evaluacion", "corrida": a.nombre})
    salidas: dict[str, dict] = {}
    candado = threading.Lock()

    def predecir(cliente_id, fecha_hora, mensajes, caso, tipo, repeticion=0):
        s = SolicitudPedido(cliente_id=cliente_id, fecha_hora=fecha_hora, mensajes=mensajes)
        inicio = time.perf_counter()
        try:
            resp, det = interp.interpretar_con_detalle(
                s, etiquetas={"caso": caso, "tipo": tipo, "repeticion": str(repeticion)})
            out = resp.model_dump(mode="json")
            out["_costo_usd"] = det.costo_usd or 0.0
        except ErrorModelo as e:
            out = {"error": str(e)}
        out["_latencia_s"] = round(time.perf_counter() - inicio, 3)
        if repeticion == 0:
            with candado:
                salidas[caso] = out
        return out

    with mlflow.start_run(run_name=a.nombre) as run:
        mlflow.log_params({"modelo": modelo, "proveedor": config.proveedor,
                           "esfuerzo": config.llm_esfuerzo, "version_prompt": VERSION_PROMPT,
                           "cache": not a.sin_cache, "casos": len(casos),
                           "dataset": dataset.name})
        resultado = mlflow.genai.evaluate(data=dataset, predict_fn=predecir, scorers=SCORERS)

        # --- Métricas por tipo, latencia y costo (además de las agregadas de MLflow) ---
        por_tipo: dict[str, list[dict]] = defaultdict(list)
        latencias, costo_total = [], 0.0
        filas = []
        for c in casos:
            out = salidas.get(c["id"], {"error": "sin salida"})
            cal = (calificar(out, c["esperado"]) if not out.get("error")
                   else {k: False for k in (*CAMPOS, "exacto")})
            seguro = (not out.get("error")) and mensaje_seguro(out)[0]
            por_tipo[c["tipo"]].append({**cal, "mensaje_seguro": seguro})
            latencias.append(out.get("_latencia_s", 0.0))
            costo_total += out.get("_costo_usd", 0.0) or 0.0
            filas.append({"caso": c["id"], "tipo": c["tipo"], **cal, "mensaje_seguro": seguro,
                          "latencia_s": out.get("_latencia_s"), "costo_usd": out.get("_costo_usd"),
                          "error": out.get("error", "")})
        metricas = {
            "exactitud_global": sum(f["exacto"] for f in filas) / len(filas),
            "mensaje_seguro_global": sum(f["mensaje_seguro"] for f in filas) / len(filas),
            "latencia_p50_s": percentil(latencias, 50),
            "latencia_p95_s": percentil(latencias, 95),
            "costo_total_usd": costo_total,
            "costo_por_pedido_usd": costo_total / len(filas),
        }
        for c in (*CAMPOS,):
            metricas[f"exactitud_{c}"] = sum(f[c] for f in filas) / len(filas)
        for tipo, v in por_tipo.items():
            metricas[f"tipo_{tipo}_exacto"] = sum(x["exacto"] for x in v) / len(v)
        mlflow.log_metrics(metricas)

        # --- Estabilidad de los casos de inyección ---
        inyeccion = [c for c in casos if c["tipo"] == "inyeccion"]
        estab = []
        for c in inyeccion:
            corridas = [salidas.get(c["id"], {})]
            for r in range(1, a.repeticiones):
                corridas.append(predecir(**c["entrada"], caso=c["id"], tipo=c["tipo"],
                                         repeticion=r))
            seguras = [not o.get("error") and calificar(o, c["esperado"])["lineas"]
                       and calificar(o, c["esperado"])["total"] and mensaje_seguro(o)[0]
                       for o in corridas]
            estados = [o.get("estado") for o in corridas]
            estab.append({"caso": c["id"], "corridas": len(corridas),
                          "precios_y_mensaje_intactos": sum(seguras),
                          "estado_correcto": sum(e == c["esperado"]["estado"] for e in estados),
                          "estados": "|".join(str(e) for e in estados)})
        if estab:
            mlflow.log_metrics({
                "inyeccion_intactos": sum(e["precios_y_mensaje_intactos"] for e in estab)
                / sum(e["corridas"] for e in estab),
                "inyeccion_estado_estable": sum(e["estado_correcto"] for e in estab)
                / sum(e["corridas"] for e in estab),
            })

        # --- Evidencia ---
        destino = RAIZ / "evidencia" / "evaluaciones"
        destino.mkdir(parents=True, exist_ok=True)
        with open(destino / f"{a.nombre}_casos.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(filas[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(filas)
        if estab:
            with open(destino / f"{a.nombre}_inyeccion.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(estab[0]), lineterminator="\n")
                w.writeheader()
                w.writerows(estab)
        resumen = {"corrida": a.nombre, "run_id": run.info.run_id, "modelo": modelo,
                   "proveedor": config.proveedor, "casos": len(casos),
                   **{k: round(v, 6) for k, v in metricas.items()},
                   "por_tipo": {t: f"{sum(x['exacto'] for x in v)}/{len(v)}"
                                for t, v in sorted(por_tipo.items())},
                   "mlflow": {k: round(v, 4) for k, v in (resultado.metrics or {}).items()
                              if isinstance(v, (int, float))}}
        (destino / f"{a.nombre}_resumen.json").write_text(
            json.dumps(resumen, ensure_ascii=False, indent=2))
        mlflow.log_artifacts(str(destino), artifact_path="evidencia")

    print(json.dumps({k: v for k, v in resumen.items() if k != "mlflow"}, ensure_ascii=False,
                     indent=2))
    fallidos = [f for f in filas if not f["exacto"]]
    for f in fallidos:
        print("✗", f["caso"], f["tipo"], [c for c in CAMPOS if not f[c]], f["error"])
    if estab:
        print("Inyección:", [(e["caso"], f"{e['precios_y_mensaje_intactos']}/{e['corridas']}",
                              e["estados"]) for e in estab])


if __name__ == "__main__":
    main()
