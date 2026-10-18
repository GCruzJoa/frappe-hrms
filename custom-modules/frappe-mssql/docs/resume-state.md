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

## Punto pendiente

La instalación todavía no termina: SQL Server exige que los campos de `ORDER BY`
aparezcan en `SELECT DISTINCT`. Falla la consulta de dominios activos durante
la instalación de Frappe. `scripts/make_patches.py` contiene la corrección para
aplicar la validación existente de PostgreSQL también a SQL Server; falta
regenerar `patches/frappe.patch`, construir y verificarla.

No se ha certificado la instalación de ERPNext/HRMS, login del piloto, empresa,
empleados, permisos, migraciones repetidas, reinicio ni backup/restauración.

La reconstrucción pública `Dockerfile.source` comenzó, pero se canceló por la
pausa. Su flujo todavía debe terminar y validarse. El respaldo/restauración de
archivos se amplió y también necesita ejecutarse.

## Entorno local y continuación

El banco de trabajo original está en
`C:\Users\kafay\Documents\Proyectos\frappe\custom-modules\frappe-mssql`.
El fork local está en `C:\Users\kafay\Documents\Proyectos\frappe\hrms`.
Los archivos públicos del módulo se incorporan al fork bajo
`custom-modules/frappe-mssql`; los secretos, respaldos, referencias upstream y
logs permanecen en el banco de trabajo, excluidos de Git.

Los volúmenes `frappe-mssql-pilot_*` conservan la instalación incompleta. No
recrear bases automáticamente ni tocar el sitio original. La marca
`.core-created` aún no existe. Las herramientas locales de diagnóstico
`private/resume_core.py` y sus logs permiten continuar sin borrar las tablas.
La configuración y contraseñas están exclusivamente en `.env` ignorado.

1. Regenerar y revisar los parches contra las referencias privadas fijadas.
2. Construir el piloto y levantar únicamente SQL Server/Redis para continuar
   el núcleo incompleto mediante la herramienta de diagnóstico.
3. Tras completar el núcleo, iniciar Frappe para instalar ERPNext/HRMS.
4. Corregir incompatibilidades explícitas; no omitir hooks ni sustituir motores.
5. Validar instalación nueva desde cero, criterios de aceptación y navegador.
6. Detener los contenedores temporales conservando volúmenes al terminar, salvo
   petición explícita de dejarlos activos. Conservar el sitio original activo.

Actualizar este registro con resultados reales antes de la entrega final.
