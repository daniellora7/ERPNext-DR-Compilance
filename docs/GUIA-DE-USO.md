# Guía de uso de ERPNext RD

Cómo poner a funcionar la localización de República Dominicana en una empresa, paso a paso. Todo está en el dock de ERPNext → **RD Compliance** (lo fiscal) y en el dock de Frappe HR → **Nómina RD** (la nómina, si Frappe HR está instalado).

La app solo actúa en las empresas con país **Dominican Republic**. Las empresas de otros países del mismo sitio siguen igual.

## 1. Empresa

1. En la empresa (*Company*), el país debe ser **Dominican Republic** y el **RNC** debe estar en *Tax ID*, sin guiones. La app lo valida con el dígito verificador y el padrón de la DGII.
2. Si la empresa no tiene movimientos, la app aplica el **catálogo de cuentas DGII** (NIIF PYMES), con las plantillas de ITBIS y de retenciones. Se controla en *RD Compliance → Configuración DGII*.
3. El **padrón RNC** se descarga solo al instalar la app y después cada día a las 2:00 a. m., si la DGII publicó uno nuevo. Al escribir un RNC o una cédula en un cliente o un proveedor, la razón social se completa sola.
4. La **tasa del dólar** del Banco Central se registra sola cada día laborable como tipo de cambio USD → DOP, y ERPNext la usa en las facturas, los pagos y la revaluación. Por defecto es la tasa de compra; en *Configuración DGII* se puede cambiar a la de venta, o usar compra en las ventas y venta en las compras. Un tipo de cambio puesto a mano para una fecha no se cambia.

## 2. Comprobantes fiscales (NCF)

1. En *RD Compliance → Secuencias NCF*, registre cada rango que autorizó la DGII: empresa, tipo (B01, B02…, E31…), desde, hasta y vencimiento.
2. En la factura de venta, elija el **tipo de comprobante**. Hay un tipo por defecto: el que tenga el cliente o, si no, crédito fiscal si tiene RNC o cédula válidos y consumo si no los tiene. El NCF se asigna al aprobar la factura, sin duplicados aunque se aprueben dos a la vez.
3. En las compras, escriba el NCF del proveedor; la app revisa el formato y que no esté repetido. Los gastos menores (B13), las compras a informales (B11) y los pagos al exterior (B17) llevan NCF de la empresa.
4. Para anular una factura con NCF, indique antes el *tipo de anulación* del 608.
5. El panel avisa cuando una secuencia está por agotarse o por vencer.

Los formatos de impresión **Factura Fiscal RD** y **Recibo POS RD** (80 mm) se pueden editar en el constructor de formatos de Frappe.

## 3. Declaraciones DGII

En *RD Compliance → Declaraciones DGII*:

- **606, 607, 608 y 609**: se elige la empresa y el mes, se revisa la columna de observaciones y se descarga el TXT con el nombre que pide la DGII. Antes de enviarlo, conviene pasarlo por la herramienta de pre-validación de la DGII.
- **IT-1** e **IR-17**: resúmenes con los mismos registros, para llenar los formularios en la Oficina Virtual.

El **Panel de cumplimiento** muestra en una pantalla los plazos y los montos del mes.

Para recibir los vencimientos por correo, active *Enviar recordatorios de vencimientos* en *Configuración DGII*. Cada mañana llega un correo por empresa con lo que vence en los próximos días (3 por defecto) o ese mismo día: IR-17, 606-609, IT-1 y, si hay nómina, el pago de la TSS, el IR-3, la regalía y el IR-13. Los lunes incluye las secuencias NCF por agotarse o por vencer. Hace falta una cuenta de correo saliente en Frappe. El botón *Vista previa de recordatorios* muestra lo que se enviaría hoy.

## 4. Facturación electrónica (e-CF)

### Emisor

1. En *RD Compliance → Configuración DGII*, elija el **ambiente**: TesteCF (pruebas), CerteCF (certificación) o eCF (producción).
2. En *Configuración → Emisores y certificados*, cree el emisor de la empresa. Suba el **certificado .p12** emitido a nombre del RNC (queda como archivo privado) y su contraseña. La app muestra el titular y la vigencia.
3. Si marca **Enviar los e-CF a la DGII**, cada e-CF firmado se envía a la DGII. Con **Emitir al aprobar la factura** se emite en segundo plano, sin usar el botón.
4. Registre las secuencias electrónicas (E31, E32…) como en el paso 2.

### Emitir

- En una factura aprobada con tipo electrónico, use **e-CF → Emitir e-CF**. Se crea un **Envío e-CF** con el XML firmado, el código de seguridad y la respuesta de la DGII. El resultado se consulta solo cada 15 minutos.
- Las facturas de consumo (E32) menores a RD$250,000 se envían además como resumen (RFCE). El monto se configura en el emisor.
- **Contingencia:** si la DGII no responde, el e-CF queda *En contingencia* y se reenvía solo, cada vez más espaciado. Si la DGII rechaza la solicitud, el envío queda en *Error* y se reenvía con el botón **Enviar a la DGII**, después de corregir.
- Los e-CF aceptados con un comprador que también es receptor electrónico se le **entregan** solos. Su acuse de recibo y su aprobación o rechazo comercial quedan en el envío.

### Recibir e-CF de proveedores

1. Registre en el portal de la DGII la URL del sitio (por ejemplo, `https://erp.suempresa.com.do`) como URL de recepción, aprobación comercial y autenticación. La app atiende las rutas del estándar: `/fe/recepcion/api/ecf`, `/fe/aprobacioncomercial/api/ecf` y `/fe/autenticacion/api/...`.
2. Cada e-CF que llega queda en *RD Compliance → e-CF recibidos*, y el proveedor recibe su acuse de recibo al momento. La app revisa la firma, el esquema, que el comprador sea su empresa y que no esté repetido.
3. Con **Aprobar** o **Rechazar** (con el motivo), se firma la aprobación comercial y se envía a la DGII y al proveedor.
4. Al aprobar la factura de compra con ese e-NCF, el e-CF recibido se enlaza solo.

### Anular secuencias que no se usarán

En *RD Compliance → Anulación de e-NCF*, agregue los rangos (la app propone desde el siguiente número hasta el final) y valide. La anulación se firma y se envía a la DGII, y la secuencia ya no da esos números. No se pueden anular números ya usados en facturas aprobadas ni e-CF ya enviados.

### Certificación (CerteCF)

1. Cambie el ambiente a **CerteCF**.
2. En *Configuración → Set de pruebas e-CF*, suba el archivo que entrega la DGII en el portal de certificación, en Excel o CSV.
3. Use **Firmar los e-CF**. Cada fila queda como un envío firmado, y las filas con errores se listan con su motivo.
4. Use **Enviar a la DGII** y siga el resultado en **Ver envíos**.

## 5. Nómina RD (con Frappe HR)

1. Revise *Nómina RD → Configuración Nómina RD*: tasas y topes de la TSS, escalas del ISR por año, prestaciones, horas extras (recargos y jornada nocturna) y vacaciones. Todo es editable cuando cambie la ley.
2. En cada empleado, complete los datos RD: cédula o NSS, AFP, ARS y tipo de ingreso TSS.
3. Use una estructura salarial de Frappe HR. AFP, SFS, ISR y los aportes del empleador se calculan solos en cada recibo.
4. Cada mes, desde *Nómina RD*:
   - Descargue la autodeterminación (AM) y las novedades (NV) de la TSS.
   - Revise el resumen del IR-3.
   - En diciembre, genere la regalía pascual. Al año, la bonificación y el IR-13.
5. **Prestaciones al salir:** el *Gratuity* de Frappe HR usa las reglas "Preaviso RD", "Cesantía RD" y "Regalía RD". Las vacaciones pendientes se pagan con *Leave Encashment*.
6. **Horas extras:** use el tipo "Horas extras RD" de Frappe HR. Los recargos de ley se aplican solos: 35 %, 100 % sobre 68 horas semanales y en feriados, y 15 % más en la parte nocturna.

## Soporte

- Errores y sugerencias: [issues de GitHub](https://github.com/daniellora7/ERPNext-DR-Compilance/issues). Indique las versiones de Frappe, ERPNext y Frappe HR y los pasos para reproducirlo. Nunca adjunte certificados, contraseñas ni datos reales de clientes.
- Detalles técnicos de cada módulo: [NOTAS-TECNICAS.md](NOTAS-TECNICAS.md).
