<template>
	<PageHeader>
		<PageHeaderTitle :title="__('Panel de cumplimiento')" class="max-sm:hidden" />
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
				:tooltip="__('Actualizar')"
				:loading="datos.loading"
				@click="datos.reload()"
			/>
		</div>
	</PageHeader>

	<div class="contenido-panel mx-auto w-full max-w-6xl space-y-8 px-5 py-6">
		<Alert
			v-if="ctx.error || datos.error"
			theme="red"
			:title="__('No se pudo cargar el panel')"
			:description="(ctx.error || datos.error)?.message"
		/>
		<Alert
			v-else-if="ctx.data && !ctx.data.empresas.length"
			theme="blue"
			:title="__('No hay empresas de República Dominicana')"
			:description="
				__(
					'El panel muestra las empresas con país Dominican Republic. Configure el país de la empresa para ver su estado fiscal.',
				)
			"
		/>

		<div v-if="!r && datos.loading" class="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(16rem,1fr))]">
			<Skeleton v-for="i in 6" :key="i" class="h-48 rounded-6" />
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
					{{ __("Declaraciones de {0} {1}", [MESES[r.periodo.mes - 1].toLowerCase(), r.periodo.anio]) }}
				</h2>
				<div class="grid gap-4 [grid-template-columns:repeat(auto-fill,minmax(16rem,1fr))]">
					<Tarjeta
						v-for="f in r.formatos"
						:key="f.formato"
						:titulo="f.formato"
						:subtitulo="SUBTITULOS[f.formato]"
						:vence="f.vence"
						:valor="formatoNumero(f.registros)"
						:etiqueta-valor="f.registros === 1 ? __('registro en el TXT') : __('registros en el TXT')"
						:detalle="detalleFormato(f)"
						:enlace="rutaReporte(f.reporte, filtros)"
					/>

					<Tarjeta
						titulo="IT-1"
						:subtitulo="__('ITBIS')"
						:vence="r.it1.vence"
						:valor="formatoMoneda(r.it1.total_a_pagar)"
						:etiqueta-valor="__('Total a pagar')"
						:detalle="[
							{ label: __('ITBIS facturado'), valor: formatoMoneda(r.it1.itbis_facturado) },
							{ label: __('ITBIS deducible'), valor: formatoMoneda(r.it1.itbis_deducible) },
							{ label: __('ITBIS retenido a terceros'), valor: formatoMoneda(r.it1.itbis_retenido_a_terceros) },
							...(r.it1.nuevo_saldo_favor
								? [{ label: __('Saldo a favor'), valor: formatoMoneda(r.it1.nuevo_saldo_favor), clase: 'text-ink-green-6' }]
								: []),
						]"
						:enlace="rutaReporte('Resumen IT-1 DGII', filtros)"
						:texto-enlace="__('Abrir resumen')"
					/>

					<Tarjeta
						titulo="IR-17"
						:subtitulo="__('Retenciones ISR')"
						:vence="r.ir17.total_isr ? r.ir17.vence : null"
						:valor="formatoMoneda(r.ir17.total_isr)"
						:etiqueta-valor="r.ir17.total_isr ? __('ISR retenido') : __('Sin retenciones: no hay que presentarlo')"
						:detalle="r.ir17.grupos.map((g) => ({ label: g.concepto, valor: formatoMoneda(g.isr) }))"
						:enlace="rutaReporte('Resumen IR-17 DGII', filtros)"
						:texto-enlace="__('Abrir resumen')"
					/>
					<Tarjeta
						v-if="r.ecf"
						titulo="e-CF"
						:subtitulo="__('Últimos 30 días')"
						:valor="formatoNumero(r.ecf.aceptados)"
						:etiqueta-valor="__('aceptados por la DGII')"
						:detalle="[
							{
								label: __('Rechazados o con error'),
								valor: formatoNumero(r.ecf.rechazados),
								clase: r.ecf.rechazados ? 'text-ink-red-6' : 'text-ink-gray-8',
							},
							{
								label: __('En contingencia'),
								valor: formatoNumero(r.ecf.contingencia),
								clase: r.ecf.contingencia ? 'text-ink-amber-8' : 'text-ink-gray-8',
							},
							{
								label: __('Facturas sin e-CF'),
								valor: formatoNumero(r.ecf.sin_emitir),
								clase: r.ecf.sin_emitir ? 'text-ink-amber-8' : 'text-ink-gray-8',
							},
						]"
						:enlace="RUTA_MONITOR"
						:texto-enlace="__('Abrir monitor')"
					/>
				</div>
			</section>

			<section>
				<div class="mb-3 flex items-center justify-between">
					<h2 class="text-lg-semibold text-ink-gray-8">{{ __("Secuencias NCF") }}</h2>
					<Button
						variant="ghost"
						:label="__('Ver todas')"
						icon-right="lucide-arrow-up-right"
						:href="rutaDocumento('Secuencia NCF')"
					/>
				</div>
				<div
					v-if="!r.secuencias.length"
					class="flex flex-col items-center gap-3 rounded-6 border border-dashed border-outline-gray-2 px-4 py-8 text-center"
				>
					<p class="text-base text-ink-gray-5">{{ __("Esta empresa no tiene secuencias NCF registradas.") }}</p>
					<Button
						variant="subtle"
						icon-left="lucide-plus"
						:label="__('Registrar secuencia')"
						:href="rutaDocumento('Secuencia NCF', 'new')"
					/>
				</div>
				<div v-else class="divide-y divide-outline-gray-1 rounded-6 border border-outline-gray-2 bg-surface-base">
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
									{{ __("{0} de {1} disponibles", [formatoNumero(s.disponibles), formatoNumero(s.total)]) }}
								</span>
							</template>
						</Progress>
						<div class="text-sm text-ink-gray-5 sm:text-right">
							{{ s.fecha_vencimiento ? __("Vence {0}", [formatoFecha(s.fecha_vencimiento)]) : __("Sin vencimiento") }}
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

			<section v-if="lic">
				<div class="mb-3 flex flex-wrap items-center justify-between gap-2">
					<h2 class="text-lg-semibold text-ink-gray-8">{{ __("Licitaciones del Estado") }}</h2>
					<div class="flex gap-1">
						<Button
							variant="ghost"
							:label="__('Procesos de compra')"
							icon-right="lucide-arrow-up-right"
							:href="rutaDocumento('Proceso Compra DGCP')"
						/>
						<Button
							variant="ghost"
							:label="__('Ofertas al Estado')"
							icon-right="lucide-arrow-up-right"
							:href="rutaReporte('Ofertas Estado', { company: empresa })"
						/>
					</div>
				</div>

				<div class="grid gap-4 lg:grid-cols-2">
					<div class="rounded-6 border border-outline-gray-2 bg-surface-base">
						<h3 class="border-b border-outline-gray-1 px-4 py-2.5 text-base-medium text-ink-gray-8">
							{{ __("Ofertas en curso") }}
							<span class="text-ink-gray-5">· {{ formatoNumero(lic.total_ofertas) }}</span>
						</h3>
						<p v-if="!lic.ofertas.length" class="px-4 py-3 text-p-sm text-ink-gray-5">
							{{ __("Sin ofertas en curso. Cree una desde el proceso de compra con «Crear oferta».") }}
						</p>
						<div v-else class="divide-y divide-outline-gray-1">
							<div v-for="o in lic.ofertas" :key="o.oportunidad" class="space-y-1 px-4 py-2.5">
								<div class="flex items-baseline justify-between gap-3">
									<a
										:href="rutaDocumento('Opportunity', o.oportunidad)"
										class="line-clamp-1 text-base-medium text-ink-gray-8 hover:underline"
									>
										{{ o.titulo || o.oportunidad }}
									</a>
									<Badge
										variant="subtle"
										class="shrink-0"
										:theme="TEMA_OFERTA[o.estado] || 'gray'"
										:label="o.estado"
									/>
								</div>
								<div class="flex flex-wrap gap-x-3 gap-y-0.5 text-sm text-ink-gray-5">
									<span>{{ o.institucion }}</span>
									<span v-if="o.cierre" :class="cierraPronto(o.cierre) ? 'text-ink-amber-8' : ''">
										{{ __("Cierra {0}", [formatoFecha(o.cierre)]) }}
									</span>
									<span v-if="o.documentos_pendientes" class="text-ink-amber-8">
										{{ __("{0} documentos pendientes", [o.documentos_pendientes]) }}
									</span>
									<span v-if="o.garantias_por_gestionar" class="text-ink-amber-8">
										{{ __("{0} garantías por gestionar", [o.garantias_por_gestionar]) }}
									</span>
								</div>
							</div>
						</div>
					</div>

					<div class="rounded-6 border border-outline-gray-2 bg-surface-base">
						<h3 class="border-b border-outline-gray-1 px-4 py-2.5 text-base-medium text-ink-gray-8">
							{{ __("Procesos nuevos de sus rubros") }}
							<span class="text-ink-gray-5">· {{ formatoNumero(lic.total_nuevos) }}</span>
						</h3>
						<p v-if="!lic.nuevos.length" class="px-4 py-3 text-p-sm text-ink-gray-5">
							{{ __("Sin procesos nuevos en los últimos 7 días.") }}
						</p>
						<div v-else class="divide-y divide-outline-gray-1">
							<div v-for="p in lic.nuevos" :key="p.name" class="space-y-1 px-4 py-2.5">
								<a
									:href="rutaDocumento('Proceso Compra DGCP', p.name)"
									class="line-clamp-1 text-base-medium text-ink-gray-8 hover:underline"
								>
									{{ p.titulo || p.name }}
								</a>
								<div class="flex flex-wrap gap-x-3 gap-y-0.5 text-sm text-ink-gray-5">
									<span>{{ p.institucion }}</span>
									<span v-if="p.monto" class="tabular-nums">{{ formatoMonedaDe(p.monto, p.moneda) }}</span>
									<span v-if="p.cierre">{{ __("Cierra {0}", [formatoFecha(p.cierre)]) }}</span>
								</div>
							</div>
						</div>
					</div>
				</div>

				<div
					v-if="lic.garantias.length"
					class="mt-4 divide-y divide-outline-gray-1 rounded-6 border border-outline-gray-2 bg-surface-base"
				>
					<h3 class="px-4 py-2.5 text-base-medium text-ink-gray-8">{{ __("Garantías que vencen pronto") }}</h3>
					<div
						v-for="(g, i) in lic.garantias"
						:key="i"
						class="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2.5"
					>
						<a
							:href="rutaDocumento('Opportunity', g.oportunidad)"
							class="text-base-medium text-ink-gray-8 hover:underline"
						>
							{{ g.oportunidad }}
						</a>
						<span class="text-sm text-ink-gray-6">{{ g.tipo }}{{ g.emisor ? ` · ${g.emisor}` : "" }}</span>
						<span class="text-sm tabular-nums text-ink-gray-6">{{ formatoMonedaDe(g.monto, g.moneda) }}</span>
						<span class="text-sm text-ink-amber-8">{{ __("Vence {0}", [formatoFecha(g.vence)]) }}</span>
					</div>
				</div>

				<p class="mt-2 text-sm text-ink-gray-5">
					{{
						lic.ultima_sincronizacion
							? __("Datos abiertos de la DGCP, descargados {0}. Confirme las fechas en el Portal Transaccional.", [
									formatoFecha(lic.ultima_sincronizacion),
								])
							: __("Los procesos de la DGCP aún no se han descargado.")
					}}
				</p>
			</section>

			<section>
				<h2 class="mb-1 text-lg-semibold text-ink-gray-8">{{ __("Observaciones") }}</h2>
				<p class="mb-3 text-p-sm text-ink-gray-5">
					{{
						__(
							"Registros que la DGII podría rechazar: RNC o cédula inválidos, NCF duplicados o datos faltantes. Corríjalos antes de enviar los formatos.",
						)
					}}
				</p>
				<div
					v-if="!r.avisos.total"
					class="flex items-center gap-2 rounded-6 border border-outline-gray-2 bg-surface-base px-4 py-3 text-base text-ink-gray-6"
				>
					<span class="lucide-circle-check size-4 text-ink-green-6" />
					{{ __("Sin observaciones en el período.") }}
				</div>
				<div v-else class="divide-y divide-outline-gray-1 rounded-6 border border-outline-gray-2 bg-surface-base">
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
						{{ __("Mostrando {0} de {1}. Vea el resto en cada reporte.", [r.avisos.lista.length, r.avisos.total]) }}
					</div>
				</div>
			</section>

			<footer class="flex flex-wrap gap-x-4 gap-y-1 border-t border-outline-gray-1 pt-4 text-sm text-ink-gray-5">
				<span>
					{{
						r.padron.registros
							? __("Padrón RNC: {0} contribuyentes, actualizado {1}", [
									formatoNumero(r.padron.registros),
									formatoFecha(r.padron.ultima_sincronizacion),
								])
							: __("Padrón RNC: sin descargar")
					}}
				</span>
				<span>{{ __("Los plazos no corren por días feriados.") }}</span>
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
import { __ } from "@/translation"
import {
	MESES,
	diasHasta,
	embebido,
	formatoFecha,
	formatoMoneda,
	formatoMonedaDe,
	formatoNumero,
	rutaDocumento,
	rutaReporte,
} from "@/utils"

const API = "/api/v2/method/erpnext_rd.rd_compliance.panel"
// El monitor es otra pantalla de esta app (en el escritorio, la página monitor-ecf)
const RUTA_MONITOR = embebido ? "/desk/monitor-ecf" : "/rd-compliance/ecf"

const SUBTITULOS = {
	606: __("Compras"),
	607: __("Ventas"),
	608: __("Anulados"),
	609: __("Pagos al exterior"),
}

const ESTADOS = {
	ok: { label: __("Al día"), theme: "green" },
	por_agotarse: { label: __("Por agotarse"), theme: "amber" },
	por_vencer: { label: __("Por vencer"), theme: "amber" },
	agotada: { label: __("Agotada"), theme: "red" },
	vencida: { label: __("Vencida"), theme: "red" },
	deshabilitada: { label: __("Deshabilitada"), theme: "gray" },
}

// Estados de la oferta (Fase 10.5); el servidor los manda traducidos
const TEMA_OFERTA = {
	[__("Evaluando")]: "gray",
	[__("En preparación")]: "blue",
	[__("Presentada")]: "green",
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
const lic = computed(() => r.value?.licitaciones)

function cierraPronto(cierre) {
	const dias = diasHasta(cierre)
	return dias !== null && dias >= 0 && dias <= (lic.value?.dias_aviso_cierre || 3)
}
const filtros = computed(() => ({ company: empresa.value, anio: anio.value, mes: mes.value }))

const opcionesMes = MESES.map((label, i) => ({ label, value: i + 1 }))
const opcionesAnio = computed(() => {
	const actual = new Date().getFullYear()
	return Array.from({ length: 6 }, (_, i) => ({ label: String(actual - i), value: actual - i }))
})

function detalleFormato(f) {
	const detalle = []
	if (f.monto !== null) detalle.push({ label: __("Monto"), valor: formatoMoneda(f.monto) })
	detalle.push({
		label: __("Con observaciones"),
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
			title: __("La empresa no tiene secuencias NCF"),
			description: __(
				"Sin secuencias no se pueden validar facturas con comprobante fiscal. Registre los rangos que le autorizó la DGII en la Oficina Virtual.",
			),
			accion: { label: __("Registrar secuencia"), href: rutaDocumento("Secuencia NCF", "new") },
		})
	}

	const sinNumeros = sec.filter((s) => ["agotada", "vencida"].includes(s.estado))
	if (sinNumeros.length) {
		lista.push({
			theme: "red",
			title: __("Secuencias NCF sin números: {0}", [sinNumeros.map((s) => s.tipo_comprobante).join(", ")]),
			description: __(
				"No se pueden emitir comprobantes de estos tipos. Solicite una nueva autorización en la Oficina Virtual y regístrela.",
			),
			accion: { label: __("Nueva secuencia"), href: rutaDocumento("Secuencia NCF", "new") },
		})
	}

	const enAlerta = sec.filter((s) => ["por_agotarse", "por_vencer"].includes(s.estado))
	if (enAlerta.length) {
		lista.push({
			theme: "amber",
			title: __("Secuencias NCF por agotarse o vencer: {0}", [enAlerta.map((s) => s.tipo_comprobante).join(", ")]),
			description: __("Solicite la próxima autorización de NCF antes de que se agoten."),
		})
	}

	if (r.value.avisos.total) {
		const n = r.value.avisos.total
		const vence = r.value.formatos[0].vence
		const dias = diasHasta(vence)
		lista.push({
			theme: "amber",
			title: n === 1 ? __("1 registro tiene observaciones") : __("{0} registros tienen observaciones", [n]),
			description:
				dias >= 0
					? __("Corríjalos antes del {0}, cuando vence el envío de los formatos.", [formatoFecha(vence)])
					: __("Revíselos en la sección Observaciones."),
		})
	}

	if (lic.value) {
		const urgentes = lic.value.ofertas.filter((o) => o.documentos_pendientes && o.cierre && cierraPronto(o.cierre))
		if (urgentes.length) {
			lista.push({
				theme: "amber",
				title:
					urgentes.length === 1
						? __("1 oferta al Estado cierra pronto con documentos pendientes")
						: __("{0} ofertas al Estado cierran pronto con documentos pendientes", [urgentes.length]),
				description: __("Complete los documentos obligatorios antes del cierre de ofertas."),
				accion: { label: __("Ver ofertas"), href: rutaReporte("Ofertas Estado", { company: empresa.value }) },
			})
		}
		if (lic.value.garantias.length) {
			lista.push({
				theme: "amber",
				title: __("Garantías de ofertas al Estado por vencer: {0}", [lic.value.garantias.length]),
				description: __("Renueve las garantías antes de su vencimiento o confirme su devolución."),
			})
		}
	}

	const ecf = r.value.ecf
	if (ecf) {
		const accion = { label: __("Abrir monitor"), href: RUTA_MONITOR }
		if (ecf.emisor.certificado === "vencido") {
			lista.push({
				theme: "red",
				title: __("El certificado digital del e-CF venció"),
				description: __("No se pueden firmar comprobantes electrónicos. Renueve el certificado y súbalo al emisor."),
				accion,
			})
		} else if (ecf.emisor.certificado === "por_vencer") {
			lista.push({
				theme: "amber",
				title: __("El certificado digital del e-CF vence en {0} días", [ecf.emisor.dias_certificado]),
				description: __("Solicite la renovación a su entidad certificadora."),
				accion,
			})
		}
		if (ecf.rechazados) {
			lista.push({
				theme: "red",
				title: __("{0} e-CF rechazados o con error en los últimos 30 días", [ecf.rechazados]),
				description: __("Un e-CF rechazado no tiene validez fiscal: revíselos en el monitor."),
				accion,
			})
		}
	}

	if (!r.value.padron.registros) {
		lista.push({
			theme: "blue",
			title: __("El padrón RNC aún no se ha descargado"),
			description: __(
				"Se descarga solo en segundo plano. Mientras tanto no se autocompleta la razón social al escribir un RNC.",
			),
		})
	}
	return lista
})
</script>
