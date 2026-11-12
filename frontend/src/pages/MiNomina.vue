<template>
	<PageHeader>
		<PageHeaderTitle :title="__('Mi nómina')" />
		<Button
			v-if="d"
			variant="solid"
			icon-left="lucide-calendar-plus"
			:label="__('Solicitar permiso')"
			:disabled="!d.tipos_permiso.length"
			@click="abrirSolicitud"
		/>
	</PageHeader>

	<div class="mx-auto w-full max-w-4xl space-y-8 px-5 py-6">
		<Alert v-if="datos.error" theme="red" :title="__('No se pudo cargar su nómina')" :description="datos.error.message" />

		<div v-if="!d && datos.loading" class="space-y-4">
			<Skeleton class="h-24 rounded-6" />
			<Skeleton class="h-48 rounded-6" />
		</div>

		<template v-if="d">
			<section class="rounded-6 border border-outline-gray-2 bg-surface-base px-4 py-3">
				<div class="text-lg-semibold text-ink-gray-8">{{ d.empleado.nombre }}</div>
				<div class="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-sm text-ink-gray-5">
					<span v-if="d.empleado.cargo">{{ d.empleado.cargo }}</span>
					<span v-if="d.empleado.departamento">{{ d.empleado.departamento }}</span>
					<span>{{ d.empleado.empresa }}</span>
					<span v-if="d.empleado.ingreso">{{ __("Ingreso: {0}", [formatoFecha(d.empleado.ingreso)]) }}</span>
					<span v-if="d.empleado.proximo_aniversario">
						{{ __("Próximo aniversario: {0}", [formatoFecha(d.empleado.proximo_aniversario)]) }}
					</span>
				</div>
			</section>

			<section>
				<h2 class="mb-3 text-lg-semibold text-ink-gray-8">{{ __("Acumulado de {0}", [d.acumulado.anio]) }}</h2>
				<div class="grid gap-3 [grid-template-columns:repeat(auto-fill,minmax(9rem,1fr))]">
					<div
						v-for="c in cifras"
						:key="c.label"
						class="rounded-6 border border-outline-gray-2 bg-surface-base px-4 py-3"
					>
						<div class="text-sm text-ink-gray-5">{{ c.label }}</div>
						<div class="mt-1 text-lg-semibold tabular-nums text-ink-gray-8">{{ formatoMoneda(c.valor) }}</div>
					</div>
				</div>
				<p class="mt-2 text-sm text-ink-gray-5">
					{{ __("Según {0} volantes aprobados del año. La empresa reporta estos montos a la DGII en el IR-13.", [d.acumulado.volantes]) }}
				</p>
			</section>

			<section>
				<h2 class="mb-3 text-lg-semibold text-ink-gray-8">{{ __("Vacaciones y permisos") }}</h2>
				<p
					v-if="!d.permisos.length"
					class="rounded-6 border border-dashed border-outline-gray-2 px-4 py-6 text-center text-base text-ink-gray-5"
				>
					{{ __("No tiene días de permiso asignados todavía. Las vacaciones se asignan al cumplir cada año de trabajo.") }}
				</p>
				<div v-else class="divide-y divide-outline-gray-1 rounded-6 border border-outline-gray-2 bg-surface-base">
					<div
						v-for="p in d.permisos"
						:key="p.tipo"
						class="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-4 py-2.5"
					>
						<span class="text-base-medium text-ink-gray-8">{{ p.etiqueta }}</span>
						<span class="text-sm tabular-nums text-ink-gray-6">
							{{ __("{0} disponibles de {1}", [formatoNumero(p.disponibles), formatoNumero(p.asignados)]) }}
							<template v-if="p.pendientes_aprobar">
								· <span class="text-ink-amber-8">{{ __("{0} por aprobar", [formatoNumero(p.pendientes_aprobar)]) }}</span>
							</template>
						</span>
					</div>
				</div>

				<div
					v-if="d.solicitudes.length"
					class="mt-4 divide-y divide-outline-gray-1 rounded-6 border border-outline-gray-2 bg-surface-base"
				>
					<h3 class="px-4 py-2.5 text-base-medium text-ink-gray-8">{{ __("Mis solicitudes") }}</h3>
					<div
						v-for="s in d.solicitudes"
						:key="s.name"
						class="flex flex-wrap items-baseline gap-x-3 gap-y-1 px-4 py-2.5"
					>
						<span class="text-base text-ink-gray-8">{{ __(s.leave_type) }}</span>
						<span class="text-sm text-ink-gray-5">
							{{ formatoFecha(s.from_date) }} – {{ formatoFecha(s.to_date) }} ·
							{{ __("{0} días", [formatoNumero(s.total_leave_days)]) }}
						</span>
						<Badge variant="subtle" :theme="TEMA_SOLICITUD[s.status] || 'gray'" :label="__(s.status)" />
					</div>
				</div>
			</section>

			<section>
				<h2 class="mb-3 text-lg-semibold text-ink-gray-8">{{ __("Volantes de pago") }}</h2>
				<p
					v-if="!d.volantes.length"
					class="rounded-6 border border-dashed border-outline-gray-2 px-4 py-6 text-center text-base text-ink-gray-5"
				>
					{{ __("Aún no tiene volantes de pago aprobados.") }}
				</p>
				<div v-else class="divide-y divide-outline-gray-1 rounded-6 border border-outline-gray-2 bg-surface-base">
					<div
						v-for="v in d.volantes"
						:key="v.name"
						class="grid grid-cols-[1fr_auto] items-center gap-x-4 gap-y-1 px-4 py-2.5 sm:grid-cols-[1fr_8rem_8rem_auto]"
					>
						<div>
							<div class="text-base-medium text-ink-gray-8">
								{{ formatoFecha(v.start_date) }} – {{ formatoFecha(v.end_date) }}
							</div>
							<div class="text-sm text-ink-gray-5 sm:hidden">
								{{ __("Neto {0}", [formatoMonedaDe(v.net_pay, v.currency)]) }}
							</div>
						</div>
						<div class="text-sm tabular-nums text-ink-gray-5 max-sm:hidden sm:text-right">
							{{ __("Descuentos {0}", [formatoMonedaDe(v.total_deduction, v.currency)]) }}
						</div>
						<div class="text-base-medium tabular-nums text-ink-gray-8 max-sm:hidden sm:text-right">
							{{ formatoMonedaDe(v.net_pay, v.currency) }}
						</div>
						<Button
							variant="ghost"
							icon-left="lucide-download"
							:label="__('PDF')"
							:href="`${API}.volante?name=${encodeURIComponent(v.name)}`"
						/>
					</div>
				</div>
			</section>
		</template>
	</div>

	<Dialog v-model="solicitud.abierta" :options="{ title: __('Solicitar permiso') }">
		<template #body-content>
			<div class="space-y-3">
				<FormControl v-model="solicitud.tipo" type="select" :label="__('Tipo')" :options="d?.tipos_permiso || []" />
				<div class="grid grid-cols-2 gap-3">
					<FormControl v-model="solicitud.desde" type="date" :label="__('Desde')" />
					<FormControl v-model="solicitud.hasta" type="date" :label="__('Hasta')" />
				</div>
				<FormControl v-model="solicitud.motivo" type="textarea" :label="__('Motivo (opcional)')" />
				<p class="text-p-sm text-ink-gray-5">
					{{ __("La solicitud queda abierta hasta que su supervisor la apruebe.") }}
				</p>
			</div>
		</template>
		<template #actions>
			<Button
				variant="solid"
				class="w-full"
				:label="__('Enviar solicitud')"
				:loading="enviar.loading"
				:disabled="!solicitud.tipo || !solicitud.desde || !solicitud.hasta"
				@click="enviarSolicitud"
			/>
		</template>
	</Dialog>
</template>

<script setup>
import { computed, reactive } from "vue"
import { Alert, Badge, Button, Dialog, FormControl, PageHeader, PageHeaderTitle, Skeleton, toast, useCall } from "frappe-ui"

import { __ } from "@/translation"
import { formatoFecha, formatoMoneda, formatoMonedaDe, formatoNumero } from "@/utils"

const API = "/api/method/erpnext_rd.nomina_rd.portal"

const TEMA_SOLICITUD = { Open: "blue", Approved: "green", Rejected: "red", Cancelled: "gray" }

const datos = useCall({ url: "/api/v2/method/erpnext_rd.nomina_rd.portal.resumen" })
const d = computed(() => datos.data)

const cifras = computed(() => {
	const a = d.value.acumulado
	return [
		{ label: __("Salario bruto"), valor: a.bruto },
		{ label: __("AFP"), valor: a.afp },
		{ label: __("SFS"), valor: a.sfs },
		{ label: __("ISR retenido"), valor: a.isr },
		{ label: __("Neto recibido"), valor: a.neto },
	]
})

const solicitud = reactive({ abierta: false, tipo: null, desde: null, hasta: null, motivo: "" })

function abrirSolicitud() {
	Object.assign(solicitud, { abierta: true, tipo: d.value.tipos_permiso[0]?.value, desde: null, hasta: null, motivo: "" })
}

const enviar = useCall({
	url: "/api/v2/method/erpnext_rd.nomina_rd.portal.solicitar_permiso",
	method: "POST",
	immediate: false,
})

async function enviarSolicitud() {
	try {
		await enviar.submit({
			leave_type: solicitud.tipo,
			desde: solicitud.desde,
			hasta: solicitud.hasta,
			motivo: solicitud.motivo,
		})
		solicitud.abierta = false
		toast.success(__("Solicitud enviada"))
		datos.reload()
	} catch (error) {
		toast.error(error.message || __("No se pudo enviar la solicitud"))
	}
}
</script>
