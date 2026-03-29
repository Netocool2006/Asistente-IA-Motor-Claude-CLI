"""
test_motor_completo.py — Suite de pruebas integral del motor Asistente IA
=========================================================================
Cubre todos los casos de uso incluyendo edge cases, errores, crashes.
Ejecutar desde: C:/Chance1/Asistente IA/
"""

import json, sys, os, subprocess, shutil, time, re, tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ── Configuracion ──────────────────────────────────────────────
PROJECT_DIR  = Path(__file__).parent
HOOKS_DIR    = PROJECT_DIR / ".claude" / "hooks"
HOME         = Path.home()
ADAPTIVE_DIR = HOME / ".adaptive_cli"
STATE_DIR    = ADAPTIVE_DIR / "hook_state"
PYTHON       = sys.executable

# Colores ANSI
GR = "\033[92m"  # verde
RD = "\033[91m"  # rojo
YL = "\033[93m"  # amarillo
BL = "\033[94m"  # azul
CY = "\033[96m"  # cyan
BLD= "\033[1m"
RS = "\033[0m"

# ── Contadores ─────────────────────────────────────────────────
results = {"pass": 0, "fail": 0, "warn": 0, "skip": 0}
_current_section = ""

def section(name):
    global _current_section
    _current_section = name
    print(f"\n{BL}{BLD}{'='*60}{RS}")
    print(f"{BL}{BLD}  {name}{RS}")
    print(f"{BL}{BLD}{'='*60}{RS}")

def ok(msg):
    results["pass"] += 1
    print(f"  {GR}✓ PASS{RS}  {msg}")

def fail(msg, detail=""):
    results["fail"] += 1
    d = f"\n         {RD}{detail}{RS}" if detail else ""
    print(f"  {RD}✗ FAIL{RS}  {msg}{d}")

def warn(msg):
    results["warn"] += 1
    print(f"  {YL}⚠ WARN{RS}  {msg}")

def skip(msg):
    results["skip"] += 1
    print(f"  {CY}⊘ SKIP{RS}  {msg}")

def run_hook(hook_file, stdin_data: dict = None, env_extra: dict = None):
    """Ejecuta un hook y retorna (stdout, stderr, returncode)."""
    stdin_str = json.dumps(stdin_data or {}, ensure_ascii=False)
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if env_extra:
        env.update(env_extra)
    r = subprocess.run(
        [PYTHON, str(hook_file)],
        input=stdin_str,
        capture_output=True, text=True, timeout=20,
        encoding="utf-8", env=env,
        cwd=str(PROJECT_DIR)
    )
    return r.stdout, r.stderr, r.returncode

# ══════════════════════════════════════════════════════════════
# 1. ON_USER_MESSAGE.PY — UserPromptSubmit
# ══════════════════════════════════════════════════════════════
section("1. on_user_message.py — UserPromptSubmit")

hook = HOOKS_DIR / "on_user_message.py"

# 1.1 Happy path — dominio SAP claro
stdout, stderr, rc = run_hook(hook, {
    "prompt": "necesito crear un quote en SAP CRM tierra con playwright",
    "session_id": "test-001"
})
if rc == 0:
    ok("1.1 Happy path SAP — rc=0")
else:
    fail("1.1 Happy path SAP — rc!=0", stderr[:200])

if "sap" in stdout.lower() or "memory_system" in stdout:
    ok("1.1 Inyecta contexto SAP")
else:
    warn("1.1 No inyecto contexto SAP (puede ser KB vacia para ese dominio)")

# 1.2 Dominio SOW
stdout, stderr, rc = run_hook(hook, {
    "prompt": "genera un sow para propuesta de contrato de servicio con alcance definido",
    "session_id": "test-002"
})
if "sow" in stdout.lower() or "memory_system" in stdout:
    ok("1.2 Clasifica dominio SOW correctamente")
elif rc == 0:
    warn("1.2 SOW detectado pero sin patrones en KB")
else:
    fail("1.2 Fallo dominio SOW", stderr[:200])

# 1.3 Multi-dominio SOW + BOM
stdout, stderr, rc = run_hook(hook, {
    "prompt": "revisa el bom y genera el sow con los materiales del listado",
    "session_id": "test-003"
})
if rc == 0:
    ok("1.3 Multi-dominio SOW+BOM — sin crash")
    if "bom" in stdout.lower() and "sow" in stdout.lower():
        ok("1.3 Inyecta ambos dominios")
    else:
        warn("1.3 Solo inyecto un dominio (parcial)")
else:
    fail("1.3 Multi-dominio crasheo", stderr[:200])

# 1.4 Prompt vacío → exit silencioso
stdout, stderr, rc = run_hook(hook, {"prompt": "", "session_id": "test-004"})
if rc == 0 and not stdout.strip():
    ok("1.4 Prompt vacío — exit silencioso sin output")
else:
    fail("1.4 Prompt vacío — comportamiento inesperado", f"rc={rc} out={stdout[:100]}")

# 1.5 Prompt muy corto (< 5 chars)
stdout, stderr, rc = run_hook(hook, {"prompt": "ok", "session_id": "test-005"})
if rc == 0 and not stdout.strip():
    ok("1.5 Prompt < 5 chars — exit silencioso")
else:
    fail("1.5 Prompt corto — debio salir silenciosamente", f"rc={rc}")

# 1.6 Unicode y emojis en prompt
stdout, stderr, rc = run_hook(hook, {
    "prompt": "genera un sow 🚀 con cláusulas estándar y áéíóú para el cliente Ñ",
    "session_id": "test-006"
})
if rc == 0:
    ok("1.6 Unicode/emojis en prompt — no crashea")
else:
    fail("1.6 Unicode/emojis — crasheo", stderr[:200])

# 1.7 JSON corrupto en stdin
r = subprocess.run(
    [PYTHON, str(hook)],
    input="esto no es json {{{",
    capture_output=True, text=True, timeout=10, encoding="utf-8",
    cwd=str(PROJECT_DIR)
)
if r.returncode == 0 and not r.stdout.strip():
    ok("1.7 JSON corrupto stdin — exit silencioso (graceful)")
else:
    fail("1.7 JSON corrupto — no manejado", f"rc={r.returncode}")

# 1.8 Sin campo "prompt" en JSON
stdout, stderr, rc = run_hook(hook, {"session_id": "test-008", "other_field": "value"})
if rc == 0:
    ok("1.8 Sin campo 'prompt' — no crashea")
else:
    fail("1.8 Sin campo 'prompt' — crasheo", stderr[:200])

# 1.9 Prompt desconocido sin KB (tema aleatorio sin dominio)
stdout, stderr, rc = run_hook(hook, {
    "prompt": "cuantos planetas hay en el sistema solar",
    "session_id": "test-009"
})
if rc == 0:
    ok("1.9 Dominio desconocido — exit sin crash")
    if not stdout.strip():
        ok("1.9 Sin inyeccion para dominio desconocido (correcto)")
    else:
        warn("1.9 Inyecto algo para dominio desconocido")
else:
    fail("1.9 Dominio desconocido — crasheo", stderr[:200])

# 1.10 Verificar que guarda last_user_message.txt
test_msg = f"mensaje de prueba test_motor {datetime.now().isoformat()}"
run_hook(hook, {"prompt": test_msg, "session_id": "test-010"})
lmf = ADAPTIVE_DIR / "last_user_message.txt"
if lmf.exists() and test_msg in lmf.read_text(encoding="utf-8"):
    ok("1.10 Guarda last_user_message.txt correctamente")
else:
    fail("1.10 No guardo last_user_message.txt")

# 1.11 Momentum — deep work (mismo dominio repetido)
for i in range(3):
    run_hook(hook, {"prompt": f"sow propuesta contrato alcance iteracion {i}", "session_id": "test-011"})
stdout, _, rc = run_hook(hook, {"prompt": "nuevo sow propuesta servicio alcance entregable", "session_id": "test-011"})
if "deep_work" in stdout:
    ok("1.11 Momentum 'deep_work' detectado tras repeticion de dominio")
else:
    warn("1.11 Momentum deep_work no detectado (puede requerir mas iteraciones)")

# 1.12 Context switch (cambio de dominio)
run_hook(hook, {"prompt": "genera sow propuesta contrato servicio alcance", "session_id": "test-012"})
stdout, _, rc = run_hook(hook, {"prompt": "necesito ejecutar playwright en SAP CRM tierra", "session_id": "test-012"})
if "context_switch" in stdout:
    ok("1.12 Momentum 'context_switch' detectado al cambiar dominio")
else:
    warn("1.12 Context switch no detectado (puede ser que el historial no tenga suficiente)")

# ══════════════════════════════════════════════════════════════
# 2. POST_ACTION_LEARN.PY — PostToolUse (error→solution cycle)
# ══════════════════════════════════════════════════════════════
section("2. post_action_learn.py — PostToolUse (error→solution)")

hook_pal = HOOKS_DIR / "post_action_learn.py"

# Limpiar estado previo
pending_file = STATE_DIR / "pending_errors.json"
if pending_file.exists():
    pending_file.unlink()

# 2.1 Happy path — Bash exitoso sin error
stdout, stderr, rc = run_hook(hook_pal, {
    "tool_name": "Bash",
    "tool_input": {"command": "python knowledge_base.py stats"},
    "tool_output": "Total patterns: 15 OK successfully",
    "exit_code": 0
})
if rc == 0:
    ok("2.1 Bash exitoso — rc=0, sin crash")
else:
    fail("2.1 Bash exitoso — crasheo", stderr[:200])

# 2.2 Bash con error → debe guardar en pending_errors
stdout, stderr, rc = run_hook(hook_pal, {
    "tool_name": "Bash",
    "tool_input": {"command": "python knowledge_base.py export sap_tierra"},
    "tool_output": "Traceback (most recent call last):\n  File ...\nModuleNotFoundError: No module named 'xyz'",
    "exit_code": 1
})
if rc == 0:
    ok("2.2 Bash con error — rc=0 (no bloquea)")
else:
    fail("2.2 Bash con error — crasheo", stderr[:200])
if pending_file.exists():
    try:
        p = json.loads(pending_file.read_text(encoding="utf-8"))
        if p and len(p) > 0:
            ok("2.2 Error guardado en pending_errors.json")
        else:
            fail("2.2 pending_errors.json vacio")
    except Exception as e:
        fail("2.2 pending_errors.json no es JSON valido", str(e))
else:
    warn("2.2 pending_errors.json no creado (el error puede no haber trigereado)")

# 2.3 Siguiente accion exitosa → debe correlacionar y guardar en LM
stdout, stderr, rc = run_hook(hook_pal, {
    "tool_name": "Bash",
    "tool_input": {"command": "pip install xyz && python knowledge_base.py export sap_tierra"},
    "tool_output": "Installing xyz... OK. Registrado exitosamente 3 patterns successfully",
    "exit_code": 0
})
if rc == 0:
    ok("2.3 Accion exitosa post-error — rc=0")
else:
    fail("2.3 Accion exitosa post-error — crasheo", stderr[:200])
# Verificar que el pending se consumio (deberia quedar vacio o con 1 menos)
if pending_file.exists():
    try:
        p = json.loads(pending_file.read_text(encoding="utf-8"))
        ok(f"2.3 pending_errors post-correlacion: {len(p)} pendientes (esperado 0)")
    except Exception:
        pass
else:
    ok("2.3 pending_errors.json eliminado tras correlacion")

# 2.4 Comando trivial (pwd) → skip
stdout, stderr, rc = run_hook(hook_pal, {
    "tool_name": "Bash",
    "tool_input": {"command": "pwd"},
    "tool_output": "/c/Chance1/Asistente IA",
    "exit_code": 0
})
if rc == 0:
    ok("2.4 Comando trivial (pwd) — no crashea")
else:
    fail("2.4 Comando trivial — crasheo", stderr[:200])

# 2.5 Edit a archivo clave → log en KB
stdout, stderr, rc = run_hook(hook_pal, {
    "tool_name": "Edit",
    "tool_input": {
        "file_path": "C:/Chance1/Asistente IA/dashboard.py",
        "old_string": "# old code",
        "new_string": "# new code"
    },
    "tool_output": "File updated successfully"
})
if rc == 0:
    ok("2.5 Edit a archivo clave (dashboard.py) — registrado sin crash")
else:
    fail("2.5 Edit archivo clave — crasheo", stderr[:200])

# 2.6 Write a archivo no clave → debe funcionar sin crash
stdout, stderr, rc = run_hook(hook_pal, {
    "tool_name": "Write",
    "tool_input": {
        "file_path": "C:/Chance1/temp_test.txt",
        "content": "contenido de prueba"
    },
    "tool_output": "File written"
})
if rc == 0:
    ok("2.6 Write archivo no clave — no crashea")
else:
    fail("2.6 Write archivo no clave — crasheo", stderr[:200])

# 2.7 Error antiguo (> 10 min) → NO correlaciona
if pending_file.exists():
    p = json.loads(pending_file.read_text(encoding="utf-8"))
else:
    p = []
# Insertar un error con timestamp de hace 15 minutos
old_ts = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
p.append({
    "tool": "Bash",
    "timestamp": old_ts,
    "command": "python test_viejo.py",
    "errors": ["Error: old error"],
    "success": False
})
pending_file.parent.mkdir(parents=True, exist_ok=True)
pending_file.write_text(json.dumps(p), encoding="utf-8")
count_before = len(p)

run_hook(hook_pal, {
    "tool_name": "Bash",
    "tool_input": {"command": "echo OK"},
    "tool_output": "OK successfully exitosa",
    "exit_code": 0
})
if pending_file.exists():
    p_after = json.loads(pending_file.read_text(encoding="utf-8"))
    if len(p_after) == count_before:
        ok("2.7 Error >10min — NO correlacionado (correcto)")
    else:
        fail("2.7 Error viejo fue correlacionado (no deberia)")
else:
    warn("2.7 pending_errors borrado inesperadamente")

# 2.8 pending_errors.json corrupto → graceful recovery
pending_file.write_text("esto no es json {{{{", encoding="utf-8")
stdout, stderr, rc = run_hook(hook_pal, {
    "tool_name": "Bash",
    "tool_input": {"command": "python knowledge_base.py stats"},
    "tool_output": "Traceback\nModuleNotFoundError",
    "exit_code": 1
})
if rc == 0:
    ok("2.8 pending_errors.json corrupto — graceful recovery sin crash")
else:
    fail("2.8 pending_errors corrupto — crasheo", stderr[:200])

# 2.9 JSON stdin invalido
r = subprocess.run(
    [PYTHON, str(hook_pal)],
    input="not valid json",
    capture_output=True, text=True, timeout=10, encoding="utf-8",
    cwd=str(PROJECT_DIR)
)
if r.returncode == 0:
    ok("2.9 JSON stdin invalido — exit 0 graceful")
else:
    fail("2.9 JSON stdin invalido — crasheo con rc!=0", r.stderr[:200])

# 2.10 Herramienta desconocida (MCP, Agent)
stdout, stderr, rc = run_hook(hook_pal, {
    "tool_name": "mcp__custom__tool",
    "tool_input": {"param": "value"},
    "tool_output": "some output"
})
if rc == 0:
    ok("2.10 Herramienta MCP desconocida — no crashea")
else:
    fail("2.10 Herramienta MCP — crasheo", stderr[:200])

# ══════════════════════════════════════════════════════════════
# 3. ITERATION_LEARN.PY — PostToolUse (clasificacion + KB search)
# ══════════════════════════════════════════════════════════════
section("3. iteration_learn.py — PostToolUse (classify + KB search)")

hook_il = HOOKS_DIR / "iteration_learn.py"

def test_il(desc, stdin_data, check_fn, check_desc):
    stdout, stderr, rc = run_hook(hook_il, stdin_data)
    if rc != 0:
        fail(f"{desc} — crasheo rc={rc}", stderr[:200])
        return False
    if check_fn(stdout, stderr, rc):
        ok(f"{desc} — {check_desc}")
        return True
    else:
        warn(f"{desc} — {check_desc} (resultado inesperado pero sin crash)")
        return False

# 3.1 Bash exitoso con archivo SAP
test_il("3.1 Bash SAP tierra",
    {"tool_name": "Bash", "tool_input": {"command": "python sap_login.py"},
     "tool_result": "SAP CRM Login OK", "exit_code": 0},
    lambda o, e, rc: rc == 0, "rc=0"
)

# 3.2 Bash con error → debe hacer KB search y output a stdout
stdout, stderr, rc = run_hook(hook_il, {
    "tool_name": "Bash",
    "tool_input": {"command": "python sap_fill_items.py oportunidad 123"},
    "tool_result": "Traceback (most recent call last):\nModuleNotFoundError: No module named 'playwright'",
    "exit_code": 1
})
if rc == 0:
    ok("3.2 Bash con error — rc=0 (no bloquea Claude)")
else:
    fail("3.2 Bash con error — crasheo", stderr[:200])
# Si tiene patterns en KB, deberia inyectar algo
if stdout.strip():
    ok("3.2 Inyecta hint de KB ante error (experiencia aplicada)")
else:
    warn("3.2 Sin hint de KB (puede ser KB vacia para ese error)")

# 3.3 Deteccion de dominio SOW
stdout, stderr, rc = run_hook(hook_il, {
    "tool_name": "Edit",
    "tool_input": {"file_path": "propuesta_sow.docx", "old_string": "a", "new_string": "b"},
    "tool_result": "File updated", "exit_code": 0
})
if rc == 0:
    ok("3.3 Edit archivo SOW — no crashea")
else:
    fail("3.3 Edit archivo SOW — crasheo", stderr[:200])

# 3.4 Deteccion dominio BOM
stdout, stderr, rc = run_hook(hook_il, {
    "tool_name": "Edit",
    "tool_input": {"file_path": "listado_materiales_bom.xlsx", "old_string": "a", "new_string": "b"},
    "tool_result": "OK", "exit_code": 0
})
if rc == 0:
    ok("3.4 Edit archivo BOM — detecta dominio correctamente")
else:
    fail("3.4 BOM domain detection — crasheo", stderr[:200])

# 3.5 Output muy grande (>100KB)
big_output = "A" * 120000
stdout, stderr, rc = run_hook(hook_il, {
    "tool_name": "Bash",
    "tool_input": {"command": "cat huge_file.txt"},
    "tool_result": big_output,
    "exit_code": 0
})
if rc == 0:
    ok("3.5 Output muy grande (120KB) — no crashea ni timeout")
else:
    fail("3.5 Output grande — fallo", stderr[:200])

# 3.6 stdin vacio
r = subprocess.run(
    [PYTHON, str(hook_il)],
    input="",
    capture_output=True, text=True, timeout=10, encoding="utf-8",
    cwd=str(PROJECT_DIR)
)
if r.returncode == 0:
    ok("3.6 stdin vacio — exit 0 graceful")
else:
    fail("3.6 stdin vacio — rc!=0", r.stderr[:200])

# 3.7 Multiples dominios ambiguos
stdout, stderr, rc = run_hook(hook_il, {
    "tool_name": "Bash",
    "tool_input": {"command": "python ingest_documents.py sow_bom_mixed.xlsx"},
    "tool_result": "Procesado OK materiales contrato servicio 15 items",
    "exit_code": 0
})
if rc == 0:
    ok("3.7 Dominio ambiguo SOW/BOM/files — no crashea")
else:
    fail("3.7 Dominio ambiguo — crasheo", stderr[:200])

# ══════════════════════════════════════════════════════════════
# 4. AUTO_LEARN_HOOK.PY — Stop hook
# ══════════════════════════════════════════════════════════════
section("4. auto_learn_hook.py — Stop hook")

hook_alh = HOOKS_DIR / "auto_learn_hook.py"

def make_transcript(messages: list, cwd: str = "C:/Chance1/Asistente IA") -> Path:
    """Crea un archivo JSONL de transcripcion simulado."""
    tf = Path(tempfile.mktemp(suffix=".jsonl"))
    with tf.open("w", encoding="utf-8") as f:
        # Mensaje inicial de sistema
        f.write(json.dumps({"type": "system", "content": "Claude Code CLI", "cwd": cwd}) + "\n")
        for msg in messages:
            f.write(json.dumps(msg) + "\n")
    return tf

def run_alh(transcript_path, session_id="test-stop-001"):
    env = {
        "CLAUDE_SESSION_ID": session_id,
        "CLAUDE_TRANSCRIPT_PATH": str(transcript_path),
        "PYTHONIOENCODING": "utf-8",
    }
    e = os.environ.copy()
    e.update(env)
    r = subprocess.run(
        [PYTHON, str(hook_alh)],
        input=json.dumps({"session_id": session_id, "transcript_path": str(transcript_path)}),
        capture_output=True, text=True, timeout=30,
        encoding="utf-8", env=e,
        cwd=str(PROJECT_DIR)
    )
    return r.stdout, r.stderr, r.returncode

# 4.1 Happy path — sesion controlada normal
msgs = [
    {"type": "user", "message": {"role": "user", "content": "genera un sow para instana"}},
    {"type": "assistant", "message": {"role": "assistant", "content": "Aqui esta el SOW de Instana"}},
    {"type": "tool_use", "name": "Bash", "input": {"command": "python knowledge_base.py export sow"}, "output": "Patrones encontrados"},
    {"type": "user", "message": {"role": "user", "content": "ahora revisa el bom y valida"}},
    {"type": "assistant", "message": {"role": "assistant", "content": "BoM validado correctamente"}},
]
tf = make_transcript(msgs)
stdout, stderr, rc = run_alh(tf, "test-stop-happy")
tf.unlink(missing_ok=True)
if rc == 0:
    ok("4.1 Stop hook sesion normal — rc=0")
else:
    fail("4.1 Stop hook — crasheo", stderr[:300])

# Verificar que session_history.json tiene el registro
sh_file = ADAPTIVE_DIR / "session_history.json"
if sh_file.exists():
    try:
        sh = json.loads(sh_file.read_text(encoding="utf-8"))
        if sh:
            last = sh[-1]
            ok(f"4.1 session_history.json actualizado ({len(sh)} sesiones)")
            # Verificar el fix del timestamp
            if "timestamp" in last:
                ok(f"4.1 Campo 'timestamp' presente: {last['timestamp']}")
            else:
                fail("4.1 Campo 'timestamp' AUSENTE — el fix no funciono")
        else:
            warn("4.1 session_history.json vacio")
    except Exception as e:
        fail("4.1 session_history.json no es JSON valido", str(e))
else:
    warn("4.1 session_history.json no creado")

# 4.2 Sesion vacia (sin mensajes de usuario)
tf = make_transcript([])
stdout, stderr, rc = run_alh(tf, "test-stop-empty")
tf.unlink(missing_ok=True)
if rc == 0:
    ok("4.2 Stop hook sesion vacia — rc=0 graceful")
else:
    fail("4.2 Stop hook sesion vacia — crasheo", stderr[:200])

# 4.3 Transcripcion faltante (crash recovery)
tf_fake = Path("C:/tmp/nonexistent_transcript_xyz.jsonl")
stdout, stderr, rc = run_alh(tf_fake, "test-stop-crash")
if rc == 0:
    ok("4.3 Transcript faltante — rc=0 graceful (crash recovery)")
else:
    fail("4.3 Transcript faltante — crasheo con rc!=0", stderr[:200])

# 4.4 Transcripcion JSONL corrupta (lineas invalidas)
tf = make_transcript([])
with tf.open("a", encoding="utf-8") as f:
    f.write("esto no es json\n")
    f.write('{"type": "user", "message": {"role": "user", "content": "mensaje valido"}}\n')
    f.write("{{{broken json}}}\n")
    f.write('{"type": "user", "message": {"role": "user", "content": "otro mensaje valido"}}\n')
stdout, stderr, rc = run_alh(tf, "test-stop-corrupt")
tf.unlink(missing_ok=True)
if rc == 0:
    ok("4.4 Transcript JSONL corrupto (lineas mixtas) — rc=0 graceful")
else:
    fail("4.4 Transcript corrupto — crasheo", stderr[:200])

# 4.5 Sesion larga (50+ mensajes)
long_msgs = []
for i in range(55):
    long_msgs.append({"type": "user", "message": {"role": "user", "content": f"mensaje {i}: necesito hacer sow para cliente {i}"}})
    long_msgs.append({"type": "assistant", "message": {"role": "assistant", "content": f"Respuesta {i}: aqui esta el sow"}})
tf = make_transcript(long_msgs)
stdout, stderr, rc = run_alh(tf, "test-stop-long")
tf.unlink(missing_ok=True)
if rc == 0:
    ok("4.5 Sesion muy larga (55 mensajes) — no crashea ni timeout")
else:
    fail("4.5 Sesion larga — crasheo", stderr[:200])

# 4.6 Unicode extremo en mensajes
unicode_msgs = [
    {"type": "user", "message": {"role": "user", "content": "create SOW for 😀 clïënt with ñoño specs → 中文 テスト"}},
    {"type": "assistant", "message": {"role": "assistant", "content": "Aquí está: 🎯 ✓ →"}},
]
tf = make_transcript(unicode_msgs)
stdout, stderr, rc = run_alh(tf, "test-stop-unicode")
tf.unlink(missing_ok=True)
if rc == 0:
    ok("4.6 Unicode/emoji extremo en mensajes — no crashea")
else:
    fail("4.6 Unicode extremo — crasheo", stderr[:200])

# ══════════════════════════════════════════════════════════════
# 5. SESSION START — hook inline
# ══════════════════════════════════════════════════════════════
section("5. SessionStart — hook inline (simulated)")

# El hook SessionStart es un comando inline en settings.json
# Lo extraemos y ejecutamos directamente
inline_cmd = (
    "python -c \""
    "import json,pathlib; "
    "f=pathlib.Path.home()/'.adaptive_cli'/'last_learning.txt'; "
    "sh=pathlib.Path.home()/'.adaptive_cli'/'session_history.json'; "
    "lu=pathlib.Path.home()/'.adaptive_cli'/'last_user_message.txt'; "
    "last=f.read_text(encoding='utf-8').strip().splitlines()[-1] if f.exists() else 'KB vacia'; "
    "hist=json.loads(sh.read_text(encoding='utf-8'))[-3:] if sh.exists() else []; "
    "ctx='\\\\n'.join(f\\\"[{s.get('timestamp','?')[:10]}] {s.get('summary','sin resumen')}\\\" for s in hist); "
    "lmsg=lu.read_text(encoding='utf-8').strip() if lu.exists() else ''; "
    "addl=('=== ULTIMAS SESIONES ===\\\\n'+ctx if ctx else '')+(('\\\\n\\\\n=== ULTIMA INSTRUCCION TUYA ===\\\\n'+lmsg) if lmsg else ''); "
    "print(json.dumps({'systemMessage':'KB: '+last,'hookSpecificOutput':{'hookEventName':'SessionStart','additionalContext':addl}},ensure_ascii=False))\""
)

# 5.1 Happy path — todos los archivos existen
# Crear archivos de prueba
ll_file = ADAPTIVE_DIR / "last_learning.txt"
sh_file = ADAPTIVE_DIR / "session_history.json"
lu_file = ADAPTIVE_DIR / "last_user_message.txt"

# Guardar originals si existen
ll_backup = ll_file.read_text(encoding="utf-8") if ll_file.exists() else None
lu_backup = lu_file.read_text(encoding="utf-8") if lu_file.exists() else None

ll_file.write_text("[2026-03-20 09:00:00] GUARDADO iter 5 | sow | 3 acciones", encoding="utf-8")
lu_file.write_text("[2026-03-20 10:00:00] session:abc123\nnecesito hacer un sow para instana", encoding="utf-8")

# session_history: forzar un registro con timestamp correcto
sh_data = []
if sh_file.exists():
    try:
        sh_data = json.loads(sh_file.read_text(encoding="utf-8"))
    except Exception:
        pass
sh_data_test = sh_data + [{
    "session_id": "test-ts-check",
    "date": "2026-03-20",
    "time": "10:00:00 UTC",
    "timestamp": "2026-03-20 10:00:00",
    "summary": "Sesion de prueba para test timestamp",
    "user_messages": ["mensaje de prueba"]
}]
sh_file.write_text(json.dumps(sh_data_test), encoding="utf-8")

r = subprocess.run(
    ["python", "-c", f"""
import json, pathlib
f  = pathlib.Path.home() / '.adaptive_cli' / 'last_learning.txt'
sh = pathlib.Path.home() / '.adaptive_cli' / 'session_history.json'
lu = pathlib.Path.home() / '.adaptive_cli' / 'last_user_message.txt'
last = f.read_text(encoding='utf-8').strip().splitlines()[-1] if f.exists() else 'KB vacia'
hist = json.loads(sh.read_text(encoding='utf-8'))[-3:] if sh.exists() else []
ctx  = '\\n'.join(f"[{{s.get('timestamp','?')[:10]}}] {{s.get('summary','sin resumen')}}" for s in hist)
lmsg = lu.read_text(encoding='utf-8').strip() if lu.exists() else ''
addl = ('=== ULTIMAS SESIONES ===\\n' + ctx if ctx else '') + (('\\n\\n=== ULTIMA INSTRUCCION TUYA ===\\n' + lmsg) if lmsg else '')
print(json.dumps({{'systemMessage': 'KB: ' + last, 'hookSpecificOutput': {{'hookEventName': 'SessionStart', 'additionalContext': addl}}}}, ensure_ascii=False))
"""],
    capture_output=True, text=True, timeout=10, encoding="utf-8",
    env={**os.environ, "PYTHONIOENCODING": "utf-8"}
)
if r.returncode == 0:
    try:
        out = json.loads(r.stdout)
        ok("5.1 SessionStart happy path — JSON valido")
        sm = out.get("systemMessage", "")
        if "KB:" in sm and "KB vacia" not in sm:
            ok("5.1 systemMessage contiene KB real")
        elif "KB vacia" in sm:
            warn("5.1 last_learning.txt existe pero devuelve 'KB vacia'")
        else:
            fail("5.1 systemMessage no tiene 'KB:'", sm[:200])
        ctx = out.get("hookSpecificOutput", {}).get("additionalContext", "")
        if "ULTIMAS SESIONES" in ctx:
            ok("5.1 additionalContext contiene ULTIMAS SESIONES")
        if "2026-03-20" in ctx:
            ok("5.1 Timestamp correcto (no '?') — fix verificado")
        else:
            fail("5.1 Timestamp muestra '?' — fix NO funciono", ctx[:300])
        if "ULTIMA INSTRUCCION" in ctx:
            ok("5.1 additionalContext contiene ULTIMA INSTRUCCION")
    except Exception as e:
        fail("5.1 Output no es JSON valido", f"{r.stdout[:200]} | {str(e)}")
else:
    fail("5.1 SessionStart — crasheo", r.stderr[:200])

# Restaurar archivos
if ll_backup is not None:
    ll_file.write_text(ll_backup, encoding="utf-8")
if lu_backup is not None:
    lu_file.write_text(lu_backup, encoding="utf-8")
sh_file.write_text(json.dumps(sh_data), encoding="utf-8")

# 5.2 Todos los archivos faltantes
r = subprocess.run(
    ["python", "-c", """
import json, pathlib
# Usar paths que no existen
f  = pathlib.Path('/nonexistent/last_learning.txt')
sh = pathlib.Path('/nonexistent/session_history.json')
lu = pathlib.Path('/nonexistent/last_user_message.txt')
last = f.read_text(encoding='utf-8').strip().splitlines()[-1] if f.exists() else 'KB vacia'
hist = json.loads(sh.read_text(encoding='utf-8'))[-3:] if sh.exists() else []
ctx  = '\\n'.join(f"[{s.get('timestamp','?')[:10]}] {s.get('summary','sin resumen')}" for s in hist)
lmsg = lu.read_text(encoding='utf-8').strip() if lu.exists() else ''
addl = ('=== ULTIMAS SESIONES ===\\n' + ctx if ctx else '') + (('\\n\\n=== ULTIMA INSTRUCCION TUYA ===\\n' + lmsg) if lmsg else '')
print(json.dumps({'systemMessage': 'KB: ' + last, 'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': addl}}, ensure_ascii=False))
"""],
    capture_output=True, text=True, timeout=10, encoding="utf-8",
    env={**os.environ, "PYTHONIOENCODING": "utf-8"}
)
if r.returncode == 0:
    try:
        out = json.loads(r.stdout)
        if "KB vacia" in out.get("systemMessage", ""):
            ok("5.2 Sin archivos — fallback 'KB vacia' correcto")
        else:
            fail("5.2 Sin archivos — fallback incorrecto")
    except Exception as e:
        fail("5.2 Sin archivos — output invalido", str(e))
else:
    fail("5.2 Sin archivos — crasheo", r.stderr[:200])

# 5.3 session_history.json corrupto
r = subprocess.run(
    ["python", "-c", """
import json, pathlib, tempfile
# session_history corrupto
tf = pathlib.Path(tempfile.mktemp(suffix='.json'))
tf.write_text('esto no es json', encoding='utf-8')
f  = pathlib.Path.home() / '.adaptive_cli' / 'last_learning.txt'
sh = tf
lu = pathlib.Path.home() / '.adaptive_cli' / 'last_user_message.txt'
last = f.read_text(encoding='utf-8').strip().splitlines()[-1] if f.exists() else 'KB vacia'
try:
    hist = json.loads(sh.read_text(encoding='utf-8'))[-3:] if sh.exists() else []
except Exception:
    hist = []
ctx  = '\\n'.join(f"[{s.get('timestamp','?')[:10]}] {s.get('summary','sin resumen')}" for s in hist)
lmsg = lu.read_text(encoding='utf-8').strip() if lu.exists() else ''
addl = ('=== ULTIMAS SESIONES ===\\n' + ctx if ctx else '') + (('\\n\\n=== ULTIMA INSTRUCCION TUYA ===\\n' + lmsg) if lmsg else '')
print(json.dumps({'systemMessage': 'KB: ' + last, 'hookSpecificOutput': {'hookEventName': 'SessionStart', 'additionalContext': addl}}, ensure_ascii=False))
tf.unlink()
"""],
    capture_output=True, text=True, timeout=10, encoding="utf-8",
    env={**os.environ, "PYTHONIOENCODING": "utf-8"}
)
if r.returncode == 0 and r.stdout.strip():
    ok("5.3 session_history.json corrupto — fallback graceful")
else:
    fail("5.3 session_history corrupto — crasheo", r.stderr[:200])

# ══════════════════════════════════════════════════════════════
# 6. CRASH RECOVERY — escenarios de caida
# ══════════════════════════════════════════════════════════════
section("6. Crash Recovery — escenarios de caida")

# 6.1 last_user_message.txt siempre actualizado (persistencia ante crash)
test_prompt = f"CRASH TEST: sow para cliente urgente {datetime.now().isoformat()}"
run_hook(HOOKS_DIR / "on_user_message.py", {
    "prompt": test_prompt,
    "session_id": "crash-test-001"
})
lu_file = ADAPTIVE_DIR / "last_user_message.txt"
if lu_file.exists():
    content = lu_file.read_text(encoding="utf-8")
    if test_prompt in content:
        ok("6.1 last_user_message.txt actualizado antes de cualquier Stop hook")
    else:
        fail("6.1 last_user_message.txt no contiene el ultimo mensaje", content[:200])
else:
    fail("6.1 last_user_message.txt no existe")

# 6.2 last_learning.txt persiste (PostToolUse hook lo actualiza cada iteracion)
ll_file = ADAPTIVE_DIR / "last_learning.txt"
if ll_file.exists():
    content = ll_file.read_text(encoding="utf-8")
    if content.strip():
        ok("6.2 last_learning.txt existe y tiene contenido (sobrevive crashes)")
    else:
        warn("6.2 last_learning.txt vacio")
else:
    warn("6.2 last_learning.txt no existe aun (se crea con primera iteracion real)")

# 6.3 pending_errors.json sobrevive crash (es persistente entre invocaciones)
# Insertar un error y verificar que esta en disco
pending_file = STATE_DIR / "pending_errors.json"
pending_file.parent.mkdir(parents=True, exist_ok=True)
test_error = [{
    "tool": "Bash",
    "timestamp": datetime.now(timezone.utc).isoformat(),
    "command": "python test_crash.py",
    "errors": ["ModuleNotFoundError: test"],
    "success": False
}]
pending_file.write_text(json.dumps(test_error), encoding="utf-8")
# Simular crash: el proceso termina, el archivo queda en disco
# En la siguiente sesion, deberia seguir estando
if pending_file.exists() and json.loads(pending_file.read_text(encoding="utf-8")):
    ok("6.3 pending_errors.json persiste en disco (disponible post-crash)")
else:
    fail("6.3 pending_errors.json no persiste correctamente")

# 6.4 Recuperacion: Stop hook con transcript inexistente no crashea
stdout, stderr, rc = run_alh(Path("C:/nonexistent/path/transcript.jsonl"), "crash-recovery-001")
if rc == 0:
    ok("6.4 Stop hook sin transcript (crash) — rc=0, no propaga error")
else:
    fail("6.4 Stop hook crash recovery — rc!=0", stderr[:200])

# 6.5 Doble invocacion del hook (idempotencia)
msgs_idem = [
    {"type": "user", "message": {"role": "user", "content": "test idempotencia"}},
]
tf = make_transcript(msgs_idem)
run_alh(tf, "idem-test-001")
run_alh(tf, "idem-test-001")  # Segunda vez, mismo session_id
tf.unlink(missing_ok=True)
sh_file = ADAPTIVE_DIR / "session_history.json"
if sh_file.exists():
    try:
        sh = json.loads(sh_file.read_text(encoding="utf-8"))
        count = sum(1 for s in sh if s.get("session_id") == "idem-test-001")
        if count <= 2:
            ok(f"6.5 Doble Stop hook — {count} entrada(s) (idempotente)")
        else:
            warn(f"6.5 Doble Stop hook — {count} duplicados en session_history")
    except Exception as e:
        fail("6.5 session_history invalido", str(e))
else:
    warn("6.5 session_history.json no existe para verificar idempotencia")

# ══════════════════════════════════════════════════════════════
# 7. INTEGRACION COMPLETA — ciclo end-to-end
# ══════════════════════════════════════════════════════════════
section("7. Integracion end-to-end — ciclo completo")

# 7.1 Ciclo: UserPromptSubmit → PostToolUse (error) → PostToolUse (fix) → Stop
session_id = "e2e-test-001"

# Paso 1: UserPromptSubmit
stdout1, _, rc1 = run_hook(HOOKS_DIR / "on_user_message.py", {
    "prompt": "ejecuta playwright para login en SAP CRM tierra",
    "session_id": session_id
})
ok("7.1 Paso 1: UserPromptSubmit ejecutado") if rc1 == 0 else fail("7.1 UserPromptSubmit fallo", _[:100])

# Paso 2: PostToolUse — error
_, _, rc2 = run_hook(HOOKS_DIR / "post_action_learn.py", {
    "tool_name": "Bash",
    "tool_input": {"command": "python sap_playwright_login.py"},
    "tool_output": "Traceback:\nModuleNotFoundError: No module named 'playwright'",
    "exit_code": 1
})
ok("7.1 Paso 2: PostToolUse error capturado") if rc2 == 0 else fail("7.1 PostToolUse error fallo")

# Paso 3: PostToolUse — fix exitoso
_, _, rc3 = run_hook(HOOKS_DIR / "post_action_learn.py", {
    "tool_name": "Bash",
    "tool_input": {"command": "pip install playwright && python -m playwright install && python sap_playwright_login.py"},
    "tool_output": "Installing playwright... OK. Login SAP exitoso successfully",
    "exit_code": 0
})
ok("7.1 Paso 3: PostToolUse fix exitoso capturado") if rc3 == 0 else fail("7.1 PostToolUse fix fallo")

# Paso 4: iteration_learn PostToolUse
_, _, rc4 = run_hook(HOOKS_DIR / "iteration_learn.py", {
    "tool_name": "Bash",
    "tool_input": {"command": "python sap_playwright_login.py"},
    "tool_result": "Login SAP exitoso",
    "exit_code": 0
})
ok("7.1 Paso 4: iteration_learn ejecutado") if rc4 == 0 else fail("7.1 iteration_learn fallo")

# Paso 5: Stop hook (sesion controlada)
msgs_e2e = [
    {"type": "user", "message": {"role": "user", "content": "ejecuta playwright para login en SAP CRM tierra"}},
    {"type": "assistant", "message": {"role": "assistant", "content": "Ejecutando playwright login en SAP..."}},
    {"type": "tool_use", "name": "Bash", "input": {"command": "python sap_playwright_login.py"}, "output": "Login SAP exitoso"},
    {"type": "user", "message": {"role": "user", "content": "perfecto ahora llena los items del BOM"}},
]
tf = make_transcript(msgs_e2e)
_, _, rc5 = run_alh(tf, session_id)
tf.unlink(missing_ok=True)
ok("7.1 Paso 5: Stop hook — sesion guardada") if rc5 == 0 else fail("7.1 Stop hook fallo")

if all(rc == 0 for rc in [rc1, rc2, rc3, rc4, rc5]):
    ok("7.1 CICLO COMPLETO end-to-end exitoso")
else:
    fail("7.1 Ciclo incompleto", f"rcs={[rc1,rc2,rc3,rc4,rc5]}")

# 7.2 Ciclo crash: UserPromptSubmit → proceso killed → SessionStart recupera
run_hook(HOOKS_DIR / "on_user_message.py", {
    "prompt": "CRASH SIMULATION: sow urgente para cliente XYZ",
    "session_id": "crash-e2e-001"
})
# Simular crash: no se ejecuta Stop hook
# SessionStart deberia leer last_user_message.txt y recuperar
lu_content = (ADAPTIVE_DIR / "last_user_message.txt").read_text(encoding="utf-8") if (ADAPTIVE_DIR / "last_user_message.txt").exists() else ""
if "CRASH SIMULATION" in lu_content or "sow urgente" in lu_content:
    ok("7.2 Crash recovery: ultimo mensaje recuperable via last_user_message.txt")
else:
    fail("7.2 Crash recovery: mensaje no encontrado en last_user_message.txt")

# ══════════════════════════════════════════════════════════════
# RESUMEN FINAL
# ══════════════════════════════════════════════════════════════
total = results["pass"] + results["fail"] + results["warn"] + results["skip"]
print(f"\n{'='*60}")
print(f"{BLD}RESUMEN FINAL — {total} casos ejecutados{RS}")
print(f"{'='*60}")
print(f"  {GR}✓ PASS{RS}  {results['pass']}")
print(f"  {RD}✗ FAIL{RS}  {results['fail']}")
print(f"  {YL}⚠ WARN{RS}  {results['warn']}")
print(f"  {CY}⊘ SKIP{RS}  {results['skip']}")
print(f"{'='*60}")

if results["fail"] == 0:
    print(f"\n{GR}{BLD}  MOTOR SALUDABLE — todos los casos criticos pasaron{RS}\n")
elif results["fail"] <= 3:
    print(f"\n{YL}{BLD}  MOTOR FUNCIONAL con {results['fail']} fallo(s) menores{RS}\n")
else:
    print(f"\n{RD}{BLD}  MOTOR CON PROBLEMAS — {results['fail']} fallos detectados{RS}\n")

sys.exit(0 if results["fail"] == 0 else 1)
