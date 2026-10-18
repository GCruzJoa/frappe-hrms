# Estado de continuación — 2026-10-18

Repositorio principal solicitado: `https://github.com/GCruzJoa/frappe-hrms`, rama
`codex/frappe-mssql-pilot`, basada en `develop` del fork. El repositorio separado
`GCruzJoa/frappe-mssql` conserva la primera entrega; los próximos cambios se
publican en el fork de HRMS.

## Comprobado

- Actualización original completada con `bench update`, sin reset/force, con
  respaldo previo completo y snapshot exportado. Sitio MariaDB original activo.
- Revisiones exactas en `versions.lock.json`; los parches validan commit y hashes.
- Imagen `local/frappe-mssql:pilot` construida con ODBC 18.6.1.1 y pyodbc 5.3.0.
- 17 pruebas unitarias y prueba real ODBC aprobadas. Esta última incluye Unicode
  largo, commit/rollback encadenados, savepoints, bloqueos y upsert compuesto.
- La sincronización del esquema Frappe avanzó hasta las tareas posteriores a
  DocTypes. Se adaptaron índices por prefijo y unicidad parcial de la cola.

## Punto actual

La corrección de DISTINCT/ORDER BY está aplicada y comprobada. Frappe completó
la resincronización de todos sus DocTypes y sus hooks de instalación. Se adaptó
NOWAIT y se verificó con dos conexiones y un bloqueo real. Pasan 19 pruebas
unitarias. ERPNext se está instalando en el contenedor principal del piloto.

No se ha certificado la instalación de ERPNext/HRMS, login del piloto, empresa,
empleados, permisos, migraciones repetidas, reinicio ni backup/restauración.

La reconstrucción pública `Dockerfile.source` está en curso. El primer intento
completó dependencias pero falló al suponer que Bench usa un remoto `origin`;
se corrigió para los remotos reales y se dividió en fases con cachés. El flujo
todavía debe terminar y validarse. El respaldo/restauración de archivos se
amplió y también necesita ejecutarse.

## Entorno local y continuación

El código activo está en el fork local:
`C:\Users\kafay\Documents\Proyectos\frappe\hrms\custom-modules\frappe-mssql`.
Se continúa trabajando y publicando desde ese directorio. La ubicación anterior
`C:\Users\kafay\Documents\Proyectos\frappe\custom-modules\frappe-mssql`
conserva los artefactos privados; los directorios locales `private` y `.venv`
del módulo activo son junctions ignoradas por Git/Docker hacia esos artefactos.
El `.env` local está copiado e ignorado. No editar ni publicar la copia anterior
del código como repositorio principal.

Los volúmenes `frappe-mssql-pilot_*` conservan la instalación incompleta. No
recrear bases automáticamente ni tocar el sitio original. La marca
`.core-created` existe después de completar los hooks del núcleo. Las
herramientas y logs de diagnóstico están en `private/`; el restablecimiento de
sitios incompletos se niega a borrar un sitio con ese marcador.
La configuración y contraseñas están exclusivamente en `.env` ignorado.

1. Continuar la instalación de ERPNext/HRMS y revisar su log.
2. Completar la construcción de fuentes públicas y comprobar sus revisiones.
3. Conservar las versiones fijadas al corregir nuevas incompatibilidades.
4. Corregir incompatibilidades explícitas; no omitir hooks ni sustituir motores.
5. Validar instalación nueva desde cero, criterios de aceptación y navegador.
6. Detener los contenedores temporales conservando volúmenes al terminar, salvo
   petición explícita de dejarlos activos. Conservar el sitio original activo.

Actualizar este registro con resultados reales antes de la entrega final.
