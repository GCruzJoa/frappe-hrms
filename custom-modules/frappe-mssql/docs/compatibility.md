# Matriz de compatibilidad

Verificación del piloto: 2026-10-18. Los resultados corresponden únicamente a
las revisiones de versions.lock.json; detalles en acceptance-results.md y
module-coverage.md/json. El catálogo completo no certifica todos los procesos.

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
| Parámetros, listas, upserts y SQL común | Verificados en cobertura del piloto | 51 pruebas unitarias; GROUP BY parametrizado, tuplas IN, IN vacío, predicados escalares, alias y literales Unicode |
| Transacciones y conexiones reutilizadas | Verificadas | Commit/rollback encadenados, ocho conexiones devueltas sin escrituras pendientes y savepoints reutilizables |
| Bloqueos y NOWAIT | Verificados | Dos conexiones con bloqueo real en conflicto; advisory locks implementados |
| Secuencias nativas | Verificadas | Creación, consulta, avance, reinicio, is_val_used e instalación idempotente |
| Actualización del entorno MariaDB original | Verificada | Respaldo/exportación previa, bench update sin reset/force y login API/navegador |
| Migración de datos MariaDB → SQL Server | Fuera de esta entrega | Solo datos ficticios |
| Catálogo de módulos y DocTypes | Verificado | 46 módulos; 1,000 DocTypes esperados e instalados, sin faltantes ni asignaciones incorrectas |
| Lecturas de esquema | Verificadas | 974 aprobadas; 26 DocTypes virtuales sin tabla propia |
| Informes estándar activos Script/Query | Pruebas de humo | 217 aprobados; tres conservan restricciones de país; detalle de filas en module-coverage.json |
| Recorridos de negocio | 24 verificados | QA aislada, datos ficticios y rollback; no acreditan todas las combinaciones de un módulo |
| Asistencia y turnos | Escenarios concretos verificados | Enviar/cancelar Attendance, Shift Assignment, dos Checkin e informe con ocho horas |
| Nómina y beneficios | Escenarios concretos verificados | Structure/Assignment/Slip, bruto/neto ficticio 30,000, cancelación, declaración e informes Register/CTC/Income Tax |
| Ventas, compras, contabilidad e inventario | Cobertura parcial | Orders, facturas, Journal/Expense Claim con GL balanceado, recepción con Stock Ledger y cancelaciones |
| Fabricación, proyectos, activos, mantenimiento y calidad | Cobertura parcial | BOM/Explorer, Task, activo existente, visita, Quality Goal y plantilla de inspección |
| Solo lectura | Comprobada en el adaptador | sql()/native() rechazan escrituras; no equivale a un login SQL con permisos exclusivamente de lectura |
| Contrato de tipos de Frappe | Adaptado | sql() entrega NUMERIC como float y TIME como timedelta; native() conserva Decimal y datetime.time exactos |
| Bloqueos por transacción y esquema | Verificados | sp_getapplock en dos conexiones y liberación con commit/rollback; rename_column real y conteo estimado |
| Grafos BOM/Task | Casos concretos verificados | Sub-BOM compartida, ancestros por Item/Operation y rechazo de ciclos sin sustituir UNION DISTINCT por UNION ALL |

## Inventario pendiente

- FOR UPDATE SKIP LOCKED, FOR SHARE y tuplas IN con subconsulta:
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
- Completar los escenarios propios de los módulos señalados en
  module-coverage.md, además de sus lecturas e informes. Pendientes permisos
  por empresa/fila, cargas masivas, integraciones externas y pruebas de carga.
- Las divisiones reales de lotes, subcontratación, reservas, depreciación,
  combinaciones de nómina/stock y fiscalidad necesitan recorridos adicionales.
- IRS 1099, UAE VAT 201 y VAT Audit Report no aplican a la empresa dominicana;
  sus cálculos regionales siguen pendientes. La tasa fiscal cero de QA es
  ficticia y no implementa legislación dominicana.
- Time fuera de un día se rechaza, pues no cabe en TIME de SQL Server;
  Duration usa decimal. TIMESTAMPDIFF, GROUP_CONCAT DISTINCT y búsquedas de
  texto completo no quedan certificados por esta auditoría.
- La instalación vacía se verificó en la primera entrega. Esta ampliación
  reconstruye la imagen y prueba sitios existentes; repetir la instalación
  desde cero con todos los parches nuevos sigue pendiente.

Los inventarios estáticos frappe-sql-inventory.json, erpnext-sql-inventory.json
y hrms-sql-inventory.json contienen respectivamente 575, 287 y 18 candidatos a
revisión. Son coincidencias de patrones de SQL, no una lista de errores
confirmados ni una certificación de cobertura.

Las lecturas ordinarias usan READ COMMITTED con RCSI; las secciones críticas
con FOR UPDATE utilizan UPDLOCK/HOLDLOCK. Las pruebas no certifican equivalencia
de aislamiento con todas las configuraciones de MariaDB/PostgreSQL.
