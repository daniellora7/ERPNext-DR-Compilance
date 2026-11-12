<template>
	<PageHeader>
		<PageHeaderTitle :title="__('Monitor de e-CF')" class="max-sm:hidden" />
		<div v-if="ctx.data?.empresas?.length" class="flex items-center gap-2 max-sm:w-full">
			<Select
				v-if="ctx.data.empresas.length > 1"
				v-model="empresa"
				class="w-56 max-sm:min-w-0 max-sm:flex-1"
				:options="ctx.data.empresas.map((e) => ({ label: e.company_name, value: e.name }))"
			/>
			<Select v-model="dias" class="w-40 max-sm:min-w-0 max-sm:flex-1" :options="opcionesDias" />
			<Button
				icon="lucide-refresh-cw"
				:tooltip="__('Actualizar')"
				:loading="datos.loading"
				@click="datos.reload()"
			/>
		</div>
	</PageHeader>

	<div class="mx-auto w-full max-w-6xl space-y-8 px-5 py-6">
		<Alert
			v-if="ctx.error || datos.error"
			theme="red"
			:title="__('No se pudo cargar el monitor')"
			:description="(ctx.error || datos.error)?.message"
		/>

		<div v-if="!r && datos.loading" class="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(10rem,1fr))]">
			<Skeleton v-for="i in 6" :key="i" class="h-24 rounded-6" />
		</div>

		<template v-if="r">
			<section v-if="alertas.length" class="space-y-2">
				<Alert
					v-for="a in alertas"
					:key="a.title"
					:theme="a.theme"
					:title="a.title"
					:description="a.description"
					:primary-action="a.accion"
				/>
			</section>

			<section>
				<h2 class="mb-3 text-lg-semibold text-ink-gray-8">
					{{ __("Envíos de los últimos {0} días", [r.dias]) }}
					<span class="text-base text-ink-gray-5">· {{ __("Ambiente {0}", [r.ambiente]) }}</span>
				</h2>
				<div class="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(10rem,1fr))]">
					<a
						v-for="c in cifras"
						:key="c.estado"
						:href="rutaEnvios({ estado: c.estado, company: empresa })"
						class="rounded-6 border border-outline-gray-2 bg-surface-base px-4 py-3 transition-colors hover:bg-surface-gray-1"
					>
						<div class="text-sm text-ink-gray-5">{{ c.label }}</div>
						<div class="mt-1 text-2xl-semibold tabular-nums" :class="c.valor ? c.clase : 'text-ink-gray-8'">
							{{ formatoNumero(c.valor) }}
						</div>
					</a>
				</div>
			</section>

			<Lista
				v-if="r.contingencia.length"
				:titulo="__('En contingencia')"
				:descripcion="
					__(
						'La DGII no respondió. Los e-CF ya firmados son válidos y se reenvían solos, cada vez más espaciado; puede reenviarlos ahora.',
					)
				"
				:filas="r.contingencia"
			>
				<template #fila="{ fila }">
					<FilaEnvio :envio="fila">
						<span class="text-sm text-ink-gray-5">
							{{ __("Intentos: {0}", [fila.intentos || 0]) }}
							<template v-if="fila.proximo_intento">
								· {{ __("próximo {0}", [formatoFechaHora(fila.proximo_intento)]) }}
							</template>
						</span>
						<template #accion>
							<Button
								size="sm"
								:label="__('Reenviar')"
								:loading="enCurso === fila.name"
								@click="reenviar(fila)"
							/>
						</template>
					</FilaEnvio>
				</template>
			</Lista>

			<Lista
				v-if="r.con_problemas.length"
				:titulo="__('Rechazados, con error o aceptados con condiciones')"
				:descripcion="
					__(
						'Un e-CF rechazado no tiene validez fiscal: corrija la factura y emita un comprobante nuevo. Los aceptados con condiciones son válidos, pero revise el mensaje de la DGII.',
					)
				"
				:filas="r.con_problemas"
			>
				<template #fila="{ fila }">
					<FilaEnvio :envio="fila">
						<p v-if="fila.mensajes" class="line-clamp-2 text-p-sm text-ink-gray-6">{{ fila.mensajes }}</p>
						<template v-if="fila.estado === 'Error'" #accion>
							<Button
								size="sm"
								:label="__('Reenviar')"
								:loading="enCurso === fila.name"
								@click="reenviar(fila)"
							/>
						</template>
					</FilaEnvio>
				</template>
			</Lista>

			<Lista
				v-if="r.entregas.fallidas.length"
				:titulo="__('Entregas al comprador fallidas')"
				:descripcion="
					__(
						'El comprador es receptor electrónico y no acusó recibo. Se reintenta solo hasta {0} veces.',
						[r.entregas.maximo_intentos],
					)
				"
				:filas="r.entregas.fallidas"
			>
				<template #fila="{ fila }">
					<FilaEnvio :envio="fila">
						<span class="text-sm text-ink-amber-8">
							{{ __(fila.estado_comprador) }} · {{ __("Intentos: {0}", [fila.intentos_comprador || 0]) }}
						</span>
						<template #accion>
							<Button
								size="sm"
								:label="__('Entregar')"
								:loading="enCurso === fila.name"
								@click="entregar(fila)"
							/>
						</template>
					</FilaEnvio>
				</template>
			</Lista>

			<Lista
				v-if="r.sin_emitir.length"
				:titulo="__('Facturas sin e-CF')"
				:descripcion="
					__(
						'Facturas aprobadas con comprobante electrónico que aún no tienen e-CF. Emítalo desde la factura con «e-CF › Emitir».',
					)
				"
				:filas="r.sin_emitir"
			>
				<template #fila="{ fila }">
					<div class="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2.5">
						<a
							:href="rutaDocumento(fila.doctype, fila.name)"
							class="text-base-medium text-ink-gray-8 hover:underline"
						>
							{{ fila.rd_ncf || fila.name }}
						</a>
						<Badge variant="outline" theme="gray" :label="fila.rd_tipo_comprobante" />
						<span class="text-sm text-ink-gray-5">{{ formatoFecha(fila.posting_date) }}</span>
						<span class="text-sm tabular-nums text-ink-gray-6">{{ formatoMoneda(fila.grand_total) }}</span>
					</div>
				</template>
			</Lista>

			<Lista
				v-if="recibidosPendientes.length"
				:titulo="__('e-CF recibidos por aprobar')"
				:descripcion="
					__(
						'Comprobantes electrónicos de proveedores con la aprobación comercial pendiente o cuyo envío falló.',
					)
				"
				:filas="recibidosPendientes"
			>
				<template #fila="{ fila }">
					<div class="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2.5">
						<a
							:href="rutaDocumento('ECF Recibido', fila.name)"
							class="text-base-medium text-ink-gray-8 hover:underline"
						>
							{{ fila.encf }}
						</a>
						<span class="text-sm text-ink-gray-6">{{ fila.razon_social_emisor }}</span>
						<span class="text-sm tabular-nums text-ink-gray-6">{{ formatoMoneda(fila.monto_total) }}</span>
						<span class="text-sm text-ink-gray-5">{{ formatoFecha(fila.fecha_emision) }}</span>
						<Badge
							v-if="fila.envio_aprobacion === 'Error'"
							variant="subtle"
							theme="red"
							:label="__('Error al enviar la aprobación')"
						/>
					</div>
				</template>
			</Lista>

			<section>
				<div class="mb-3 flex items-center justify-between">
					<h2 class="text-lg-semibold text-ink-gray-8">{{ __("Últimos envíos") }}</h2>
					<Button
						variant="ghost"
						:label="__('Ver todos')"
						icon-right="lucide-arrow-up-right"
						:href="rutaEnvios({ company: empresa })"
					/>
				</div>
				<div
					v-if="!r.ultimos.length"
					class="rounded-6 border border-dashed border-outline-gray-2 px-4 py-8 text-center text-base text-ink-gray-5"
				>
					{{ __("Esta empresa aún no ha emitido e-CF.") }}
				</div>
				<div v-else class="divide-y divide-outline-gray-1 rounded-6 border border-outline-gray-2 bg-surface-base">
					<FilaEnvio v-for="e in r.ultimos" :key="e.name" :envio="e">
						<span v-if="e.estado_comprador" class="text-sm text-ink-gray-5">
							{{ __("Comprador: {0}", [__(e.estado_comprador)]) }}
						</span>
					</FilaEnvio>
				</div>
			</section>
		</template>
	</div>
</template>

<script setup>
import { computed, defineComponent, h, ref, watch } from "vue"
import { Alert, Badge, Button, PageHeader, PageHeaderTitle, Select, Skeleton, toast, useCall } from "frappe-ui"

import { __ } from "@/translation"
import { formatoFecha, formatoFechaHora, formatoMoneda, formatoNumero, rutaDocumento } from "@/utils"

const API = "/api/v2/method/erpnext_rd"

// Tema del estado de un envío (los nombres son los del registro Envio ECF)
const TEMA = {
	Aceptado: "green",
	"Aceptado condicional": "amber",
	Rechazado: "red",
	Error: "red",
	Contingencia: "amber",
	"En proceso": "blue",
	Firmado: "gray",
}

const empresa = ref(null)
const dias = ref(30)
const enCurso = ref(null)

const opcionesDias = [7, 30, 90, 365].map((d) => ({ label: __("Últimos {0} días", [d]), value: d }))

const ctx = useCall({
	url: `${API}.rd_compliance.panel.contexto`,
	onSuccess(d) {
		empresa.value = d.empresa
	},
})

const datos = useCall({
	url: `${API}.ecf.monitor.resumen`,
	params: () => ({ company: empresa.value, dias: dias.value }),
	immediate: false,
})

watch([empresa, dias], () => {
	if (empresa.value) datos.reload()
})

const r = computed(() => datos.data)
const recibidosPendientes = computed(() => (r.value ? [...r.value.recibidos.con_error, ...r.value.recibidos.pendientes] : []))

const cifras = computed(() => {
	const e = r.value.conteo.por_estado
	return [
		{ estado: "Aceptado", label: __("Aceptados"), valor: e.Aceptado, clase: "text-ink-green-6" },
		{ estado: "Aceptado condicional", label: __("Con condiciones"), valor: e["Aceptado condicional"], clase: "text-ink-amber-8" },
		{ estado: "Rechazado", label: __("Rechazados"), valor: e.Rechazado, clase: "text-ink-red-6" },
		{ estado: "Error", label: __("Con error"), valor: e.Error, clase: "text-ink-red-6" },
		{ estado: "En proceso", label: __("En proceso"), valor: e["En proceso"], clase: "text-ink-blue-6" },
		{ estado: "Contingencia", label: __("En contingencia"), valor: e.Contingencia, clase: "text-ink-amber-8" },
		{ estado: "Firmado", label: __("Firmados sin enviar"), valor: e.Firmado, clase: "text-ink-gray-8" },
	]
})

const alertas = computed(() => {
	if (!r.value) return []
	const lista = []
	const em = r.value.emisor
	const rutaEmisor = rutaDocumento("Emisor ECF", em.configurado ? empresa.value : "new")

	if (!em.configurado) {
		lista.push({
			theme: "amber",
			title: __("La empresa no tiene emisor e-CF"),
			description: __(
				"Registre el emisor con el certificado digital (.p12) para firmar y enviar comprobantes electrónicos.",
			),
			accion: { label: __("Configurar emisor"), href: rutaEmisor },
		})
		return lista
	}
	if (em.certificado === "vencido") {
		lista.push({
			theme: "red",
			title: __("El certificado digital venció el {0}", [formatoFecha(em.vigente_hasta)]),
			description: __("No se pueden firmar e-CF. Renueve el certificado y súbalo al emisor."),
			accion: { label: __("Abrir emisor"), href: rutaEmisor },
		})
	} else if (em.certificado === "por_vencer") {
		lista.push({
			theme: "amber",
			title: __("El certificado digital vence en {0} días", [em.dias_certificado]),
			description: __("Solicite la renovación a su entidad certificadora antes del {0}.", [formatoFecha(em.vigente_hasta)]),
			accion: { label: __("Abrir emisor"), href: rutaEmisor },
		})
	}
	if (!em.habilitado) {
		lista.push({
			theme: "blue",
			title: __("El envío a la DGII está deshabilitado"),
			description: __("Los e-CF se firman y se guardan, pero no se envían. Habilítelo en el emisor cuando esté autorizado."),
			accion: { label: __("Abrir emisor"), href: rutaEmisor },
		})
	}
	if (r.value.ambiente !== "eCF") {
		lista.push({
			theme: "blue",
			title: __("Ambiente de pruebas: {0}", [r.value.ambiente]),
			description: __("Los e-CF de este ambiente no tienen validez fiscal. Cámbielo a eCF en la Configuración DGII al pasar a producción."),
		})
	}
	if (r.value.entregas.pendientes) {
		lista.push({
			theme: "blue",
			title: __("{0} e-CF por entregar al comprador", [r.value.entregas.pendientes]),
			description: __("Se entregan solos en segundo plano a los compradores que son receptores electrónicos."),
		})
	}
	return lista
})

function rutaEnvios(filtros) {
	const params = new URLSearchParams(Object.entries(filtros).filter(([, v]) => v))
	return `${rutaDocumento("Envio ECF")}?${params}`
}

const llamadaReenviar = useCall({ url: `${API}.ecf.emision.reenviar`, method: "POST", immediate: false })
const llamadaEntregar = useCall({ url: `${API}.ecf.emision.entregar`, method: "POST", immediate: false })

async function accion(llamada, fila, mensaje) {
	enCurso.value = fila.name
	try {
		const resultado = await llamada.submit({ envio: fila.name })
		toast.success(mensaje(__(resultado)))
		datos.reload()
	} catch (error) {
		toast.error(error.message || __("No se pudo completar la acción"))
	} finally {
		enCurso.value = null
	}
}

const reenviar = (fila) => accion(llamadaReenviar, fila, (estado) => __("e-CF {0}: {1}", [fila.encf, estado]))
const entregar = (fila) => accion(llamadaEntregar, fila, (estado) => __("Entrega de {0}: {1}", [fila.encf, estado]))

// Sección con título, explicación y una fila por elemento
const Lista = defineComponent({
	props: { titulo: String, descripcion: String, filas: Array },
	setup(props, { slots }) {
		return () =>
			h("section", [
				h("h2", { class: "mb-1 text-lg-semibold text-ink-gray-8" }, `${props.titulo} · ${props.filas.length}`),
				h("p", { class: "mb-3 text-p-sm text-ink-gray-5" }, props.descripcion),
				h(
					"div",
					{ class: "divide-y divide-outline-gray-1 rounded-6 border border-outline-gray-2 bg-surface-base" },
					props.filas.map((fila) => slots.fila({ fila })),
				),
			])
	},
})

// Un envío: e-NCF, tipo, estado y documento, con detalle y acción opcionales
const FilaEnvio = defineComponent({
	props: { envio: Object },
	setup(props, { slots }) {
		return () => {
			const e = props.envio
			return h("div", { class: "flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5" }, [
				h("div", { class: "flex min-w-0 flex-1 flex-col gap-1" }, [
					h("div", { class: "flex flex-wrap items-baseline gap-x-3 gap-y-1" }, [
						h(
							"a",
							{ href: rutaDocumento("Envio ECF", e.name), class: "text-base-medium text-ink-gray-8 hover:underline" },
							e.encf || e.name,
						),
						h(Badge, { variant: "subtle", theme: TEMA[e.estado] || "gray", label: __(e.estado) }),
						e.es_rfce ? h(Badge, { variant: "outline", theme: "gray", label: "RFCE" }) : null,
						e.documento
							? h(
									"a",
									{ href: rutaDocumento(e.tipo_documento, e.documento), class: "text-sm text-ink-gray-5 hover:underline" },
									e.documento,
								)
							: null,
						h("span", { class: "text-sm text-ink-gray-5" }, formatoFechaHora(e.fecha_firma || e.creation)),
					]),
					slots.default?.(),
				]),
				slots.accion ? h("div", { class: "shrink-0" }, slots.accion()) : null,
			])
		}
	},
})
</script>
