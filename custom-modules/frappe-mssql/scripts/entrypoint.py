"""Create the dedicated SQL Server site once, then start the web/worker stack."""
import json
import os
from pathlib import Path
import subprocess

SITE = "mssql.localhost"
BENCH = Path("/home/frappe/frappe-bench")
os.chdir(BENCH)


def bench(*args):
    # Captured command arguments must never be echoed: they contain bootstrap secrets.
    try:
        subprocess.run(["bench", *args], check=True)
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f"Bench operation failed (exit {error.returncode}); inspect the preceding application error") from None


sites = BENCH / "sites"
config_path = sites / "common_site_config.json"
config = json.loads(config_path.read_text()) if config_path.exists() else {}
config.update(db_type="mssql", db_host="sqlserver", db_port=1433,
    redis_cache="redis://redis:6379", redis_queue="redis://redis:6379",
    redis_socketio="redis://redis:6379", socketio_port=9000, webserver_port=8000,
    webserver_host="http://127.0.0.1",
    serve_default_site=True, default_site=SITE, mssql_trust_server_certificate=True)
config_path.write_text(json.dumps(config, indent=2))
site = sites / SITE
if not site.exists():
    bench("new-site", SITE, "--db-type", "mssql", "--db-host", "sqlserver", "--db-port", "1433",
        "--db-name", "frappe_pilot", "--db-user", "frappe_pilot",
        "--db-password", os.environ["PILOT_DB_PASSWORD"], "--db-root-username", "sa",
        "--db-root-password", os.environ["MSSQL_SA_PASSWORD"],
        "--admin-password", os.environ["PILOT_ADMIN_PASSWORD"], "--set-default")
    (site / ".core-created").touch()
elif not (site / ".core-created").exists():
    raise RuntimeError("An incomplete site exists. Inspect the installation log before explicitly recreating the disposable pilot.")
site_config_path = site / "site_config.json"
site_config = json.loads(site_config_path.read_text())
# Node listens on the container port; the browser must use the published port.
site_config["socketio_port"] = 19000
site_config_path.write_text(json.dumps(site_config, indent=2))
if not (site / ".hrms-installed").exists():
    bench("--site", SITE, "install-app", "hrms")
    bench("--site", SITE, "enable-scheduler")
    (site / ".hrms-installed").touch()
bench("use", SITE)
(BENCH / "Procfile").write_text("web: bench serve --host 0.0.0.0 --port 8000\nsocketio: bench socketio\nschedule: bench schedule\nworker: bench worker\n")
for secret in ("MSSQL_SA_PASSWORD", "PILOT_DB_PASSWORD", "PILOT_ADMIN_PASSWORD"):
    os.environ.pop(secret, None)
os.execvp("bench", ["bench", "start"])
