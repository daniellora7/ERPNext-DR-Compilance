// Utilidades del panel: formato de montos y fechas, y enlaces al escritorio de Frappe (/desk)

// Dentro del escritorio el panel se muestra en un iframe (página /desk/panel-cumplimiento)
export const embebido = (() => {
	try {
		return window.self !== window.top && Boolean(window.top.frappe)
	} catch {
		return false
	}
})()

const moneda = new Intl.NumberFormat("es-DO", {
	style: "currency",
	currency: "DOP",
	minimumFractionDigits: 2,
})
const fecha = new Intl.DateTimeFormat("es-DO", { day: "numeric", month: "short", year: "numeric" })

export const MESES = [
	"Enero",
	"Febrero",
	"Marzo",
	"Abril",
	"Mayo",
	"Junio",
	"Julio",
	"Agosto",
	"Septiembre",
	"Octubre",
	"Noviembre",
	"Diciembre",
]

export function formatoMoneda(valor) {
	return moneda.format(Number(valor) || 0)
}

export function formatoNumero(valor) {
	return new Intl.NumberFormat("es-DO").format(Number(valor) || 0)
}

// Las fechas llegan como "AAAA-MM-DD": se leen como fecha local, sin zona horaria
export function aFecha(valor) {
	if (!valor) return null
	const [a, m, d] = String(valor).slice(0, 10).split("-").map(Number)
	return new Date(a, m - 1, d)
}

export function formatoFecha(valor) {
	const f = aFecha(valor)
	return f ? fecha.format(f) : "—"
}

export function diasHasta(valor) {
	const f = aFecha(valor)
	if (!f) return null
	const hoy = new Date()
	hoy.setHours(0, 0, 0, 0)
	return Math.round((f - hoy) / 86400000)
}

// "Formato 606 DGII" -> /desk/query-report/Formato 606 DGII?company=...
export function rutaReporte(reporte, filtros = {}) {
	const params = new URLSearchParams(filtros)
	return `/desk/query-report/${encodeURIComponent(reporte)}?${params}`
}

export function rutaDocumento(doctype, nombre) {
	const slug = doctype.toLowerCase().replace(/ /g, "-")
	return nombre ? `/desk/${slug}/${encodeURIComponent(nombre)}` : `/desk/${slug}`
}
