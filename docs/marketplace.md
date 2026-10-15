# Ficha del Marketplace de Frappe Cloud

Textos y lista de lo que falta para publicar ERPNext RD. Requisitos técnicos: `docs/PLAN.md`, Fase 7.

## Textos

**Nombre:** ERPNext RD

**Descripción corta:** Localización de República Dominicana para ERPNext y Frappe HR: NCF y e-CF, reportes DGII, padrón RNC y nómina RD.

**Descripción larga:**

ERPNext RD adapta ERPNext y Frappe HR a la República Dominicana sin modificar su código.

- **Comprobantes fiscales:** secuencias NCF sin duplicados en ventas, compras y POS; validación de RNC y cédula con el padrón de la DGII; catálogo de cuentas DGII.
- **Facturación electrónica (e-CF):** XML de los diez tipos y del resumen de consumo según los esquemas oficiales, firma digital con el certificado de la empresa, envío a la DGII y consulta del resultado.
- **Declaraciones DGII:** formatos 606, 607, 608 y 609 con su archivo TXT, y resúmenes del IT-1 e IR-17.
- **Nómina RD (con Frappe HR):** AFP, SFS, ISR e INFOTEP; prestaciones, vacaciones, regalía y bonificación; archivos de la TSS (AM, NV, RT), IR-3, IR-13 y planillas del Ministerio de Trabajo.
- **Panel de cumplimiento:** plazos y montos del mes en una pantalla.

Todas las tasas y escalas se editan en la configuración. Solo actúa en empresas con país República Dominicana, así que convive con empresas de otros países. Frappe HR es opcional.

**Categorías:** Localization, Accounting, HR & Payroll.

**Licencia:** GPL-3.0. **Código:** https://github.com/daniellora7/ERPNext-DR-Compilance

## Capturas (tomar en claro, a 1440 × 900)

1. Panel de cumplimiento.
2. Factura fiscal impresa con NCF.
3. Formato 606 con sus observaciones.
4. Envío e-CF aceptado.
5. Recibo de nómina con AFP, SFS e ISR.
6. Archivo de autodeterminación TSS.

## Pendiente

- [ ] Rama `version-16` (Frappe Cloud instala por rama).
- [ ] CI público en verde (los workflows ya están escritos) y versiones con tag.
- [ ] Capturas con datos de ejemplo (no de la empresa real).
- [ ] Enlace de soporte (correo o issues de GitHub) y página de documentación de uso.
- [x] Logo: `erpnext_rd/public/images/erpnext_rd_logo.svg` (`app_logo_url`).
- [x] Instala sin acceso a la máquina, funciona sin Frappe HR y se desinstala limpio.
