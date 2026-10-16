"""Validaciones de identificadores fiscales dominicanos (RNC, Cédula, NCF / e-NCF).

Funciones puras, sin dependencias de Frappe, para poder probarlas de forma aislada.
"""

import re

PESOS_RNC = (7, 9, 8, 6, 5, 4, 3, 2)

# Serie B (NCF tradicional): B + tipo (2) + secuencial (8) = 11 caracteres
# Serie E (e-NCF electrónico): E + tipo (2) + secuencial (10) = 13 caracteres
DIGITOS_SECUENCIAL = {"B": 8, "E": 10}

_NCF_RE = re.compile(r"^(?P<serie>[BE])(?P<tipo>\d{2})(?P<secuencial>\d+)$")


def limpiar_identificacion(valor: str | None) -> str:
	"""Quita guiones, espacios y cualquier caracter no numérico."""
	return re.sub(r"\D", "", valor or "")


def es_rnc_valido(rnc: str | None) -> bool:
	"""RNC de 9 dígitos con dígito verificador (módulo 11, pesos 7-9-8-6-5-4-3-2)."""
	rnc = limpiar_identificacion(rnc)
	if len(rnc) != 9:
		return False

	suma = sum(int(d) * p for d, p in zip(rnc[:8], PESOS_RNC, strict=False))
	resto = suma % 11
	if resto == 0:
		verificador = 2
	elif resto == 1:
		verificador = 1
	else:
		verificador = 11 - resto

	return verificador == int(rnc[8])


def es_cedula_valida(cedula: str | None) -> bool:
	"""Cédula de 11 dígitos con dígito verificador Luhn (pesos alternos 1-2)."""
	cedula = limpiar_identificacion(cedula)
	if len(cedula) != 11:
		return False

	suma = 0
	for i, d in enumerate(cedula[:10]):
		producto = int(d) * (1 if i % 2 == 0 else 2)
		suma += producto // 10 + producto % 10

	verificador = (10 - suma % 10) % 10
	return verificador == int(cedula[10])


def tipo_identificacion(valor: str | None) -> str | None:
	"""Devuelve "RNC", "Cédula" o None según la longitud del número limpio."""
	limpio = limpiar_identificacion(valor)
	if len(limpio) == 9:
		return "RNC"
	if len(limpio) == 11:
		return "Cédula"
	return None


def es_identificacion_valida(valor: str | None) -> bool:
	"""Valida un número que puede ser RNC o Cédula."""
	tipo = tipo_identificacion(valor)
	if tipo == "RNC":
		return es_rnc_valido(valor)
	if tipo == "Cédula":
		return es_cedula_valida(valor)
	return False


def formatear_ncf(serie: str, tipo: str, secuencial: int) -> str:
	"""Arma un NCF: formatear_ncf("B", "01", 5) -> "B0100000005"."""
	digitos = DIGITOS_SECUENCIAL[serie]
	if secuencial < 1 or len(str(secuencial)) > digitos:
		raise ValueError(f"Secuencial {secuencial} fuera de rango para serie {serie}")
	return f"{serie}{tipo}{secuencial:0{digitos}d}"


def parsear_ncf(ncf: str | None) -> dict | None:
	"""Descompone un NCF en serie, tipo y secuencial. None si el formato es inválido."""
	ncf = (ncf or "").strip().upper()
	m = _NCF_RE.match(ncf)
	if not m:
		return None
	serie = m.group("serie")
	if len(m.group("secuencial")) != DIGITOS_SECUENCIAL[serie]:
		return None
	return {
		"serie": serie,
		"tipo": m.group("tipo"),
		"codigo": f"{serie}{m.group('tipo')}",
		"secuencial": int(m.group("secuencial")),
	}


def es_ncf_valido(ncf: str | None, codigo_tipo: str | None = None) -> bool:
	"""Formato de NCF válido y, opcionalmente, del tipo indicado (p. ej. "B01")."""
	datos = parsear_ncf(ncf)
	if not datos:
		return False
	return codigo_tipo is None or datos["codigo"] == codigo_tipo
