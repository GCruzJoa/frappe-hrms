# Estado de continuación — 2026-10-18

Repositorio principal: https://github.com/GCruzJoa/frappe-hrms, rama
codex/frappe-mssql-pilot, basada en develop del fork. El remoto upstream apunta
a https://github.com/frappe/hrms.git. Las personalizaciones están en
custom-modules/frappe-mssql; el repositorio separado GCruzJoa/frappe-mssql
conserva únicamente la primera entrega histórica.

## Trabajo completado

- Sitio original MariaDB actualizado con bench update, sin reset/force, con
  respaldo de base/archivos/configuración y snapshot exportado antes de migrar.
  Login API y navegador verificados. Se conserva activo.
- Construcción pública de Frappe, ERPNext y HRMS fijados; instalación nueva de
  las tres aplicaciones en SQL Server 2025 y adaptador independiente integrado
  mediante parches que validan commit y hashes.
- Veintitrés pruebas unitarias y prueba ODBC real aprobadas, incluidas precisión,
  bloqueos, conexiones reutilizadas, transacciones y secuencias.
- Aceptación funcional aprobada: empresa, empleados, permisos básicos, rollback
  ante error, numeración concurrente, dos migraciones, reinicio y restauración
  nativa de base/archivos. Ver acceptance-results.md.
- Navegador: login, alta de Lucía Núñez y edición/consulta de Lucía María Núñez
  (HR-EMP-00001). Captura en private/employee-ui.jpg.
- Piloto detenido al finalizar; volúmenes conservados. No quedan builds ni
  comandos de desarrollo iniciados por esta tarea en ejecución.

## Ubicación y operación

Código activo:
C:\Users\kafay\Documents\Proyectos\frappe\hrms\custom-modules\frappe-mssql.
La ubicación anterior
C:\Users\kafay\Documents\Proyectos\frappe\custom-modules\frappe-mssql
conserva los artefactos privados; private y .venv del módulo activo son
junctions ignoradas hacia esos directorios. .env también está ignorado.
No continuar publicando la copia anterior del código.

Desde el módulo activo, ./scripts/Start-Pilot.ps1 reanuda los volúmenes;
./scripts/Verify-Pilot.ps1 verifica y detiene, y ./scripts/Stop-Pilot.ps1
detiene sin eliminar volúmenes. Para reconstruir desde fuentes públicas usar
Build-SourceBase.ps1 y Start-Pilot.ps1 -Build -FromPublicSources.
Web localhost:18000; socket 19000; SQL Server localhost,14333.

No recrear ni eliminar automáticamente las bases. Los marcadores
.core-created y .hrms-installed corresponden a la instalación completa.
Las credenciales están exclusivamente en .env y la configuración privada.

## Próximas etapas opcionales

No queda trabajo pendiente de los recorridos de esta primera entrega. La
matriz de compatibilidad registra cobertura parcial y casos no implementados.
Migración de datos desde MariaDB, producción y cobertura completa de nómina,
asistencia, permisos e informes requieren una etapa posterior.

Actualizar upstream no actualiza automáticamente los commits de la imagen:
cualquier cambio de versions.lock.json exige regenerar/revisar los parches y
repetir construcción, instalación nueva y aceptación. Mantener código, base y
archivos del mismo respaldo si es necesario recuperar el sitio original.
