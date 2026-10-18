# Personalizaciones de este fork

Este repositorio conserva HRMS de Frappe y reúne nuestras personalizaciones en
`custom-modules/frappe-mssql`. Consultar su README, matriz de compatibilidad y
`docs/resume-state.md` para conocer las pruebas realizadas y pendientes.

La rama `codex/frappe-mssql-pilot` parte de `develop` del fork. El remoto
`upstream` del checkout local apunta a `https://github.com/frappe/hrms.git`;
`origin` apunta a `https://github.com/GCruzJoa/frappe-hrms.git`.

El piloto fija por separado los commits de Frappe, ERPNext y HRMS en
`versions.lock.json`. Actualizar HRMS desde upstream no actualiza esos commits
automáticamente: cualquier cambio de versiones requiere regenerar los parches
y repetir las pruebas del piloto.

Los scripts de shell se guardan con finales de línea LF para ejecutarse en
Linux desde Docker Desktop. Credenciales, bases, respaldos y snapshots locales
se excluyen del repositorio.
