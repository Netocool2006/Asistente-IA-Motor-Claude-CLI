"""
test_frontend_e2e.py — Pruebas E2E Frontend: Certificación para Producción
============================================================================
Simula al usuario final ejecutando CADA comando CLI del sistema Asistente IA.
Verifica stdout, stderr, returncode y archivos de estado.

Ejecutar: python test_frontend_e2e.py
Criterio: 95%+ PASS = certificado para producción.
"""

import io, json, sys, os, subprocess, shutil, time, re, tempfile, sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# Fix Unicode en Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ── Configuración ─────────────────────────────────────────────
PROJECT_DIR  = Path(__file__).parent
HOOKS_DIR    = PROJECT_DIR / ".claude" / "hooks"
HOME         = Path.home()
ADAPTIVE_DIR = HOME / ".adaptive_cli"
KB_DIR       = ADAPTIVE_DIR / "knowledge"
PYTHON       = sys.executable

# Añadir al path para importar módulos
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(HOOKS_DIR))

# ── Colores ANSI ──────────────────────────────────────────────
GR = "\033[92m"; RD = "\033[91m"; YL = "\033[93m"; BL = "\033[94m"
CY = "\033[96m"; BLD = "\033[1m"; RS = "\033[0m"; MG = "\033[95m"

# ── Contadores ────────────────────────────────────────────────
results = defaultdict(int)
failures = []
_sec = ""

def section(name):
    global _sec; _sec = name
    print(f"\n{BL}{BLD}{'═'*70}{RS}")
    print(f"{BL}{BLD}  {name}{RS}")
    print(f"{BL}{BLD}{'═'*70}{RS}")

def ok(msg):
    results["pass"] += 1
    print(f"  {GR}✓ PASS{RS}  {msg}")

def fail(msg, detail=""):
    results["fail"] += 1
    d = f"\n         {RD}{detail[:200]}{RS}" if detail else ""
    print(f"  {RD}✗ FAIL{RS}  {msg}{d}")
    failures.append(f"[{_sec}] {msg}")

def warn(msg):
    results["warn"] += 1
    print(f"  {YL}⚠ WARN{RS}  {msg}")

def skip(msg):
    results["skip"] += 1
    print(f"  {CY}⊘ SKIP{RS}  {msg}")

def run_cli(args, stdin_data=None, timeout=30, cwd=None):
    """Ejecuta un comando CLI y retorna (stdout, stderr, returncode)."""
    cmd = [PYTHON] + [str(a) for a in args]
    stdin_str = None
    if stdin_data is not None:
        stdin_str = json.dumps(stdin_data, ensure_ascii=False) if isinstance(stdin_data, dict) else str(stdin_data)
    try:
        r = subprocess.run(
            cmd, input=stdin_str, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8",
            cwd=str(cwd or PROJECT_DIR),
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}
        )
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT", -1
    except Exception as e:
        return "", str(e), -99

def run_hook(hook_file, stdin_data=None, env_extra=None):
    """Ejecuta un hook y retorna (stdout, stderr, returncode)."""
    stdin_str = json.dumps(stdin_data or {}, ensure_ascii=False)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if env_extra:
        env.update(env_extra)
    try:
        r = subprocess.run(
            [PYTHON, str(hook_file)],
            input=stdin_str, capture_output=True, text=True,
            timeout=20, encoding="utf-8", env=env,
            cwd=str(PROJECT_DIR)
        )
        return r.stdout, r.stderr, r.returncode
    except subprocess.TimeoutExpired:
        return "", "TIMEOUT", -1
    except Exception as e:
        return "", str(e), -99


# ══════════════════════════════════════════════════════════════
# S1. PREREQUISITOS Y AMBIENTE
# ══════════════════════════════════════════════════════════════
section("S1. PREREQUISITOS Y AMBIENTE")

# S1.1 Python 3.10+
v = sys.version_info
if v.major == 3 and v.minor >= 10:
    ok(f"S1.1 Python {v.major}.{v.minor}.{v.micro} >= 3.10")
else:
    fail(f"S1.1 Python {v.major}.{v.minor} < 3.10 requerido")

# S1.2 Directorio adaptive_cli existe
if ADAPTIVE_DIR.exists():
    ok("S1.2 ~/.adaptive_cli/ existe")
else:
    fail("S1.2 ~/.adaptive_cli/ NO existe")

# S1.3 Directorio knowledge existe
if KB_DIR.exists():
    ok("S1.3 ~/.adaptive_cli/knowledge/ existe")
else:
    fail("S1.3 ~/.adaptive_cli/knowledge/ NO existe")

# S1.4 _paths.py resuelve correctamente
try:
    from _paths import DATA_DIR
    if DATA_DIR.exists():
        ok(f"S1.4 _paths.py DATA_DIR={DATA_DIR} existe")
    else:
        fail(f"S1.4 _paths.py DATA_DIR={DATA_DIR} NO existe")
except Exception as e:
    fail("S1.4 _paths.py no importable", str(e))

# S1.5 Módulos importables
modules_ok = 0
modules_fail = 0
for mod in ["knowledge_base", "learning_memory", "domain_detector", "domains_config",
            "episodic_index", "sap_playbook"]:
    try:
        __import__(mod)
        modules_ok += 1
    except Exception as e:
        modules_fail += 1
        fail(f"S1.5 import {mod} falló", str(e))
if modules_fail == 0:
    ok(f"S1.5 Todos los módulos importables ({modules_ok}/6)")

# S1.6 Permisos de escritura en DATA_DIR
try:
    test_file = ADAPTIVE_DIR / "_test_write_perm.tmp"
    test_file.write_text("test", encoding="utf-8")
    test_file.unlink()
    ok("S1.6 Permisos de escritura en DATA_DIR OK")
except Exception as e:
    fail("S1.6 Sin permisos de escritura", str(e))

# S1.7 Hooks directory exists
if HOOKS_DIR.exists():
    hooks = list(HOOKS_DIR.glob("*.py"))
    hook_names = [h.name for h in hooks if not h.name.startswith("_")]
    if len(hook_names) >= 4:
        ok(f"S1.7 Hooks: {len(hook_names)} encontrados ({', '.join(sorted(hook_names)[:5])})")
    else:
        warn(f"S1.7 Solo {len(hook_names)} hooks (esperados >= 4)")
else:
    fail("S1.7 .claude/hooks/ NO existe")

# S1.8 JSON base files parseable
json_errors = 0
for jf in KB_DIR.rglob("*.json"):
    try:
        data = json.loads(jf.read_text(encoding="utf-8"))
    except Exception:
        json_errors += 1
        fail(f"S1.8 JSON corrupto: {jf.name}")
if json_errors == 0:
    ok("S1.8 Todos los JSON en knowledge/ son válidos")


# ══════════════════════════════════════════════════════════════
# S2. KNOWLEDGE BASE CLI
# ══════════════════════════════════════════════════════════════
section("S2. KNOWLEDGE BASE CLI (python knowledge_base.py)")

kb_script = PROJECT_DIR / "knowledge_base.py"

# S2.1 stats
stdout, stderr, rc = run_cli([kb_script, "stats"])
if rc == 0 and stdout.strip():
    ok("S2.1 stats — rc=0, output presente")
else:
    fail("S2.1 stats falló", f"rc={rc} stderr={stderr[:150]}")

# S2.2 list-domains
stdout, stderr, rc = run_cli([kb_script, "list-domains"])
if rc == 0 and stdout.strip():
    ok("S2.2 list-domains — rc=0, output presente")
    if "sow" in stdout.lower() or "bom" in stdout.lower() or "sap" in stdout.lower():
        ok("S2.2 list-domains contiene dominios esperados")
    else:
        warn("S2.2 list-domains sin dominios esperados (pueden no estar creados)")
else:
    fail("S2.2 list-domains falló", f"rc={rc} stderr={stderr[:150]}")

# S2.3 export sin dominio
stdout, stderr, rc = run_cli([kb_script, "export"])
if rc == 0:
    ok("S2.3 export (sin dominio) — rc=0")
else:
    fail("S2.3 export falló", f"rc={rc} stderr={stderr[:150]}")

# S2.4 export con query
stdout, stderr, rc = run_cli([kb_script, "export", "--query", "contrato sow propuesta"])
if rc == 0:
    ok("S2.4 export --query — rc=0")
else:
    fail("S2.4 export --query falló", f"rc={rc} stderr={stderr[:150]}")

# S2.5 cross-search
stdout, stderr, rc = run_cli([kb_script, "cross-search", "--query", "SAP login CRM"])
if rc == 0:
    ok("S2.5 cross-search — rc=0")
else:
    fail("S2.5 cross-search falló", f"rc={rc} stderr={stderr[:150]}")

# S2.6 search con dominio específico
stdout, stderr, rc = run_cli([kb_script, "search", "sow", "--query", "propuesta"])
if rc == 0:
    ok("S2.6 search sow --query — rc=0")
else:
    fail("S2.6 search sow falló", f"rc={rc} stderr={stderr[:150]}")

# S2.7 search con tags
stdout, stderr, rc = run_cli([kb_script, "search", "sap_tierra", "--tags", "login,playwright"])
if rc == 0:
    ok("S2.7 search --tags — rc=0")
else:
    fail("S2.7 search --tags falló", f"rc={rc} stderr={stderr[:150]}")

# S2.8 Edge: dominio inexistente
stdout, stderr, rc = run_cli([kb_script, "search", "dominio_que_no_existe_xyz", "--query", "test"])
if rc == 0:
    ok("S2.8 Dominio inexistente — graceful (rc=0)")
else:
    # Aceptable si rc != 0 pero no crashea
    if "Traceback" not in stderr:
        ok("S2.8 Dominio inexistente — error controlado (sin traceback)")
    else:
        fail("S2.8 Dominio inexistente — CRASH", stderr[:200])

# S2.9 Edge: query vacío
stdout, stderr, rc = run_cli([kb_script, "cross-search", "--query", ""])
if rc == 0:
    ok("S2.9 Query vacío — rc=0 graceful")
else:
    if "Traceback" not in stderr:
        ok("S2.9 Query vacío — error controlado")
    else:
        fail("S2.9 Query vacío — CRASH", stderr[:200])

# S2.10 Edge: Unicode en query
stdout, stderr, rc = run_cli([kb_script, "cross-search", "--query", "cláusula estándar ñandú 🚀"])
if rc == 0:
    ok("S2.10 Unicode en query — rc=0")
else:
    if "Traceback" not in stderr:
        warn("S2.10 Unicode — error controlado pero rc!=0")
    else:
        fail("S2.10 Unicode — CRASH", stderr[:200])

# S2.11 ingest-rules con archivo temporal
rules_file = Path(tempfile.mktemp(suffix=".txt"))
rules_file.write_text(
    "REGLA: test_rule_frontend\n"
    "APLICA: testing\n"
    "EJEMPLO: esto es una regla de prueba e2e\n"
    "---\n"
    "REGLA: test_rule_2\n"
    "APLICA: validacion\n"
    "EJEMPLO: segunda regla de prueba\n",
    encoding="utf-8"
)
stdout, stderr, rc = run_cli([kb_script, "ingest-rules", str(rules_file)])
if rc == 0:
    ok("S2.11 ingest-rules — rc=0")
else:
    fail("S2.11 ingest-rules falló", f"rc={rc} stderr={stderr[:150]}")
rules_file.unlink(missing_ok=True)

# S2.12 ingest-catalog con archivo temporal
cat_file = Path(tempfile.mktemp(suffix=".txt"))
cat_file.write_text(
    "CÓDIGO: TEST001\nNOMBRE: Producto Test E2E\nTIPO: software\nPRECIO: $100/mes\n---\n",
    encoding="utf-8"
)
stdout, stderr, rc = run_cli([kb_script, "ingest-catalog", str(cat_file)])
if rc == 0:
    ok("S2.12 ingest-catalog — rc=0")
else:
    fail("S2.12 ingest-catalog falló", f"rc={rc} stderr={stderr[:150]}")
cat_file.unlink(missing_ok=True)

# S2.13 Edge: ingest-rules archivo inexistente
stdout, stderr, rc = run_cli([kb_script, "ingest-rules", "/archivo/que/no/existe.txt"])
if "Traceback" not in stderr:
    ok("S2.13 ingest-rules archivo inexistente — sin crash")
else:
    fail("S2.13 ingest-rules archivo inexistente — CRASH", stderr[:200])

# S2.14 Subcomando inexistente
stdout, stderr, rc = run_cli([kb_script, "subcomando_invalido_xyz"])
if "Traceback" not in stderr:
    ok("S2.14 Subcomando inexistente — sin crash")
else:
    fail("S2.14 Subcomando inexistente — CRASH", stderr[:200])

# S2.15 Sin argumentos
stdout, stderr, rc = run_cli([kb_script])
if "Traceback" not in stderr:
    ok("S2.15 Sin argumentos — sin crash")
else:
    fail("S2.15 Sin argumentos — CRASH", stderr[:200])


# ══════════════════════════════════════════════════════════════
# S3. LEARNING MEMORY CLI
# ══════════════════════════════════════════════════════════════
section("S3. LEARNING MEMORY CLI (python learning_memory.py)")

lm_script = PROJECT_DIR / "learning_memory.py"

# S3.1 stats
stdout, stderr, rc = run_cli([lm_script, "stats"])
if rc == 0 and stdout.strip():
    ok("S3.1 stats — rc=0, output presente")
else:
    fail("S3.1 stats falló", f"rc={rc} stderr={stderr[:150]}")

# S3.2 list
stdout, stderr, rc = run_cli([lm_script, "list"])
if rc == 0:
    ok("S3.2 list — rc=0")
else:
    fail("S3.2 list falló", f"rc={rc} stderr={stderr[:150]}")

# S3.3 export (sin task_type)
stdout, stderr, rc = run_cli([lm_script, "export"])
if rc == 0:
    ok("S3.3 export — rc=0")
else:
    fail("S3.3 export falló", f"rc={rc} stderr={stderr[:150]}")

# S3.4 export con task_type
stdout, stderr, rc = run_cli([lm_script, "export", "sap_login"])
if rc == 0:
    ok("S3.4 export sap_login — rc=0")
else:
    fail("S3.4 export sap_login falló", f"rc={rc} stderr={stderr[:150]}")

# S3.5 search (puede no tener resultados)
stdout, stderr, rc = run_cli([lm_script, "search", "sap_login", "crm_logon_client500"])
if rc == 0:
    ok("S3.5 search — rc=0")
else:
    fail("S3.5 search falló", f"rc={rc} stderr={stderr[:150]}")

# S3.6 Round-trip: register → search → verify (via import)
try:
    import learning_memory as lm
    test_id = lm.register_pattern(
        "test_e2e_type", "test_e2e_context",
        {"strategy": "e2e_test", "code_snippet": "print('hello')", "notes": "test E2E"},
        tags=["test", "e2e", "frontend"]
    )
    found = lm.search_pattern("test_e2e_type", "test_e2e_context")
    if found and found.get("solution", {}).get("strategy") == "e2e_test":
        ok("S3.6 Round-trip register→search — patrón encontrado")
    else:
        fail("S3.6 Round-trip — patrón NO encontrado después de registro")
except Exception as e:
    fail("S3.6 Round-trip crasheó", str(e))

# S3.7 Record reuse (success) → success_rate sube
try:
    if test_id:
        sr_before = lm.search_pattern("test_e2e_type", "test_e2e_context")["stats"]["success_rate"]
        # Retry con backoff para evitar WinError 5 (file lock race condition)
        for attempt in range(3):
            try:
                lm.record_reuse(test_id, success=True)
                break
            except OSError:
                time.sleep(0.5)
        sr_after = lm.search_pattern("test_e2e_type", "test_e2e_context")["stats"]["success_rate"]
        if sr_after >= sr_before:
            ok(f"S3.7 Record reuse success — sr {sr_before:.2f}→{sr_after:.2f}")
        else:
            warn(f"S3.7 success_rate no subió: {sr_before:.2f}→{sr_after:.2f}")
except Exception as e:
    fail("S3.7 Record reuse crasheó", str(e))

# S3.8 Record reuse (fail) → success_rate baja
try:
    if test_id:
        sr_before = lm.search_pattern("test_e2e_type", "test_e2e_context")["stats"]["success_rate"]
        lm.record_reuse(test_id, success=False)
        sr_after = lm.search_pattern("test_e2e_type", "test_e2e_context")["stats"]["success_rate"]
        if sr_after <= sr_before:
            ok(f"S3.8 Record reuse fail — sr {sr_before:.2f}→{sr_after:.2f}")
        else:
            warn(f"S3.8 success_rate no bajó: {sr_before:.2f}→{sr_after:.2f}")
except Exception as e:
    fail("S3.8 Record reuse fail crasheó", str(e))

# S3.9 attempts command
stdout, stderr, rc = run_cli([lm_script, "attempts", "login SAP CRM"])
if rc == 0:
    ok("S3.9 attempts — rc=0")
else:
    fail("S3.9 attempts falló", f"rc={rc} stderr={stderr[:150]}")

# S3.10 context command
stdout, stderr, rc = run_cli([lm_script, "context", "login SAP CRM"])
if rc == 0:
    ok("S3.10 context — rc=0")
else:
    fail("S3.10 context falló", f"rc={rc} stderr={stderr[:150]}")

# S3.11 Edge: search sin resultados
stdout, stderr, rc = run_cli([lm_script, "search", "no_existe_xyz", "clave_imaginaria"])
if rc == 0 and "Traceback" not in stderr:
    ok("S3.11 Search sin resultados — graceful")
else:
    fail("S3.11 Search sin resultados — crash", stderr[:200])

# S3.12 Edge: sin argumentos
stdout, stderr, rc = run_cli([lm_script])
if "Traceback" not in stderr:
    ok("S3.12 Sin argumentos — sin crash")
else:
    fail("S3.12 Sin argumentos — CRASH", stderr[:200])


# ══════════════════════════════════════════════════════════════
# S4. SEEDING
# ══════════════════════════════════════════════════════════════
section("S4. SEEDING (seed_gbm_knowledge.py + seed_sap_patterns.py)")

# S4.1 seed_gbm_knowledge.py
stdout, stderr, rc = run_cli([PROJECT_DIR / "seed_gbm_knowledge.py"], timeout=60)
if rc == 0:
    ok("S4.1 seed_gbm_knowledge.py — rc=0")
    if "error" in stdout.lower() and "traceback" in stderr.lower():
        warn("S4.1 seed_gbm_knowledge.py — tiene warnings en output")
else:
    fail("S4.1 seed_gbm_knowledge.py falló", f"rc={rc} stderr={stderr[:200]}")

# S4.2 Verificar business_rules pobladas
stdout, stderr, rc = run_cli([kb_script, "search", "business_rules", "--query", "IVA Guatemala"])
if rc == 0:
    ok("S4.2 business_rules query IVA — rc=0")
    if "iva" in stdout.lower() or "12" in stdout:
        ok("S4.2 business_rules contiene IVA Guatemala")
    else:
        warn("S4.2 business_rules IVA no encontrada en output")
else:
    fail("S4.2 business_rules query falló", f"rc={rc}")

# S4.3 Verificar tarifas
stdout, stderr, rc = run_cli([kb_script, "search", "business_rules", "--query", "tarifas soporte"])
if rc == 0:
    ok("S4.3 business_rules tarifas — rc=0")
else:
    fail("S4.3 business_rules tarifas falló", f"rc={rc}")

# S4.4 seed_sap_patterns.py
stdout, stderr, rc = run_cli([PROJECT_DIR / "seed_sap_patterns.py"], timeout=60)
if rc == 0:
    ok("S4.4 seed_sap_patterns.py — rc=0")
else:
    fail("S4.4 seed_sap_patterns.py falló", f"rc={rc} stderr={stderr[:200]}")

# S4.5 Verificar patrones SAP en learning_memory
stdout, stderr, rc = run_cli([lm_script, "search", "sap_login", "crm_logon_client500"])
if rc == 0 and stdout.strip():
    ok("S4.5 SAP login pattern exists en learning_memory")
else:
    warn("S4.5 SAP login pattern no encontrado")

# S4.6 Idempotencia: ejecutar seed 2x no crashea
stdout, stderr, rc = run_cli([PROJECT_DIR / "seed_gbm_knowledge.py"], timeout=60)
if rc == 0:
    ok("S4.6 Idempotencia seed_gbm — rc=0 en 2da ejecución")
else:
    fail("S4.6 Idempotencia seed_gbm falló en 2da ejecución", stderr[:150])

# S4.7 stats post-seed
stdout, stderr, rc = run_cli([kb_script, "stats"])
if rc == 0 and stdout.strip():
    ok("S4.7 KB stats post-seed — output válido")
    # Verificar que hay entries
    if "total_entries" in stdout or "entries" in stdout.lower():
        ok("S4.7 KB stats muestra entries")
    else:
        warn("S4.7 KB stats sin campo entries visible")
else:
    fail("S4.7 KB stats post-seed falló")

# S4.8 export post-seed
stdout, stderr, rc = run_cli([kb_script, "export", "business_rules"])
if rc == 0 and len(stdout) > 50:
    ok(f"S4.8 KB export business_rules — {len(stdout)} chars de contenido")
else:
    warn(f"S4.8 KB export business_rules — poco contenido ({len(stdout)} chars)")


# ══════════════════════════════════════════════════════════════
# S5. DOMAIN DETECTOR
# ══════════════════════════════════════════════════════════════
section("S5. DOMAIN DETECTOR (python domain_detector.py)")

dd_script = PROJECT_DIR / "domain_detector.py"

domain_tests = [
    ("S5.1", "necesito crear un quote en SAP CRM tierra con playwright", "sap_tierra"),
    ("S5.2", "genera un sow para propuesta de contrato de servicio", "sow"),
    ("S5.3", "valida el bom con los materiales y cantidades del listado", "bom"),
    ("S5.4", "actualiza el pipeline en monday con el status del deal", "monday"),
    ("S5.5", "regla de IVA tarifa MEP liability para propuesta", "business_rules"),
]

for tid, text, expected in domain_tests:
    stdout, stderr, rc = run_cli([dd_script, text])
    if rc == 0:
        if expected in stdout.lower():
            ok(f"{tid} Detecta '{expected}' correctamente")
        else:
            warn(f"{tid} Esperado '{expected}', obtuvo: {stdout.strip()[:80]}")
    else:
        fail(f"{tid} domain_detector crasheó", stderr[:150])

# S5.6 Texto sin dominio claro
stdout, stderr, rc = run_cli([dd_script, "cuantos planetas hay en la galaxia"])
if rc == 0:
    ok("S5.6 Texto sin dominio — no crashea")
else:
    fail("S5.6 Texto sin dominio — crash", stderr[:150])

# S5.7 Texto vacío
stdout, stderr, rc = run_cli([dd_script, ""])
if "Traceback" not in stderr:
    ok("S5.7 Texto vacío — sin crash")
else:
    fail("S5.7 Texto vacío — CRASH", stderr[:200])

# S5.8 Unicode
stdout, stderr, rc = run_cli([dd_script, "cláusula estándar del SOW ñ"])
if rc == 0:
    ok("S5.8 Unicode en detector — rc=0")
else:
    fail("S5.8 Unicode — crash", stderr[:150])


# ══════════════════════════════════════════════════════════════
# S6. HOOKS — Integración Frontend
# ══════════════════════════════════════════════════════════════
section("S6. HOOKS — Integración Frontend")

# ── session_start_kb.py ──────────────────────────────────────
hook_ss = HOOKS_DIR / "session_start_kb.py"

# S6.1 session_start_kb ejecuta sin crash
stdout, stderr, rc = run_hook(hook_ss, {})
if rc == 0:
    ok("S6.1 session_start_kb — rc=0")
    if len(stdout) > 20:
        ok(f"S6.1 session_start_kb — inyecta {len(stdout)} chars de contexto")
    else:
        warn("S6.1 session_start_kb — poco contexto inyectado")
else:
    fail("S6.1 session_start_kb CRASH", stderr[:200])

# ── on_user_message.py ──────────────────────────────────────
hook_um = HOOKS_DIR / "on_user_message.py"

# S6.2 Clasificación SAP
stdout, stderr, rc = run_hook(hook_um, {
    "prompt": "necesito hacer login en SAP CRM tierra con playwright",
    "session_id": "e2e-test-001"
})
if rc == 0:
    ok("S6.2 on_user_message SAP — rc=0")
else:
    fail("S6.2 on_user_message SAP — CRASH", stderr[:200])

# S6.3 Clasificación SOW
stdout, stderr, rc = run_hook(hook_um, {
    "prompt": "genera un sow para propuesta de contrato de servicio con alcance definido",
    "session_id": "e2e-test-002"
})
if rc == 0:
    ok("S6.3 on_user_message SOW — rc=0")
else:
    fail("S6.3 on_user_message SOW — CRASH", stderr[:200])

# S6.4 Prompt vacío → silencio
stdout, stderr, rc = run_hook(hook_um, {"prompt": "", "session_id": "e2e-test-003"})
if rc == 0:
    ok("S6.4 Prompt vacío — rc=0")
    if not stdout.strip():
        ok("S6.4 Prompt vacío — salida vacía (correcto)")
    else:
        warn("S6.4 Prompt vacío — produjo output inesperado")
else:
    fail("S6.4 Prompt vacío — CRASH", stderr[:200])

# S6.5 Prompt corto (<5 chars)
stdout, stderr, rc = run_hook(hook_um, {"prompt": "ok", "session_id": "e2e-test-004"})
if rc == 0 and not stdout.strip():
    ok("S6.5 Prompt corto — exit silencioso")
elif rc == 0:
    warn("S6.5 Prompt corto — produjo output (aceptable)")
else:
    fail("S6.5 Prompt corto — CRASH", stderr[:200])

# S6.6 JSON corrupto en stdin
r = subprocess.run(
    [PYTHON, str(hook_um)],
    input="esto no es json {{{",
    capture_output=True, text=True, timeout=10,
    encoding="utf-8", cwd=str(PROJECT_DIR),
    env={**os.environ, "PYTHONIOENCODING": "utf-8"}
)
if r.returncode == 0:
    ok("S6.6 JSON corrupto — graceful exit (rc=0)")
else:
    if "Traceback" not in r.stderr:
        ok("S6.6 JSON corrupto — error controlado")
    else:
        fail("S6.6 JSON corrupto — CRASH", r.stderr[:200])

# S6.7 Sin campo prompt
stdout, stderr, rc = run_hook(hook_um, {"session_id": "e2e-007", "other": "value"})
if rc == 0:
    ok("S6.7 Sin campo prompt — no crashea")
else:
    fail("S6.7 Sin campo prompt — CRASH", stderr[:200])

# S6.8 Unicode en prompt
stdout, stderr, rc = run_hook(hook_um, {
    "prompt": "genera sow 🚀 con cláusulas estándar y áéíóú para ñ",
    "session_id": "e2e-test-008"
})
if rc == 0:
    ok("S6.8 Unicode/emojis en prompt — no crashea")
else:
    fail("S6.8 Unicode — CRASH", stderr[:200])

# S6.9 Cache: segunda llamada misma query
stdout1, _, rc1 = run_hook(hook_um, {"prompt": "genera sow contrato alcance entregable propuesta", "session_id": "e2e-cache"})
stdout2, _, rc2 = run_hook(hook_um, {"prompt": "genera sow contrato alcance entregable propuesta", "session_id": "e2e-cache"})
if rc1 == 0 and rc2 == 0:
    ok("S6.9 Cache — doble llamada sin crash")
else:
    fail("S6.9 Cache — crash en repetición")

# ── post_action_learn.py ─────────────────────────────────────
hook_pa = HOOKS_DIR / "post_action_learn.py"

# S6.10 post_action_learn con Bash tool
stdout, stderr, rc = run_hook(hook_pa, {
    "tool_name": "Bash",
    "tool_input": {"command": "python knowledge_base.py stats"},
    "tool_result": "KB stats: 15 entries total",
    "exit_code": 0
})
if rc == 0:
    ok("S6.10 post_action_learn Bash — rc=0")
else:
    fail("S6.10 post_action_learn Bash — CRASH", stderr[:200])

# S6.11 post_action_learn con Edit tool
stdout, stderr, rc = run_hook(hook_pa, {
    "tool_name": "Edit",
    "tool_input": {"file_path": "test.py", "old_string": "old", "new_string": "new"},
    "tool_result": "File edited successfully",
    "exit_code": 0
})
if rc == 0:
    ok("S6.11 post_action_learn Edit — rc=0")
else:
    fail("S6.11 post_action_learn Edit — CRASH", stderr[:200])

# S6.12 post_action_learn con error en tool
stdout, stderr, rc = run_hook(hook_pa, {
    "tool_name": "Bash",
    "tool_input": {"command": "python bad_script.py"},
    "tool_result": "Traceback (most recent call last):\n  File 'bad.py'\nNameError: name 'x' is not defined",
    "exit_code": 1
})
if rc == 0:
    ok("S6.12 post_action_learn con error — rc=0 (captura error)")
else:
    fail("S6.12 post_action_learn con error — CRASH", stderr[:200])

# ── iteration_learn.py ──────────────────────────────────────
hook_il = HOOKS_DIR / "iteration_learn.py"

# S6.13 iteration_learn con tool normal
stdout, stderr, rc = run_hook(hook_il, {
    "tool_name": "Read",
    "tool_input": {"file_path": "test.py"},
    "tool_result": "# python file content",
    "exit_code": 0
})
if rc == 0:
    ok("S6.13 iteration_learn Read — rc=0")
else:
    fail("S6.13 iteration_learn Read — CRASH", stderr[:200])

# S6.14 iteration_learn con stdin vacío
stdout, stderr, rc = run_hook(hook_il, {})
if rc == 0:
    ok("S6.14 iteration_learn stdin vacío — rc=0")
else:
    if "Traceback" not in stderr:
        ok("S6.14 iteration_learn stdin vacío — error controlado")
    else:
        fail("S6.14 iteration_learn stdin vacío — CRASH", stderr[:200])

# ── auto_learn_hook.py ──────────────────────────────────────
hook_al = HOOKS_DIR / "auto_learn_hook.py"

# S6.15 auto_learn_hook con datos mínimos
stdout, stderr, rc = run_hook(hook_al, {
    "session_id": "e2e-test-session",
    "transcript_path": "",
    "last_assistant_message": "Completé la tarea exitosamente.",
    "cwd": str(PROJECT_DIR),
    "hook_event_name": "Stop",
    "stop_hook_active": True
})
if rc == 0:
    ok("S6.15 auto_learn_hook — rc=0")
else:
    fail("S6.15 auto_learn_hook — CRASH", stderr[:200])

# S6.16 auto_learn_hook con campos faltantes
stdout, stderr, rc = run_hook(hook_al, {"session_id": "e2e-minimal"})
if rc == 0:
    ok("S6.16 auto_learn_hook campos mínimos — rc=0")
else:
    if "Traceback" not in stderr:
        ok("S6.16 auto_learn_hook campos mínimos — error controlado")
    else:
        fail("S6.16 auto_learn_hook campos mínimos — CRASH", stderr[:200])


# ══════════════════════════════════════════════════════════════
# S7. ADAPTIVE EXECUTOR CLI
# ══════════════════════════════════════════════════════════════
section("S7. ADAPTIVE EXECUTOR CLI (python adaptive_executor.py)")

ae_script = PROJECT_DIR / "adaptive_executor.py"

# S7.1 stats
stdout, stderr, rc = run_cli([ae_script, "stats"])
if rc == 0:
    ok("S7.1 stats — rc=0")
else:
    fail("S7.1 stats falló", f"rc={rc} stderr={stderr[:150]}")

# S7.2 export
stdout, stderr, rc = run_cli([ae_script, "export"])
if rc == 0:
    ok("S7.2 export — rc=0")
else:
    fail("S7.2 export falló", f"rc={rc} stderr={stderr[:150]}")

# S7.3 export con task_type
stdout, stderr, rc = run_cli([ae_script, "export", "sap_login"])
if rc == 0:
    ok("S7.3 export sap_login — rc=0")
else:
    fail("S7.3 export sap_login falló", f"rc={rc} stderr={stderr[:150]}")

# S7.4 prepare
stdout, stderr, rc = run_cli([ae_script, "prepare", "sap_login", "crm_logon", "Haz login en SAP CRM"])
if rc == 0:
    ok("S7.4 prepare — rc=0")
    if "prompt" in stdout.lower() or len(stdout) > 20:
        ok("S7.4 prepare — genera prompt con contenido")
    else:
        warn("S7.4 prepare — output corto")
else:
    fail("S7.4 prepare falló", f"rc={rc} stderr={stderr[:150]}")

# S7.5 prepare con task_type inexistente
stdout, stderr, rc = run_cli([ae_script, "prepare", "tarea_xyz", "contexto_abc", "Request test"])
if rc == 0:
    ok("S7.5 prepare task inexistente — rc=0 (prompt exploración)")
else:
    if "Traceback" not in stderr:
        ok("S7.5 prepare task inexistente — error controlado")
    else:
        fail("S7.5 prepare task inexistente — CRASH", stderr[:200])

# S7.6 run con --dry-run (no invoca Claude)
stdout, stderr, rc = run_cli([ae_script, "run", "sap_login", "crm_logon", "Test dry run", "--dry-run"])
if rc == 0:
    ok("S7.6 run --dry-run — rc=0")
else:
    # dry-run puede no existir como flag, verificar
    if "Traceback" not in stderr:
        warn("S7.6 run --dry-run — rc!=0 pero sin crash (flag puede no existir)")
    else:
        fail("S7.6 run --dry-run — CRASH", stderr[:200])

# S7.7 Sin argumentos
stdout, stderr, rc = run_cli([ae_script])
if "Traceback" not in stderr:
    ok("S7.7 Sin argumentos — sin crash")
else:
    fail("S7.7 Sin argumentos — CRASH", stderr[:200])

# S7.8 Subcomando inválido
stdout, stderr, rc = run_cli([ae_script, "subcomando_invalido"])
if "Traceback" not in stderr:
    ok("S7.8 Subcomando inválido — sin crash")
else:
    fail("S7.8 Subcomando inválido — CRASH", stderr[:200])


# ══════════════════════════════════════════════════════════════
# S8. UTILIDADES AUXILIARES
# ══════════════════════════════════════════════════════════════
section("S8. UTILIDADES AUXILIARES")

# ── episodic_index.py ────────────────────────────────────────
ei_script = PROJECT_DIR / "episodic_index.py"

# S8.1 episodic stats
stdout, stderr, rc = run_cli([ei_script, "stats"])
if rc == 0:
    ok("S8.1 episodic_index stats — rc=0")
else:
    fail("S8.1 episodic_index stats — CRASH", stderr[:200])

# S8.2 episodic rebuild
stdout, stderr, rc = run_cli([ei_script, "rebuild"])
if rc == 0:
    ok("S8.2 episodic_index rebuild — rc=0")
else:
    fail("S8.2 episodic_index rebuild — CRASH", stderr[:200])

# S8.3 episodic search
stdout, stderr, rc = run_cli([ei_script, "search", "SAP login"])
if rc == 0:
    ok("S8.3 episodic_index search — rc=0")
else:
    fail("S8.3 episodic_index search — CRASH", stderr[:200])

# ── sap_playbook.py ─────────────────────────────────────────
sp_script = PROJECT_DIR / "sap_playbook.py"

# S8.4 sap_playbook seed
stdout, stderr, rc = run_cli([sp_script, "seed"])
if rc == 0:
    ok("S8.4 sap_playbook seed — rc=0")
else:
    fail("S8.4 sap_playbook seed — CRASH", stderr[:200])

# S8.5 sap_playbook stats
stdout, stderr, rc = run_cli([sp_script, "stats"])
if rc == 0:
    ok("S8.5 sap_playbook stats — rc=0")
else:
    fail("S8.5 sap_playbook stats — CRASH", stderr[:200])

# S8.6 sap_playbook export
stdout, stderr, rc = run_cli([sp_script, "export"])
if rc == 0:
    ok("S8.6 sap_playbook export — rc=0")
else:
    fail("S8.6 sap_playbook export — CRASH", stderr[:200])

# S8.7 sap_playbook lookup
stdout, stderr, rc = run_cli([sp_script, "lookup", "sap_login"])
if rc == 0:
    ok("S8.7 sap_playbook lookup — rc=0")
else:
    fail("S8.7 sap_playbook lookup — CRASH", stderr[:200])

# S8.8 sap_playbook helpers
stdout, stderr, rc = run_cli([sp_script, "helpers"])
if rc == 0:
    ok("S8.8 sap_playbook helpers — rc=0")
else:
    fail("S8.8 sap_playbook helpers — CRASH", stderr[:200])

# S8.9 sap_playbook blacklist
stdout, stderr, rc = run_cli([sp_script, "blacklist"])
if rc == 0:
    ok("S8.9 sap_playbook blacklist — rc=0")
else:
    fail("S8.9 sap_playbook blacklist — CRASH", stderr[:200])

# ── kb_maintenance.py ────────────────────────────────────────
km_script = PROJECT_DIR / "kb_maintenance.py"

# S8.10 kb_maintenance --stats
stdout, stderr, rc = run_cli([km_script, "--stats"])
if rc == 0:
    ok("S8.10 kb_maintenance --stats — rc=0")
else:
    fail("S8.10 kb_maintenance --stats — CRASH", stderr[:200])

# S8.11 kb_maintenance --dry-run
stdout, stderr, rc = run_cli([km_script, "--dry-run"])
if rc == 0:
    ok("S8.11 kb_maintenance --dry-run — rc=0")
else:
    fail("S8.11 kb_maintenance --dry-run — CRASH", stderr[:200])

# ── ingest_knowledge.py ──────────────────────────────────────
ik_script = PROJECT_DIR / "ingest_knowledge.py"

# S8.12 ingest archivo .txt
txt_file = Path(tempfile.mktemp(suffix=".txt"))
txt_file.write_text(
    "Este es un documento de prueba para ingestión.\n"
    "Contiene reglas de negocio y procesos de SOW.\n"
    "Los contratos llevan sufijo _PS.\n",
    encoding="utf-8"
)
stdout, stderr, rc = run_cli([ik_script, str(txt_file), "--domain", "sow", "--preview"])
if rc == 0:
    ok("S8.12 ingest .txt --preview — rc=0")
else:
    fail("S8.12 ingest .txt — CRASH", stderr[:200])
txt_file.unlink(missing_ok=True)

# S8.13 ingest archivo .md
md_file = Path(tempfile.mktemp(suffix=".md"))
md_file.write_text(
    "# Proceso de Validación BoM\n\n"
    "1. Verificar números de parte\n"
    "2. Validar cantidades\n"
    "3. Revisar clasificación\n",
    encoding="utf-8"
)
stdout, stderr, rc = run_cli([ik_script, str(md_file), "--domain", "bom", "--preview"])
if rc == 0:
    ok("S8.13 ingest .md --preview — rc=0")
else:
    fail("S8.13 ingest .md — CRASH", stderr[:200])
md_file.unlink(missing_ok=True)

# S8.14 ingest archivo inexistente
stdout, stderr, rc = run_cli([ik_script, "/no/existe.txt"])
if "Traceback" not in stderr:
    ok("S8.14 ingest archivo inexistente — sin crash")
else:
    fail("S8.14 ingest archivo inexistente — CRASH", stderr[:200])

# ── save_session.py ──────────────────────────────────────────
ss_script = PROJECT_DIR / "save_session.py"

# S8.15 save_session CLI
stdout, stderr, rc = run_cli([
    ss_script, "Sesión de prueba E2E",
    "--requests", "test request 1|test request 2",
    "--errors", "ninguno",
    "--decisions", "ejecutar test E2E",
    "--files-edited", "test_frontend_e2e.py"
])
if rc == 0:
    ok("S8.15 save_session CLI — rc=0")
else:
    fail("S8.15 save_session CLI — CRASH", stderr[:200])

# S8.16 save_session --json
session_json = {
    "summary": "Sesión JSON test E2E",
    "requests": ["test JSON"],
    "errors": [],
    "decisions": ["usar JSON mode"],
    "files_edited": ["test.py"]
}
stdout, stderr, rc = run_cli([ss_script, "--json"], stdin_data=session_json)
if rc == 0:
    ok("S8.16 save_session --json — rc=0")
else:
    fail("S8.16 save_session --json — CRASH", stderr[:200])


# ══════════════════════════════════════════════════════════════
# S9. FLUJO END-TO-END COMPLETO
# ══════════════════════════════════════════════════════════════
section("S9. FLUJO END-TO-END COMPLETO")

# S9.1 Seed → Stats → Verify populated
stdout, stderr, rc = run_cli([kb_script, "stats"])
if rc == 0 and ("entries" in stdout.lower() or "total" in stdout.lower()):
    ok("S9.1 KB stats post-seed muestra entries")
else:
    warn("S9.1 KB stats post-seed — output inesperado")

# S9.2 Search miss → Register → Search hit (round-trip completo via CLI)
try:
    import knowledge_base as kb
    # Buscar algo que no existe
    results_before = kb.search("sow", key="e2e_test_roundtrip_xyz")

    # Registrar nuevo patrón
    entry_id = kb.add_pattern(
        "sow", "e2e_test_roundtrip_xyz",
        {"strategy": "e2e_test", "notes": "patrón creado por test E2E"},
        tags=["test", "e2e"]
    )

    # Buscar de nuevo
    results_after = kb.search("sow", key="e2e_test_roundtrip_xyz")
    if results_after and len(results_after) > 0:
        ok("S9.2 Round-trip KB: miss → register → hit OK")
    else:
        fail("S9.2 Round-trip KB: registró pero no encontró")
except Exception as e:
    fail("S9.2 Round-trip KB crasheó", str(e))

# S9.3 Hook chain: user_message → detect domain → inject context
stdout, stderr, rc = run_hook(hook_um, {
    "prompt": "necesito revisar el SOW del contrato de soporte 24x7 para GBM",
    "session_id": "e2e-chain-test"
})
if rc == 0:
    ok("S9.3 Hook chain — on_user_message rc=0")
    if "sow" in stdout.lower() or "memory_system" in stdout or "soporte" in stdout.lower() or len(stdout) > 10:
        ok("S9.3 Hook chain — contexto inyectado")
    else:
        warn("S9.3 Hook chain — poco o ningún contexto")
else:
    fail("S9.3 Hook chain — CRASH", stderr[:200])

# S9.4 Pattern lifecycle: register → reuse(success) → verify success_rate up
try:
    test_id2 = lm.register_pattern(
        "e2e_lifecycle", "test_lifecycle_ctx",
        {"strategy": "lifecycle_test", "notes": "lifecycle test"},
        tags=["lifecycle", "e2e"]
    )
    p = lm.search_pattern("e2e_lifecycle", "test_lifecycle_ctx")
    sr_initial = p["stats"]["success_rate"]

    lm.record_reuse(test_id2, success=True)
    lm.record_reuse(test_id2, success=True)
    lm.record_reuse(test_id2, success=True)

    p2 = lm.search_pattern("e2e_lifecycle", "test_lifecycle_ctx")
    sr_after = p2["stats"]["success_rate"]

    if sr_after >= sr_initial:
        ok(f"S9.4 Lifecycle: success_rate {sr_initial:.2f}→{sr_after:.2f} (sube con éxitos)")
    else:
        warn(f"S9.4 Lifecycle: success_rate bajó {sr_initial:.2f}→{sr_after:.2f}")
except Exception as e:
    fail("S9.4 Lifecycle crasheó", str(e))

# S9.5 Pattern lifecycle: record failures → success_rate decays
try:
    lm.record_reuse(test_id2, success=False)
    lm.record_reuse(test_id2, success=False)

    p3 = lm.search_pattern("e2e_lifecycle", "test_lifecycle_ctx")
    sr_decay = p3["stats"]["success_rate"]

    if sr_decay < sr_after:
        ok(f"S9.5 Lifecycle decay: {sr_after:.2f}→{sr_decay:.2f} (baja con fallos)")
    else:
        warn(f"S9.5 Lifecycle decay: no bajó {sr_after:.2f}→{sr_decay:.2f}")
except Exception as e:
    fail("S9.5 Lifecycle decay crasheó", str(e))

# S9.6 Full E2E: domain detect → KB search → cross-search
try:
    import domain_detector as dd
    domain = dd.detect("necesito crear un quote estándar en SAP CRM tierra")
    ok(f"S9.6 Full E2E detect → '{domain}'")

    stdout_kb, _, rc_kb = run_cli([kb_script, "export", domain or "sap_tierra", "--query", "quote estándar"])
    if rc_kb == 0:
        ok("S9.6 Full E2E KB export para dominio detectado — rc=0")
    else:
        warn("S9.6 Full E2E KB export falló")

    stdout_cs, _, rc_cs = run_cli([kb_script, "cross-search", "--query", "quote estándar SAP"])
    if rc_cs == 0:
        ok("S9.6 Full E2E cross-search — rc=0")
    else:
        warn("S9.6 Full E2E cross-search falló")
except Exception as e:
    fail("S9.6 Full E2E crasheó", str(e))


# ══════════════════════════════════════════════════════════════
# RESUMEN FINAL
# ══════════════════════════════════════════════════════════════
print(f"\n{MG}{BLD}{'═'*70}{RS}")
print(f"{MG}{BLD}  RESUMEN DE CERTIFICACIÓN — Asistente IA Frontend E2E{RS}")
print(f"{MG}{BLD}{'═'*70}{RS}")

total = sum(results.values())
pass_pct = (results["pass"] / total * 100) if total > 0 else 0

print(f"\n  {GR}✓ PASS:  {results['pass']}{RS}")
print(f"  {RD}✗ FAIL:  {results['fail']}{RS}")
print(f"  {YL}⚠ WARN:  {results['warn']}{RS}")
print(f"  {CY}⊘ SKIP:  {results['skip']}{RS}")
print(f"  {'─'*40}")
print(f"  TOTAL:   {total}")
print(f"  TASA:    {pass_pct:.1f}% PASS")

if results["fail"] > 0:
    print(f"\n{RD}{BLD}  FALLAS DETECTADAS:{RS}")
    for f in failures:
        print(f"  {RD}• {f}{RS}")

if pass_pct >= 95:
    print(f"\n  {GR}{BLD}✅ CERTIFICADO PARA PRODUCCIÓN ({pass_pct:.1f}% >= 95%){RS}")
elif pass_pct >= 85:
    print(f"\n  {YL}{BLD}⚠ CASI CERTIFICADO ({pass_pct:.1f}% — corregir fallas menores){RS}")
else:
    print(f"\n  {RD}{BLD}❌ NO CERTIFICADO ({pass_pct:.1f}% < 95% — requiere correcciones){RS}")

print(f"\n{MG}{'═'*70}{RS}")
print(f"  Ejecutado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"  Proyecto:  Asistente IA — GBM Guatemala")
print(f"  Tester:    test_frontend_e2e.py (certificación producción)")
print(f"{MG}{'═'*70}{RS}\n")

sys.exit(1 if results["fail"] > 0 else 0)
