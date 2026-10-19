# Registro de implementación

## 2026-10-18

- Se creó el directorio independiente `custom-modules/frappe-mssql`.
- Se inspeccionó el entorno Frappe/ERPNext/HRMS 17 en Docker.
- Se puso el sitio en mantenimiento, se deshabilitó el scheduler y se generó un respaldo completo con archivos.
- Los respaldos, configuraciones y snapshots se conservan bajo `private/`, excluido del control de versiones.
- Los criterios de esta primera entrega se completaron; la cobertura completa de HRMS sigue fuera del alcance del piloto.

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
- 23 pruebas unitarias pasaron. NOWAIT se verificó con dos conexiones ODBC y un bloqueo real en conflicto.
- Imagen del piloto construida; sincronización de DocTypes Frappe y hooks de instalación completados, incluyendo resincronización de tablas existentes.
- Índices por prefijo, unicidad parcial de la cola y validación DISTINCT/ORDER BY cuentan con adaptaciones explícitas.
- Sitio original comprobado también en navegador: login correcto y escritorio con Frappe HR/ERPNext.
- Código incorporado al fork `GCruzJoa/frappe-hrms`, rama `codex/frappe-mssql-pilot`; las siguientes revisiones se publican allí.
- Construcción desde las fuentes públicas fijadas completada; commits y árboles limpios verificados antes de aplicar parches.
- Instalación nueva completa de Frappe, ERPNext y HRMS sobre SQL Server, con sus hooks reales.
- Se corrigieron transacciones ODBC y limpieza de conexiones reutilizadas, conversión de Singles, UPDATE correlado, secuencias, comprobación TCP de migraciones y manifiestos de recursos web.
- Verificación completa aprobada: asistente oficial, empleados, búsqueda/paginación, permisos básicos, rollback ante clave duplicada, doce números concurrentes, dos migraciones y persistencia tras reinicio.
- Respaldo nativo verificado y restaurado en una base nueva; archivos públicos/privados y configuración recuperados y comparados por hash.
- Login del piloto comprobado en navegador; alta de Lucía Núñez (HR-EMP-00001), edición a Lucía María Núñez y consulta en la lista. Evidencia privada guardada.
- Piloto detenido al terminar, conservando volúmenes. Sitio original conservado activo. Detalles y límites en acceptance-results.md y compatibility.md.

### Ampliación posterior solicitada

- Se reanudó el piloto y se apagaron los tres contenedores originales por
  petición del usuario; el piloto queda autorizado a seguir encendido.
- Se corrigió la búsqueda Link con literales Unicode N'T' sin deshabilitar
  validación ni interpolar valores en SQL.
- La auditoría comparó las fuentes fijadas con los 1,000 DocTypes instalados:
  Frappe 308, ERPNext 534 y HRMS 158, sin faltantes ni módulos mal asignados.
- Se incorporaron auditoría reproducible y matriz para los 46 módulos
  declarados: 974 lecturas y 26 virtuales sin tabla propia.
- Se adaptaron GROUP BY parametrizado y dependencias por clave primaria,
  predicados escalares, tuplas/IN vacío, funciones, alias, informes de
  almacenamiento, árboles BOM/Task/lotes y bloqueos de stock.
- Se agregó una QA separada mediante restauración nativa; los fixtures de
  informes persisten exclusivamente allí. Sus correos y scheduler se inhiben.
- Con datos, se detectaron y corrigieron errores adicionales en resúmenes de
  clientes/proveedores, lotes, agregación fiscal y contrato TIME de Frappe.
- sql() entrega NUMERIC como float y TIME como timedelta, como espera Frappe;
  native() conserva Decimal/time y sus microsegundos para comprobación exacta.
- Se verificaron 217 informes de 220; tres regionales mantienen restricciones
  de país para la empresa dominicana. No se acreditan sus cálculos extranjeros.
- Se añadieron 24 recorridos de negocio con rollback y 51 pruebas unitarias.
  La matriz separa área funcional del módulo donde viven los documentos.
- Parche explícito para el nombre de Item Balance (Simple), cuyo directorio
  Python en ERPNext fijado continúa llamándose item_balance.
- Se conserva un inventario pendiente: módulos sin escenarios propios,
  permisos avanzados, integraciones, lotes reales, carga y nueva instalación
  vacía con la ampliación. La cobertura de humo no es certificación total.
