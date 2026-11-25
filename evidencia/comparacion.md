# Comparación de alternativas

Generado por `scripts/comparar.py` a partir de `evidencia/evaluaciones/`. Cada corrida evalúa 116 casos (84 publicados + 32 propios). Valores: media de las corridas (mín–máx).

| Alternativa | Corridas | Exactos | Estado | Líneas | Total | Pendientes | Mensaje seguro | Inyección intacta | Latencia p50 (s) | Latencia p95 (s) | US$ por 1000 pedidos |
|---|---|---|---|---|---|---|---|---|---|---|---|
| haiku-low | 2 | 99.6 % (99.1–100.0) | 100.0 % | 100.0 % | 100.0 % | 99.6 % (99.1–100.0) | 100.0 % | 100.0 % | 1.31 (1.30–1.31) | 2.19 (2.15–2.22) | 0.133 (0.131–0.134) |
| haiku-medium | 2 | 98.7 % (98.3–99.1) | 100.0 % | 100.0 % | 100.0 % | 98.7 % (98.3–99.1) | 100.0 % | 100.0 % | 1.68 (1.52–1.84) | 2.87 (2.66–3.08) | 0.155 (0.154–0.157) |
| haiku-sin-cache | 2 | 98.7 % (98.3–99.1) | 100.0 % | 100.0 % | 100.0 % | 98.7 % (98.3–99.1) | 100.0 % | 100.0 % | 1.30 (1.27–1.34) | 2.12 (2.02–2.22) | 0.573 (0.572–0.573) |
| sonnet-low | 2 | 99.1 % | 100.0 % | 100.0 % | 100.0 % | 99.1 % | 100.0 % | 100.0 % | 1.82 (1.78–1.86) | 2.69 (2.66–2.71) | 2.127 (2.126–2.129) |

## Detalle por corrida

- `haiku-low-r1` (run `a40a8525`, claude-haiku-5-5, esfuerzo low, caché True): tipos con fallos: ninguno
- `haiku-low-r2` (run `4f6e082e`, claude-haiku-5-5, esfuerzo low, caché True): tipos con fallos: docenas 2/3
- `haiku-medium-r1` (run `4563af15`, claude-haiku-5-5, esfuerzo medium, caché True): tipos con fallos: ambiguo 7/8
- `haiku-medium-r2` (run `ead7a116`, claude-haiku-5-5, esfuerzo medium, caché True): tipos con fallos: ambiguo 7/8, docenas 2/3
- `haiku-sin-cache-r1` (run `5e51a53c`, claude-haiku-5-5, esfuerzo low, caché False): tipos con fallos: docenas 2/3
- `haiku-sin-cache-r2` (run `41b693d5`, claude-haiku-5-5, esfuerzo low, caché False): tipos con fallos: audio 2/3, docenas 2/3
- `sonnet-low-r1` (run `299bf1a5`, claude-sonnet-5-5, esfuerzo low, caché True): tipos con fallos: ambiguo 7/8
- `sonnet-low-r2` (run `6870e160`, claude-sonnet-5-5, esfuerzo low, caché True): tipos con fallos: ambiguo 7/8
