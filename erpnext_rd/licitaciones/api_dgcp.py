"""Cliente de la API de datos abiertos de la DGCP (Dirección General de Contrataciones Públicas).

Solo lectura y sin token. Límite: 60 consultas por minuto (cabeceras `x-ratelimit-*`). Los datos se
actualizan 4 veces al día (00:00, 07:00, 14:00 y 21:00, hora RD). Detalle en docs/PLAN.md, Fase 10.1.

Respuesta: {"hasError", "payload": {"content": [...] | null, "message"}, "page", "limit", "pages"}.
"""

import time

import requests

URL_API = "https://datosabiertos.dgcp.gob.do/api-dgcp/v1"
TIMEOUT = 60
REINTENTOS = 3
# Espera máxima cuando se agota el límite por minuto
ESPERA_MAXIMA = 65
LIMITE_PAGINA = 1000
ENCABEZADOS = {"User-Agent": "ERPNext-RD", "Accept": "application/json"}


class ErrorAPIDGCP(Exception):
	pass


def _espera(respuesta) -> int:
	try:
		segundos = int(respuesta.headers.get("x-ratelimit-reset") or ESPERA_MAXIMA)
	except ValueError:
		segundos = ESPERA_MAXIMA
	return max(1, min(segundos, ESPERA_MAXIMA))


def consultar(ruta: str, **parametros) -> list[dict]:
	"""Una página de `ruta` (por ejemplo "proveedores"). Sin resultados, devuelve []."""
	for _intento in range(REINTENTOS):
		respuesta = requests.get(f"{URL_API}/{ruta}", params=parametros, timeout=TIMEOUT, headers=ENCABEZADOS)
		if respuesta.status_code == 429:
			time.sleep(_espera(respuesta))
			continue
		datos = respuesta.json() if respuesta.content else {}
		payload = datos.get("payload") or {}
		if respuesta.status_code >= 400 or datos.get("hasError"):
			raise ErrorAPIDGCP(payload.get("message") or f"HTTP {respuesta.status_code}")
		# Última consulta del minuto: esperar antes de la siguiente
		if respuesta.headers.get("x-ratelimit-remaining") == "0":
			time.sleep(_espera(respuesta))
		return payload.get("content") or []
	raise ErrorAPIDGCP("La API de la DGCP no respondió: límite de consultas agotado")


def todas(ruta: str, limite: int = LIMITE_PAGINA, maximo_paginas: int = 50, **parametros) -> list[dict]:
	"""Todas las páginas de `ruta`, hasta `maximo_paginas`."""
	filas = []
	for pagina in range(1, maximo_paginas + 1):
		contenido = consultar(ruta, page=pagina, limit=limite, **parametros)
		filas += contenido
		if len(contenido) < limite:
			break
	return filas


def proveedor(numero_documento: str) -> dict | None:
	"""El proveedor del RPE con ese RNC o cédula (solo dígitos), o None si no está inscrito."""
	filas = consultar("proveedores", numero_documento=numero_documento)
	return filas[0] if filas else None


def rubros(rpe: int | str) -> list[dict]:
	"""Familias UNSPSC registradas del proveedor: [{"familia_unspsc", "descripcion"}]."""
	return todas("proveedores/rubro", rpe=rpe)
