"""A quién aplica la app: a las empresas con país República Dominicana y a los usuarios que trabajan con ellas.

En un sitio con empresas de varios países (una multinacional con sucursal en RD) los DocTypes son los mismos
para todas, así que nada se puede quitar de una empresa sola. Lo que se hace:

- Los campos que la app agrega se ocultan en los documentos de empresas que no son de RD (`condicion_campo`,
  con `frappe.boot.empresas_rd`); en los maestros sin empresa (clientes, proveedores, artículos...) solo se
  ven si el usuario trabaja con alguna empresa de RD.
- Los módulos de la app (RD Compliance, Nómina RD...) se bloquean en *Usuario → Módulos* a quien no trabaja
  con ninguna empresa de RD: así no ve el menú, el dock ni los íconos (`sincronizar_modulos`).
- El idioma Español (República Dominicana) se pone una sola vez (`idioma_inicial`).

Las empresas de un usuario son las de sus *Permisos de usuario* sobre Company o, si no tiene, todas.
"""

import frappe

from erpnext_rd.dgii_fiscal.ncf import PAIS
from erpnext_rd.formatos import IDIOMA

MODULOS = ("ERPNext RD", "DGII Fiscal", "ECF", "DGII Reportes", "Padron RNC", "Nomina RD", "RD Compliance")
# Ya se aplicó el idioma de la primera instalación: no se vuelve a tocar
CLAVE_IDIOMA = "erpnext_rd_idioma_inicial"

# Condición de los campos de la app (en `depends_on`, se evalúa en el navegador)
EN_EMPRESA_RD = "(frappe.boot.empresas_rd || []).includes(doc.company)"
CON_EMPRESAS_RD = "(frappe.boot.empresas_rd || []).length"
EN_COMPANY = f"doc.country == '{PAIS}'"


def hay_empresas_rd() -> bool:
	return bool(frappe.get_all("Company", filters={"country": PAIS}, limit=1))


def empresas_del_usuario(user: str | None = None) -> list[str]:
	user = user or frappe.session.user
	permitidas = frappe.get_all(
		"User Permission", filters={"user": user, "allow": "Company"}, pluck="for_value", distinct=True
	)
	return permitidas or frappe.get_all("Company", pluck="name")


def empresas_rd(user: str | None = None) -> list[str]:
	rd = set(frappe.get_all("Company", filters={"country": PAIS}, pluck="name"))
	return [c for c in empresas_del_usuario(user) if c in rd]


def condicion_campo(doctype: str, depends_on: str | None) -> str:
	"""`depends_on` del campo con la condición de RD por delante."""
	if doctype == "Company":
		condicion = EN_COMPANY
	elif frappe.get_meta(doctype).has_field("company"):
		condicion = EN_EMPRESA_RD
	else:
		condicion = CON_EMPRESAS_RD
	if not depends_on:
		return f"eval:{condicion}"
	propia = depends_on[5:] if depends_on.startswith("eval:") else f"doc.{depends_on}"
	return f"eval:({condicion}) && ({propia})"


# Módulos ----------------------------------------------------------------------------------------------


def _usuarios():
	return frappe.get_all("User", filters={"user_type": "System User", "name": ("!=", "Guest")}, pluck="name")


def _limpiar_cache(user: str):
	# Frappe lee los módulos bloqueados del User en caché (frappe.utils.modules.get_blocked_modules)
	frappe.clear_cache(user=user)
	frappe.clear_document_cache("User", user)


def sincronizar_modulos(user: str):
	"""Bloquea los módulos de la app a quien no trabaja con empresas de RD y los desbloquea a quien sí."""
	bloqueados = set(
		frappe.get_all(
			"Block Module",
			filters={"parenttype": "User", "parent": user, "module": ("in", MODULOS)},
			pluck="module",
		)
	)
	if empresas_rd(user):
		if bloqueados:
			frappe.db.delete(
				"Block Module", {"parenttype": "User", "parent": user, "module": ("in", list(bloqueados))}
			)
			_limpiar_cache(user)
		return
	faltan = [m for m in MODULOS if m not in bloqueados and frappe.db.exists("Module Def", m)]
	for modulo in faltan:
		frappe.get_doc(
			{
				"doctype": "Block Module",
				"parenttype": "User",
				"parentfield": "block_modules",
				"parent": user,
				"module": modulo,
			}
		).db_insert()
	if faltan:
		_limpiar_cache(user)


def sincronizar_todos():
	for user in _usuarios():
		sincronizar_modulos(user)


def al_crear_usuario(doc, method=None):
	if doc.user_type == "System User":
		sincronizar_modulos(doc.name)


def al_cambiar_permiso(doc, method=None):
	"""User Permission sobre Company: cambian las empresas del usuario."""
	if doc.allow == "Company":
		sincronizar_modulos(doc.user)


def al_cambiar_empresa(doc, method=None):
	"""Empresa nueva o que cambió de país: puede cambiar quién trabaja con empresas de RD."""
	if doc.has_value_changed("country"):
		sincronizar_todos()
		if doc.country == PAIS and frappe.db.count("Company", {"country": PAIS}) == 1:
			_primera_empresa_rd()
	if doc.country == PAIS:
		idioma_inicial()


def _primera_empresa_rd():
	"""Al instalar sin empresas de RD no se tocaron los registros de ERPNext y Frappe HR (formatos,
	componentes de nómina, feriados...): se crean con la primera. Si falla no detiene la creación de la
	empresa (p. ej. el asistente de configuración): lo repite el siguiente migrate."""
	from erpnext_rd import install

	frappe.db.savepoint("rd_primera_empresa")
	try:
		install.registros_rd()
		install.programar_padron_inicial()
	except Exception:
		frappe.db.rollback(save_point="rd_primera_empresa")
		frappe.log_error(title="ERPNext RD: preparar la primera empresa de RD")


# Idioma -----------------------------------------------------------------------------------------------


def idioma_inicial():
	"""Una sola vez, al instalar la app o, si aún no había empresas, al crear la primera de RD: habilita el
	español de República Dominicana, lo pone a los usuarios cuyas empresas son todas de RD y al sitio si todas
	sus empresas lo son. Después cada quien lo puede cambiar."""
	if frappe.db.get_default(CLAVE_IDIOMA) or not frappe.db.exists("Language", IDIOMA):
		return
	frappe.db.set_value("Language", IDIOMA, "enabled", 1)
	empresas = frappe.get_all("Company", fields=["name", "country"])
	if not empresas:
		return  # El asistente de configuración ya lo ofrece; se decide al crear la primera empresa de RD
	if all(e.country == PAIS for e in empresas):
		frappe.db.set_single_value("System Settings", "language", IDIOMA)
	for user in _usuarios():
		propias = empresas_del_usuario(user)
		if propias and len(empresas_rd(user)) == len(propias):
			frappe.db.set_value("User", user, "language", IDIOMA, update_modified=False)
	frappe.db.set_default(CLAVE_IDIOMA, "1")
	frappe.clear_cache()
