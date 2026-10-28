<!-- Escanear facturas desde el celular: el QR del e-CF con la cámara, o una foto o el PDF de la factura.
     Se instala en la pantalla de inicio (PWA) y funciona sin conexión: lo capturado se envía al volver. -->
<template>
	<PageHeader>
		<PageHeaderTitle :title="__('Escanear facturas')" />
		<Instalar />
	</PageHeader>

	<div class="mx-auto w-full max-w-md space-y-5 px-4 py-4">
		<Alert v-if="ctx.error" theme="red" :title="__('No se pudo cargar')" :description="ctx.error.message" />
		<Alert
			v-if="pendientes.length"
			theme="amber"
			:title="__('{0} capturas sin enviar', [pendientes.length])"
			:description="__('Se envían solas al volver la conexión.')"
		>
			<template #actions>
				<Button :label="__('Enviar ahora')" :loading="enviando" @click="vaciarCola" />
			</template>
		</Alert>
		<Alert v-if="aviso" :theme="aviso.theme" :title="aviso.title" :description="aviso.description" />

		<Select
			v-if="empresas.length > 1"
			v-model="empresa"
			:options="empresas.map((e) => ({ label: e.company_name, value: e.name }))"
		/>

		<!-- Paso 1: leer el comprobante -->
		<div v-if="!leido" class="space-y-3">
			<div v-show="camara" class="overflow-hidden rounded-6 border border-outline-gray-2 bg-surface-gray-2">
				<video ref="video" class="aspect-square w-full object-cover" muted playsinline />
			</div>
			<Button
				v-if="!camara"
				variant="solid"
				size="lg"
				class="w-full"
				icon-left="lucide-scan-qr-code"
				:label="__('Escanear el QR')"
				:disabled="!empresa"
				@click="abrirCamara"
			/>
			<Button
				v-else
				size="lg"
				class="w-full"
				icon-left="lucide-x"
				:label="__('Cerrar la cámara')"
				@click="cerrarCamara"
			/>
			<Button
				size="lg"
				class="w-full"
				icon-left="lucide-file-image"
				:label="__('Foto o PDF de la factura')"
				:disabled="!empresa"
				@click="selector.click()"
			/>
			<input
				ref="selector"
				type="file"
				class="hidden"
				accept="image/*,application/pdf"
				capture="environment"
				@change="elegirArchivo"
			/>
			<p class="text-p-sm text-ink-gray-5">
				{{
					__(
						"Apunte la cámara al QR de la factura electrónica. Si es un PDF que le enviaron, súbalo: se leen el ITBIS y el total.",
					)
				}}
			</p>
		</div>

		<!-- Paso 2: revisar y enviar -->
		<div v-else class="space-y-4 rounded-6 border border-outline-gray-2 bg-surface-base p-4">
			<dl class="space-y-1.5 text-base">
				<div v-for="d in datosLeidos" :key="d.label" class="flex justify-between gap-3">
					<dt class="text-ink-gray-5">{{ d.label }}</dt>
					<dd class="text-right font-medium tabular-nums text-ink-gray-8">{{ d.valor }}</dd>
				</div>
			</dl>
			<FormControl
				v-if="!esPdf"
				v-model="itbis"
				type="number"
				inputmode="decimal"
				:label="__('ITBIS facturado')"
				:placeholder="sugerencia"
				:description="
					__('Como aparece en la factura. Si no tiene ITBIS, escriba 0. Puede completarlo después.')
				"
			/>
			<FormControl v-model="tipo606" type="select" :label="__('Tipo de gasto (606)')" :options="opciones606" />
			<div class="flex gap-2">
				<Button class="flex-1" size="lg" :label="__('Cancelar')" @click="reiniciar" />
				<Button
					class="flex-1"
					size="lg"
					variant="solid"
					:label="__('Enviar')"
					:loading="enviando"
					@click="enviarCaptura"
				/>
			</div>
		</div>
	</div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, useTemplateRef } from "vue"
import { Alert, Button, FormControl, PageHeader, PageHeaderTitle, Select } from "frappe-ui"

import Instalar from "@/components/Instalar.vue"
import {
	actualizarPendientes,
	api,
	comprimir,
	enviar,
	enviarPendientes,
	escaner,
	leerUrl,
	pendientes,
	qrDeImagen,
} from "@/captura"
import { __ } from "@/translation"
import { formatoMoneda } from "@/utils"

const ctx = ref({ data: null, error: null })
const empresa = ref(null)
const empresas = computed(() => ctx.value.data?.empresas || [])
const opciones606 = computed(() => [
	{ label: __("Según el proveedor"), value: "" },
	...(ctx.value.data?.tipos_606 || []).map((t) => ({ label: t, value: t })),
])

const video = useTemplateRef("video")
const selector = useTemplateRef("selector")
const camara = ref(null)
const url = ref(null)
const archivo = ref(null)
const itbis = ref("")
const tipo606 = ref("")
const enviando = ref(false)
const aviso = ref(null)

const qr = computed(() => (url.value ? leerUrl(url.value) : null))
const esPdf = computed(() => archivo.value?.type === "application/pdf")
const leido = computed(() => Boolean(url.value || archivo.value))
const sugerencia = computed(() =>
	qr.value?.montoTotal ? __("Si es 18 %: {0}", [((qr.value.montoTotal * 18) / 118).toFixed(2)]) : "",
)
const datosLeidos = computed(() => {
	if (!qr.value) return [{ label: __("Archivo"), valor: archivo.value?.name || "" }]
	return [
		{ label: __("e-NCF"), valor: qr.value.encf },
		{ label: __("RNC del emisor"), valor: qr.value.rncEmisor },
		{ label: __("Fecha"), valor: qr.value.fechaEmision || "—" },
		{ label: __("Total"), valor: formatoMoneda(qr.value.montoTotal) },
	]
})

onMounted(async () => {
	try {
		ctx.value.data = await api.get("contexto")
		empresa.value = ctx.value.data.empresa
		localStorage.setItem("rd-compliance-contexto", JSON.stringify(ctx.value.data))
	} catch (error) {
		// Sin conexión: el último contexto que se cargó
		const guardado = JSON.parse(localStorage.getItem("rd-compliance-contexto") || "null")
		if (guardado) {
			ctx.value.data = guardado
			empresa.value = guardado.empresa
		} else ctx.value.error = error
	}
	await actualizarPendientes()
	window.addEventListener("online", vaciarCola)
	if (navigator.onLine && pendientes.value.length) vaciarCola()
})

onBeforeUnmount(() => {
	cerrarCamara()
	window.removeEventListener("online", vaciarCola)
})

async function abrirCamara() {
	aviso.value = null
	camara.value = escaner(video.value, (texto) => {
		if (!leerUrl(texto)) {
			aviso.value = { theme: "amber", title: __("Ese QR no es de una factura electrónica de la DGII") }
			return
		}
		url.value = texto
		cerrarCamara()
	})
	try {
		await camara.value.start()
	} catch {
		cerrarCamara()
		aviso.value = {
			theme: "red",
			title: __("No se pudo abrir la cámara"),
			description: __("Permita el uso de la cámara o tome una foto de la factura."),
		}
	}
}

function cerrarCamara() {
	camara.value?.destroy()
	camara.value = null
}

async function elegirArchivo(evento) {
	const elegido = evento.target.files?.[0]
	evento.target.value = ""
	if (!elegido) return
	aviso.value = null
	if (elegido.type.startsWith("image/")) {
		const texto = await qrDeImagen(elegido)
		if (texto && leerUrl(texto)) url.value = texto
		else
			aviso.value = {
				theme: "amber",
				title: __("No se encontró el QR en la foto"),
				description: __("Se enviará la foto y el contador completará los datos."),
			}
		archivo.value = new File([await comprimir(elegido)], nombreFoto(), { type: "image/jpeg" })
	} else {
		archivo.value = elegido
	}
}

function nombreFoto() {
	return `factura-${new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14)}.jpg`
}

async function enviarCaptura() {
	enviando.value = true
	aviso.value = null
	try {
		const resultado = await enviar({
			company: empresa.value,
			url_timbre: url.value,
			archivo: archivo.value,
			nombre_archivo: archivo.value?.name,
			total_itbis: itbis.value === "" ? null : Number(itbis.value),
			rd_tipo_bienes_servicios: tipo606.value,
		})
		aviso.value = resultado.enviada
			? {
					theme: resultado.captura.estado === "Requiere revisión" ? "amber" : "green",
					title: __("Factura enviada: {0}", [resultado.captura.encf || resultado.captura.name]),
					description: resultado.captura.avisos || __("Estado: {0}", [__(resultado.captura.estado)]),
				}
			: {
					theme: "amber",
					title: __("Sin conexión: la captura quedó guardada en el celular"),
					description: __("Se enviará al volver la conexión."),
				}
		reiniciar()
	} catch (error) {
		aviso.value = { theme: "red", title: __("No se pudo enviar"), description: error.message }
	} finally {
		enviando.value = false
	}
}

function reiniciar() {
	url.value = null
	archivo.value = null
	itbis.value = ""
	tipo606.value = ""
}

async function vaciarCola() {
	if (enviando.value) return
	enviando.value = true
	try {
		const errores = await enviarPendientes()
		if (errores.length)
			aviso.value = { theme: "red", title: __("Capturas rechazadas"), description: errores.join("\n") }
	} finally {
		enviando.value = false
	}
}
</script>
