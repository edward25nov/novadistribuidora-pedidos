"""Compara las corridas de evaluación (calidad, latencia y costo) y escribe la evidencia.

Lee evidencia/evaluaciones/<corrida>_resumen.json. Las corridas repetidas de una misma
alternativa se nombran <alternativa>-r1, <alternativa>-r2… y se agregan (media, mín, máx).

Uso: python scripts/comparar.py [alternativa ...]
Salida: evidencia/comparacion.md y evidencia/comparacion.csv
"""

from __future__ import annotations

import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ORIGEN = RAIZ / "evidencia" / "evaluaciones"

METRICAS = [
    ("exactitud_global", "Exactos", "pct"),
    ("exactitud_estado", "Estado", "pct"),
    ("exactitud_lineas", "Líneas", "pct"),
    ("exactitud_total", "Total", "pct"),
    ("exactitud_pendientes", "Pendientes", "pct"),
    ("mensaje_seguro_global", "Mensaje seguro", "pct"),
    ("inyeccion_intactos", "Inyección intacta", "pct"),
    ("latencia_p50_s", "Latencia p50 (s)", "s"),
    ("latencia_p95_s", "Latencia p95 (s)", "s"),
    ("costo_por_pedido_usd", "US$ por 1000 pedidos", "mil"),
]


def cargar() -> dict[str, list[dict]]:
    grupos: dict[str, list[dict]] = defaultdict(list)
    for f in sorted(ORIGEN.glob("*_resumen.json")):
        r = json.loads(f.read_text())
        alternativa = re.sub(r"-r\d+$", "", r["corrida"])
        grupos[alternativa].append(r)
    return grupos


def fmt(valores: list[float], tipo: str) -> str:
    if tipo == "mil":
        valores = [v * 1000 for v in valores]
    media = statistics.mean(valores)
    if tipo == "pct":
        base = f"{media * 100:.1f} %"
        rango = f"{min(valores) * 100:.1f}–{max(valores) * 100:.1f}"
    else:
        dec = 3 if tipo == "mil" else 2
        base = f"{media:.{dec}f}"
        rango = f"{min(valores):.{dec}f}–{max(valores):.{dec}f}"
    return base if len(valores) == 1 or min(valores) == max(valores) else f"{base} ({rango})"


def main() -> None:
    grupos = cargar()
    if len(sys.argv) > 1:
        grupos = {k: v for k, v in grupos.items() if k in sys.argv[1:]}
    filas_csv = []
    encabezado = ["Alternativa", "Corridas", *[m[1] for m in METRICAS]]
    lineas = ["| " + " | ".join(encabezado) + " |", "|" + "---|" * len(encabezado)]
    for alt, corridas in grupos.items():
        celdas = [alt, str(len(corridas))]
        fila = {"alternativa": alt, "corridas": len(corridas),
                "modelo": corridas[0]["modelo"], "esfuerzo": corridas[0].get("esfuerzo"),
                "cache": corridas[0].get("cache"), "casos": corridas[0]["casos"],
                "dataset": corridas[0].get("dataset")}
        for clave, _, tipo in METRICAS:
            valores = [c[clave] for c in corridas if clave in c]
            celdas.append(fmt(valores, tipo) if valores else "—")
            fila[clave] = statistics.mean(valores) if valores else None
        lineas.append("| " + " | ".join(celdas) + " |")
        filas_csv.append(fila)
    tabla = "\n".join(lineas)
    detalle = []
    for alt, corridas in grupos.items():
        for c in corridas:
            fallos = [t for t, v in c["por_tipo"].items() if v.split("/")[0] != v.split("/")[1]]
            detalle.append(f"- `{c['corrida']}` (run `{c['run_id'][:8]}`, {c['modelo']}, "
                           f"esfuerzo {c.get('esfuerzo')}, caché {c.get('cache')}): tipos con "
                           f"fallos: {', '.join(f'{t} {c['por_tipo'][t]}' for t in fallos) or 'ninguno'}")
    md = (f"# Comparación de alternativas\n\nGenerado por `scripts/comparar.py` a partir de "
          f"`evidencia/evaluaciones/`. Cada corrida evalúa {filas_csv[0]['casos']} casos "
          f"(84 publicados + 32 propios). Valores: media de las corridas (mín–máx).\n\n"
          f"{tabla}\n\n## Detalle por corrida\n\n" + "\n".join(detalle) + "\n")
    (RAIZ / "evidencia" / "comparacion.md").write_text(md)
    with open(RAIZ / "evidencia" / "comparacion.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(filas_csv[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(filas_csv)
    print(md)


if __name__ == "__main__":
    main()
