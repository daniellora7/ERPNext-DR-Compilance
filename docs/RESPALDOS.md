# Respaldos

## Respaldo diario automático

El servicio `backup` de `deploy/compose.yaml` corre `bench --site all backup --with-files` una vez al día. El respaldo incluye la base de datos, los archivos públicos y privados y la configuración del sitio.

| Variable | Valor por defecto | Para qué |
|---|---|---|
| `BACKUP_HORA` | `07:00` | Hora del respaldo, en UTC. Las 07:00 UTC son las 3:00 a. m. en República Dominicana. |
| `BACKUP_DIAS` | `7` | Días que se guardan. Los respaldos más viejos se borran. |

Los respaldos quedan en el volumen `sites`, en `sites/<sitio>/private/backups/`:

```
20261016_070001-erp_ejemplo_com-database.sql.gz
20261016_070001-erp_ejemplo_com-files.tar
20261016_070001-erp_ejemplo_com-private-files.tar
20261016_070001-erp_ejemplo_com-site_config_backup.json
```

Para ver la hora del próximo respaldo, o si alguno falló:

```bash
docker compose -f deploy/compose.yaml logs backup
```

## Copia fuera del servidor

El respaldo diario queda en el mismo disco que los datos. Si el servidor se pierde, se pierden los dos. Por eso conviene guardar también una copia en otro lugar.

Frappe trae esa copia en *S3 Backup Settings* (busque «S3 Backup Settings» en la barra). Funciona con cualquier almacenamiento compatible con S3: AWS S3, Backblaze B2, Cloudflare R2, Wasabi o MinIO.

1. Cree un bucket privado y una llave de acceso que solo pueda escribir en ese bucket.
2. En *S3 Backup Settings*, marque *Enable Automatic Backup* y llene *Endpoint URL*, *Access Key ID*, *Secret Access Key* y *Bucket*.
3. Elija la frecuencia (*Daily*) y marque *Backup Files* para incluir los archivos adjuntos.
4. Pulse *Take Backup Now* y revise que aparezca en el bucket.

En Dokploy también se pueden programar copias del volumen `db-data` a un destino S3, en *Volume Backups*.

## Respaldo manual

Antes de actualizar ERPNext, Frappe HR o la app, haga siempre un respaldo manual:

```bash
docker compose -f deploy/compose.yaml exec backend bench --site <sitio> backup --with-files
```

## Restaurar

1. Copie los cuatro archivos del respaldo al contenedor, por ejemplo a `/tmp/respaldo/`:

   ```bash
   docker cp ./respaldo <proyecto>-backend-1:/tmp/respaldo
   ```

2. Restaure. Esto **reemplaza** la base de datos y los archivos del sitio:

   ```bash
   docker compose -f deploy/compose.yaml exec backend bench --site <sitio> restore \
     /tmp/respaldo/<fecha>-database.sql.gz \
     --with-public-files /tmp/respaldo/<fecha>-files.tar \
     --with-private-files /tmp/respaldo/<fecha>-private-files.tar \
     --db-root-username root
   ```

   La contraseña que pide es la de `DB_ROOT_PASSWORD`.

3. Ponga la base al día, revise que las tareas programadas estén activas y reinicie:

   ```bash
   docker compose -f deploy/compose.yaml exec backend bench --site <sitio> migrate
   docker compose -f deploy/compose.yaml exec backend bench --site <sitio> scheduler status
   docker compose -f deploy/compose.yaml exec backend bench --site <sitio> enable-scheduler
   docker compose -f deploy/compose.yaml restart
   ```

   Sin las tareas programadas no se descarga el padrón RNC ni se reenvían los e-CF en contingencia.

La `encryption_key` del sitio está en `site_config_backup.json`. Sin ella no se pueden leer las contraseñas guardadas, como la del certificado `.p12` del e-CF. Si restaura en un sitio nuevo, copie esa llave a `sites/<sitio>/site_config.json` antes de abrirlo.

Pruebe la restauración de vez en cuando en un sitio aparte. Un respaldo que nunca se restauró no está probado.
