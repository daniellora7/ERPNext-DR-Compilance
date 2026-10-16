# Despliegue en Dokploy

Esta guía publica ERPNext, Frappe HR y `erpnext_rd` con `deploy/compose.yaml`. Es el mismo compose que se usa en local y en el CI. El sitio queda con HTTPS en su dominio y con respaldo diario (ver [RESPALDOS.md](RESPALDOS.md)).

## Requisitos

- Un servidor con Dokploy instalado. Lo mínimo son 4 GB de RAM y 2 vCPU; con 8 GB va mejor, sobre todo al importar el padrón RNC.
- Un dominio o subdominio, por ejemplo `erp.ejemplo.com`, con un registro **A** que apunte a la IP del servidor.
- La imagen publicada en GHCR. El workflow `build-image.yml` la publica en cada push a `main` y en cada tag `vX.Y.Z`:

  ```
  ghcr.io/daniellora7/erpnext-dr-compilance:<versión>
  ```

  El paquete de GHCR nace privado. Hay dos opciones:
  - Hacerlo público: en GitHub, *Packages* → `erpnext-dr-compilance` → *Package settings* → *Change visibility*.
  - Dejarlo privado y registrarlo en Dokploy, en *Settings* → *Registry*, con un token de GitHub que solo tenga `read:packages`.

## 1. Crear el servicio

1. En Dokploy, cree un proyecto y dentro un servicio **Compose**.
2. Use estos datos para el origen:
   - *Provider*: GitHub, repositorio `daniellora7/ERPNext-DR-Compilance`.
   - *Branch*: `main`.
   - *Compose Path*: `./deploy/compose.yaml`.
3. En *Advanced*, active **Isolated Deployments**. Así todos los servicios del stack quedan en su propia red junto al proxy de Dokploy, y el `frontend` sigue viendo al `backend` y al `websocket`.

## 2. Variables de entorno

En la pestaña *Environment*:

```
ERPNEXT_IMAGE=ghcr.io/daniellora7/erpnext-dr-compilance
ERPNEXT_IMAGE_TAG=0.3.0
SITE_NAME=erp.ejemplo.com
ADMIN_PASSWORD=<contraseña larga del Administrator>
DB_ROOT_PASSWORD=<otra contraseña larga>
BACKUP_HORA=07:00
BACKUP_DIAS=7
```

- `SITE_NAME` debe ser el dominio. El receptor de e-CF y los enlaces de los correos usan ese nombre.
- Genere las contraseñas con un gestor de contraseñas y guárdelas ahí. **No las suba al repositorio.**
- `HTTP_PUBLISH_PORT` y `HTTP_BIND_ADDRESS` no hacen falta. El puerto solo queda abierto en el `127.0.0.1` del servidor y el acceso público entra por el proxy.

## 3. Dominio y HTTPS

En la pestaña *Domains*, agregue el dominio:

- *Service*: `frontend`.
- *Container Port*: `8080`.
- *HTTPS*: activado, con el certificado de *Let's Encrypt*.

Con *Preview Compose* puede revisar las etiquetas de Traefik que agrega Dokploy.

## 4. Primer despliegue

Pulse *Deploy*. La primera vez, el servicio `create-site` crea el sitio con las tres apps, y eso tarda unos minutos. Para seguirlo, abra los *Logs* de `create-site`; termina con código 0.

Después:

1. Entre a `https://erp.ejemplo.com` como `Administrator` y complete el asistente con la empresa (país República Dominicana, moneda DOP).
2. Siga la [guía de uso](GUIA-DE-USO.md) para los tipos de comprobante, las secuencias, el catálogo de cuentas y la nómina.
3. En una terminal del servicio `backend` (*Docker* → *Terminal*), fije la URL pública:

   ```bash
   bench --site erp.ejemplo.com set-config host_name https://erp.ejemplo.com
   ```

## 5. Actualizar

1. Haga un respaldo manual (ver [RESPALDOS.md](RESPALDOS.md)).
2. Cambie `ERPNEXT_IMAGE_TAG` a la versión nueva y pulse *Deploy*.
3. `create-site` ve que el sitio ya existe y corre `bench migrate`. Revise que termine con código 0.

Si algo sale mal, vuelva a la versión anterior y restaure el respaldo.

## 6. e-CF: receptor público

Con el sitio en línea y HTTPS, las rutas que exige la DGII para recibir e-CF de proveedores ya responden:

```
https://erp.ejemplo.com/fe/autenticacion/api/semilla
https://erp.ejemplo.com/fe/autenticacion/api/validacioncertificado
https://erp.ejemplo.com/fe/recepcion/api/ecf
https://erp.ejemplo.com/fe/aprobacioncomercial/api/ecf
```

Registre `https://erp.ejemplo.com` como URL de recepción y de aprobación comercial en el portal de facturación electrónica de la DGII. Hágalo cuando tenga el certificado y haya pasado la certificación.

## Problemas comunes

| Síntoma | Causa probable |
|---|---|
| `create-site` falla con `Access denied` | Se cambió `DB_ROOT_PASSWORD` después de crear la base. Use la contraseña original. |
| 404 o «site does not exist» | `SITE_NAME` cambió después del primer despliegue. El sitio conserva el nombre con que se creó. |
| Error 502 en el dominio | El `backend` todavía arranca, o *Isolated Deployments* está apagado. |
| No baja la imagen | El paquete de GHCR es privado y falta el registro en Dokploy. |
