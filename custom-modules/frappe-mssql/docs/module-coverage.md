# Cobertura por módulo

Ejecución UTC: 2026-10-19T01:39:32.921721+00:00.

La comparación con las fuentes fijadas no encontró DocTypes faltantes ni módulos asignados incorrectamente.
Se revisaron 46 módulos declarados y 1000 DocTypes: 974 lecturas aprobadas y 26 DocTypes virtuales sin tabla propia.

Informes: 217 aprobados, 3 excluidos por país y 72 con filas. Recorridos de negocio: 24 aprobados.

Las lecturas y ejecuciones de informes son pruebas de humo. Tener filas puede significar filas de estructura o totales; no equivale a validar cada cálculo. Los recorridos de negocio usan datos ficticios en una base QA separada y hacen rollback.

Los módulos nuevos de navegación de HRMS mantienen DocTypes bajo HR/Payroll en estas revisiones. Por eso algunos muestran cero DocTypes y sí tienen recorridos. System/Build/Data/Users también son agrupaciones sin DocTypes propios.

Los recorridos se cuentan por área funcional y por módulo del esquema donde se guardan sus documentos; pueden abarcar varios módulos.

| Aplicación | Módulo | DocTypes | Informes aprobados / fuera de país | Con filas | Recorridos área / esquema |
|---|---|---:|---:|---:|---:|
| frappe | Core | 114 | 4 / 0 | 3 | 0 / 0 |
| frappe | Website | 39 | 1 / 0 | 0 | 1 / 1 |
| frappe | Workflow | 10 | 0 / 0 | 0 | 0 / 0 |
| frappe | Email | 17 | 0 / 0 | 0 | 1 / 1 |
| frappe | Custom | 5 | 1 / 0 | 1 | 0 / 0 |
| frappe | Geo | 2 | 0 / 0 | 0 | 0 / 0 |
| frappe | Desk | 66 | 1 / 0 | 0 | 0 / 0 |
| frappe | Integrations | 24 | 0 / 0 | 0 | 0 / 0 |
| frappe | Printing | 8 | 0 / 0 | 0 | 0 / 0 |
| frappe | Contacts | 7 | 1 / 0 | 0 | 1 / 1 |
| frappe | Automation | 16 | 0 / 0 | 0 | 0 / 0 |
| frappe | System | 0 | 0 / 0 | 0 | 0 / 0 |
| frappe | Build | 0 | 0 / 0 | 0 | 0 / 0 |
| frappe | Data | 0 | 0 / 0 | 0 | 0 / 0 |
| frappe | Users | 0 | 0 / 0 | 0 | 0 / 0 |
| erpnext | Accounts | 191 | 56 / 0 | 29 | 1 / 1 |
| erpnext | CRM | 28 | 9 / 0 | 0 | 1 / 1 |
| erpnext | Buying | 19 | 10 / 0 | 2 | 1 / 1 |
| erpnext | Projects | 15 | 5 / 0 | 0 | 1 / 1 |
| erpnext | Selling | 20 | 23 / 0 | 7 | 1 / 1 |
| erpnext | Setup | 40 | 0 / 0 | 0 | 0 / 1 |
| erpnext | Manufacturing | 49 | 21 / 0 | 4 | 1 / 1 |
| erpnext | Stock | 78 | 50 / 0 | 19 | 1 / 4 |
| erpnext | Support | 11 | 4 / 0 | 1 | 1 / 1 |
| erpnext | Utilities | 4 | 1 / 0 | 0 | 0 / 0 |
| erpnext | Assets | 26 | 1 / 0 | 0 | 1 / 1 |
| erpnext | Portal | 2 | 0 / 0 | 0 | 0 / 0 |
| erpnext | Maintenance | 5 | 1 / 0 | 0 | 1 / 1 |
| erpnext | Regional | 5 | 0 / 3 | 0 | 0 / 0 |
| erpnext | ERPNext Integrations | 1 | 0 / 0 | 0 | 0 / 0 |
| erpnext | Quality Management | 16 | 1 / 0 | 0 | 1 / 1 |
| erpnext | Communication | 2 | 0 / 0 | 0 | 0 / 0 |
| erpnext | Telephony | 5 | 0 / 0 | 0 | 0 / 0 |
| erpnext | Bulk Transaction | 2 | 0 / 0 | 0 | 0 / 0 |
| erpnext | Subcontracting | 13 | 3 / 0 | 0 | 0 / 0 |
| erpnext | EDI | 2 | 0 / 0 | 0 | 0 / 0 |
| hrms | HR Setup | 0 | 0 / 0 | 0 | 1 / 0 |
| hrms | Tenure | 0 | 0 / 0 | 0 | 1 / 0 |
| hrms | Recruitment | 0 | 0 / 0 | 0 | 1 / 0 |
| hrms | Shift and Attendance | 0 | 0 / 0 | 0 | 2 / 0 |
| hrms | Leaves | 0 | 0 / 0 | 0 | 1 / 0 |
| hrms | Expenses | 0 | 0 / 0 | 0 | 1 / 0 |
| hrms | Performance | 0 | 0 / 0 | 0 | 1 / 0 |
| hrms | Payroll | 43 | 8 / 0 | 5 | 1 / 2 |
| hrms | Tax and Benefits | 0 | 0 / 0 | 0 | 1 / 0 |
| hrms | HR | 115 | 16 / 0 | 1 | 0 / 8 |

## Cobertura funcional pendiente

Todavía necesitan escenarios funcionales propios, además de las lecturas o informes anteriores: Core, Workflow, Custom, Geo, Desk, Integrations, Printing, Automation, Utilities, Portal, Regional, ERPNext Integrations, Communication, Telephony, Bulk Transaction, Subcontracting, EDI.

Los informes IRS 1099, UAE VAT 201 y VAT Audit Report conservan sus validaciones de país y no aplican a la empresa dominicana. No se certifican sus cálculos regionales. La tabla fiscal de QA es ficticia, con tasa cero; no implementa legislación dominicana.

También quedan pendientes los permisos avanzados por empresa/fila, combinaciones y casos límite de nómina/stock, integraciones externas, cargas masivas, búsquedas de texto completo, recuperación completa desde cero con esta ampliación y pruebas de carga. Ver compatibility.md para operaciones SQL que se rechazan expresamente.

Reproducir con `./scripts/Verify-Modules.ps1 -KeepRunning`. La evidencia detallada privada queda en `private/module-validation`; este documento y module-coverage.json no contienen credenciales ni SQL ejecutado.
