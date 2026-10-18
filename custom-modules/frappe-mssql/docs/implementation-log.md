# Registro de implementación

## 2026-10-18

- Se creó el directorio independiente `custom-modules/frappe-mssql`.
- Se inspeccionó el entorno Frappe/ERPNext/HRMS 17 en Docker.
- Se puso el sitio en mantenimiento, se deshabilitó el scheduler y se generó un respaldo completo con archivos.
- Los respaldos, configuraciones y snapshots se conservan bajo `private/`, excluido del control de versiones.
- Los criterios del piloto siguen pendientes de validación; este registro no acredita compatibilidad completa.

### Avance comprobado

- Snapshot previo: `local/frappe-hrms:pre-mssql-20261018`; exportado a Windows, con hash SHA-256 y manifiesto de imagen comprobados.
- El respaldo SQL comprimido se leyó correctamente (11,896,426 bytes descomprimidos); los archivos públicos y privados también se verificaron.
- `bench update` terminó con código 0, incluyendo requisitos, migraciones y compilación.
- Revisiones actualizadas: Frappe `ec6e65cb5a18ecda14364f85a04e8f0b91e59414`, ERPNext `b365eb695844e1db9a7484df255c428cefe6e57e`, HRMS `44e80d64686ae07297095930e5102aadaf034bc8`.
- Sitio original reactivado: `/login` respondió 200, la autenticación devolvió `Logged In` y Redis respondió `PONG`.
- SQL Server 2025: `17.0.5015.4`, Enterprise Developer; imagen oficial fijada por digest.
- Esquema inicial: 11 tablas creadas realmente en SQL Server; prueba de Unicode/savepoint satisfactoria y base temporal eliminada.
- Prueba real con pyodbc 5.3.0 y ODBC 18.6.1.1: parámetros, Unicode, commit, rollback, savepoint, bloqueo, upsert compuesto y NOT IN vacío satisfactorios.
- SQLGlot se alineó con el requisito existente de Frappe: versión 30.16.0.
- 19 pruebas unitarias pasaron. NOWAIT se verificó con dos conexiones ODBC y un bloqueo real en conflicto.
- Imagen del piloto construida; sincronización de DocTypes Frappe y hooks de instalación completados, incluyendo resincronización de tablas existentes.
- Índices por prefijo, unicidad parcial de la cola y validación DISTINCT/ORDER BY cuentan con adaptaciones explícitas.
- Sitio original comprobado también en navegador: login correcto y escritorio con Frappe HR/ERPNext.
- Código incorporado al fork `GCruzJoa/frappe-hrms`, rama `codex/frappe-mssql-pilot`; las siguientes revisiones se publican allí.
- Pendientes: ERPNext/HRMS, construcción pública final y aceptación funcional completa.
