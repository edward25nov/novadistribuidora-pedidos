# NovaDistribuidora · Toma de pedidos por WhatsApp

Aplicación con LLMs (LangChain + FastAPI + MLflow + Docker) que convierte mensajes informales
de WhatsApp en pedidos estructurados y verificables. Laboratorio 3 de Product Development.

> En construcción: este README se completa fase a fase.

## 1. Datos del GES

Los datos no forman parte del repositorio ni de la imagen de Docker. Descomprima el archivo
publicado en el GES (cualquiera que sea su nombre) en la carpeta `ges/` de la raíz del repositorio,
de modo que queden así:

```
ges/
├── datos/            productos, sinonimos, precios_escala, clientes, historial_pedidos (.parquet)
├── ejemplos/         mensajes_dev.jsonl
├── politicas.md
└── catalogo_problemas.md
```

```bash
unzip <archivo-del-GES>.zip -d ges
ls ges/datos          # debe listar los 5 .parquet
```

Si el zip trae una carpeta raíz propia (p. ej. `lab3/datos/...`), mueva su contenido a `ges/`.
Si faltan archivos, la API arranca igual, `GET /health` responde `degradado` con la ruta que
buscó y `POST /v1/pedidos/interpretar` responde 503 explicando qué falta.

## 2. Credenciales

```bash
cp .env.example .env
```

Ponga **una** de las dos claves en `.env`:

| Clave | Proveedor que se usa (con `PROVEEDOR_LLM=auto`) |
|---|---|
| `OPENROUTER_API_KEY` | OpenRouter, modelo `anthropic/claude-haiku-5.5` |
| `ANTHROPIC_API_KEY` | API de Anthropic, modelo `claude-haiku-5-5` |

El modelo es `MODELO_LLM` (`claude-haiku-5-5`); con OpenRouter el id se traduce solo y se
prefiere el proveedor Anthropic dentro de OpenRouter (para aprovechar la caché de prompt).
Ambos caminos están probados con los casos publicados (84/84 por Anthropic y por OpenRouter).
`.env` está en `.gitignore` y en `.dockerignore`: nunca se versiona ni entra en la imagen.

## 3. Levantar el producto

```bash
docker compose up -d --build
curl localhost:8000/health        # {"estado":"ok",...}
```

| Servicio | URL |
|---|---|
| API | http://localhost:8000 (documentación interactiva en `/docs`) |
| MLflow | http://localhost:5001 (en macOS el 5000 lo ocupa AirPlay) |

Cada solicitud deja una traza en MLflow (experimento `novadistribuidora-pedidos`) con los
pasos `extraer` (modelo, tokens, costo), `reglas` y `confirmacion`, y etiquetas para filtrar
por `cliente_id`, `estado`, `modelo` y `proveedor`.

Si MLflow no está disponible, la API sigue respondiendo (sin trazar esas solicitudes) y
`GET /health` devuelve `{"estado": "degradado", "motivo": "mlflow: no disponible (...)"}`.
Cuando MLflow vuelve, la API reconecta sola.

Ejemplo:

```bash
curl -s -X POST localhost:8000/v1/pedidos/interpretar \
  -H 'content-type: application/json' \
  -d '{"cliente_id":"C001","fecha_hora":"2026-11-23T15:20",
       "mensajes":["Buenas, mándeme 2 fardos de kola 600, una caja de aceite","y 48 latas de energía max"]}'
```

Códigos: 200 pedido interpretado · 404 cliente inexistente · 422 solicitud inválida (con el
motivo en español) · 503 modelo o datos no disponibles (nunca se inventa un pedido).

## 4. Desarrollo local y pruebas

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt && .venv/bin/pip install -e .
.venv/bin/python -m pytest        # no llama al modelo ni necesita los datos del GES
```

Para verificar el motor de reglas contra los casos publicados (sin modelo):

```bash
.venv/bin/python scripts/verificar_reglas_dev.py ges     # 84/84 casos reproducidos
```

Para correr los casos de punta a punta con el modelo real (exactitud por campo y por tipo,
latencia p50/p95, tokens):

```bash
.venv/bin/python scripts/evaluar_dev.py --salida salidas/dev.jsonl
```

Las pruebas corren también en GitHub Actions en cada PR (`.github/workflows/pruebas.yml`).
