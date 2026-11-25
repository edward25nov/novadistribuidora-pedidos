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
- **MLflow sin configurar (`MLFLOW_TRACKING_URI` vacío) cuenta como `degradado`**: el enunciado
  exige trazas de cada solicitud, así que un servicio que no las está enviando no está "ok".
  En compose siempre está configurado.
- **Configuración inválida** (p. ej. `PROVEEDOR_LLM=openai`, `LLM_TIMEOUT_S=abc`): la app arranca
  igual, `/health` responde `degradado` con `config: …` y el `POST` responde 503. Así el contenedor
  no entra en un bucle de reinicios y el problema se ve en `/health`.
- **El 503 por falla del modelo tiene un mensaje fijo**; el detalle de la excepción (códigos e
  ids del proveedor) solo va al log.
- En compose la API **no** espera a que MLflow esté sano (`depends_on` sin condición): la API
  debe arrancar y responder aunque MLflow no esté. Verificado: con `docker compose stop mlflow`
  `/health` pasa a `degradado` (3 ms) y vuelve a `ok` al reiniciarlo.

## D8. Motor de reglas en código (fase 2): interpretación de `politicas.md`

Separación: `consolidacion.py` (§2 cantidades, §3 "lo de siempre") recibe menciones ya resueltas
a SKU; `reglas.py` (§4–§8) calcula líneas, total, crédito, fecha y estado. Todo con `Decimal`.
Donde la política deja margen, se decidió así (y se probó):

| Regla | Interpretación | Prueba |
|---|---|---|
| §2 repetidas | Se suman **antes** de convertir: se acumulan unidades sueltas por SKU y se convierte al final (12 + 12 latas de un fardo de 24 = 1 fardo). | `test_s2_se_suma_antes_de_convertir` |
| §2 conversión | Exacta y positiva, o pendiente `cantidad_no_convertible` (opciones = [sku]); nunca se redondea. Medio quintal tampoco. | `test_s2_conversion_*` |
| §2 corrección | Reemplaza toda la cantidad acumulada del SKU (incluida una no convertible). | `test_s2_correccion_*` |
| §3 habitual | Último pedido `entregado` por `fecha_entrega` (cancelados no cuentan), en el orden del historial. Sin ninguno → pendiente `producto_ambiguo` con texto de la mención y sin opciones: no se adivina. | `test_s3_*` |
| §4 sustituto | Se entrega el sustituto a **su** precio y con **su** escala. Sin cadenas: si el sustituto está agotado o no existe → `agotado_sin_sustituto` (texto = nombre del catálogo, como en los casos dev). Si el sustituto también se pidió directo, es una sola línea. | `test_s4_*` |
| §5 escala | Por **línea** (no acumulada por categoría), mayor % con `cantidad >= mínimo`. Subtotal redondeado a 2 decimales `ROUND_HALF_UP`; total = suma de subtotales redondeados. | `test_s5_*` |
| §6 crédito | `saldo + total > límite` (igual no excede). Líneas y total se devuelven igual. | `test_s6_*` |
| §7 fecha | Recibido `>= 14:00` cuenta como el día siguiente; entrega = primera visita **estrictamente posterior** a esa fecha. Hora local, sin conversión de zona. | `test_s7_*` |
| §8 estado | `fuera_de_alcance` solo si no hay líneas **ni** pendientes. Con solo pendientes → `requiere_revision` (con fecha de entrega calculada). Si el cliente quita todo lo que pidió, también `fuera_de_alcance`: el contrato exige un pendiente o crédito excedido para `requiere_revision`. | `test_s8_*` (incluye la propiedad confirmado ⇔ líneas y sin motivos) |
| SKU fuera del catálogo | Defensa en profundidad (la resolución de la fase 3 ya valida): en `consolidar` y en `calcular_pedido` se vuelve pendiente `producto_no_existe`, nunca un 500. Un SKU del historial que ya no se vende, también. | `test_sku_fuera_del_catalogo_*`, `test_s3_sku_historico_*` |

**Validación con los casos publicados** (`scripts/verificar_reglas_dev.py`, sin modelo):
- **`reglas.py` (§4–§8): 84/84.** Los ítems de cada caso se reconstruyen desde la respuesta
  esperada (sustituciones separadas en solicitado/entregado; agotados sin sustituto como ítem
  para que el motor los marque) y se comparan estado, líneas, total, fecha, sustituciones,
  pendientes (motivo y opciones) y motivos. **No** cubre `consolidacion.py`: los ítems ya llegan
  en unidades de venta. En 25 casos el día efectivo es de visita (prueba "estrictamente
  posterior" contra los datos); 28 están después del corte.
- **`consolidacion.py` + `reglas.py` (§2–§8): 8/8 casos `habitual`**, con las menciones escritas
  a mano a partir del mensaje ("lo de siempre" + agregados / exclusiones) y el historial real.
- La conversión de unidades, las correcciones y las cantidades por omisión con el texto real se
  verifican de punta a punta con el modelo en la fase 3.

**Validación de los datos al cargar:** columnas mínimas por tabla, `unidades_por_empaque >= 1`,
porcentajes y mínimos de la escala enteros no negativos, y días de visita conocidos; si no, `ErrorDatos` claro al arrancar (la API queda degradada).
