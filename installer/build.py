"""
build.py — Preparar bundle offline para Asistente IA (Claude Code CLI)
=======================================================================
Ejecutar UNA VEZ en una maquina CON internet antes de distribuir.
Crea assets/ con todo lo necesario para instalar sin internet:
  - Python portable (embeddable)
  - Node.js portable
  - Claude Code CLI + dependencias (node_modules pre-instalado)
  - Archivos del proyecto Asistente IA

Uso:
    python build.py              # build completo
    python build.py --skip-node  # sin Claude Code (ya instalado en target)
"""

import sys
import os
import shutil
import subprocess
import argparse
import json
import zipfile
from pathlib import Path
from urllib.request import urlretrieve, urlopen
from urllib.error import URLError

# ── Configuracion ─────────────────────────────────────────────────────────────
INSTALLER_DIR   = Path(__file__).parent
ASSETS_DIR      = INSTALLER_DIR / "assets"
PROJECT_ROOT    = INSTALLER_DIR.parent.parent  # C:\Chance1\
ASISTENTE_DIR   = INSTALLER_DIR.parent         # Asistente IA/

# URLs
PYTHON_WIN_URL  = "https://www.python.org/ftp/python/3.12.9/python-3.12.9-embed-amd64.zip"
GET_PIP_URL     = "https://bootstrap.pypa.io/get-pip.py"
NODE_WIN_URL    = "https://nodejs.org/dist/v20.19.0/node-v20.19.0-win-x64.zip"
NODE_LIN_URL    = "https://nodejs.org/dist/v20.19.0/node-v20.19.0-linux-x64.tar.xz"

CLAUDE_PKG      = "@anthropic-ai/claude-code"
NODE_VERSION    = "v20.19.0"

# Archivos/carpetas a EXCLUIR al copiar el proyecto
EXCLUDE_DIRS  = {"__pycache__", ".git", ".pytest_cache", "node_modules",
                 "installer", "venv", ".venv", "backups"}
EXCLUDE_FILES = {".pyc", ".pyo", ".log", ".tmp"}

# ── Helpers ───────────────────────────────────────────────────────────────────

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def title(msg):
    print(f"\n{'='*60}\n  {msg}\n{'='*60}")

def step(msg):
    print(f"\n  >> {msg}")

def ok(msg):
    print(f"    [OK] {msg}")

def warn(msg):
    print(f"    [!]  {msg}")

def err(msg):
    print(f"    [ERROR] {msg}", file=sys.stderr)

def progress_hook(block_num, block_size, total_size):
    if total_size > 0:
        pct = min(100, block_num * block_size * 100 // total_size)
        mb = total_size / (1024*1024)
        print(f"\r    Descargando... {pct}% de {mb:.1f} MB", end="", flush=True)
    if block_num * block_size >= total_size:
        print()


def download(url, dest, label):
    if dest.exists():
        ok(f"{label} ya existe, saltando")
        return
    step(f"Descargando {label}...")
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        urlretrieve(url, dest, progress_hook)
        ok(f"{label} ({dest.stat().st_size//1024} KB)")
    except URLError as e:
        err(f"No se pudo descargar {label}: {e}")
        raise


def copy_project(src, dst, label):
    step(f"Copiando {label}...")
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)

    copied = 0
    for item in src.rglob("*"):
        if any(ex in item.parts for ex in EXCLUDE_DIRS):
            continue
        if item.is_file() and item.suffix in EXCLUDE_FILES:
            continue
        rel = item.relative_to(src)
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
            copied += 1

    ok(f"{label}: {copied} archivos")


def bundle_claude_code(node_dir: Path):
    """
    Instala @anthropic-ai/claude-code en un directorio temporal
    y empaqueta node_modules como ZIP para distribución offline.
    """
    step(f"Instalando {CLAUDE_PKG} para bundle offline...")
    bundle_dir = ASSETS_DIR / "claude_code"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    node_modules_zip = bundle_dir / "node_modules.zip"
    if node_modules_zip.exists():
        ok("node_modules.zip ya existe, saltando")
        return

    # Extraer Node.js portable temporalmente para hacer npm install
    node_zip = ASSETS_DIR / "node" / "node-win.zip"
    if not node_zip.exists():
        err("Node.js ZIP no encontrado. Descarga primero con --skip-claude-only no.")
        return

    tmp_node = ASSETS_DIR / "_tmp_node"
    if not tmp_node.exists():
        step("Extrayendo Node.js temporal...")
        import zipfile as zf
        with zf.ZipFile(node_zip) as z:
            z.extractall(tmp_node)

    # node.exe y npm están en el primer subdirectorio
    node_dirs = list(tmp_node.iterdir())
    if not node_dirs:
        err("No se pudo extraer Node.js")
        return
    node_bin = node_dirs[0] / "node.exe"
    npm_cmd  = node_dirs[0] / "npm.cmd"

    if not node_bin.exists():
        err(f"node.exe no encontrado en {node_dirs[0]}")
        return

    # npm install en directorio temporal
    install_dir = bundle_dir / "_install"
    install_dir.mkdir(exist_ok=True)

    # Crear package.json mínimo
    pkg_json = install_dir / "package.json"
    pkg_json.write_text('{"name":"claude-bundle","version":"1.0.0","private":true}', "utf-8")

    step(f"Ejecutando npm install {CLAUDE_PKG} (esto puede tardar 2-5 min)...")
    env = os.environ.copy()
    env["PATH"] = str(node_dirs[0]) + os.pathsep + env.get("PATH", "")

    result = subprocess.run(
        [str(npm_cmd), "install", CLAUDE_PKG],
        cwd=str(install_dir),
        env=env,
        capture_output=True,
        text=True,
        timeout=600
    )

    if result.returncode != 0:
        err(f"npm install falló:\n{result.stderr[-500:]}")
        raise RuntimeError("npm install failed")

    ok("npm install completado")

    # Comprimir node_modules
    step("Comprimiendo node_modules...")
    nm_dir = install_dir / "node_modules"
    if not nm_dir.exists():
        err("node_modules no creado")
        return

    total = sum(1 for _ in nm_dir.rglob("*"))
    done = 0
    with zipfile.ZipFile(node_modules_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in nm_dir.rglob("*"):
            zf.write(f, f.relative_to(install_dir))
            done += 1
            if done % 1000 == 0:
                print(f"\r    {done}/{total} archivos...", end="", flush=True)
    print()

    size_mb = node_modules_zip.stat().st_size / (1024*1024)
    ok(f"node_modules.zip creado: {size_mb:.0f} MB")

    # Limpiar temporal
    shutil.rmtree(install_dir)

    # También copiar el package.json con la versión instalada
    pkg_lock = install_dir.parent / "_install" / "package-lock.json"
    if pkg_lock.exists():
        shutil.copy2(pkg_lock, bundle_dir / "package-lock.json")


def create_manifest():
    import datetime
    manifest = {
        "created_at": datetime.datetime.now().isoformat(),
        "python_url": PYTHON_WIN_URL,
        "node_url": NODE_WIN_URL,
        "claude_pkg": CLAUDE_PKG,
        "projects": ["Asistente IA"],
        "installer_version": "1.0.0",
    }
    (ASSETS_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), "utf-8"
    )
    ok("manifest.json creado")


def verify_bundle():
    title("Verificacion del Bundle")
    checks = [
        (ASSETS_DIR / "python" / "python-embed-win.zip", "Python embeddable (Windows)"),
        (ASSETS_DIR / "python" / "get-pip.py", "get-pip.py"),
        (ASSETS_DIR / "node" / "node-win.zip", "Node.js (Windows)"),
        (ASSETS_DIR / "node" / "node-linux.tar.xz", "Node.js (Linux)"),
        (ASSETS_DIR / "claude_code" / "node_modules.zip", "Claude Code (node_modules)"),
        (ASSETS_DIR / "project" / "asistente", "Asistente IA"),
        (ASSETS_DIR / "manifest.json", "Manifest"),
    ]

    all_ok = True
    for path, label in checks:
        if path.exists():
            if path.is_file():
                print(f"  [OK] {label:<45} {path.stat().st_size//1024:>8} KB")
            else:
                print(f"  [OK] {label:<45} (directorio)")
        else:
            print(f"  [--] {label:<45} FALTA")
            all_ok = False

    total = sum(f.stat().st_size for f in ASSETS_DIR.rglob("*") if f.is_file())
    print(f"\n  Tamaño total: {total/(1024*1024):.0f} MB")
    if all_ok:
        print("  [OK] Bundle completo.")
    else:
        print("  [!] Bundle incompleto.")
    return all_ok


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-node",    action="store_true", help="No descargar Node.js")
    parser.add_argument("--skip-claude",  action="store_true", help="No bundlear Claude Code")
    parser.add_argument("--skip-python",  action="store_true", help="No descargar Python embeddable")
    parser.add_argument("--verify-only",  action="store_true")
    args = parser.parse_args()

    title("Asistente IA — Build Installer")

    if args.verify_only:
        verify_bundle()
        return

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Python embeddable (Windows)
    if not args.skip_python:
        py_dir = ASSETS_DIR / "python"
        py_dir.mkdir(exist_ok=True)
        download(PYTHON_WIN_URL, py_dir / "python-embed-win.zip", "Python 3.12 embeddable (Windows)")
        download(GET_PIP_URL, py_dir / "get-pip.py", "get-pip.py")

    # 2. Node.js
    if not args.skip_node:
        node_dir = ASSETS_DIR / "node"
        node_dir.mkdir(exist_ok=True)
        download(NODE_WIN_URL, node_dir / "node-win.zip", f"Node.js {NODE_VERSION} (Windows)")
        download(NODE_LIN_URL, node_dir / "node-linux.tar.xz", f"Node.js {NODE_VERSION} (Linux)")

    # 3. Claude Code bundle
    if not args.skip_claude:
        node_dir = ASSETS_DIR / "node"
        bundle_claude_code(node_dir)

    # 4. Proyecto Asistente IA
    copy_project(ASISTENTE_DIR, ASSETS_DIR / "project" / "asistente", "Asistente IA")

    # 5. Manifest
    create_manifest()

    # 6. Verificar
    verify_bundle()

    # Limpiar temporal
    tmp = ASSETS_DIR / "_tmp_node"
    if tmp.exists():
        shutil.rmtree(tmp)

    title("Build completado")
    print(f"""
  Para distribuir:
    Comprime la carpeta: {INSTALLER_DIR.name}/
    En la PC destino:
      Windows: install.bat
      Linux:   ./install.sh
""")


if __name__ == "__main__":
    main()
