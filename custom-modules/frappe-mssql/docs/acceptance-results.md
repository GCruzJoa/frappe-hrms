# Resultados de aceptación — 2026-10-18

La primera entrega se documenta a continuación. La ampliación de módulos usa
el mismo manifiesto de versiones y añade 51 pruebas unitarias, 24 recorridos
con rollback en QA, inventario de 46 módulos/1,000 DocTypes y ejecución de 217
informes; tres informes regionales conservan restricciones de país. Resultados
vigentes, filas devueltas y límites: module-coverage.md/json y compatibility.md.
El piloto se mantiene encendido y el entorno original apagado por instrucción
posterior del usuario. Usar -KeepRunning en los scripts de verificación para
conservar ese estado.

La ampliación pasó Verify-Modules.ps1 -KeepRunning y después
Verify-Pilot.ps1 -KeepRunning, este último con resultado passed el
2026-10-19 a las 01:41:01 UTC. Se comprobaron login, empleados, permisos,
rollback, concurrencia, dos migraciones, reinicio y restauración nativa.
El respaldo exportado quedó en private/backups/20261019T014100Z/; seis
archivos del sitio restaurados y comprobados. La ejecución de módulos está
en private/modules-release-validation.log y la aceptación del piloto en
private/modules-pilot-acceptance.log. Los informes públicos detallados están
en module-coverage.json, con su fecha UTC de ejecución.

Se ejecutó el piloto con SQL Server 2025 17.0.5015.4 Enterprise Developer,
Python 3.14.8, pyodbc 5.3.0, Microsoft ODBC Driver 18.6.1.1 y SQLGlot 30.16.0.
Los commits exactos de Frappe, ERPNext y HRMS están en versions.lock.json.

## Construcción e instalación

Build-SourceBase.ps1 completó la construcción desde la imagen pública Bench
fijada por digest, sin depender del snapshot privado del sitio original.
Se comprobaron los tres commits y los árboles limpios antes de integrar parches.
La imagen fuente resultante fue
sha256:cf5deadd336605bf884a87ba4323b9124e0273869d8ec470b24ece48d8cd5260.
Se construyó la imagen del adaptador, aplicando parches con validación de origen,
y se instaló un sitio vacío con las tres aplicaciones y sus hooks completos.

El sitio mssql.localhost usa la base y login exclusivos frappe_pilot.
La comprobación del servidor devolvió major 17 y DB_NAME frappe_pilot.
El proyecto Compose tiene exactamente frappe, redis y sqlserver.
La instancia MariaDB original sigue en su proyecto independiente.

## Recorridos comprobados

- Inicio de sesión de Administrator por API y navegador; escritorio con
  ERPNext, Frappe HR y Framework, recursos web cargados.
- Asistente de configuración oficial completo para Piloto SQL Server RD,
  país República Dominicana, moneda DOP y zona America/Santo_Domingo.
- ORM: alta y consulta de María Peña y Ángel Peña, edición a María José Peña,
  dirección con tildes y ñ, filtro LIKE y dos páginas distintas de un registro.
- Navegador: alta de Lucía Núñez, identificador HR-EMP-00001, edición del
  segundo nombre a María, confirmación Saved y consulta en la lista con tres
  empleados. Evidencia local privada: private/employee-ui.jpg.
- Usuario ficticio sin roles de Employee: lista vacía o permiso denegado y
  rechazo explícito de la lectura del documento. No se ensayaron todas las
  combinaciones de permisos por empresa, rol y fila.
- Error SQL real de clave primaria duplicada después de modificar un empleado;
  rollback al savepoint recupera José y mantiene ambos identificadores.
- Doce llamadas concurrentes a getseries, con cuatro conexiones, produjeron
  doce números distintos.
- Dos migraciones consecutivas completas, reinicio del contenedor y lectura
  del valor persistido, sin cambiar de motor.
- BACKUP DATABASE con CHECKSUM y RESTORE VERIFYONLY; restauración en la base
  separada frappe_pilot_restore, lectura del empleado y eliminación de esa
  copia temporal. La base activa no se reemplaza.
- Restauración del archivo tar del sitio en una carpeta temporal y comparación
  SHA-256 de seis archivos en la ejecución final, incluyendo fixtures públicos/privados y
  site_config.json.

## Pruebas del adaptador

Las 23 pruebas unitarias de pytest -q pasaron. La prueba ODBC real comprobó
parámetros, Unicode largo con emoji, decimal(21,9), datetime2(6), time(6),
commit/rollback encadenados, savepoints reutilizables, ocho ciclos de conexiones
cerradas sin confirmar escrituras, NOWAIT con conflicto real, UPDATE correlado,
upsert de clave compuesta, listas vacías y secuencias nativas.
Su base temporal y prefijo de caché se aíslan del sitio del piloto.

## Evidencia y repetición

Los logs completos, manifiestos y respaldos están en private/, excluido de
Git/Docker. Verify-Pilot.ps1 solo escribe private/acceptance.json si termina
todo el recorrido; el resultado completo registrado fue passed.
private/acceptance-run.log conserva la ejecución completa; la revisión final
de la imagen se registra en private/final-acceptance-run.log. La última
verificación completa terminó el 2026-10-18 a las 23:14:47 UTC con resultado passed.
El respaldo posterior al recorrido de navegador se exportó a
private/backups/20261018T231217Z/, con .bak, archivos y SHA-256. Ejecuciones
posteriores generan otro directorio fechado sin sobrescribir este respaldo.
El respaldo de la ejecución final está en private/backups/20261018T231445Z/.

Para repetir, desde el módulo:

```powershell
./scripts/Build-SourceBase.ps1
./scripts/Start-Pilot.ps1 -Build -FromPublicSources
./scripts/Verify-Pilot.ps1
```

La verificación detiene el piloto al terminar y conserva sus volúmenes.
Para repetir el recorrido manual, arrancar con Start-Pilot.ps1, acceder a
http://localhost:18000 con Administrator y la contraseña local de .env, abrir
Frappe HR → Employee y crear/editar únicamente datos ficticios. Al terminar,
ejecutar Stop-Pilot.ps1.

La compilación fija las revisiones de aplicaciones, imágenes principales y
dependencias del adaptador; no garantiza identidad binaria de todos los paquetes
transitivos descargados en el futuro. Los escenarios no ejecutados y las
incompatibilidades pendientes están en compatibility.md.
