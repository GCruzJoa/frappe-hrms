# Matriz de compatibilidad

Verificación del piloto: 2026-10-18. Los resultados corresponden únicamente a
las revisiones de versions.lock.json; detalles en acceptance-results.md.

| Capacidad | Estado | Evidencia / límite |
|---|---|---|
| Construcción desde fuentes públicas fijadas | Verificada | Imagen Bench por digest, tres commits exactos y árboles limpios antes de parches |
| Rechazo de parches con otra versión | Verificado | Commit, hashes de archivos y git apply --check antes de aplicar |
| Instalación nueva de Frappe, ERPNext y HRMS | Verificada | Sitio vacío sobre SQL Server 2025; hooks reales completos |
| Login, escritorio y recursos web | Verificados | API y navegador, sin reutilizar cookies del sitio original |
| Empresa de prueba | Verificada | Asistente oficial; República Dominicana y moneda DOP |
| Alta, consulta y edición de empleados | Verificadas | ORM y navegador; Lucía María Núñez, María José Peña y Ángel Peña |
| Búsqueda y paginación | Verificadas | Filtro LIKE con Peña; dos páginas distintas de un registro |
| Permisos básicos | Verificados | Usuario sin roles de empleado no puede listar ni leer el documento; permisos por empresa/fila no certificados |
| Rollback ante operación fallida | Verificado | Escritura seguida de clave primaria duplicada; rollback al savepoint restaura el dato anterior |
| Numeración concurrente | Verificada | frappe.model.naming.getseries, 12 reservas en cuatro conexiones sin duplicados |
| Migración repetida y persistencia | Verificadas | Dos bench migrate, reinicio y lectura del empleado persistido |
| Respaldo y restauración nativos | Verificados | BACKUP con CHECKSUM, VERIFYONLY, RESTORE en base nueva y comprobación del empleado |
| Restauración de archivos del sitio | Verificada | Archivos públicos/privados y configuración: seis archivos comprobados por SHA-256 en la ejecución final |
| Ausencia de MariaDB en el piloto | Verificada | Compose contiene solo Frappe, Redis y SQL Server; DB_NAME y servidor major 17 comprobados |
| Unicode, precisión numérica y temporal | Verificados | Acentos/ñ, texto largo con emoji, decimal(21,9), datetime2(6) y time(6) por ODBC |
| Parámetros, listas, upserts y SQL común | Verificados en cobertura del piloto | 23 pruebas unitarias y consultas reales de instalación/aceptación |
| Transacciones y conexiones reutilizadas | Verificadas | Commit/rollback encadenados, ocho conexiones devueltas sin escrituras pendientes y savepoints reutilizables |
| Bloqueos y NOWAIT | Verificados | Dos conexiones con bloqueo real en conflicto; advisory locks implementados |
| Secuencias nativas | Verificadas | Creación, consulta, avance, reinicio, is_val_used e instalación idempotente |
| Actualización del entorno MariaDB original | Verificada | Respaldo/exportación previa, bench update sin reset/force y login API/navegador |
| Migración de datos MariaDB → SQL Server | Fuera de esta entrega | Solo datos ficticios |
| Nómina, asistencia, permisos avanzados e informes completos | Fuera de esta entrega | Instalar sus tablas no acredita estos recorridos |

## Inventario pendiente

- FOR UPDATE SKIP LOCKED, FOR SHARE y transacciones de solo lectura:
  producen UnsupportedSQL; necesitan semántica y pruebas específicas.
- Upserts complejos, REPLACE, actualizaciones multitabla y opciones de
  índices especiales: requieren adaptaciones explícitas; no hay sustitución
  automática por otro motor.
- Cambios de tipo o reducción de longitud con datos existentes e índices
  especiales: necesitan una migración diseñada para SQL Server.
- Secuencias temporales o con slug personalizado e importación de dumps de
  otro motor: se rechazan expresamente.
- Casos límite de capacidad UTF-16 en columnas acotadas e índices con muchos
  caracteres suplementarios: no certificados. El texto largo con emoji sí se
  comprobó mediante nvarchar(max) y LongAsMax.
- Contabilidad, inventario, búsquedas globales avanzadas, nómina, asistencia,
  informes y demás recorridos no ejecutados requieren pruebas propias.

Los inventarios estáticos frappe-sql-inventory.json, erpnext-sql-inventory.json
y hrms-sql-inventory.json contienen respectivamente 575, 287 y 18 candidatos a
revisión. Son coincidencias de patrones de SQL, no una lista de errores
confirmados ni una certificación de cobertura.

Las lecturas ordinarias usan READ COMMITTED con RCSI; las secciones críticas
con FOR UPDATE utilizan UPDLOCK/HOLDLOCK. Las pruebas no certifican equivalencia
de aislamiento con todas las configuraciones de MariaDB/PostgreSQL.
