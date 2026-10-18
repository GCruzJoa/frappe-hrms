"""Build a clean bench from pinned public sources, without copying any site."""
import json
import os
from pathlib import Path
import subprocess
import sys

lock = json.loads(Path('/opt/frappe-source/versions.lock.json').read_text())
sources = Path('/tmp/frappe-mssql-sources')
sources.mkdir(exist_ok=True)
os.environ['CI'] = '1'


def run(*args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True)


bench = Path('/home/frappe/frappe-bench')
phase = sys.argv[1]
if phase == 'sources':
    for app, version in lock['apps'].items():
        source = sources / app
        run('git', 'init', '--initial-branch=develop', str(source))
        run('git', 'remote', 'add', 'origin', f'https://github.com/frappe/{app}.git', cwd=source)
        run('git', 'fetch', '--depth=1', 'origin', version['commit'], cwd=source)
        run('git', 'checkout', '-B', 'develop', 'FETCH_HEAD', cwd=source)
elif phase == 'framework':
    if bench.exists():
        raise FileExistsError('A clean source build requires an empty bench location')
    run('bench', 'init', str(bench), '--frappe-path', str(sources / 'frappe'),
        '--frappe-branch', 'develop', '--skip-assets', '--skip-redis-config-generation', '--no-backups')
elif phase in ('erpnext', 'hrms'):
    app = phase
    run('bench', 'get-app', '--branch', 'develop', '--skip-assets', str(sources / app), cwd=bench)
elif phase == 'finalize':
    for app, version in lock['apps'].items():
        source = bench / 'apps' / app
        actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
        if actual != version['commit']:
            raise RuntimeError(f'Unexpected source revision for {app}')
        remotes = subprocess.check_output(['git', 'remote'], cwd=source, text=True).split()
        for remote in remotes:
            run('git', 'remote', 'set-url', remote, f'https://github.com/frappe/{app}.git', cwd=source)
    run('bench', 'build', cwd=bench)
    (bench / '.frappe-mssql-source-lock.json').write_text(json.dumps(lock['apps'], sort_keys=True))
else:
    raise ValueError('Unknown source build phase')
