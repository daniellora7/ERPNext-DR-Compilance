# Cambios

Versiones con [versionado semántico](https://semver.org/lang/es/). La rama `version-16` sigue a Frappe v16; cada versión lleva un tag `vX.Y.Z` desde `main`, que publica la imagen en GHCR.

## Sin publicar

### Fiscal (RD Compliance)
- Tasa del dólar del Banco Central registrada cada día como tipo de cambio USD → DOP (compra, venta o compra en ventas y venta en compras).
- Recordatorios por correo de los vencimientos: IR-17, 606-609, IT-1 y, con nómina, TSS, IR-3, regalía e IR-13; los lunes, las secuencias NCF en alerta. Apagados por defecto.
- Formato *Cheque RD* del *Payment Entry*, con comprobante de pago, editable en el constructor y con las posiciones del cheque ajustables por banco.
- Consulta del NCF del proveedor en la DGII al guardar la factura de compra (no corresponde al RNC, vencido) y aviso de proveedores no activos en el padrón. Opción para impedir validar con un NCF no válido.
- Proporcionalidad del ITBIS (art. 349): proveedores y compras con ITBIS sujeto a proporcionalidad, columna del 606 y porcentaje no admitido en el resumen del IT-1.
- Anticipos del ISR (art. 314): base anual con los datos del IR-2, cuota mensual, reporte del año y recordatorio.
- Cuadre fiscal del IR-2: ajuste por inflación (anexo D-2) con los multiplicadores de la DGII, depreciación fiscal por categoría del art. 287 (anexos D y D-1) frente a la contable, ajustes del anexo G y liquidación estimada del impuesto. Categoría fiscal en las categorías de activo. Reparaciones de edificaciones por encima del 10% capitalizadas y formato de impresión del cuadre.
- Recordatorio del IR-2, 120 días después del cierre del año fiscal.
- Anexos A-1 (balance general) y B-1 (estado de resultados) del IR-2 por casilla, con la casilla en cada cuenta (asignada en el catálogo DGII). El cuadre toma de ahí el beneficio antes del ISR.

- Perfil tributario por empresa: régimen, tamaño, cierre fiscal, actividades con tratamiento especial, incentivos y situación con el e-CF, con asistente desde la empresa y lista de requisitos con su estado. Los emisores electrónicos venden con la serie E y el IR-2 solo aplica a personas jurídicas del régimen ordinario.

### Nómina RD
- Dependientes adicionales del SFS en la ficha del empleado, con el per cápita y el Fonamat descontados en cada recibo.
- Registro de subsidios de la SISALRIL (enfermedad común, maternidad y lactancia) con el monto estimado y el seguimiento del reembolso.

## v0.3.0 (primera versión)

Para Frappe v16.52, ERPNext v16.51 y Frappe HR v16.51 (opcional).

### Fiscal (RD Compliance)
- Tipos de comprobante B01–B17 y E31–E47 y secuencias NCF sin duplicados, en ventas, compras y POS.
- Validación de RNC y cédula, y padrón RNC de la DGII actualizado cada día.
- Catálogo de cuentas DGII (NIIF PYMES) con plantillas de ITBIS y retenciones (Ley 30-26).
- Formatos de impresión *Factura Fiscal RD* y *Recibo POS RD*, editables en el constructor. Cada empresa puede elegir su formato de factura; las de otros países usan el estándar.
- Las devoluciones creadas desde la factura toman solas la nota de crédito (B04/E34).
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
- La cuenta *Nómina por Pagar* del catálogo DGII queda lista para validar la nómina de Frappe HR.
- Archivos de la TSS (AM, NV, RT), resúmenes IR-3 e IR-13, y planillas DGT-3 y DGT-4 para el SIRLA.
- Volante de pago RD y datos RD del empleado.

### Despliegue
- Respaldo diario automático de la base y los archivos, con limpieza de los viejos.
- Guías de despliegue en Dokploy y de respaldo y restauración.

### Idioma
- Nombres del dock en el idioma del usuario.
- Frappe HR completo en español, con 90 traducciones erradas de su catálogo oficial corregidas.
