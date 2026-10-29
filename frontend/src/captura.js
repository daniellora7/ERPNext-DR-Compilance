// Captura de facturas desde el celular: API, lectura del QR, compresión de fotos y cola sin conexión.
// Lo que no se pudo enviar (sin conexión, apagón) queda en IndexedDB y se envía al volver la conexión.

import QrScanner from "qr-scanner"
import { ref } from "vue"

const API = "/api/method/erpnext_rd.captura_compras.api."
const BASE = "rd-compliance-capturas"
const TABLA = "pendientes"
const LADO_MAXIMO = 2000

// ---------------------------------------------------------------- API

async function pedir(url, opciones = {}) {
	const respuesta = await fetch(url, {
		...opciones,
		headers: { Accept: "application/json", "X-Frappe-CSRF-Token": window.csrf_token, ...opciones.headers },
	})
	const datos = await respuesta.json().catch(() => ({}))
	if (!respuesta.ok) {
		const error = new Error(mensajeDeError(datos) || respuesta.statusText)
		error.validacion = respuesta.status === 417 || respuesta.status === 403
		throw error
	}
	return datos.message
}

function mensajeDeError(datos) {
	try {
		const lista = JSON.parse(datos._server_messages || "[]").map((m) => JSON.parse(m).message)
		return lista.join("\n").replace(/<[^>]+>/g, "")
	} catch {
		return datos.exception
	}
}

export const api = {
	get: (metodo, params = {}) => pedir(`${API}${metodo}?${new URLSearchParams(params)}`),
	post: (metodo, datos) =>
		pedir(API + metodo, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(datos),
		}),
}

async function subir(archivo, nombre) {
	const formulario = new FormData()
	formulario.append("file", archivo, nombre)
	formulario.append("is_private", "1")
	formulario.append("folder", "Home/Attachments")
	const subido = await pedir("/api/method/upload_file", { method: "POST", body: formulario })
	return subido.file_url
}

// ---------------------------------------------------------------- QR y fotos

/** Datos del QR para mostrarlos antes de enviar (el servidor los vuelve a validar). */
export function leerUrl(texto) {
	try {
		const url = new URL(texto.trim())
		if (!["ecf.dgii.gov.do", "fc.dgii.gov.do"].includes(url.hostname)) return null
		const p = Object.fromEntries([...url.searchParams].map(([k, v]) => [k.toLowerCase(), v]))
		if (!p.encf) return null
		return {
			encf: p.encf.toUpperCase(),
			rncEmisor: p.rncemisor,
			rncComprador: p.rnccomprador,
			fechaEmision: p.fechaemision,
			montoTotal: Number(p.montototal) || 0,
		}
	} catch {
		return null
	}
}

/** NCF serie B (11 caracteres) o e-NCF (13), como los valida el servidor. */
export const esNcf = (texto) => /^(B\d{10}|E\d{12})$/.test(texto)

/** Busca el QR en una foto. null si no lo encuentra. */
export async function qrDeImagen(archivo) {
	try {
		const { data } = await QrScanner.scanImage(archivo, { returnDetailedScanResult: true })
		return data || null
	} catch {
		return null
	}
}

export function escaner(video, alLeer) {
	return new QrScanner(video, (resultado) => alLeer(resultado.data), {
		preferredCamera: "environment",
		highlightScanRegion: true,
		returnDetailedScanResult: true,
	})
}

/** Foto en JPEG de máximo 2000 px por lado: las fotos del celular pesan varios MB. */
export async function comprimir(archivo) {
	if (!archivo.type.startsWith("image/")) return archivo
	const imagen = await createImageBitmap(archivo)
	const escala = Math.min(1, LADO_MAXIMO / Math.max(imagen.width, imagen.height))
	const lienzo = document.createElement("canvas")
	lienzo.width = Math.round(imagen.width * escala)
	lienzo.height = Math.round(imagen.height * escala)
	lienzo.getContext("2d").drawImage(imagen, 0, 0, lienzo.width, lienzo.height)
	return new Promise((listo) => lienzo.toBlob((blob) => listo(blob || archivo), "image/jpeg", 0.85))
}

// ---------------------------------------------------------------- cola sin conexión

function abrir() {
	return new Promise((listo, falla) => {
		const pedido = indexedDB.open(BASE, 1)
		pedido.onupgradeneeded = () => pedido.result.createObjectStore(TABLA, { keyPath: "id_cliente" })
		pedido.onsuccess = () => listo(pedido.result)
		pedido.onerror = () => falla(pedido.error)
	})
}

async function tabla(modo, accion) {
	const base = await abrir()
	return new Promise((listo, falla) => {
		const pedido = accion(base.transaction(TABLA, modo).objectStore(TABLA))
		pedido.onsuccess = () => listo(pedido.result)
		pedido.onerror = () => falla(pedido.error)
	})
}

export const pendientes = ref([])

export async function actualizarPendientes() {
	pendientes.value = await tabla("readonly", (t) => t.getAll()).catch(() => [])
}

/**
 * Envía una captura: sube el archivo (si hay) y crea la *Captura Compra*. Si no hay conexión queda en la
 * cola. Devuelve { enviada, captura } o lanza el error de validación del servidor (no se encola).
 */
export async function enviar(captura) {
	captura.id_cliente ||= crypto.randomUUID()
	try {
		const enviada = await enviarAhora(captura)
		return { enviada: true, captura: enviada }
	} catch (error) {
		if (error.validacion) throw error
		await tabla("readwrite", (t) => t.put({ ...captura, creada: Date.now() }))
		await actualizarPendientes()
		return { enviada: false }
	}
}

async function enviarAhora(captura) {
	const file_url = captura.archivo ? await subir(captura.archivo, captura.nombre_archivo) : undefined
	return api.post("crear", {
		company: captura.company,
		url_timbre: captura.url_timbre || undefined,
		file_url,
		total_itbis: captura.total_itbis ?? undefined,
		rd_tipo_bienes_servicios: captura.rd_tipo_bienes_servicios || undefined,
		id_cliente: captura.id_cliente,
		// Factura sin QR: lo que escribió el usuario
		rnc_emisor: captura.rnc_emisor || undefined,
		ncf: captura.ncf || undefined,
		fecha_emision: captura.fecha_emision || undefined,
		monto_total: captura.monto_total ?? undefined,
	})
}

/** e-NCF del QR, NCF escrito o nombre del archivo: para mostrar una captura de la cola. */
export function nombreCaptura(captura) {
	return leerUrl(captura.url_timbre || "")?.encf || captura.ncf || captura.nombre_archivo
}

/** Envía la cola. Las que el servidor rechaza (repetidas, de otra empresa) salen de la cola con su error. */
export async function enviarPendientes() {
	await actualizarPendientes()
	const errores = []
	for (const captura of pendientes.value) {
		try {
			await enviarAhora(captura)
		} catch (error) {
			if (!error.validacion) break
			errores.push(`${nombreCaptura(captura)}: ${error.message}`)
		}
		await tabla("readwrite", (t) => t.delete(captura.id_cliente))
	}
	await actualizarPendientes()
	return errores
}
