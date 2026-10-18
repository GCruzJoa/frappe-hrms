# Frappe HR / SQL Server: piloto experimental

Personalización independiente para utilizar SQL Server 2025 como motor principal
de un sitio Frappe/ERPNext/HRMS 17. El código fuente de las aplicaciones se fija
por commit y los cambios de integración se distribuyen como parches verificables.

## Estado

La imagen del piloto se construyó y Frappe completó la sincronización de su
esquema y hooks de instalación en SQL Server. ERPNext/HRMS y los criterios de
aceptación completos se están verificando. Consultar
`docs/compatibility.md` y `docs/implementation-log.md` para distinguir las pruebas
realizadas de las comprobaciones pendientes. La existencia de un adaptador o de
una imagen construida no acredita el funcionamiento completo de HRMS.

## Organización

- `src/frappe_mssql`: conexión ODBC, parámetros SQL, traducción por AST,
  esquema, aprovisionamiento, respaldo y comprobaciones de aceptación.
- `patches`: diferencias y hashes del código original para las tres aplicaciones.
- `scripts`: operaciones PowerShell y herramientas de preparación de parches.
- `private`: respaldos, snapshots y referencias locales, excluidos de Git y Docker.

## Requisitos y operación

Docker Desktop en Linux/x86_64; al menos 3.5 GiB de memoria disponible para el
piloto además del consumo del entorno existente. SQL Server Developer se utiliza
para desarrollo. Las credenciales se generan en `.env`, excluido de Git.

Las revisiones y los parches ya están registrados. En una máquina nueva, desde
este directorio ejecutar primero `./scripts/Build-SourceBase.ps1` para construir
las aplicaciones desde los commits públicos fijados. Este flujo está en
validación. En la máquina de desarrollo también puede utilizarse el snapshot
local registrado. No sustituir las versiones registradas por una imagen `latest`.

```powershell
./scripts/Start-Pilot.ps1 -Build
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

Los parches se rechazan si cambia un commit o el hash de un archivo original.
Actualizar las aplicaciones exige regenerar y revisar los parches y repetir
las pruebas. El piloto no migra datos desde MariaDB ni certifica módulos de
nómina, contabilidad, inventario o producción.
