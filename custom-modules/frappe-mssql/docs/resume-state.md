# Estado de continuación — ampliación SQL Server

Repositorio: https://github.com/GCruzJoa/frappe-hrms, rama codex/frappe-mssql-pilot.
upstream: https://github.com/frappe/hrms.git.
Código activo: C:\Users\kafay\Documents\Proyectos\frappe\hrms\custom-modules\frappe-mssql.
No publicar la copia histórica del repositorio separado GCruzJoa/frappe-mssql.

## Estado operativo solicitado

Piloto encendido: http://localhost:18000; Socket.IO 19000; SQL 127.0.0.1,14333.
Proyecto frappe-mssql-pilot: frappe, redis y sqlserver; sin MariaDB.
Original docker-frappe-1/docker-mariadb-1/docker-redis-1 apagados por pedido
del usuario. No encenderlos automáticamente ni tocar servicios ajenos.
No dejar comandos de prueba/build ni servidores adicionales al terminar.
El piloto tiene autorización explícita para seguir encendido.

Credenciales exclusivamente en .env y configuración privada; no imprimirlas.
Web: Administrator / PILOT_ADMIN_PASSWORD; SQL: frappe_pilot / PILOT_DB_PASSWORD.
La contraseña web no es admin.

## Trabajo verificado

Primera entrega: actualización original con respaldo completo y snapshot
exportados, bench update sin reset/force, fuente pública fijada, instalación
vacía de las tres aplicaciones, login/navegador, empresa, empleados, permisos
básicos, rollback, numeración concurrente, migraciones, reinicio y restauración.

Ampliación: búsqueda Link con N'T', agregaciones, parámetros GROUP BY,
funciones, tuplas/IN vacío, predicados escalares, alias, almacenamiento,
grafos BOM/Task/lotes, bloqueos de inventario y tipos NUMERIC/TIME adaptados.
Cambios al núcleo como parches reproducibles para versions.lock.json.

51 pruebas unitarias y contrato ODBC real. Catálogo de 46 módulos/1,000
DocTypes sin faltantes; 974 lecturas y 26 virtuales; 217 informes y tres
exclusiones por país; 24 recorridos con rollback. Ver module-coverage.md/json,
compatibility.md y private/module-validation para cobertura y límites.

Verify-Modules completo y Verify-Pilot posterior aprobaron. La aceptación
operativa final terminó a las 01:41:01 UTC del 2026-10-19, con dos migraciones,
reinicio y backup/restore de base más seis archivos. Respaldo exportado en
private/backups/20261019T014100Z/. Logs: modules-release-validation.log y
modules-pilot-acceptance.log, bajo private.

## QA aislada

Sitio mssql-qa.localhost / base y login frappe_mssql_qa, restaurada del piloto
con archivos y cifrado del sitio. Scheduler pausado y correos silenciados.
Misma instancia SQL, sin puertos ni procesos adicionales. Marcador
.frappe-mssql-qa.json y
manifiesto privado mssql-report-fixtures.json.

Datos ficticios persistidos solo en QA: empleado, asistencia, nómina, tasa
fiscal cero, cliente/proveedor, facturas, stock, BOM y plan de producción.
Los recorridos hacen rollback y limpian caché al terminar.

qa.prepare conserva una QA marcada existente y rechaza entornos parciales.
No borrar/restaurar automáticamente sobre las bases existentes. Refrescar QA
desde otra línea base necesita un procedimiento explícito; repetir prepare
no vuelve a copiar los datos del piloto.

## Operación

Desde el módulo activo:

- ./scripts/Start-Pilot.ps1
- ./scripts/Verify-Modules.ps1 -KeepRunning
- ./.venv/Scripts/python.exe scripts/export_module_results.py
- ./scripts/Verify-Pilot.ps1 -KeepRunning

Las dos verificaciones detienen el piloto por defecto; usar KeepRunning
mientras se mantenga la instrucción de dejarlo encendido. Stop-Pilot conserva
volúmenes. Build-SourceBase y Start-Pilot -Build -FromPublicSources permiten
reconstruir las fuentes fijadas.

private y .venv son junctions ignoradas hacia la ubicación antigua
C:\Users\kafay\Documents\Proyectos\frappe\custom-modules\frappe-mssql.
Backups, snapshots, credenciales, SQL ejecutado y trazas quedan privados.
Recuperar código, base y archivos originales desde el mismo respaldo.

## Trabajo pendiente del objetivo amplio

La integración completa de todos los procesos aún no está certificada.
Priorizar módulos sin recorridos propios de module-coverage.md, divisiones de
lotes, reservas/subcontratación, permisos por empresa/fila, casos de nómina,
contabilidad/stock, integraciones, texto completo, cargas masivas y una nueva
instalación vacía con esta ampliación. El inventario estático señala candidatos,
no fallos confirmados. No presentar catálogo o informes de humo como cobertura total.

Cambiar cualquier commit fijado exige regenerar/revisar parches y repetir
construcción, instalación y aceptación. No usar latest ni reset/force para
disimular incompatibilidades.
