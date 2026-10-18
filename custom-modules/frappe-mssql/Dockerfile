ARG FRAPPE_BASE_IMAGE=local/frappe-hrms:updated-20261018
FROM ${FRAPPE_BASE_IMAGE} AS odbc
USER root
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates unixodbc unixodbc-dev libgssapi-krb5-2 \
    && curl -fsSLo /tmp/packages-microsoft-prod.deb https://packages.microsoft.com/config/debian/13/packages-microsoft-prod.deb \
    && dpkg -i /tmp/packages-microsoft-prod.deb \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18=18.6.1.1-1 \
    && rm -rf /var/lib/apt/lists/* /tmp/packages-microsoft-prod.deb
FROM odbc AS pilot
COPY --chown=frappe:frappe . /opt/frappe-mssql
USER frappe
WORKDIR /home/frappe/frappe-bench
RUN uv pip install --python env/bin/python -e /opt/frappe-mssql \
    && env/bin/python /opt/frappe-mssql/scripts/apply_patches.py apps/frappe /opt/frappe-mssql/patches frappe \
    && env/bin/python /opt/frappe-mssql/scripts/apply_patches.py apps/erpnext /opt/frappe-mssql/patches erpnext \
    && env/bin/python /opt/frappe-mssql/scripts/apply_patches.py apps/hrms /opt/frappe-mssql/patches hrms
RUN python3 -c "from pathlib import Path; import shutil; p=Path('/opt/frappe-mssql/built-assets'); p.mkdir(); [shutil.copy2(x,p/x.name) for x in Path('sites/assets').glob('*.json')]"
# Keep applications/assets; site databases, credentials and logs belong to the pilot volumes.
RUN python3 -c "from pathlib import Path; import shutil; p=Path('sites'); [shutil.rmtree(x) for x in p.iterdir() if x.is_dir() and x.name != 'assets']; [(p/x).unlink(missing_ok=True) for x in ('common_site_config.json', 'currentsite.txt')]; p=Path('logs'); [x.unlink() for x in p.iterdir() if x.is_file()]"
ENTRYPOINT ["/home/frappe/frappe-bench/env/bin/python", "/opt/frappe-mssql/scripts/entrypoint.py"]
