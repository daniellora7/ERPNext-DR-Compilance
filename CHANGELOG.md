# Cambios

Versiones con [versionado semántico](https://semver.org/lang/es/). La rama `version-16` sigue a Frappe v16; cada versión lleva un tag `vX.Y.Z` desde `main`, que publica la imagen en GHCR.

## v0.3.0 (primera versión)

Para Frappe v16.52, ERPNext v16.51 y Frappe HR v16.51 (opcional).

### Fiscal (RD Compliance)
- Tipos de comprobante B01–B17 y E31–E47 y secuencias NCF sin duplicados, en ventas, compras y POS.
- Validación de RNC y cédula, y padrón RNC de la DGII actualizado cada día.
- Catálogo de cuentas DGII (NIIF PYMES) con plantillas de ITBIS y retenciones (Ley 30-26).
- Formatos de impresión *Factura Fiscal RD* y *Recibo POS RD*, editables en el constructor.
- Formatos 606, 607, 608 y 609 con su TXT, y resúmenes del IT-1 y el IR-17.
- Panel de cumplimiento con plazos, montos y secuencias. Respeta la apariencia «Ancho completo» del escritorio.

### e-CF
- XML guiado por los XSD oficiales (E31–E47 y RFCE), firma XMLDSig y servicios de la DGII: token, recepción, RFCE y consultas.
- Contingencia: el envío se reintenta solo, cada vez más espaciado, si la DGII no responde.
- Entrega de los e-CF aceptados al comprador si es receptor electrónico.
- Recepción de e-CF de proveedores (servicios `/fe/...`) con acuse de recibo y aprobación o rechazo comercial.
- Anulación de rangos de e-NCF (ANECF).
- Set de pruebas de la certificación (CerteCF).

### Nómina RD (con Frappe HR)
- AFP, SFS, ISR y aportes del empleador en el recibo, con topes de la TSS y escalas del ISR 2026 y 2027.
- Preaviso, cesantía, regalía (proporcional y de diciembre), vacaciones, bonificación anual y feriados RD.
- Horas extras con los recargos de ley, incluido el nocturno (art. 204).
- Archivos de la TSS (AM, NV, RT), resúmenes IR-3 e IR-13, y planillas DGT-3 y DGT-4 para el SIRLA.
- Volante de pago RD y datos RD del empleado.

### Idioma
- Nombres del dock en el idioma del usuario.
- Frappe HR completo en español, con 90 traducciones erradas de su catálogo oficial corregidas.
