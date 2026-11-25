# Decisiones

Cada decisión registra sus alternativas y su justificación. Las que dependen de mediciones se
actualizan con los números de la evaluación (fase 6).

## D1. Proveedor del modelo: Anthropic directo, con OpenRouter seleccionable

- **Contexto:** el enunciado pide OpenRouter; en el curso trabajamos con la API de Anthropic
  (clase 6). El equipo docente evaluará con **su** clave de OpenRouter y el modelo de `.env.example`.
- **Alternativas:** (a) solo OpenRouter; (b) solo Anthropic; (c) proveedor por variable.
- **Decisión:** (c). `PROVEEDOR_LLM=anthropic|openrouter|auto` en `.env`; con `auto` se usa
  Anthropic si `ANTHROPIC_API_KEY` tiene valor y, si no, OpenRouter. Una sola fábrica
  (`crear_llm` en `src/pedidos/llm.py`): `ChatAnthropic` o `ChatOpenAI` con
  `base_url=https://openrouter.ai/api/v1`.
- **Por qué:** desarrollamos y medimos con Anthropic, pero el docente no queda bloqueado: con
  solo poner su clave de OpenRouter en el `.env` copiado de `.env.example`, funciona. El mismo
  modelo (Claude Haiku 5.5) se usa en los dos proveedores, así que la calidad medida se mantiene.
- **Id del modelo:** `MODELO_LLM` usa el id de Anthropic (`claude-haiku-5-5`); para OpenRouter
  se traduce a `anthropic/claude-haiku-5.5` (ids verificados en `GET /api/v1/models` de
  OpenRouter el 2026-11-25). Un id con `/` se pasa tal cual.
- **Pendiente:** smoke test manual por proveedor, documentado en el README (fase 7).

## D2. Datos del GES fuera del repositorio, en `ges/`

- **Decisión:** el zip del GES se descomprime tal cual en `ges/` (ignorada por `.gitignore` y
  `.dockerignore`); la ruta se configura con `RUTA_DATOS` y en Docker se monta como volumen de
  solo lectura. Los casos de evaluación propios sí se versionan, en `ejemplos/`.
- **Por qué:** el enunciado prohíbe datos y credenciales en el repo y en las imágenes; descomprimir
  sin reorganizar evita errores del equipo docente al colocar los archivos.

## D3. Arquitectura: una cadena con una sola llamada al modelo (no agente)

- **Alternativas:** (a) agente con herramientas (buscar producto, calcular precio…);
  (b) cadena: extracción estructurada + motor de reglas en código.
- **Decisión:** (b). El LLM solo extrae menciones (texto, candidatos, cantidad, unidad) con
  salida estructurada; precios, descuentos, crédito y fechas los calcula código con pruebas.
- **Por qué:** la latencia se evalúa (una llamada frente a varias vueltas de agente); los
  cálculos deben ser exactos y reproducibles; y un mensaje no puede influir en un número que el
  modelo nunca produce (defensa ante inyección). Se medirá en la fase 6.

## D4. Límites de la llamada al modelo y comportamiento ante fallos

- **Límites:** `LLM_TIMEOUT_S=15`, `LLM_MAX_RETRIES=1` (peor caso ≈ 30 s) y `LLM_ESFUERZO=low`.
  Medición inicial (1 llamada de prueba, Anthropic, 2026-11-25): Haiku 5.5 2,7 s y Sonnet 5.5
  1,5 s para una extracción corta. Se recalibran con el p95 de la fase 6.
- **Alternativas ante un fallo del modelo** (timeout, 429/5xx, salida que no valida):
  (a) 500; (b) `requiere_revision` sin líneas; (c) **503 con mensaje claro**.
- **Decisión:** (c). Un 503 dice la verdad ("no pude interpretar"); (b) se confundiría con un
  pedido realmente vacío y la bodega podría tratarlo como interpretado. Nunca se inventa un pedido.
  Cualquier otra excepción se responde 500 con un mensaje genérico y queda en el log.
- **Sin `temperature`:** Haiku 5.5 y Sonnet 5.5 responden 400 a valores distintos del
  predeterminado (documentación de la API de Claude); se controla el gasto con el esfuerzo.

## D5. Salida estructurada con `json_schema` (no `function_calling`)

- **Contexto:** `with_structured_output` de LangChain usa por defecto `function_calling`, que
  fuerza `tool_choice`; Claude Sonnet 5.5 rechaza el `tool_choice` forzado con 400.
- **Decisión:** `method="json_schema"` (salida estructurada nativa) para ambos proveedores, con
  `include_raw=True` para obtener el uso de tokens (costo) y el error de parseo sin excepción.
- **Verificado** con la API de Anthropic con Haiku 5.5 y Sonnet 5.5 (2026-11-25).
- **Pendiente:** verificarlo por OpenRouter con una clave de OpenRouter (smoke test, fase 3);
  si OpenRouter no lo soporta para Claude, el método pasará a depender del proveedor.

## D6. Validación de la solicitud (422) y orden 422 → 404

- `mensajes`: entre 1 y 20, ninguno vacío o solo con espacios, máx. 2000 caracteres cada uno
  (limita costo y superficie de inyección; un pedido real de WhatsApp es mucho más corto).
- `fecha_hora`: exactamente `AAAA-MM-DDTHH:MM` y fecha real; hora local de Guatemala, sin
  conversión de zona. Campos extra se ignoran.
- Los errores se devuelven con `detail` en español y la lista `errores` (`campo`, `motivo`).
- Se valida primero (422) y luego se busca el cliente (404): un cuerpo inválido con un cliente
  inexistente es 422.

## D7. `/health` y MLflow

- `GET /health` revisa datos, clave del modelo y MLflow (`GET /health` de MLflow con timeout
  de 1 s y resultado en caché 5 s, para que un MLflow caído no vuelva lento al servicio).
  Responde siempre 200: `ok`, o `degradado` con `motivo`.
- En compose la API **no** espera a que MLflow esté sano (`depends_on` sin condición): la API
  debe arrancar y responder aunque MLflow no esté. Verificado: con `docker compose stop mlflow`
  `/health` pasa a `degradado` (3 ms) y vuelve a `ok` al reiniciarlo.
