"""Datos dominicanos del empleado (*Employee* de ERPNext): documento, NSS, segundo apellido, AFP y ARS.

Se reutiliza lo que ya tiene la ficha: nombre, primer apellido (*Last Name*), sexo, fecha de nacimiento
y pasaporte (*Passport Number*). Son los datos que piden la TSS (archivo de autodeterminación del SUIR)
y la DGII (IR-3 / IR-13). Como Employee es de ERPNext, no dependen de Frappe HR.

La validación (doc_events Employee validate) solo aplica a empresas RD, salvo el nombre completo, y
solo avisa: se puede contratar con pasaporte u otro documento (extranjeros) y la cédula no es obligatoria.
"""

import frappe
from frappe import _

from erpnext_rd.dgii_fiscal.identificacion import identificacion_valida
from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.dgii_fiscal.validaciones import limpiar_identificacion

CEDULA = "Cédula"
NSS = "NSS"
PASAPORTE = "Pasaporte"
OTRO = "Otro"
TIPOS_DOCUMENTO = (CEDULA, NSS, PASAPORTE, OTRO)

AFP = "AFP"
ARS = "ARS"
# Catálogo inicial (editable): entidades del SDSS conocidas al publicar esta versión
ENTIDADES = {
	AFP: (
		"AFP Atlántico",
		"AFP Crecer",
		"AFP JMMB BDI",
		"AFP Popular",
		"AFP Reservas",
		"AFP Romana",
		"AFP Siembra",
	),
	ARS: (
		"ARS Futuro",
		"ARS Humano",
		"ARS Mapfre Salud",
		"ARS Monumental",
		"ARS Palic Salud",
		"ARS Renacer",
		"ARS Reservas",
		"ARS Semma",
		"ARS SeNaSa",
		"ARS Universal",
		"ARS Yunén",
	),
}


def validar_empleado(doc, method=None):
	"""doc_events: Employee -> validate."""
	nombre_completo(doc)
	if not (doc.company and es_empresa_rd(doc.company)):
		return
	validar_cedula(doc)
	if doc.rd_nss:
		doc.rd_nss = limpiar_identificacion(doc.rd_nss)
	if doc.get("rd_numero_documento"):
		doc.rd_numero_documento = doc.rd_numero_documento.strip().upper()
	if doc.rd_tipo_documento == PASAPORTE:
		# El número va en el campo estándar Passport Number y en el de la sección RD
		if doc.get("rd_numero_documento"):
			doc.passport_number = doc.rd_numero_documento
		elif doc.passport_number:
			doc.passport_number = doc.rd_numero_documento = doc.passport_number.strip().upper()
	if doc.get("rd_clave_nomina"):
		doc.rd_clave_nomina = doc.rd_clave_nomina.strip().zfill(3)


def nombre_completo(doc):
	"""ERPNext arma el nombre con nombre + segundo nombre + apellido; se agrega el segundo apellido."""
	if doc.get("rd_segundo_apellido"):
		partes = (doc.first_name, doc.middle_name, doc.last_name, doc.rd_segundo_apellido)
		doc.employee_name = " ".join(p for p in partes if p)


def cedula_valida(cedula: str | None) -> bool:
	cedula = limpiar_identificacion(cedula or "")
	return len(cedula) == 11 and identificacion_valida(cedula, CEDULA)


def _avisar(mensaje: str, titulo: str):
	frappe.msgprint(mensaje, title=titulo, indicator="orange", alert=False)


def validar_cedula(doc):
	"""Solo avisa: la cédula no es obligatoria (extranjeros con pasaporte u otro documento) y un
	error de captura no debe impedir registrar al empleado. El archivo de la TSS vuelve a avisar."""
	if not doc.rd_cedula:
		return
	doc.rd_cedula = cedula = limpiar_identificacion(doc.rd_cedula)
	if not (doc.is_new() or doc.has_value_changed("rd_cedula")):
		return
	if not cedula_valida(cedula):
		_avisar(
			_("La cédula {0} no parece válida (11 dígitos con dígito verificador). Revísela.").format(cedula),
			_("Revise la cédula"),
		)

	# Un reingreso es otro Employee: solo choca con empleados que siguen en la empresa
	otro = frappe.db.get_value(
		"Employee",
		{
			"rd_cedula": cedula,
			"company": doc.company,
			"status": ("!=", "Left"),
			"name": ("!=", doc.name or ""),
		},
		["name", "employee_name"],
		as_dict=True,
	)
	if otro:
		_avisar(
			_("La cédula {0} también es del empleado {1} ({2}) en {3}.").format(
				cedula, frappe.bold(otro.employee_name), otro.name, doc.company
			),
			_("Cédula repetida"),
		)


def crear_entidades():
	"""Llena el catálogo de AFP y ARS si está vacío (el usuario puede agregar o deshabilitar)."""
	if frappe.db.count("Entidad Seguridad Social RD"):
		return
	for tipo, nombres in ENTIDADES.items():
		for nombre in nombres:
			frappe.get_doc({"doctype": "Entidad Seguridad Social RD", "nombre": nombre, "tipo": tipo}).insert(
				ignore_permissions=True
			)
