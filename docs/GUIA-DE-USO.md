# Guía de uso de ERPNext RD

Cómo poner a funcionar la localización de República Dominicana en una empresa, paso a paso. Todo está en el dock de ERPNext → **RD Compliance** (lo fiscal) y en el dock de Frappe HR → **Nómina RD** (la nómina, si Frappe HR está instalado).

La app solo actúa en las empresas con país **Dominican Republic**. Las empresas de otros países del mismo sitio siguen igual.

**Alcance:** hoy la app cubre a la **persona jurídica del régimen ordinario** (comercio, servicios, manufactura). Aún no cubre el impuesto selectivo al consumo (ISC), las operaciones con partes relacionadas (DIOR), las zonas francas, el régimen simplificado (RST), los incentivos de leyes especiales, el impuesto sobre los activos ni a las personas físicas con negocio (IR-1); los sectores regulados (banca, seguros, AFP) quedan fuera. Están planificados en un **perfil tributario** por empresa que activará lo que corresponda a cada una.

## 1. Empresa

1. En la empresa (*Company*), el país debe ser **Dominican Republic** y el **RNC** debe estar en *Tax ID*, sin guiones. La app lo valida con el dígito verificador y el padrón de la DGII.
2. Si la empresa no tiene movimientos, la app aplica el **catálogo de cuentas DGII** (NIIF PYMES), con las plantillas de ITBIS y de retenciones. Se controla en *RD Compliance → Configuración DGII*.
3. El **padrón RNC** se descarga solo al instalar la app y después cada día a las 2:00 a. m., si la DGII publicó uno nuevo. Al escribir un RNC o una cédula en un cliente o un proveedor, la razón social se completa sola.
4. La **tasa del dólar** del Banco Central se registra sola cada día laborable como tipo de cambio USD → DOP, y ERPNext la usa en las facturas, los pagos y la revaluación. Por defecto es la tasa de compra; en *Configuración DGII* se puede cambiar a la de venta, o usar compra en las ventas y venta en las compras. Un tipo de cambio puesto a mano para una fecha no se cambia.

## 2. Comprobantes fiscales (NCF)

1. En *RD Compliance → Secuencias NCF*, registre cada rango que autorizó la DGII: empresa, tipo (B01, B02…, E31…), desde, hasta y vencimiento.
2. En la factura de venta, elija el **tipo de comprobante**. Hay un tipo por defecto: el que tenga el cliente o, si no, crédito fiscal si tiene RNC o cédula válidos y consumo si no los tiene. El NCF se asigna al aprobar la factura, sin duplicados aunque se aprueben dos a la vez.
3. En las compras, escriba el NCF del proveedor; la app revisa el formato y que no esté repetido. Los gastos menores (B13), las compras a informales (B11) y los pagos al exterior (B17) llevan NCF de la empresa.
   Al guardar la factura, la app consulta el NCF en la DGII y avisa si no corresponde al RNC del proveedor o si estaba vencido en la fecha del comprobante; el resultado queda en *NCF en la DGII*. También avisa si el proveedor aparece suspendido, dado de baja o en cese temporal en el padrón. Si la DGII no responde, la factura queda *Sin verificar* y se puede volver a consultar con *DGII → Verificar NCF en la DGII*. En *Configuración DGII* se puede impedir validar facturas con un NCF no válido.
4. Para anular una factura con NCF, indique antes el *tipo de anulación* del 608.
5. El panel avisa cuando una secuencia está por agotarse o por vencer.

Los formatos de impresión **Factura Fiscal RD** y **Recibo POS RD** (80 mm) se pueden editar en el constructor de formatos de Frappe.

Para los pagos con cheque está el formato **Cheque RD** del *Payment Entry* (Entrada de pago): arriba el cheque con la fecha, el beneficiario y el monto en números y en letras; abajo el comprobante de pago con las facturas pagadas, las retenciones, el asiento y las firmas. Escriba el número de cheque en *Nº de referencia* y su fecha en *Fecha de referencia*. Cada banco ubica los campos en otro lugar: ajuste las medidas al inicio del CSS del formato (constructor de formatos → CSS) e imprima una prueba en papel normal, puesta sobre un cheque, antes de usar los cheques reales. Se imprime sin membrete.

## 3. Declaraciones DGII

En *RD Compliance → Declaraciones DGII*:

- **606, 607, 608 y 609**: se elige la empresa y el mes, se revisa la columna de observaciones y se descarga el TXT con el nombre que pide la DGII. Antes de enviarlo, conviene pasarlo por la herramienta de pre-validación de la DGII.
- **IT-1** e **IR-17**: resúmenes con los mismos registros, para llenar los formularios en la Oficina Virtual.
- **Anticipos del ISR**: cada año, después de presentar el IR-2, registre en *Bases de anticipos ISR* los ingresos brutos y el impuesto liquidado. La app calcula la cuota mensual (art. 314: la doceava parte del impuesto, o el 1.5% de los ingresos si la tasa efectiva no pasa de 1.5%) y el reporte muestra el anticipo de cada mes con su vencimiento (día 15 del mes siguiente). Una empresa exenta se registra con régimen *Exento*.
- **Cuadre fiscal IR-2**: papel de trabajo para la declaración anual (no la reemplaza). Primero indique en cada *Categoría de activo* su categoría fiscal del art. 287 (1 edificaciones, 2 vehículos livianos, equipo y muebles de oficina y computadoras, 3 lo demás; sin indicar se toma la 3, o terreno si no se deprecia) y marque *Dado en arrendamiento* en los activos alquilados a terceros. Al crear el cuadre de un año, la app toma los activos, la depreciación contable, el resultado del año y los anticipos, y calcula:
  - el **ajuste por inflación** (anexo D-2) con el multiplicador de la DGII para la fecha de cierre (tabla en *Configuración DGII*; agregue el de cada año cuando la DGII lo publique) sobre el menor entre el patrimonio fiscal y los activos no monetarios;
  - la **depreciación fiscal**: edificaciones una por una al 5% (anexo D-1) y las categorías 2 y 3 en una cuenta cada una al 25% y 15%, con la mitad de las compras del año (anexo D);
  - el **cuadre contable-fiscal** (anexo G): la diferencia con la depreciación contable, el ajuste del inventario y las compras con NCF no válido entran solas; agregue los demás ajustes (impuestos no deducibles, provisiones, etc.). Con las pérdidas a compensar, los anticipos y los créditos da la renta neta imponible, el impuesto (27%) y la diferencia a pagar.

- **Anexos A-1 y B-1 (IR-2)**: el balance general al cierre y el estado de resultados del ejercicio, agrupados en las casillas del formulario. Cada cuenta tiene el campo *Casilla del IR-2*: las del catálogo DGII ya lo traen; una cuenta sin casilla toma la de su cuenta padre o, si ninguna la tiene, una según su tipo (el reporte avisa cuáles). El reporte avisa si el balance no cuadra. El cuadre del IR-2 toma de aquí el beneficio antes del ISR (casilla 14) y los ingresos.

  El primer año los balances iniciales se proponen con el valor en libros: reemplácelos por el costo fiscal del IR-2 anterior. Los años siguientes parten del cuadre del año anterior. Las reparaciones de cada edificación llevadas al gasto (de las *Reparaciones de activos* no capitalizadas, o escritas en la fila) son deducibles hasta el 10% de su costo fiscal ajustado; el exceso se suma al costo fiscal y entra como ajuste positivo. Imprima el cuadre con el formato *Cuadre Fiscal IR-2* (editable en el constructor) para el contador. Valide el cuadre cuando presente el IR-2, y con *Crear base de anticipos* registre la base de los anticipos del año siguiente.

**Proporcionalidad del ITBIS (art. 349).** Si la empresa vende con ITBIS y también exento, el ITBIS de los gastos comunes a ambas ventas (alquiler, teléfono, publicidad, asesorías) solo se adelanta en la proporción de las ventas gravadas. Marque *ITBIS sujeto a proporcionalidad* en esos proveedores (o en cada factura de compra): va en esa columna del 606, y el resumen del IT-1 calcula el porcentaje no admitido y lo resta del ITBIS deducible. Las exportaciones de bienes y las ventas a zonas francas (B14) cuentan como gravadas.

El **Panel de cumplimiento** muestra en una pantalla los plazos y los montos del mes.

Para recibir los vencimientos por correo, active *Enviar recordatorios de vencimientos* en *Configuración DGII*. Cada mañana llega un correo por empresa con lo que vence en los próximos días (3 por defecto) o ese mismo día: IR-17, 606-609, IT-1, el anticipo del ISR, el IR-2 (120 días después del cierre del año fiscal de ERPNext; sin año fiscal, el 31 de diciembre) y, si hay nómina, el pago de la TSS, el IR-3, la regalía y el IR-13. Los lunes incluye las secuencias NCF por agotarse o por vencer. Hace falta una cuenta de correo saliente en Frappe. El botón *Vista previa de recordatorios* muestra lo que se enviaría hoy.

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
7. **Dependientes adicionales del SFS:** si el trabajador afilió a sus padres, suegros o hijos mayores de 21 años en la TSS, regístrelos en su ficha (*Dependientes adicionales del SFS*) con la fecha desde. Cada recibo descuenta el per cápita más el Fonamat de cada uno (RD$1,970.42 al mes desde octubre 2026; el monto se cambia en la configuración).
8. **Subsidios de la SISALRIL:** registre cada licencia médica, de maternidad o lactancia en *Nómina RD → Subsidios de la SISALRIL*. La app toma el salario de los recibos de nómina y estima el subsidio: enfermedad común desde el 4.º día (60 % ambulatoria, 40 % hospitalaria, hasta 182 días), maternidad (tres meses de salario cotizable) y lactancia (33 %, 12 % o 6 % del salario por doce meses, hasta tres salarios mínimos). El monto definitivo lo calcula la SISALRIL; anote el estado y lo que se reciba para controlar los reembolsos.

## Soporte

- Errores y sugerencias: [issues de GitHub](https://github.com/daniellora7/ERPNext-DR-Compilance/issues). Indique las versiones de Frappe, ERPNext y Frappe HR y los pasos para reproducirlo. Nunca adjunte certificados, contraseñas ni datos reales de clientes.
- Detalles técnicos de cada módulo: [NOTAS-TECNICAS.md](NOTAS-TECNICAS.md).
