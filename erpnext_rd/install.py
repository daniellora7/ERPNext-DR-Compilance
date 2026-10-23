"""Instalación, migración y desinstalación: orquesta los campos (`campos.py`), los catálogos DGII,
los formatos y el menú (`navegacion.py`).

Es idempotente: corre en after_install, after_migrate y cuando se instala Frappe HR. Todo se
configura solo, sin pasos en la consola, para que la app se pueda instalar desde Frappe Cloud.
"""

import frappe

from erpnext_rd import formatos
from erpnext_rd.campos import DOCTYPES_HRMS, MODULO, crear_campos_personalizados
from erpnext_rd.dgii_fiscal import catalogo_cuentas, cheque
from erpnext_rd.dgii_fiscal import catalogos as cat
from erpnext_rd.dgii_fiscal.catalogos import TIPOS_COMPROBANTE
from erpnext_rd.dgii_reportes import estados_ir2, ir2
from erpnext_rd.navegacion import asegurar_navegacion, dock_nomina, quitar_dock_nomina
from erpnext_rd.nomina_rd import hrms_instalado, salario, volante
from erpnext_rd.rd_compliance import alcance


def crear_tipos_comprobante():
	"""Inserta los tipos faltantes. No sobrescribe cambios que el usuario haya hecho."""
	for codigo, descripcion, ventas, compras, comprador, nota, requiere_rnc in TIPOS_COMPROBANTE:
		if frappe.db.exists("Tipo Comprobante Fiscal", codigo):
			continue
		frappe.get_doc(
			{
				"doctype": "Tipo Comprobante Fiscal",
				"codigo": codigo,
				"descripcion": descripcion,
				"serie": codigo[0],
				"habilitado": 1,
				"aplica_ventas": ventas,
				"aplica_compras": compras,
				"emitido_por_comprador": comprador,
				"nota": nota,
				"requiere_rnc": requiere_rnc,
			}
		).insert(ignore_permissions=True)


def inicializar_formas_pago():
	"""Clasifica los Modos de Pago existentes que aún no tienen forma de pago DGII."""
	for modo in frappe.get_all(
		"Mode of Payment", filters={"rd_forma_pago": ("is", "not set")}, fields=["name", "type"]
	):
		nombre = modo.name.lower()
		if "card" in nombre or "tarjeta" in nombre:
			forma = cat.TARJETA
		elif modo.type == "Cash":
			forma = cat.EFECTIVO
		elif modo.type == "Bank":
			forma = cat.CHEQUE_TRANSFERENCIA
		else:
			forma = cat.OTRAS_FORMAS
		frappe.db.set_value("Mode of Payment", modo.name, "rd_forma_pago", forma, update_modified=False)


def inicializar_configuracion():
	"""Guarda las configuraciones una vez para que sus valores por defecto queden en la base."""
	if not frappe.db.exists("Singles", {"doctype": "Configuracion DGII"}):
		frappe.get_single("Configuracion DGII").save(ignore_permissions=True)
	# Quedó vacío en los sitios donde la configuración se guardó antes de agregar el campo
	if not frappe.db.get_single_value("Configuracion DGII", "ambiente_ecf"):
		frappe.db.set_single_value("Configuracion DGII", "ambiente_ecf", "TesteCF")
	for campo, valor in (
		("tasa_bcrd_activa", 1),
		("tasa_bcrd_tipo", "Compra"),
		("recordatorios_dias", 3),
		("consultar_ncf_dgii", 1),
		("anticipo_tasa_minima", 1.5),
		*ir2.TASAS_POR_DEFECTO.items(),
	):
		if not frappe.db.exists("Singles", {"doctype": "Configuracion DGII", "field": campo}):
			frappe.db.set_single_value("Configuracion DGII", campo, valor)

	# Campos agregados después de guardar la configuración: quedan con su valor por defecto
	for campo, valor in (
		("calcular_deducciones", 1),
		("dias_salario_mes", 23.83),
		("actualizar_feriados", 1),
		("dia_descanso", "Sunday"),
		("bonificacion_porcentaje", 10),
		("bonificacion_anios", 3),
		("bonificacion_dias_menor", 45),
		("bonificacion_dias_mayor", 60),
		("horas_jornada", 8),
		("horas_semana_normal", 44),
		("horas_semana_maximo", 68),
		("recargo_horas_extras", 35),
		("recargo_horas_extras_exceso", 100),
		("recargo_feriado", 100),
		("recargo_nocturno", 15),
		("inicio_jornada_nocturna", "21:00:00"),
		("fin_jornada_nocturna", "07:00:00"),
		("sfs_per_capita_adicional", 1938.18),
		("fonamat_per_capita", 32.24),
		("subsidio_enfermedad_ambulatorio", 60),
		("subsidio_enfermedad_hospitalario", 40),
		("subsidio_dias_espera", 3),
		("subsidio_dias_maximo", 182),
		("subsidio_meses_promedio", 6),
		("subsidio_maternidad_meses", 3),
		("lactancia_un_salario", 33),
		("lactancia_dos_salarios", 12),
		("lactancia_tres_salarios", 6),
	):
		if not frappe.db.exists("Singles", {"doctype": "Configuracion Nomina RD", "field": campo}):
			frappe.db.set_single_value("Configuracion Nomina RD", campo, valor)

	dgii = frappe.get_single("Configuracion DGII")
	if not dgii.multiplicadores_inflacion:
		for cierre, valor, resolucion in ir2.MULTIPLICADORES:
			dgii.append(
				"multiplicadores_inflacion",
				{"cierre": cierre, "multiplicador": valor, "resolucion": resolucion},
			)
		dgii.save(ignore_permissions=True)

	conf = frappe.get_single("Configuracion Nomina RD")
	if not conf.escala_isr:
		from erpnext_rd.nomina_rd.calculos import ESCALAS_ISR

		for anio, escala in ESCALAS_ISR.items():
			agregar_escala_isr(conf, anio, escala)
		conf.save(ignore_permissions=True)


def agregar_escala_isr(conf, anio: int, escala):
	for desde, hasta, tasa, cuota in escala:
		conf.append(
			"escala_isr", {"anio": anio, "desde": desde, "hasta": hasta, "tasa": tasa, "cuota_fija": cuota}
		)


# Formatos que deja ERPNext al instalarse ("Classic" desde v16.5x; antes "Modern with Images"); se
# reemplazan por los fiscales. Si el usuario eligió otro formato, se respeta. Las empresas de otros
# países imprimen con el estándar o con el que indiquen (Company.rd_formato_factura, ver boot.py).
FORMATOS_POR_DEFECTO = {
	"Sales Invoice": ("Factura Fiscal RD", ("Sales Invoice Classic", "Sales Invoice Modern with Images")),
	"POS Invoice": ("Recibo POS RD (POS Invoice)", ("POS Invoice Classic", "POS Invoice Modern with Images")),
}


def formato_impresion_por_defecto():
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for doctype, (formato, reemplazables) in FORMATOS_POR_DEFECTO.items():
		actual = frappe.db.get_value(
			"Property Setter", {"doc_type": doctype, "property": "default_print_format"}, "value"
		)
		if not actual or actual in reemplazables:
			make_property_setter(
				doctype,
				None,
				"default_print_format",
				formato,
				"Data",
				for_doctype=True,
				validate_fields_for_doctype=False,
			)

	# Con el módulo puesto, Frappe los borra al desinstalar la app junto con los formatos
	frappe.db.set_value(
		"Property Setter",
		{
			"property": "default_print_format",
			"value": ("in", _formatos_fiscales()),
			"module": ("is", "not set"),
		},
		"module",
		MODULO,
		update_modified=False,
	)


def _formatos_fiscales() -> list[str]:
	return [formato for formato, _reemplazables in FORMATOS_POR_DEFECTO.values()]


def prestaciones_y_feriados():
	"""Tramos de prestaciones y vacaciones en la configuración, reglas de Gratuity RD, el tipo de
	permiso Vacaciones RD y la lista de feriados RD."""
	from erpnext_rd.nomina_rd import feriados, prestaciones

	conf = frappe.get_single("Configuracion Nomina RD")
	if prestaciones.inicializar_tramos(conf):
		conf.save(ignore_permissions=True)
	if hrms_instalado():
		from erpnext_rd.nomina_rd import horas_extras, regalia, vacaciones

		reglas_gratuity_sin_tramos()
		periodo_opcional_en_vacaciones_rd()
		prestaciones.crear_reglas()
		vacaciones.crear_componente_y_tipo()
		regalia.crear_componente()
		horas_extras.crear_componente_y_tipo()
		volante.crear_formato()
	feriados.asegurar_lista_feriados()


def reglas_gratuity_sin_tramos():
	"""En una regla de prestación RD los tramos de HRMS (en años enteros) no aplican: se ocultan y
	dejan de ser obligatorios, igual que los componentes. En las demás reglas siguen igual."""
	ajustes = (
		("gratuity_rule_slabs", "reqd", "0", "Check"),
		("gratuity_rule_slabs", "mandatory_depends_on", "eval:!doc.rd_prestacion", "Code"),
		("gratuity_rule_slabs", "depends_on", "eval:!doc.rd_prestacion", "Code"),
		# Componentes opcionales: vacío = los ingresos que cotizan a la TSS (prestaciones.componentes_ordinarios)
		("applicable_earnings_component", "reqd", "0", "Check"),
		("applicable_earnings_component", "mandatory_depends_on", "eval:!doc.rd_prestacion", "Code"),
	)
	_property_setters("Gratuity Rule", ajustes)


def datos_del_empleado():
	"""Catálogo de AFP y ARS, y buscar empleados también por cédula."""
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	from erpnext_rd.nomina_rd import empleado

	empleado.crear_entidades()
	campos = [c.strip() for c in (frappe.get_meta("Employee").search_fields or "").split(",") if c.strip()]
	if "rd_cedula" not in campos:
		make_property_setter(
			"Employee",
			None,
			"search_fields",
			", ".join([*campos, "rd_cedula"]),
			"Data",
			for_doctype=True,
			validate_fields_for_doctype=False,
		)
		frappe.db.set_value(
			"Property Setter",
			{"doc_type": "Employee", "property": "search_fields", "module": ("is", "not set")},
			"module",
			MODULO,
			update_modified=False,
		)


def periodo_opcional_en_vacaciones_rd():
	"""El *Leave Period* del Leave Encashment lo pone la app en el pago de vacaciones RD (ver
	`leave_encashment_rd`); en los demás pagos sigue siendo obligatorio como en Frappe HR."""
	_property_setters(
		"Leave Encashment",
		(
			("leave_period", "reqd", "0", "Check"),
			("leave_period", "mandatory_depends_on", "eval:!doc.rd_salario_diario", "Code"),
		),
	)


def _property_setters(doctype: str, ajustes):
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for campo, propiedad, valor, tipo in ajustes:
		make_property_setter(doctype, campo, propiedad, valor, tipo, validate_fields_for_doctype=False)
	# Con el módulo de la app, Frappe los borra al desinstalarla
	frappe.db.set_value(
		"Property Setter",
		{
			"doc_type": doctype,
			"module": ("is", "not set"),
			"field_name": ("in", {a[0] for a in ajustes}),
		},
		"module",
		MODULO,
		update_modified=False,
	)


def programar_padron_inicial():
	"""Sitio nuevo: descarga el padrón RNC en segundo plano (cola long), sin pasos en la consola.

	Después lo actualiza la tarea diaria (solo si la DGII publicó uno nuevo) o el botón de Configuración DGII."""
	if frappe.flags.in_test or getattr(frappe, "in_test", False):
		return
	if not alcance.hay_empresas_rd() or frappe.get_all("Contribuyente DGII", limit=1):
		return
	from erpnext_rd.padron_rnc.padron import encolar

	encolar()


def lista_padron_sin_filtro_reciente():
	"""El padrón (~800 mil filas) es una tabla grande para Frappe, que entonces filtra la lista por
	"creados en los últimos 90 días" y avisa cada vez. En el padrón se busca por RNC o nombre, no por
	fecha: se desactiva ese filtro. Solo si no existe la configuración, para respetar la del usuario."""
	if frappe.db.exists("List View Settings", "Contribuyente DGII"):
		return
	frappe.get_doc(
		{
			"doctype": "List View Settings",
			"name": "Contribuyente DGII",
			"disable_automatic_recency_filters": 1,
		}
	).insert(ignore_permissions=True)


def setup():
	# Lo propio de la app: sus DocTypes, sus campos (ocultos fuera de RD), configuración y navegación
	crear_campos_personalizados()
	ir2.crear_formato()
	estados_ir2.asignar_casillas()
	crear_tipos_comprobante()
	inicializar_configuracion()
	asegurar_navegacion()
	lista_padron_sin_filtro_reciente()
	frappe.clear_cache()
	# Lo que crea o cambia registros de ERPNext y Frappe HR, solo si hay empresas de RD (si aún no hay,
	# lo hace la primera que se cree: alcance.al_cambiar_empresa)
	if alcance.hay_empresas_rd():
		registros_rd()


def registros_rd():
	formatos.asegurar_fiscales()
	cheque.crear_formato()
	formato_impresion_por_defecto()
	inicializar_formas_pago()
	dock_nomina()
	datos_del_empleado()
	prestaciones_y_feriados()
	frappe.clear_cache()
	catalogo_cuentas.aplicar_a_empresas_rd()
	salario.crear_componentes()


def after_install():
	# Primero el idioma, luego lo propio de la app y los módulos de cada usuario según sus empresas
	alcance.idioma_inicial()
	setup()
	alcance.sincronizar_todos()
	programar_padron_inicial()


def after_migrate():
	setup()
	programar_padron_inicial()


def al_instalar_app(app_name: str):
	"""after_app_install: Frappe HR instalado después de esta app -> activa la Nómina RD."""
	if app_name == "hrms":
		setup()


def al_desinstalar_app(app_name: str):
	"""after_app_uninstall: sin Frappe HR se quitan sus campos y la Nómina RD del dock."""
	if app_name != "hrms":
		return
	for nombre in frappe.get_all(
		"Custom Field", filters={"dt": ("in", DOCTYPES_HRMS), "module": MODULO}, pluck="name"
	):
		frappe.delete_doc("Custom Field", nombre, force=True, ignore_permissions=True)
	frappe.db.delete("Property Setter", {"doc_type": ("in", DOCTYPES_HRMS), "module": MODULO})
	quitar_dock_nomina()
	volante.quitar_formato()
	# Frappe llama este hook después del último commit de la desinstalación
	frappe.db.commit()  # nosemgrep
	frappe.clear_cache()


def before_uninstall():
	"""Quita lo que Frappe no borra solo al desinstalar (lo que no cuelga de un módulo de la app).

	Campos personalizados, formatos, reportes, DocTypes y el menú tienen módulo y los borra Frappe.
	Los datos contables del usuario (cuentas, plantillas de impuestos, facturas) se conservan."""
	frappe.db.delete(
		"Property Setter", {"property": "default_print_format", "value": ("in", _formatos_fiscales())}
	)
	volante.quitar_formato()
	for job in frappe.get_all(
		"Scheduled Job Type", filters={"method": ("like", "erpnext_rd.%")}, pluck="name"
	):
		frappe.delete_doc("Scheduled Job Type", job, force=True, ignore_permissions=True)
	if frappe.db.exists("DocType", "Dock") and frappe.db.exists("Dock", "erpnext_rd"):
		frappe.delete_doc("Dock", "erpnext_rd", force=True, ignore_permissions=True)
	quitar_dock_nomina()
	frappe.db.delete("List View Settings", {"name": "Contribuyente DGII"})
	frappe.db.delete("DefaultValue", {"defkey": ("like", "erpnext_rd_%")})
	frappe.clear_cache()
