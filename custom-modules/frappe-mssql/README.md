# Frappe HR / SQL Server: piloto experimental

Personalización independiente para utilizar SQL Server 2025 como motor principal
de un sitio Frappe/ERPNext/HRMS 17. El código fuente de las aplicaciones se fija
por commit y los cambios de integración se distribuyen como parches verificables.

## Estado

Piloto funcional verificado el 18 de octubre de 2026: instalación nueva de
Frappe, ERPNext y HRMS 17 en SQL Server 2025, login, empresa de prueba y alta,
consulta y edición de empleados desde la interfaz. Pasaron permisos básicos,
rollback ante un error real, numeración concurrente, dos migraciones, reinicio
y respaldo/restauración nativos. La instalación original de MariaDB se actualizó
y conserva su funcionamiento. El piloto se entrega detenido con sus volúmenes.

Los resultados y sus límites están en `docs/acceptance-results.md` y
`docs/compatibility.md`. No se certifica la cobertura completa de HRMS ni su uso
en producción.

## Organización

- `src/frappe_mssql`: conexión ODBC, parámetros SQL, traducción por AST,
  esquema, aprovisionamiento, respaldo y comprobaciones de aceptación.
- `patches`: diferencias y hashes del código original para las tres aplicaciones.
- `scripts`: operaciones PowerShell y herramientas de preparación de parches.
- `private`: respaldos, snapshots y referencias locales, excluidos de Git y Docker.

## Requisitos y operación

PowerShell 7 y Docker Desktop en Linux/x86_64; al menos 3.5 GiB de memoria disponible para el
piloto además del consumo del entorno existente. SQL Server Developer se utiliza
para desarrollo. Las credenciales se generan en `.env`, excluido de Git.

Las revisiones y los parches ya están registrados. En una máquina nueva, desde
este directorio ejecutar primero `./scripts/Build-SourceBase.ps1` para construir
las aplicaciones desde los commits públicos fijados. Este flujo se completó y
se utilizó para instalar el sitio desde cero. En la máquina de desarrollo
también puede utilizarse el snapshot local registrado. No sustituir las
versiones registradas por una imagen `latest`.

```powershell
./scripts/Build-SourceBase.ps1
./scripts/Start-Pilot.ps1 -Build -FromPublicSources
docker compose --project-name frappe-mssql-pilot --file compose.yaml logs --tail 100 frappe
./scripts/Verify-Pilot.ps1
./scripts/Stop-Pilot.ps1
```

`Start-Pilot.ps1 -Build -FromPublicSources` selecciona explícitamente la imagen
construida desde fuentes públicas, incluso si existe el snapshot privado local.

Web: `http://localhost:18000`; SQL Server: `localhost,14333`; Socket.IO: puerto
`19000`. Los puertos se publican solo en loopback. La verificación detiene los
contenedores al finalizar; `-KeepRunning` permite conservarlos explícitamente.
`Stop-Pilot.ps1` conserva los volúmenes y no modifica los servicios originales.
Para reanudar esta instalación existente basta `./scripts/Start-Pilot.ps1`;
el primer arranque de una instalación nueva puede tardar hasta veinte minutos.
La cuenta web es `Administrator`, con `PILOT_ADMIN_PASSWORD` de `.env`.

`Verify-Pilot.ps1` prepara una empresa y empleados ficticios mediante el
asistente oficial y el ORM. Comprueba búsqueda, paginación, permisos, error y
rollback, numeración concurrente, migra dos veces, reinicia y verifica la
restauración de un respaldo. La prueba manual de navegador está documentada
por separado. Una instalación incompleta requiere inspección: el arranque no
elimina automáticamente sus datos.

El cifrado ODBC está habilitado. El perfil local acepta el certificado
autogenerado del servidor mediante `mssql_trust_server_certificate`; cualquier
otro despliegue debe configurar un certificado verificable y deshabilitar esa
excepción.

## Respaldo y recuperación

`Backup-Pilot.ps1 -VerifyRestore` genera un `.bak` con checksum, prueba su
restauración en una base separada y exporta el respaldo junto con los archivos
del sitio a `private/backups`. Incluye configuración y debe tratarse como privado.
La restauración de validación nunca reemplaza la base activa.

El respaldo del sitio original de MariaDB y la imagen previa a la actualización
están en `private/pre-update`. Recuperar código, base y archivos de la misma
captura; el SQL de MariaDB no es un archivo de importación de SQL Server.
Las imágenes base capturadas también contienen el entorno original y se conservan
como artefactos privados de esta máquina.

## Desarrollo y pruebas

Las pruebas de SQL y bootstrap son independientes de Frappe. El paquete completo
requiere el Python 3.14 del entorno Frappe fijado.

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
./.venv/Scripts/python.exe -m pytest -q
```

Las consultas conservan parámetros separados de sus valores. La traducción usa
un árbol SQL; los bloqueos y upserts cuentan con adaptaciones explícitas. Los
comandos no representables deben fallar y recibir una adaptación comprobada.
La conexión usa el control de transacciones de ODBC, aislamiento READ COMMITTED
y READ_COMMITTED_SNAPSHOT en la base. Las lecturas con `FOR UPDATE` se traducen
a `UPDLOCK,HOLDLOCK`; no se promete equivalencia general con REPEATABLE READ de
otros motores. Las operaciones fuera de cobertura se enumeran en la matriz.

Los parches se rechazan si cambia un commit o el hash de un archivo original.
Actualizar las aplicaciones exige regenerar y revisar los parches y repetir
las pruebas. El piloto no migra datos desde MariaDB ni certifica módulos de
nómina, contabilidad, inventario o producción.
