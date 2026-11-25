# Evidencia

## Comparación de alternativas
- `comparacion.md` / `comparacion.csv`: calidad, latencia y costo de 4 alternativas × 2 corridas
  (116 casos cada una). Generado por `scripts/comparar.py`. Decisión en `DECISIONES.md` (D15).
- `evaluaciones/`: por corrida, calificación de cada caso (`*_casos.csv`), estabilidad de los
  casos de inyección (`*_inyeccion.csv`) y resumen con métricas por tipo (`*_resumen.json`).
  `linea-base-f5/` es la primera corrida de la fase 5 (anterior al hash del dataset).

## Capturas (`capturas/`)
| Archivo | Qué muestra |
|---|---|
| `api-docs.png` | Documentación interactiva de la API (`/docs`): `POST /v1/pedidos/interpretar` y `GET /health` con sus esquemas. |
| `trazas-api.png` | Lista de trazas del experimento `novadistribuidora-pedidos` con duración, estado y etiquetas (`modelo`, `proveedor`, …). |
| `traza-4-spans.png` | Una traza con sus 4 spans: `interpretar_pedido` → `extraer` → `reglas` → `confirmacion` (mensaje al cliente). |
| `traza-respuesta.png` | Traza de evaluación: entradas, respuesta calculada, expectativa `esperado` y calificaciones (`total`, `mensaje_seguro`). |
| `dataset-evaluacion.png` | Dataset `pedidos-eval-116-6027d484` registrado en MLflow (116 registros con entradas y esperados). |
| `evaluacion-haiku-low-r1.png` | Corrida `haiku-low-r1` (configuración entregada): calificaciones por caso y agregadas. |
| `evaluacion-sonnet-low-r1.png` | Corrida `sonnet-low-r1` (alternativa comparada). |
| `comparacion-runs.png` | Las corridas de evaluación lado a lado con sus métricas (exactitud por campo, costo, latencia). |
| `evaluacion-haiku-5-5-linea-base.png` | Primera corrida de la fase 5 (línea base). |

Las capturas se recortaron para quitar la barra del navegador.
