# Matriz de compatibilidad

Estado durante la implementación; actualizar con resultados reales antes de entregar.

| Capacidad | Estado | Evidencia / límite |
|---|---|---|
| Parámetros, Unicode, listas y paginación SQL | Verificado en pruebas unitarias | 19 casos del paquete |
| Bloqueos, NOWAIT y upsert de credenciales | Verificado mediante ODBC real | Dos conexiones con bloqueo en conflicto; login completo pendiente |
| Esquema inicial de Frappe | Verificado en SQL Server 2025 | 11 tablas; base de prueba eliminada al terminar |
| Unicode y savepoints del servidor | Verificado en SQL Server 2025 | Prueba con José Peña y María |
| Actualización del entorno MariaDB | Verificada | Migraciones/build completados; HTTP 200 y autenticación correctos |
| Imagen del piloto y sincronización Frappe | Verificadas | Construcción, resincronización de DocTypes y hooks completos |
| Instalación completa de las tres aplicaciones en SQL Server | En curso | ERPNext/HRMS; no se acredita por instalar Frappe |
| Login, empresa y empleados | Pendiente | Verificación de ORM y navegador |
| Permisos y numeración concurrente | Pendiente | Pruebas de aceptación del sitio |
| Migraciones repetidas y reinicio | Pendiente | Verify-Pilot.ps1 |
| Backup/restauración nativos | Pendiente | Backup-Pilot.ps1 -VerifyRestore |
| Migración de datos MariaDB → SQL Server | Fuera de esta entrega | Requiere proyecto de migración |
| Nómina, asistencia e informes completos | Fuera de esta entrega | No se certifican por instalar sus tablas |

Limitaciones explícitas del adaptador inicial: tipos de índices especiales,
cambios de tipo con datos existentes y restauración de dumps de otro motor
requieren adaptaciones específicas. El inventario de SQL registra candidatos a
revisión; su presencia no equivale automáticamente a una incompatibilidad.
