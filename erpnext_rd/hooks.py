app_name = "erpnext_rd"
app_title = "ERPNext RD"
app_publisher = "ERPNext RD"
app_description = (
	"Localizacion Republica Dominicana para ERPNext: NCF, e-CF DGII, reportes 606/607/608 y nomina RD"
)
app_email = "daniellorap.ing@gmail.com"
app_license = "gpl-3.0"

# Apps
# ------------------

# Frappe HR (hrms) es opcional: si está instalado se activa la Nómina RD (ver install.py)
required_apps = ["frappe/erpnext"]

# Includes in <head>
# ------------------

# app_include_css = "/assets/erpnext_rd/css/erpnext_rd.css"
# app_include_js = "/assets/erpnext_rd/js/erpnext_rd.js"

# Navegación: un solo módulo "RD Compliance" en el dock de ERPNext (dock/erpnext_rd, mount_on =
# erpnext), con su sidebar de secciones en rd_compliance/sidebar. Los módulos de código le ceden
# su navegación, así todo lo suyo abre dentro de RD Compliance. La excepción es Nomina RD: tiene su
# propio sidebar (nomina_rd/sidebar, app = hrms) y va en el dock de Frappe HR (install.dock_nomina).
app_include_icons = ["/assets/erpnext_rd/icons/erpnext-rd-icons.svg"]
code_only_modules = {
	"DGII Fiscal": ["RD Compliance"],
	"DGII Reportes": ["RD Compliance"],
	"Padron RNC": ["RD Compliance"],
	"ECF": ["RD Compliance"],
	"ERPNext RD": ["RD Compliance"],
}

# Panel RD Compliance (frontend frappe-ui en frontend/, página www/rd_compliance.py)
website_route_rules = [
	{"from_route": "/rd-compliance/<path:app_path>", "to_route": "rd-compliance"},
]

# Instalación
# ------------

after_install = "erpnext_rd.install.after_install"
after_migrate = "erpnext_rd.install.after_migrate"
before_uninstall = "erpnext_rd.install.before_uninstall"

# Frappe HR instalado o desinstalado después de esta app: activa o retira la Nómina RD
after_app_install = "erpnext_rd.install.al_instalar_app"
after_app_uninstall = "erpnext_rd.install.al_desinstalar_app"

# JS por DocType
# --------------

doctype_js = {
	"Customer": "public/js/party_rnc.js",
	"Supplier": "public/js/party_rnc.js",
	"Sales Invoice": "public/js/invoice_dgii.js",
	"POS Invoice": "public/js/invoice_dgii.js",
	"Purchase Invoice": "public/js/invoice_dgii.js",
}

# Document Events
# ---------------

# Sitio nuevo sin configurar (CI): completa el asistente como empresa de RD antes de los tests
before_tests = "erpnext_rd.tests.utils.antes_de_tests"

# Nómina RD: AFP, SFS, ISR y aportes del empleador en el recibo de Frappe HR
regional_overrides = {
	"Dominican Republic": {
		"hrms.payroll.doctype.salary_slip.salary_slip.apply_regional_deductions": (
			"erpnext_rd.nomina_rd.salario.deducciones_regionales"
		),
	},
}

# Prestaciones RD (preaviso y cesantía) sobre el Gratuity de Frappe HR: solo cambia el cálculo
# del monto en las reglas marcadas con rd_prestacion. La clase solo se importa si HRMS está instalado.
override_doctype_class = {
	"Gratuity": "erpnext_rd.nomina_rd.gratuity_rd.GratuityRD",
}

doc_events = {
	"Salary Slip": {
		"validate": "erpnext_rd.nomina_rd.salario.al_validar_recibo",
	},
	"Company": {
		"validate": "erpnext_rd.dgii_fiscal.identificacion.validar_party",
		"on_update": "erpnext_rd.dgii_fiscal.catalogo_cuentas.al_actualizar_empresa",
	},
	"Customer": {
		"validate": "erpnext_rd.dgii_fiscal.identificacion.validar_party",
	},
	"Supplier": {
		"validate": "erpnext_rd.dgii_fiscal.identificacion.validar_party",
	},
	"Sales Invoice": {
		"validate": "erpnext_rd.dgii_fiscal.ncf.validar_venta",
		"before_submit": "erpnext_rd.dgii_fiscal.ncf.asignar_ncf_venta",
		"before_cancel": "erpnext_rd.dgii_fiscal.ncf.antes_de_cancelar_venta",
	},
	"POS Invoice": {
		"validate": "erpnext_rd.dgii_fiscal.ncf.validar_venta",
		"before_submit": "erpnext_rd.dgii_fiscal.ncf.asignar_ncf_venta",
		"before_cancel": "erpnext_rd.dgii_fiscal.ncf.antes_de_cancelar_venta",
	},
	"Purchase Invoice": {
		"validate": "erpnext_rd.dgii_fiscal.ncf.validar_compra",
		"before_submit": "erpnext_rd.dgii_fiscal.ncf.antes_de_validar_compra",
		"before_cancel": "erpnext_rd.dgii_fiscal.ncf.antes_de_cancelar_compra",
	},
}

# Jinja (formatos de impresión)
# -----------------------------

jinja = {
	"methods": ["erpnext_rd.dgii_fiscal.impresion.rd_datos_fiscales"],
}

# Scheduled Tasks
# ---------------

# Padrón RNC: todos los días a las 2:00 a. m. (zona horaria del sitio). Un cron corre en la cola
# default con su timeout corto; `encolar` lo pasa a la cola long (1 h) y evita dos a la vez.
scheduler_events = {
	"cron": {
		"0 2 * * *": ["erpnext_rd.padron_rnc.padron.encolar"],
	},
	# Extiende la lista "Feriados RD" al año siguiente (idempotente)
	"monthly": ["erpnext_rd.nomina_rd.feriados.asegurar_lista_feriados"],
}
