"""Procesos de compra del Estado (Fase 10.3): descarga desde la API de la DGCP.

Solo se guardan los procesos con artículos de las familias UNSPSC de los perfiles de proveedor
activos. Pasos de cada sincronización (detalle en docs/PLAN.md, *Resultado de la 10.1*):
1. Por familia, /procesos/articulos (no filtra por fecha: se pagina hasta pasar la fecha de corte).
2. /procesos?startdate= con el mismo corte da el detalle de los procesos; los que falten se piden
   uno a uno por su código.
3. Los procesos guardados que siguen abiertos se vuelven a consultar para ver su estado.
"""

from collections import defaultdict
from datetime import datetime, timedelta

import frappe
from frappe import _
from frappe.utils import add_days, cint, convert_utc_to_system_timezone, get_datetime, now_datetime

from erpnext_rd.licitaciones import api_dgcp, ofertas, proveedor

DOCTYPE = "Proceso Compra DGCP"
CONFIGURACION = "Configuracion Licitaciones"
# Margen sobre la última sincronización: la API no ordena estrictamente por fecha
MARGEN_DIAS = 2
# Estados de la DGCP en los que el proceso todavía puede cambiar
ESTADOS_ABIERTOS = ("Proceso publicado", "Sobres abiertos o aperturados", "Proceso con etapa cerrada")
# Procesos abiertos que se vuelven a consultar en cada corrida (la API permite 60 por minuto)
MAXIMO_ACTUALIZACIONES = 200
CAMPOS_TEXTO = (
	"unidad_compra",
	"modalidad",
	"tipo_excepcion",
	"titulo",
	"descripcion",
	"estado_proceso",
	"objeto_proceso",
	"duracion_contrato",
	"url",
)
CAMPOS_FECHA = (
	"fecha_publicacion",
	"fecha_enmienda",
	"fecha_fin_recepcion_ofertas",
	"fecha_apertura_ofertas",
	"fecha_estimada_adjudicacion",
	"fecha_suscripcion",
)
CAMPOS_ARTICULO = (
	"familia_unspsc",
	"clase_unspsc",
	"subclase_unspsc",
	"descripcion_articulo",
	"descripcion_usuario",
	"unidad_medida",
)


def fecha_local(valor: str | None) -> datetime | None:
	"""Fecha de la API (UTC, «2026-11-04T08:01:08.4633333Z») en la zona horaria del sitio."""
	if not valor:
		return None
	texto = valor.rstrip("Z")
	if "." in texto:
		base, fraccion = texto.split(".", 1)
		texto = f"{base}.{fraccion[:6]}"
	return convert_utc_to_system_timezone(datetime.fromisoformat(texto)).replace(tzinfo=None)


def _si(valor) -> int:
	return 1 if str(valor or "").strip().lower() in ("si", "sí") else 0


def familias_por_empresa() -> dict[str, set[str]]:
	"""{familia UNSPSC: {empresas}} de los perfiles de proveedor activos."""
	activos = frappe.get_all(proveedor.DOCTYPE, filters={"habilitado": 1}, pluck="name")
	familias = defaultdict(set)
	for r in frappe.get_all(
		"Rubro Proveedor Estado",
		filters={"parenttype": proveedor.DOCTYPE, "parent": ("in", activos or [""])},
		fields=["parent", "familia_unspsc"],
	):
		familias[r.familia_unspsc].add(r.parent)
	return familias


def codigos_por_familia(familia: str, corte: datetime) -> set[str]:
	"""Códigos de los procesos con artículos de la familia publicados desde `corte`."""
	corte = get_datetime(corte)
	codigos = set()
	for pagina in range(1, 51):
		filas = api_dgcp.consultar(
			"procesos/articulos", familia=familia, page=pagina, limit=api_dgcp.LIMITE_PAGINA
		)
		recientes = [f for f in filas if (fecha_local(f.get("fecha_publicacion")) or corte) >= corte]
		codigos |= {f["codigo_proceso"] for f in recientes if f.get("codigo_proceso")}
		# Página entera anterior al corte o la última: no hay más
		if not recientes or len(filas) < api_dgcp.LIMITE_PAGINA:
			break
	return codigos


def procesos_desde(corte: datetime) -> dict[str, dict]:
	filas = api_dgcp.todas("procesos", startdate=corte.date().isoformat())
	return {f["codigo_proceso"]: f for f in filas if f.get("codigo_proceso")}


def guardar(fila: dict, articulos: list[dict] | None, empresas: dict[str, set[str]]):
	"""Crea o actualiza el proceso. `articulos` None: se conservan los que tiene."""
	codigo = fila["codigo_proceso"]
	existe = frappe.db.exists(DOCTYPE, codigo)
	doc = frappe.get_doc(DOCTYPE, codigo) if existe else frappe.new_doc(DOCTYPE)
	doc.codigo_proceso = codigo
	for campo in CAMPOS_TEXTO:
		doc.set(campo, (fila.get(campo) or "").strip() or None)
	for campo in CAMPOS_FECHA:
		doc.set(campo, fecha_local(fila.get(campo)))
	doc.codigo_unidad_compra = cint(fila.get("codigo_unidad_compra"))
	doc.divisa = fila.get("divisa") if frappe.db.exists("Currency", fila.get("divisa")) else None
	doc.monto_estimado = fila.get("monto_estimado") or 0
	doc.dirigido_mipymes = _si(fila.get("dirigido_mipymes"))
	doc.dirigido_mipymes_mujeres = _si(fila.get("dirigido_mipymes_mujeres"))
	doc.actualizado_dgcp = now_datetime()
	if articulos is not None:
		doc.set("articulos", [])
		for a in articulos:
			doc.append(
				"articulos",
				{
					**{campo: (a.get(campo) or "").strip() or None for campo in CAMPOS_ARTICULO},
					"cantidad": a.get("cantidad") or 0,
					"precio_unitario_estimado": a.get("precio_unitario_estimado") or 0,
					"precio_total_estimado": a.get("precio_total_estimado") or 0,
					"divisa": doc.divisa,
				},
			)
	if empresas:
		actuales = {e.company: set(filter(None, (e.familias or "").split(", "))) for e in doc.empresas}
		for company, familias in empresas.items():
			actuales[company] = actuales.get(company, set()) | familias
		doc.set(
			"empresas",
			[{"company": c, "familias": ", ".join(sorted(f))} for c, f in sorted(actuales.items())],
		)
	doc.flags.ignore_permissions = True
	doc.save() if existe else doc.insert()
	if existe:
		ofertas.actualizar_desde_proceso(doc)
	return doc, not existe


def corte_de_sincronizacion(conf) -> datetime:
	if conf.ultima_sincronizacion:
		return get_datetime(conf.ultima_sincronizacion) - timedelta(days=MARGEN_DIAS)
	return get_datetime(add_days(now_datetime(), -(cint(conf.dias_iniciales) or 15))).replace(
		hour=0, minute=0, second=0, microsecond=0
	)


def sincronizar() -> dict:
	"""Descarga los procesos nuevos de los rubros de las empresas y actualiza los abiertos."""
	conf = frappe.get_single(CONFIGURACION)
	familias = familias_por_empresa()
	resultado = {"nuevos": 0, "actualizados": 0}
	if not familias:
		return resultado
	inicio = now_datetime()
	corte = corte_de_sincronizacion(conf)

	# 1. Qué procesos tienen artículos de los rubros, y de qué empresas
	coincidencias = defaultdict(lambda: defaultdict(set))
	for familia, empresas in familias.items():
		for codigo in codigos_por_familia(familia, corte):
			for company in empresas:
				coincidencias[codigo][company].add(familia)

	# 2. Detalle de esos procesos
	detalle = procesos_desde(corte) if coincidencias else {}
	for codigo, empresas in coincidencias.items():
		fila = detalle.get(codigo) or next(iter(api_dgcp.consultar("procesos", proceso=codigo)), None)
		if not fila:
			continue
		nuevo = not frappe.db.exists(DOCTYPE, codigo)
		articulos = api_dgcp.todas("procesos/articulos", proceso=codigo) if nuevo else None
		guardar(fila, articulos, empresas)
		resultado["nuevos" if nuevo else "actualizados"] += 1
		frappe.db.commit()  # nosemgrep: frappe-manual-commit

	# 3. Los abiertos que no salieron en esta corrida (publicados antes del corte)
	abiertos = frappe.get_all(
		DOCTYPE,
		filters={"estado_proceso": ("in", ESTADOS_ABIERTOS), "name": ("not in", list(coincidencias) or [""])},
		order_by="fecha_publicacion desc",
		limit=MAXIMO_ACTUALIZACIONES,
		pluck="name",
	)
	for codigo in abiertos:
		fila = detalle.get(codigo) or next(iter(api_dgcp.consultar("procesos", proceso=codigo)), None)
		if fila:
			guardar(fila, None, {})
			resultado["actualizados"] += 1
			frappe.db.commit()  # nosemgrep: frappe-manual-commit

	conf.ultima_sincronizacion = inicio
	conf.ultimo_resultado = _("{0} procesos nuevos y {1} actualizados.").format(
		resultado["nuevos"], resultado["actualizados"]
	)
	conf.flags.ignore_permissions = True
	conf.save()
	frappe.db.commit()  # nosemgrep: frappe-manual-commit
	return resultado


def tarea_sincronizar():
	"""Corre en la cola long. Un error queda en el Error Log y se reintenta en la próxima corrida."""
	try:
		sincronizar()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=_("Sincronización de procesos de la DGCP"))


def encolar():
	"""Tarea programada: pasa a la cola long (una sola a la vez). Sin perfiles activos no hace nada."""
	if not frappe.db.exists(proveedor.DOCTYPE, {"habilitado": 1}):
		return
	frappe.enqueue(
		"erpnext_rd.licitaciones.procesos.tarea_sincronizar",
		queue="long",
		timeout=3600,
		job_id="erpnext_rd:sincronizar_procesos_dgcp",
		deduplicate=True,
		enqueue_after_commit=True,
	)


@frappe.whitelist(methods=["POST"])
def sincronizar_ahora() -> str:
	frappe.only_for(("System Manager", "Sales Manager"))
	if not frappe.db.exists(proveedor.DOCTYPE, {"habilitado": 1}):
		frappe.throw(_("No hay perfiles de proveedor del Estado activos con rubros."))
	encolar()
	return _("Descarga de procesos en cola. Puede tardar algunos minutos.")


@frappe.whitelist()
def documentos(codigo_proceso: str) -> list[dict]:
	"""Pliegos, fichas técnicas y actos del proceso (se consultan en el momento: cambian con las enmiendas)."""
	frappe.has_permission(DOCTYPE, "read", codigo_proceso, throw=True)
	try:
		filas = api_dgcp.consultar("procesos/documentos", proceso=codigo_proceso)
	except (api_dgcp.ErrorAPIDGCP, OSError) as e:
		frappe.throw(_("No se pudo consultar la API de la DGCP: {0}").format(str(e)))
	return sorted(
		(
			{
				"nombre": f.get("nombre_documento"),
				"tipo": f.get("tipo_documento"),
				"fecha": fecha_local(f.get("fecha_carga_archivo")),
				"url": f.get("url_documento"),
			}
			for f in filas
		),
		key=lambda d: d["fecha"] or datetime.min,
	)
