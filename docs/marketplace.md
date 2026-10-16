# Ficha del Marketplace de Frappe Cloud

Textos y lista de lo que falta para publicar ERPNext RD. Requisitos técnicos: `docs/PLAN.md`, Fase 7.

## Textos

**Nombre:** ERPNext RD

**Descripción corta:** Localización de República Dominicana para ERPNext y Frappe HR: NCF y e-CF, reportes DGII, padrón RNC y nómina RD.

**Descripción larga:**

ERPNext RD adapta ERPNext y Frappe HR a la República Dominicana sin modificar su código.

- **Comprobantes fiscales:** secuencias NCF sin duplicados en ventas, compras y POS; validación de RNC y cédula con el padrón de la DGII; catálogo de cuentas DGII.
- **Facturación electrónica (e-CF):** XML de los diez tipos y del resumen de consumo según los esquemas oficiales, firma digital con el certificado de la empresa, envío a la DGII con contingencia y entrega al comprador; recepción de e-CF de proveedores con acuse y aprobación comercial; anulación de rangos y set de pruebas para la certificación.
- **Declaraciones DGII:** formatos 606, 607, 608 y 609 con su archivo TXT, y resúmenes del IT-1 e IR-17.
- **Nómina RD (con Frappe HR):** AFP, SFS, ISR e INFOTEP; prestaciones, vacaciones, regalía y bonificación; archivos de la TSS (AM, NV, RT), IR-3, IR-13 y planillas del Ministerio de Trabajo.
- **Panel de cumplimiento:** plazos y montos del mes en una pantalla.

Todas las tasas y escalas se editan en la configuración. Solo actúa en empresas con país República Dominicana, así que convive con empresas de otros países. Frappe HR es opcional.

**Categorías:** Localization, Accounting, HR & Payroll.

**Licencia:** GPL-3.0. **Código:** https://github.com/daniellora7/ERPNext-DR-Compilance

**Documentación:** https://github.com/daniellora7/ERPNext-DR-Compilance/blob/main/docs/GUIA-DE-USO.md

**Soporte:** https://github.com/daniellora7/ERPNext-DR-Compilance/issues (plantillas de error y de sugerencia en `.github/ISSUE_TEMPLATE/`).

## Capturas (tema oscuro, 1440 × 900)

Tomadas en un sitio de demostración con empresas y datos ficticios: un mes registrado con la prueba de punta a punta (`erpnext_rd/tests/test_punta_a_punta.py`).

| Captura | Archivo |
|---|---|
| RD Compliance: panel de cumplimiento con los plazos del mes | `docs/capturas/rd-compliance.png` |
| Factura Fiscal RD (crédito fiscal B01) | `docs/capturas/factura-fiscal-rd.png` |
| Nómina RD: autodeterminación de la TSS | `docs/capturas/nomina-rd.png` |
| Volante de pago RD | `docs/capturas/volante-pago-rd.png` |

![RD Compliance](capturas/rd-compliance.png)

![Factura Fiscal RD](capturas/factura-fiscal-rd.png)

![Nómina RD](capturas/nomina-rd.png)

![Volante de pago RD](capturas/volante-pago-rd.png)

Opcionales para más adelante: formato 606 y envío e-CF aceptado (con el certificado real).

## Pendiente

- [ ] Rama `version-16` (Frappe Cloud instala por rama) y tag `v0.3.0`: se crean desde `main` cuando `develop` se fusione (ver `CHANGELOG.md`).
- [x] CI público en verde en cada PR.
- [x] Capturas en tema oscuro con datos ficticios (`docs/capturas/`).
- [x] Enlace de soporte (issues de GitHub con plantillas) y documentación de uso (`docs/GUIA-DE-USO.md`).
- [x] Padrón RNC medido: descarga 46 s (zip de 23 MB) e importación de 793 985 registros en 3 min 16 s con 154 MB de memoria pico, en la cola `long`.
- [x] Logo: `erpnext_rd/public/images/erpnext_rd_logo.svg` (`app_logo_url`).
- [x] Instala sin acceso a la máquina, funciona sin Frappe HR y se desinstala limpio.
