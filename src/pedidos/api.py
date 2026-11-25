"""API de FastAPI: contrato del Anexo (POST /v1/pedidos/interpretar, GET /health)."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from pedidos.config import ErrorConfiguracion, cargar_config
from pedidos.datos import Datos, ErrorDatos, cargar_datos
from pedidos.esquemas import RespuestaPedido, Salud, SolicitudPedido
from pedidos.salud import VerificadorMlflow
from pedidos.servicio import ErrorModelo, Interpretador, InterpretadorPendiente

log = logging.getLogger("pedidos.api")

def _motivo_en_espanol(error: dict) -> tuple[str, str]:
    """Traduce un error de validación de Pydantic a (campo, motivo) legibles."""
    loc = [str(p) for p in error.get("loc", ()) if p != "body"]
    campo = ".".join(loc) or "cuerpo"
    tipo = error.get("type", "")
    raiz = loc[0] if loc else ""
    ctx = error.get("ctx") or {}
    if tipo == "missing":
        return campo, f"falta el campo obligatorio {campo}"
    if tipo == "json_invalid":
        return "cuerpo", "el cuerpo de la solicitud no es JSON válido"
    if tipo in ("model_attributes_type", "dict_type"):
        return "cuerpo", "el cuerpo de la solicitud debe ser un objeto JSON"
    if raiz == "mensajes" and tipo == "too_short":
        return campo, "mensajes no puede estar vacío: envíe al menos un mensaje"
    if raiz == "mensajes" and tipo == "too_long":
        return campo, f"mensajes admite como máximo {ctx.get('max_length')} mensajes"
    if tipo == "string_too_short":
        return campo, f"{campo} no puede estar vacío"
    if tipo == "string_too_long":
        return campo, f"{campo} admite como máximo {ctx.get('max_length')} caracteres"
    if tipo == "string_type":
        return campo, f"{campo} debe ser texto"
    if tipo == "list_type":
        return campo, f"{campo} debe ser una lista de textos"
    if tipo == "value_error":
        return raiz or campo, str(error.get("msg", "")).removeprefix("Value error, ")
    return campo, str(error.get("msg", "valor inválido"))


def crear_app(
    datos: Datos | None = None,
    interpretador: Interpretador | None = None,
    verificador_mlflow: VerificadorMlflow | None = None,
    falta_api_key: str | None = None,
) -> FastAPI:
    """Crea la app. Sin argumentos lee .env y RUTA_DATOS; las pruebas inyectan todo."""
    error_datos: str | None = None
    if datos is None and interpretador is None:
        config = cargar_config()
        try:
            datos = cargar_datos(config.ruta_datos)
        except ErrorDatos as e:
            error_datos = str(e)
            log.error(error_datos)
        verificador_mlflow = verificador_mlflow or VerificadorMlflow(config.mlflow_tracking_uri)
        if not config.api_key:
            falta_api_key = f"falta {config.variable_api_key}"
        interpretador = InterpretadorPendiente()

    verificador_mlflow = verificador_mlflow or VerificadorMlflow("")
    interpretador = interpretador or InterpretadorPendiente()

    app = FastAPI(title="NovaDistribuidora · pedidos por WhatsApp", version="0.1.0")

    @app.exception_handler(RequestValidationError)
    async def _validacion(_: Request, exc: RequestValidationError) -> JSONResponse:
        errores = [dict(zip(("campo", "motivo"), _motivo_en_espanol(e))) for e in exc.errors()]
        detalle = "; ".join(e["motivo"] for e in errores)
        return JSONResponse(
            status_code=422,
            content={"detail": f"Solicitud inválida: {detalle}", "errores": errores},
        )

    @app.exception_handler(Exception)
    async def _inesperado(_: Request, exc: Exception) -> JSONResponse:
        log.exception("Error no controlado")
        return JSONResponse(status_code=500, content={"detail": "Error interno del servicio."})

    @app.post("/v1/pedidos/interpretar", response_model=RespuestaPedido)
    def interpretar(solicitud: SolicitudPedido):
        if datos is None:
            return JSONResponse(
                status_code=503,
                content={"detail": f"Datos no disponibles: {error_datos}"},
            )
        if not datos.existe_cliente(solicitud.cliente_id):
            return JSONResponse(
                status_code=404,
                content={"detail": f"El cliente {solicitud.cliente_id} no existe."},
            )
        try:
            return interpretador.interpretar(solicitud)
        except (ErrorModelo, ErrorConfiguracion) as e:
            log.warning("Modelo no disponible: %s", e)
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "El modelo de lenguaje no está disponible en este momento; "
                    f"intente de nuevo. ({e})"
                },
            )

    @app.get("/health", response_model=Salud)
    def health():
        dependencias = {
            "datos": "ok" if datos is not None else "no cargados",
            "llm": falta_api_key or "ok",
            "mlflow": verificador_mlflow.estado(),
        }
        problemas = [f"{k}: {v}" for k, v in dependencias.items() if v not in ("ok",)]
        if problemas:
            return Salud(estado="degradado", motivo="; ".join(problemas), dependencias=dependencias)
        return Salud(estado="ok", dependencias=dependencias)

    return app


def app_desde_entorno() -> FastAPI:
    """Fábrica para uvicorn: `uvicorn pedidos.api:app_desde_entorno --factory`."""
    logging.basicConfig(level=logging.INFO)
    return crear_app()
