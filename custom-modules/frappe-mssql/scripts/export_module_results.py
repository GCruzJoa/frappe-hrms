"""Publish only sanitized validation results, without fixtures, SQL or secrets."""
import argparse
from collections import Counter
import json
from pathlib import Path


def export(evidence, destination):
    evidence, destination = Path(evidence), Path(destination)
    inputs = {name: json.loads((evidence / (name+".json")).read_text(encoding="utf-8-sig"))
        for name in ("catalog", "schema", "reports", "workflows")}
    catalog, schema, reports, workflows = (inputs[name] for name in inputs)
    if catalog["status"] != "passed" or workflows["failed"]:
        raise RuntimeError("Do not publish incomplete validation as successful")
    if any(row["status"] not in ("passed", "not-applicable") for row in schema["entries"]):
        raise RuntimeError("Schema checks failed")
    if any(row["status"] not in ("passed", "not-applicable-country") for row in reports["entries"]):
        raise RuntimeError("Reports are incomplete")
    modules = []
    for name, app in catalog["modules"].items():
        types = [row for row in schema["entries"] if row["module"] == name]
        report_rows = [row for row in reports["entries"] if row["module"] == name]
        cases = [row for row in workflows["cases"] if row["module"] == name]
        storage_cases = [row for row in workflows["cases"] if name in row.get("storage_modules", [])]
        modules.append(dict(name=name, app=app, doctypes=len(types),
            schema=dict(Counter(row["status"] for row in types)),
            reports=dict(Counter(row["status"] for row in report_rows)),
            reports_with_rows=sum((row.get("result_rows") or 0) > 0 for row in report_rows),
            workflow_cases=[row["name"] for row in cases],
            storage_workflow_cases=[row["name"] for row in storage_cases]))
    lock = json.loads((destination.parent / "versions.lock.json").read_text())
    output = dict(verified_at=reports["verified_at"], classification=reports["classification"],
        app_commits={app: data["commit"] for app, data in lock["apps"].items()},
        catalog={key: catalog[key] for key in ("status", "source_counts", "expected", "installed", "missing", "module_mismatches")},
        schema_totals=schema["totals"], report_totals=reports["totals"],
        reports_with_rows=sum((row.get("result_rows") or 0) > 0 for row in reports["entries"]),
        workflow_totals={key: workflows[key] for key in ("passed", "failed", "fixtures")},
        modules=modules,
        report_cases=[{key: row[key] for key in ("name", "module", "app", "status", "result_rows") if key in row}
            for row in reports["entries"]],
        workflow_cases=[{key: row[key] for key in ("name", "module", "status", "storage_modules")} for row in workflows["cases"]])
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "module-coverage.json").write_text(json.dumps(output, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    lines = ["# Cobertura por módulo", "", f"Ejecución UTC: {output['verified_at']}.", "",
        "La comparación con las fuentes fijadas no encontró DocTypes faltantes ni módulos asignados incorrectamente.",
        f"Se revisaron {len(modules)} módulos declarados y {catalog['expected']} DocTypes: "
        f"{schema['totals'].get('passed', 0)} lecturas aprobadas y "
        f"{schema['totals'].get('not-applicable', 0)} DocTypes virtuales sin tabla propia.", "",
        f"Informes: {reports['totals'].get('passed', 0)} aprobados, "
        f"{reports['totals'].get('not-applicable-country', 0)} excluidos por país y "
        f"{output['reports_with_rows']} con filas. Recorridos de negocio: {workflows['passed']} aprobados.", "",
        "Las lecturas y ejecuciones de informes son pruebas de humo. Tener filas puede significar filas de estructura o totales; "
        "no equivale a validar cada cálculo. Los recorridos de negocio usan datos ficticios en una base QA separada y hacen rollback.", "",
        "Los módulos nuevos de navegación de HRMS mantienen DocTypes bajo HR/Payroll en estas revisiones. "
        "Por eso algunos muestran cero DocTypes y sí tienen recorridos. System/Build/Data/Users también son agrupaciones sin DocTypes propios.", "",
        "Los recorridos se cuentan por área funcional y por módulo del esquema donde se guardan sus documentos; pueden abarcar varios módulos.", "",
        "| Aplicación | Módulo | DocTypes | Informes aprobados / fuera de país | Con filas | Recorridos área / esquema |",
        "|---|---|---:|---:|---:|---:|"]
    for module in modules:
        report_counts = module["reports"]
        lines.append(f"| {module['app']} | {module['name']} | {module['doctypes']} | "
            f"{report_counts.get('passed',0)} / {report_counts.get('not-applicable-country',0)} | "
            f"{module['reports_with_rows']} | {len(module['workflow_cases'])} / {len(module['storage_workflow_cases'])} |")
    pending = [module["name"] for module in modules if module["doctypes"] and not module["workflow_cases"] and not module["storage_workflow_cases"]]
    lines += ["", "## Cobertura funcional pendiente", "",
        "Todavía necesitan escenarios funcionales propios, además de las lecturas o informes anteriores: "+", ".join(pending)+".", "",
        "Los informes IRS 1099, UAE VAT 201 y VAT Audit Report conservan sus validaciones de país y no aplican a la empresa dominicana. "
        "No se certifican sus cálculos regionales. La tabla fiscal de QA es ficticia, con tasa cero; no implementa legislación dominicana.", "",
        "También quedan pendientes los permisos avanzados por empresa/fila, combinaciones y casos límite de nómina/stock, "
        "integraciones externas, cargas masivas, búsquedas de texto completo, recuperación completa desde cero con esta ampliación "
        "y pruebas de carga. Ver compatibility.md para operaciones SQL que se rechazan expresamente.", "",
        "Reproducir con `./scripts/Verify-Modules.ps1 -KeepRunning`. La evidencia detallada privada queda en "
        "`private/module-validation`; este documento y module-coverage.json no contienen credenciales ni SQL ejecutado.", ""]
    (destination / "module-coverage.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(dict(modules=len(modules), doctypes=catalog["expected"],
        reports=reports["totals"], workflows=workflows["passed"])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", default="private/module-validation")
    parser.add_argument("--output", default="docs")
    args = parser.parse_args()
    export(args.evidence, args.output)
