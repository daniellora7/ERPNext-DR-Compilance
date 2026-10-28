// Service worker de RD Compliance (/rd-compliance-sw.js, alcance /rd-compliance/).
// Abre la pantalla para escanear facturas sin conexión: las páginas se piden a la red y, si no hay,
// salen de la caché; los archivos compilados (con hash en el nombre) salen de la caché y se
// actualizan en segundo plano. La API nunca se guarda: las capturas sin conexión las guarda la
// pantalla en IndexedDB y las envía al volver la conexión.
const VERSION = "rd-compliance-v1"
const PAGINAS = `${VERSION}-paginas`
const ARCHIVOS = `${VERSION}-archivos`

self.addEventListener("install", () => self.skipWaiting())

self.addEventListener("activate", (evento) => {
	evento.waitUntil(
		caches
			.keys()
			.then((nombres) =>
				Promise.all(nombres.filter((n) => !n.startsWith(VERSION)).map((n) => caches.delete(n))),
			)
			.then(() => self.clients.claim()),
	)
})

self.addEventListener("fetch", (evento) => {
	const pedido = evento.request
	if (pedido.method !== "GET") return
	const url = new URL(pedido.url)
	if (url.origin !== location.origin) return

	if (pedido.mode === "navigate" && url.pathname.startsWith("/rd-compliance")) {
		evento.respondWith(redPrimero(pedido))
	} else if (url.pathname.startsWith("/assets/")) {
		evento.respondWith(cachePrimero(pedido))
	}
})

async function redPrimero(pedido) {
	const cache = await caches.open(PAGINAS)
	try {
		const respuesta = await fetch(pedido)
		if (respuesta.ok) cache.put(pedido, respuesta.clone())
		return respuesta
	} catch (error) {
		const guardada =
			(await cache.match(pedido, { ignoreSearch: true })) ||
			(await cache.match("/rd-compliance/escanear"))
		if (guardada) return guardada
		throw error
	}
}

async function cachePrimero(pedido) {
	const cache = await caches.open(ARCHIVOS)
	const guardada = await cache.match(pedido)
	const red = fetch(pedido)
		.then((respuesta) => {
			if (respuesta.ok) cache.put(pedido, respuesta.clone())
			return respuesta
		})
		.catch(() => guardada)
	return guardada || red
}
