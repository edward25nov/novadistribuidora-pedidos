# Toma de pedidos por WhatsApp · NovaDistribuidora (Lab 3)

## Producto
Convierte los mensajes informales que un tendero envía por WhatsApp en un pedido estructurado
(líneas, total, fecha de entrega), aplica las reglas de `ges/politicas.md`, marca los casos que
requieren revisión humana y redacta la confirmación para el cliente. El contrato de la API está
en el Anexo del enunciado (`POST /v1/pedidos/interpretar`, `GET /health`, puerto 8000).

## Arquitectura (no cambiarla sin registrarlo en DECISIONES.md)
- El LLM **solo extrae** (salida estructurada Pydantic): menciones de producto, cantidad y unidad
  tal como se escribieron, y si hay o no un pedido. Una sola llamada por solicitud.
- Todo lo que tiene números lo calcula **código Python probado**: resolución de SKU contra el
  catálogo, conversión de unidades, agotados/sustitutos, descuentos por escala, subtotales y total
  (con `Decimal`, redondeo mitad hacia arriba), crédito, hora de corte y fecha de entrega.
- Lo que devuelve el modelo se valida siempre en código: un SKU que no esté en el catálogo nunca
  entra en `lineas`. Ante la duda, se registra un pendiente; no se adivina.
- Ningún mensaje puede cambiar precios, descuentos, crédito ni el comportamiento del asistente.

## Stack
- Python 3.12+, LangChain 1.x, FastAPI, MLflow 3, pandas, pytest. Código en `src/pedidos/`.
- El modelo se crea solo en `src/pedidos/llm.py` (`crear_llm`). Proveedor por `.env`
  (`PROVEEDOR_LLM=anthropic|openrouter|auto`). Sin `temperature`.
- MLflow en el puerto **5001** del host (en macOS el 5000 lo ocupa AirPlay); API en el 8000.

## Reglas
- `.env` y los datos del GES (`ges/`) nunca van a Git ni a la imagen de Docker.
- Las pruebas no llaman al LLM ni usan los datos del GES (interpretador falso y datos sintéticos
  en `tests/conftest.py`). Dependencias de desarrollo en `requirements-dev.txt`.
- Levantar: `docker compose up -d --build`; pruebas: `.venv/bin/python -m pytest`.
- Decisiones nuevas → `DECISIONES.md` (alternativas, justificación, números medidos).
- Commits cortos, Conventional Commits en español, sin `Co-Authored-By`. Una rama y un PR por fase.
