"""Create this PC's environment instead of reusing a broken copied Windows venv."""
import argparse
from datetime import datetime
from pathlib import Path
import subprocess
import sys

from local_config import ensure_env, verify_files


BASE = Path(__file__).resolve().parent


def environment_python(folder):
    return folder / ('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')


def environment_works(folder):
    python = environment_python(folder)
    if not python.is_file():
        return False
    try:
        version = subprocess.run(
            [str(python), '-c', 'import sys; raise SystemExit(sys.version_info < (3, 10))'],
            capture_output=True, timeout=20,
        )
        if version.returncode:
            return False
        pip = subprocess.run([str(python), '-m', 'pip', '--version'],
                             capture_output=True, timeout=20)
        return pip.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def ensure_environment(base=BASE):
    base = Path(base).resolve()
    folder = base / '.venv'
    if folder.resolve().parent != base:
        raise RuntimeError('The .venv path points outside this project. Check it manually.')
    if environment_works(folder):
        print('Using working virtual environment: ' + str(folder), flush=True)
        return environment_python(folder)
    if folder.exists():
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup = base / ('.venv.old-' + stamp)
        if backup.resolve().parent != base:
            raise RuntimeError('Invalid backup directory')
        folder.rename(backup)
        print('Backed up unusable virtual environment: ' + backup.name, flush=True)
    print('Creating a virtual environment with this PC\'s Python: ' + sys.executable, flush=True)
    subprocess.run([sys.executable, '-m', 'venv', str(folder)], check=True)
    if not environment_works(folder):
        raise RuntimeError('The new environment could not start. Check the Python installation.')
    return environment_python(folder)


def main():
    parser = argparse.ArgumentParser(description='Prepare a local Python environment and run instcopy')
    parser.add_argument('--prepare-only', action='store_true', help='Create/check .venv without installing packages or starting the DB/server')
    args = parser.parse_args()
    if sys.version_info < (3, 10):
        print('[ERROR] Python 3.10 or newer is required.')
        return 1
    try:
        verify_files()
        ensure_env()
        python = ensure_environment()
        if args.prepare_only:
            print('Environment ready: ' + str(python), flush=True)
            return 0
        probe = subprocess.run([str(python), '-c',
            'import fastapi, uvicorn, jinja2, multipart, mysql.connector, dotenv, PIL, itsdangerous'],
            capture_output=True, timeout=30)
        if probe.returncode:
            print('Installing packages (first run may take a minute) ...', flush=True)
            subprocess.run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check',
                            '-r', str(BASE / 'requirements.txt')], cwd=BASE, check=True)
        else:
            print('Required packages are already installed.', flush=True)
        return subprocess.run([str(python), str(BASE / 'run_local.py')], cwd=BASE).returncode
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print('[ERROR] ' + str(exc), flush=True)
        print('See the project README. Keep .env and uploads; only .venv is recreated.', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
