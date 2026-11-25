# Imagen de la API. No contiene datos ni credenciales (ver .dockerignore):
# los datos del GES se montan en /datos y la clave llega por variables de entorno.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pyproject.toml .
COPY src ./src
COPY configs ./configs
RUN pip install --no-deps .

RUN useradd --create-home app
USER app

ENV RUTA_DATOS=/datos RUTA_PRECIOS=/app/configs/precios.yaml
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"
CMD ["uvicorn", "pedidos.api:app_desde_entorno", "--factory", "--host", "0.0.0.0", "--port", "8000"]
