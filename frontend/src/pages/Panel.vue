<template>
	<PageHeader>
		<PageHeaderTitle title="Panel de cumplimiento" class="max-sm:hidden" />
		<div v-if="ctx.data?.empresas?.length" class="flex items-center gap-2 max-sm:w-full">
			<Select
				v-if="ctx.data.empresas.length > 1"
				v-model="empresa"
				class="w-56 max-sm:min-w-0 max-sm:flex-1"
				:options="ctx.data.empresas.map((e) => ({ label: e.company_name, value: e.name }))"
			/>
			<Select v-model="mes" class="w-32 max-sm:min-w-0 max-sm:flex-1" :options="opcionesMes" />
			<Select v-model="anio" class="w-24 shrink-0" :options="opcionesAnio" />
			<Button
				icon="lucide-refresh-cw"
				tooltip="Actualizar"
				:loading="datos.loading"
				@click="datos.reload()"
			/>
		</div>
	</PageHeader>

	<div class="mx-auto w-full max-w-6xl space-y-8 px-5 py-6">
		<Alert
			v-if="ctx.error || datos.error"
			theme="red"
			title="No se pudo cargar el panel"
			:description="(ctx.error || datos.error)?.message"
		/>
		<Alert
			v-else-if="ctx.data && !ctx.data.empresas.length"
			theme="blue"
			title="No hay empresas de República Dominicana"
			description="El panel muestra las empresas con país Dominican Republic. Configure el país de la empresa para ver su estado fiscal."
		/>

		<div v-if="!r && datos.loading" class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
			<Skeleton v-for="i in 6" :key="i" class="h-40 rounded-lg" />
		</div>

		<template v-if="r">
			<!-- Lo urgente primero -->
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
					Declaraciones de {{ MESES[r.periodo.mes - 1].toLowerCase() }} {{ r.periodo.anio }}
				</h2>
				<div class="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
					<Tarjeta
						v-for="f in r.formatos"
						:key="f.formato"
						:titulo="`Formato ${f.formato}`"
						:subtitulo="SUBTITULOS[f.formato]"
						:vence="f.vence"
						:valor="formatoNumero(f.registros)"
						:etiqueta-valor="f.registros === 1 ? 'registro en el TXT' : 'registros en el TXT'"
						:detalle="detalleFormato(f)"
						:enlace="rutaReporte(f.reporte, filtros)"
					/>

					<Tarjeta
						titulo="IT-1"
						subtitulo="Declaración de ITBIS"
						:vence="r.it1.vence"
						:valor="formatoMoneda(r.it1.total_a_pagar)"
						etiqueta-valor="Total a pagar"
						:detalle="[
							{ label: 'ITBIS facturado', valor: formatoMoneda(r.it1.itbis_facturado) },
							{ label: 'ITBIS deducible', valor: formatoMoneda(r.it1.itbis_deducible) },
							{ label: 'ITBIS retenido a terceros', valor: formatoMoneda(r.it1.itbis_retenido_a_terceros) },
							...(r.it1.nuevo_saldo_favor
								? [{ label: 'Saldo a favor', valor: formatoMoneda(r.it1.nuevo_saldo_favor), clase: 'text-ink-green-6' }]
								: []),
						]"
						:enlace="rutaReporte('Resumen IT-1 DGII', filtros)"
						texto-enlace="Abrir resumen"
					/>

					<Tarjeta
						titulo="IR-17"
						subtitulo="Retenciones de ISR"
						:vence="r.ir17.total_isr ? r.ir17.vence : null"
						:valor="formatoMoneda(r.ir17.total_isr)"
						:etiqueta-valor="r.ir17.total_isr ? 'ISR retenido' : 'Sin retenciones: no hay que presentarlo'"
						:detalle="r.ir17.grupos.map((g) => ({ label: g.concepto, valor: formatoMoneda(g.isr) }))"
						:enlace="rutaReporte('Resumen IR-17 DGII', filtros)"
						texto-enlace="Abrir resumen"
					/>
				</div>
			</section>

			<section>
				<div class="mb-3 flex items-center justify-between">
					<h2 class="text-lg-semibold text-ink-gray-8">Secuencias NCF</h2>
					<Button
						variant="ghost"
						label="Ver todas"
						icon-right="lucide-arrow-up-right"
						:href="rutaDocumento('Secuencia NCF')"
					/>
				</div>
				<div
					v-if="!r.secuencias.length"
					class="flex flex-col items-center gap-3 rounded-lg border border-dashed border-outline-gray-2 px-4 py-8 text-center"
				>
					<p class="text-base text-ink-gray-5">Esta empresa no tiene secuencias NCF registradas.</p>
					<Button
						variant="subtle"
						icon-left="lucide-plus"
						label="Registrar secuencia"
						:href="rutaDocumento('Secuencia NCF', 'new')"
					/>
				</div>
				<div v-else class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2">
					<div
						v-for="s in r.secuencias"
						:key="s.name"
						class="grid grid-cols-[4rem_1fr] items-center gap-x-4 gap-y-2 px-4 py-3 sm:grid-cols-[4rem_1fr_9rem_8rem]"
					>
						<a
							:href="rutaDocumento('Secuencia NCF', s.name)"
							class="text-base-medium text-ink-gray-8 hover:underline"
						>
							{{ s.tipo_comprobante }}
						</a>
						<Progress :value="s.usado" size="md" hint>
							<template #hint>
								<span class="text-sm tabular-nums text-ink-gray-5">
									{{ formatoNumero(s.disponibles) }} de {{ formatoNumero(s.total) }} disponibles
								</span>
							</template>
						</Progress>
						<div class="text-sm text-ink-gray-5 sm:text-right">
							{{ s.fecha_vencimiento ? `Vence ${formatoFecha(s.fecha_vencimiento)}` : "Sin vencimiento" }}
						</div>
						<div class="sm:text-right">
							<Badge
								variant="subtle"
								:theme="ESTADOS[s.estado].theme"
								:label="ESTADOS[s.estado].label"
							/>
						</div>
					</div>
				</div>
			</section>

			<section>
				<h2 class="mb-1 text-lg-semibold text-ink-gray-8">Observaciones</h2>
				<p class="mb-3 text-p-sm text-ink-gray-5">
					Registros que la DGII podría rechazar: RNC o cédula inválidos, NCF duplicados o datos
					faltantes. Corríjalos antes de enviar los formatos.
				</p>
				<div
					v-if="!r.avisos.total"
					class="flex items-center gap-2 rounded-lg border border-outline-gray-2 px-4 py-3 text-base text-ink-gray-6"
				>
					<span class="lucide-circle-check size-4 text-ink-green-6" />
					Sin observaciones en el período.
				</div>
				<div v-else class="divide-y divide-outline-gray-1 rounded-lg border border-outline-gray-2">
					<div
						v-for="(a, i) in r.avisos.lista"
						:key="i"
						class="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2.5"
					>
						<Badge variant="outline" theme="gray" :label="a.formato" />
						<a
							:href="rutaDocumento(a.doctype, a.documento)"
							class="text-base-medium text-ink-gray-8 hover:underline"
						>
							{{ a.documento }}
						</a>
						<span class="text-p-sm text-ink-amber-8">{{ a.aviso }}</span>
					</div>
					<div v-if="r.avisos.total > r.avisos.lista.length" class="px-4 py-2.5 text-sm text-ink-gray-5">
						Mostrando {{ r.avisos.lista.length }} de {{ r.avisos.total }}. Vea el resto en cada reporte.
					</div>
				</div>
			</section>

			<footer class="flex flex-wrap gap-x-4 gap-y-1 border-t border-outline-gray-1 pt-4 text-sm text-ink-gray-5">
				<span>
					Padrón RNC:
					{{
						r.padron.registros
							? `${formatoNumero(r.padron.registros)} contribuyentes, actualizado ${formatoFecha(r.padron.ultima_sincronizacion)}`
							: "sin descargar"
					}}
				</span>
				<span>Los plazos no corren por días feriados.</span>
			</footer>
		</template>
	</div>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import {
	Alert,
	Badge,
	Button,
	PageHeader,
	PageHeaderTitle,
	Progress,
	Select,
	Skeleton,
	useCall,
} from "frappe-ui"

import Tarjeta from "@/components/Tarjeta.vue"
import {
	MESES,
	diasHasta,
	formatoFecha,
	formatoMoneda,
	formatoNumero,
	rutaDocumento,
	rutaReporte,
} from "@/utils"

const API = "/api/v2/method/erpnext_rd.rd_compliance.panel"

const SUBTITULOS = {
	606: "Compras de bienes y servicios",
	607: "Ventas de bienes y servicios",
	608: "Comprobantes anulados",
	609: "Pagos al exterior",
}

const ESTADOS = {
	ok: { label: "Al día", theme: "green" },
	por_agotarse: { label: "Por agotarse", theme: "amber" },
	por_vencer: { label: "Por vencer", theme: "amber" },
	agotada: { label: "Agotada", theme: "red" },
	vencida: { label: "Vencida", theme: "red" },
	deshabilitada: { label: "Deshabilitada", theme: "gray" },
}

const empresa = ref(null)
const anio = ref(null)
const mes = ref(null)

const ctx = useCall({
	url: `${API}.contexto`,
	onSuccess(d) {
		empresa.value = d.empresa
		anio.value = d.anio
		mes.value = d.mes
	},
})

const datos = useCall({
	url: `${API}.resumen`,
	params: () => ({ company: empresa.value, anio: anio.value, mes: mes.value }),
	immediate: false,
})

watch([empresa, anio, mes], () => {
	if (empresa.value && anio.value && mes.value) datos.reload()
})

const r = computed(() => datos.data)
const filtros = computed(() => ({ company: empresa.value, anio: anio.value, mes: mes.value }))

const opcionesMes = MESES.map((label, i) => ({ label, value: i + 1 }))
const opcionesAnio = computed(() => {
	const actual = new Date().getFullYear()
	return Array.from({ length: 6 }, (_, i) => ({ label: String(actual - i), value: actual - i }))
})

function detalleFormato(f) {
	const detalle = []
	if (f.monto !== null) detalle.push({ label: "Monto", valor: formatoMoneda(f.monto) })
	detalle.push({
		label: "Con observaciones",
		valor: formatoNumero(f.con_avisos),
		clase: f.con_avisos ? "text-ink-amber-8" : "text-ink-gray-8",
	})
	return detalle
}

// Avisos que requieren acción, de más a menos grave
const alertas = computed(() => {
	if (!r.value) return []
	const lista = []
	const sec = r.value.secuencias

	if (!sec.length) {
		lista.push({
			theme: "amber",
			title: "La empresa no tiene secuencias NCF",
			description:
				"Sin secuencias no se pueden validar facturas con comprobante fiscal. Registre los rangos que le autorizó la DGII en la Oficina Virtual.",
			accion: { label: "Registrar secuencia", href: rutaDocumento("Secuencia NCF", "new") },
		})
	}

	const sinNumeros = sec.filter((s) => ["agotada", "vencida"].includes(s.estado))
	if (sinNumeros.length) {
		lista.push({
			theme: "red",
			title: `Secuencias NCF sin números: ${sinNumeros.map((s) => s.tipo_comprobante).join(", ")}`,
			description:
				"No se pueden emitir comprobantes de estos tipos. Solicite una nueva autorización en la Oficina Virtual y regístrela.",
			accion: { label: "Nueva secuencia", href: rutaDocumento("Secuencia NCF", "new") },
		})
	}

	const enAlerta = sec.filter((s) => ["por_agotarse", "por_vencer"].includes(s.estado))
	if (enAlerta.length) {
		lista.push({
			theme: "amber",
			title: `Secuencias NCF por agotarse o vencer: ${enAlerta.map((s) => s.tipo_comprobante).join(", ")}`,
			description: "Solicite la próxima autorización de NCF antes de que se agoten.",
		})
	}

	if (r.value.avisos.total) {
		const n = r.value.avisos.total
		const vence = r.value.formatos[0].vence
		const dias = diasHasta(vence)
		lista.push({
			theme: "amber",
			title: `${n} ${n === 1 ? "registro tiene" : "registros tienen"} observaciones`,
			description:
				dias >= 0
					? `Corríjalos antes del ${formatoFecha(vence)}, cuando vence el envío de los formatos.`
					: "Revíselos en la sección Observaciones.",
		})
	}

	if (!r.value.padron.registros) {
		lista.push({
			theme: "blue",
			title: "El padrón RNC aún no se ha descargado",
			description:
				"Se descarga solo en segundo plano. Mientras tanto no se autocompleta la razón social al escribir un RNC.",
		})
	}
	return lista
})
</script>
