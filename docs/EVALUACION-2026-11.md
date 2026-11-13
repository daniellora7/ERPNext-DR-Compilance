# Evaluación de ERPNext RD (2026-11-13)

Tres partes:

1. Cumplimiento en RD, con una comparación contra el mercado.
2. Seguridad.
3. Rendimiento.

Las notas van del 1 al 10. Salen de leer el código de la rama `feature/monitor-ecf-incentivos` (v0.6.0), de la suite de pruebas (325 en verde) y de Semgrep. No hubo pruebas de carga ni una auditoría externa.

## 1. Cumplimiento en RD

### Requisitos fundamentales (fuentes oficiales de la DGII)

- *Guía para ser Emisor Electrónico* (DGII, enero de 2025).
- *Descripción Técnica Servicios Emisores Electrónicos* (DGII, actualizada al 02-01-2026).
- Norma General 06-2018 (comprobantes y formatos de envío).
- Ley 32-23.
- Código Tributario, art. 50, literal h (conservación).

| Requisito | Fuente | En la app | Nota |
|---|---|---|---|
| Los 10 tipos de e-CF (E31, E32, E33, E34, E41, E43, E44, E45, E46, E47), XML validado con los XSD | Descripción técnica; lista de proveedores | Sí (`ecf/esquemas.py`, `emision.py`) | 9 |
| Firma SHA-256 sin preservar espacios; el XML no se altera después de firmar | Descripción técnica, p. 6 | Sí (`ecf/firma.py`) | 9 |
| Escapes de caracteres, sin tags vacíos, código de seguridad del QR codificado en la URL | Descripción técnica, pp. 4-6 | Sí | 9 |
| RFCE (E32 menor de RD$250,000), ANECF y consulta de estado | Descripción técnica | Sí | 9 |
| Representación impresa (RI) al receptor no electrónico | Guía, p. 4 | Sí (formatos en el constructor) | 9 |
| **Receptor obligatorio**: `/fe/recepcion/api/ecf` y `/fe/aprobacioncomercial/api/ecf` con SSL; autenticación opcional (semilla) | Descripción técnica, pp. 6-12 | Sí (`ecf/receptor.py`). Desde el 2026-11-13 revisa el certificado de quien firma y confirma cada e-CF con la DGII (ver la sección 2) | 9 |
| Recibir todos los e-CF de los proveedores y enviar acuse y aprobación comercial | Guía, p. 5 | Sí (*ECF Recibido*, captura de compras) | 8 |
| Contingencia por falta de conexión: enviar en 72 horas como máximo; RI con la leyenda de contingencia | Guía, p. 5; Instructivo de Contingencia de FE (DGII, octubre de 2026), p. 5 | Reintenta cada vez más espaciado. Desde el 2026-11-13 avisa del plazo de 72 h en el monitor y el Panel e imprime la leyenda | 9 |
| Contingencia sin poder emitir: declararla en la OFV, NCF no electrónicos por 15 días como máximo y e-CF que los reemplazan en 30 días, solo a la DGII | Guía, p. 5; Instructivo de Contingencia de FE, pp. 5-15 | Desde el 2026-11-13: fechas de la OFV en el *Emisor ECF*, serie B solo durante la contingencia y hasta 15 días, e-CF de reemplazo (`CodigoModificacion` 4) y su plazo en el monitor. Falta: *POS Invoice* y la RI del comprobante B | 8 |
| Conservar los e-CF (10 años, según fuentes secundarias) | Guía, p. 5; Código Tributario art. 50 h | Desde el 2026-11-13 no se pueden borrar los envíos, los e-CF recibidos ni las anulaciones firmadas, ni sus XML | 9 |
| Certificación ante la DGII (sets de datos, simulación y comunicación; declaración jurada) | Guía, p. 3 | El flujo existe (*Set Pruebas ECF*). **Falta pasarla de verdad** con el .p12 | pendiente |
| Formatos 606, 607, 608 y 609 | NG 06-2018 | Sí | 9 |
| IT-1, IR-17, anticipos, ISC | Instructivos de la DGII | Sí | 8 |
| IR-2 con cuadre fiscal, anexos e incentivos | Instructivo IR-2 (marzo de 2026) | Sí. La sección C del anexo D está en espera | 8 |
| DIOR (precios de transferencia) | Instructivo de la DIOR (mayo de 2026) | Sí. Los códigos de país, tipo de persona y estudio de precios van a mano | 7 |
| Nómina: TSS (AM y NV), IR-3, IR-13, regalía, bonificación, SIRLA (DGT-3 y DGT-4) | TSS, DGII, Ministerio de Trabajo | Sí | 9 |
| Padrón RNC y validación de NCF del proveedor | DGII | Sí (descarga cada noche) | 9 |
| Persona física con negocio (IR-1) y régimen simplificado (RST) | Ley 30-26 | **No** (8.7 y 8.8 en espera) | 3 |
| Impuesto sobre los activos | Código Tributario, título V | **No** (8.5 en espera de la Ley 30-26) | 3 |

**Conclusión de cumplimiento:**
- Para una **persona jurídica del régimen ordinario**, que es el caso de Dynamics Plastics, la app cubre los requisitos fundamentales. **Nota: 8/10 el 2026-11-13 por la mañana; 8.5/10 después de las correcciones de ese mismo día.**
- La contingencia y la conservación quedaron resueltas el mismo día.
- La falta que bloquea es la certificación real ante la DGII (falta el .p12).
- Para personas físicas, el RST y las empresas que pagan el impuesto sobre los activos, la app **todavía no sirve**.

### Comparación con el mercado

Estas son las fuentes de la comparación:
- La lista de proveedores autorizados de la DGII. La versión leída tiene 40 proveedores, todos con los 10 tipos de e-CF.
- Las comparativas de Galileo y Facturando (noviembre de 2026). Las publican proveedores que también aparecen en ellas, así que sus datos son **lo que dice cada proveedor**, no una verificación.
- Las páginas de Alegra, ADM Cloud e Indexa.

No se pudo confirmar nada de Monica, SAP Business One ni Dynamics 365 Business Central para RD: las páginas no respondieron o no tienen la localización en público.

Columnas: ERPNext RD; Alegra (vía Alanube); ADM Cloud (Fortech); Odoo + Indexa; Galileo; Pacioli; Facturador gratuito de la DGII.

| Función | ERPNext RD | Alegra | ADM Cloud | Odoo + Indexa | Galileo | Pacioli | Fact. gratuito |
|---|---|---|---|---|---|---|---|
| Proveedor autorizado por la DGII | No, todavía (se certifica cada empresa como emisor con software propio) | Sí (Alanube) | Sí | Sí (Indexa) | Dice que sí (2026) | Dice que sí (2025) | Es la DGII |
| e-CF, 10 tipos | Sí | Sí | Sí | Sí (Indexa) | Sí | Sí | Facturas y notas |
| Receptor y aprobación comercial | Sí | No confirmado | No confirmado | No confirmado | No confirmado | No confirmado | Sí |
| 606/607 | Sí | Sí | Sí | No confirmado | Sí | Sí | No |
| 608/609 | Sí | 608 | 608 | No confirmado | Premium | 608 | No |
| IT-1 | Sí | Sí | No confirmado | No confirmado | Sí | No confirmado | No |
| IR-17 | Sí | No confirmado | No confirmado | No confirmado | No confirmado | Sí | No |
| IR-2 con cuadre fiscal y anexos | Sí | No | No | No | No | No | No |
| DIOR | Sí | No | No | No | No | No | No |
| Nómina TSS, IR-3, regalía, SIRLA | Sí, completa | Producto aparte (TSS) | Plan nómina | No (no confirmado) | Premium (AFP, ARS, ISR) | Módulo RH | No |
| ISC, zonas francas, exportadores | Sí | No confirmado | No confirmado | No confirmado | No | No | No |
| POS sin conexión | No (POS de ERPNext en línea) | Sí | No confirmado | Sí (Odoo POS) | No | No confirmado | No |
| Persona física / RST | No | Sí (pymes) | Sí | Sí | Sí | Sí | Sí |
| Multiempresa | Sí | Planes para contadores | No confirmado | Sí | Sí | Sí | No |
| Licencia y costo | GPL-3, gratis (hosting propio) | Desde US$15/mes | Desde US$20-24/mes | LGPL-3 + Odoo | Desde gratis | US$5-95 | Gratis (150/mes) |

**Lectura de la tabla:**
- **Ventaja de ERPNext RD:** la profundidad fiscal y laboral. IR-2 con anexos, DIOR, ISC, zonas francas, nómina completa con SIRLA y receptor propio. Ningún competidor confirma estas funciones en público.
- **Desventajas:**
  1. No está certificado todavía. Los demás venden «certificado por la DGII» y es lo primero que pide el mercado.
  2. No sirve para personas físicas ni para el RST, el segmento más grande en número.
  3. Su POS no funciona sin conexión.
  4. Hay que operar el servidor. Es SaaS en los demás.

## 2. Seguridad: 7/10 (8/10 después de las correcciones)

Las notas entre paréntesis son las de después de las correcciones del 2026-11-13 por la tarde, que se describen debajo de la tabla.

| Aspecto | Nota | Hallazgos |
|---|---|---|
| Autenticación y permisos | 8 | Ningún `allow_guest`. 55 métodos whitelisted con tipos y `POST` en los que escriben. El portal del empleado comprueba el dueño del volante. Hay 58 `ignore_permissions=True` que conviene revisar uno por uno. |
| Inyección SQL y XSS | 9 | Semgrep (reglas de Frappe más `python.lang.security`) da 3 hallazgos, los tres menores: una ruta fija y dos `filter()`. Se usan `frappe.qb` y `get_all`. Vue escapa lo que muestra. |
| XML (XXE, bombas) | 9 | El parser tiene `resolve_entities=False`, `no_network` y `huge_tree=False`. Límite de 5 MB por archivo. |
| **Receptor público e-CF** | **5 (8)** | (1) `firma.verificar` comprueba la firma con el certificado que trae el mismo XML, pero no comprobaba quién era el dueño del certificado ni que lo hubiera emitido una entidad autorizada por el INDOTEL. Cualquiera con un certificado hecho a mano podía rechazar comercialmente una factura nuestra o registrar un e-CF falso de un proveedor. (2) Las cuatro rutas `/fe/...` no tenían límite de peticiones: se podían pedir semillas sin fin, y cada una ocupa Redis 5 minutos. (3) El `auth_hook` pone «Administrator» un momento para pasar el control de Frappe y lo devuelve a Guest al atender. Funciona, pero cualquier cambio de orden en Frappe lo vuelve peligroso; sigue igual. |
| Secretos y certificado | 8 | Contraseña del .p12 en un campo *Password*. El .p12 se exige privado. `.env` fuera del repo. |
| Integridad y conservación | 6 (9) | System Manager y Accounts Manager podían borrar el *Envio ECF*, y con él los XML. |

**Corrección a la primera versión de este informe:** decía que el SN del certificado debía coincidir con el RNC del emisor. La descripción técnica de la DGII (p. 6) dice que el SN es el RNC, la cédula o el pasaporte del *propietario* del certificado, y el certificado es de la persona que representa al contribuyente (Guía, p. 2). Por eso el SN no se puede comparar con el RNC del documento.

**Corregido el 2026-11-13:**
- El certificado de quien firma debe estar vigente a la fecha de la firma. Si se cargan en *Configuracion DGII* los certificados de las entidades del INDOTEL, debe haberlo emitido una de ellas.
- Cada e-CF recibido se confirma con la consulta de estado de la DGII, que solo conoce los e-CF que envió su emisor de verdad. Uno «Rechazado» o «No encontrado» no se aprueba.
- La aprobación comercial recibida debe traer el RNC del comprador y el monto del e-CF que emitimos, y no cambia una ya recibida.
- Hay un límite de peticiones por IP en `/fe/...`: 30 por minuto para la semilla y la autenticación, 300 para la recepción.
- Lo firmado y lo recibido, y sus XML, ya no se pueden borrar.
- **Queda:** cargar los certificados raíz del INDOTEL (lo hace el usuario). Sin ellos, el certificado de un e-CF de proveedor sigue sin comprobarse contra una entidad, pero la DGII lo confirma. La aprobación comercial recibida no tiene consulta en la DGII: sin los certificados raíz depende del RNC y el monto.
| Licencias y dependencias | 8 | Versiones fijas. Terceros GPL, LGPL o MIT. Semgrep en el CI del Marketplace. |
| Infraestructura | sin nota | Todavía no está desplegado. En Dokploy: HTTPS (el receptor lo exige), 2FA para los administradores, respaldos fuera del servidor y puertos de MariaDB y Redis cerrados. |

## 3. Rendimiento: 7/10 (7.5/10 después de las correcciones)

**Medido en el sitio local el 2026-11-13**, con 14 facturas de septiembre y la caché caliente:
- Antes: el 607 tardaba unos 10 ms y hacía 15 consultas por factura. En la primera corrida, con la caché fría, fueron 81 ms por factura.
- Después de la carga por lotes: 3.9 ms por factura en el 607 y 5.0 ms en el 606.
- Para 10,000 facturas son unos 40 segundos, contra unos 100 antes.
- Lo que queda es la consulta de pagos de cada factura.

| Aspecto | Nota | Hallazgos |
|---|---|---|
| Trabajo en segundo plano | 9 | Envíos a la DGII, contingencia, padrón, DGCP y conversión de compras van en colas y en el scheduler. Ninguna petición espera a la DGII sin tiempo límite. |
| Índices | 6 (8) | Hay índices en el padrón (RNC y FULLTEXT), en *Secuencia NCF* y en los campos de factura que se buscan. **Sin índices** en *Envio ECF* (`company` + `estado`, `company` + `encf`) ni en *ECF Recibido* (`company` + `rnc_emisor` + `encf`). Son las tablas que más crecen, y el monitor, la recepción y la aprobación comercial filtran por esas columnas. |
| Reportes fiscales | 6 (7) | El 606 y el 607 abren cada factura con `frappe.get_doc` (N+1), y ningún reporte es *prepared report*. Con unas 10,000 facturas al mes, el 607 puede pasar del minuto y bloquear un worker. El soporte de exportadores calcula el IT-1 doce veces. Con el volumen de hoy no se nota. |
| Panel y monitor | 7 | Acotados a 30 días, pero hacen varios `count` en cada carga. Sin caché. |
| Padrón RNC | 8 | Carga masiva cada noche en la cola `long`, con commits por lotes. |
| Frontend | 8 | Vite y frappe-ui, con rutas separadas. |
| Medición | 3 (4) | No hay pruebas de carga. Solo se midieron el 606 y el 607 en el sitio local (ver arriba). |

## Lo que más sube las notas (en orden)

1. ✅ **Receptor:** certificado vigente y de una entidad del INDOTEL (si se configuran), confirmación con la DGII, aprobación solo del comprador y límite de peticiones. (Seguridad del receptor 5 → 8.)
2. ✅ ***Envio ECF* y XML no borrables.** Un e-CF se corrige con una nota de crédito y una secuencia sin usar se anula con la ANECF. (Conservación 6 → 9.)
3. ✅ **Contingencia:** aviso de las 72 horas, serie B durante una contingencia declarada (15 días) y e-CF de reemplazo con su plazo de 30 días. (6 y 4 → 9 y 8.)
4. ✅ **Índices** de *Envio ECF* y *ECF Recibido*. El 606, el 607 y el IT-1 cargan las facturas por lotes. (Índices 6 → 8; reportes 6 → 7: los pagos de cada factura todavía se consultan uno por uno.)
5. **Certificación real** ante la DGII con el .p12 (lo hace el usuario).
6. **IR-1 y RST** cuando salgan el instructivo y el reglamento (abren el mercado de personas físicas y pymes).
7. Los pagos del 606 y el 607 en una consulta por lote, y *prepared report* para los períodos muy grandes.
