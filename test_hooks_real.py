"""
test_hooks_real.py — Verifica que los hooks disparen en una sesion real de Claude CLI
"""
import subprocess
import os
import json
import time
from pathlib import Path

PROJECT_DIR = Path("C:/Chance1/Asistente IA")
DATA_DIR    = Path("C:/Users/ntoledo/AppData/Local/ClaudeCode/.adaptive_cli")
NOTIFY_FILE = DATA_DIR / "last_learning.txt"
HISTORY_FILE = DATA_DIR / "session_history.json"
HOOK_STATE   = DATA_DIR / "hook_state" / "learning_state.json"

PASS = []
FAIL = []

def check(name, condition, detail=""):
    if condition:
        print(f"  PASS  {name}")
        PASS.append(name)
    else:
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))
        FAIL.append(name)

def call_claude(prompt: str, timeout: int = 150) -> dict:
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    safe = prompt.replace("'", "''").replace('\n', ' ')
    # Redirigir a archivo para evitar pipe-deadlock por subprocesos hijos de hooks
    out_file = PROJECT_DIR / "_claude_out.txt"
    err_file = PROJECT_DIR / "_claude_err.txt"
    cmd = (
        f"& 'c:\\chance1\\claude-fix.ps1' -p '{safe}' --output-format json"
        f" 2>'{err_file}' | Out-File -FilePath '{out_file}' -Encoding utf8"
    )
    rc = subprocess.call(
        ["powershell", "-NoProfile", "-Command", cmd],
        timeout=timeout, cwd=str(PROJECT_DIR), env=env,
    )
    try:
        stdout = out_file.read_text(encoding="utf-8-sig").strip()
    except Exception:
        stdout = ""
    try:
        stderr = err_file.read_text(encoding="utf-8").strip()
    except Exception:
        stderr = ""
    try:
        data = json.loads(stdout)
    except Exception:
        data = {"result": stdout, "raw_stderr": stderr[:500]}
    data["_rc"]     = rc
    data["_stderr"] = stderr[:300] if stderr else ""
    return data

# ─── capturar estado ANTES ───────────────────────────────────────────
notify_mtime_before  = NOTIFY_FILE.stat().st_mtime  if NOTIFY_FILE.exists()  else 0
notify_lines_before  = len(NOTIFY_FILE.read_text(encoding="utf-8").strip().split("\n")) if NOTIFY_FILE.exists() else 0
history_mtime_before = HISTORY_FILE.stat().st_mtime if HISTORY_FILE.exists() else 0
state_mtime_before   = HOOK_STATE.stat().st_mtime   if HOOK_STATE.exists()   else 0

print("=" * 60)
print("  TEST HOOKS — prueba con sesion real de Claude CLI")
print("=" * 60)
print()

# ─── T1: UserPromptSubmit hook — on_user_message inyecta contexto ───
print("[T1] UserPromptSubmit: on_user_message inyecta contexto KB")
r1 = call_claude("que es un SOW y como se estructura segun la KB local?")
response_text = r1.get("result", "") or str(r1)
has_kb_context = any(kw in response_text.lower() for kw in [
    "sow", "kb", "portada", "estructura", "gbm", "carta", "propuesta"
])
check("T1.1 Claude respondio (rc=0)", r1["_rc"] == 0, f"rc={r1['_rc']} stderr={r1['_stderr'][:100]}")
check("T1.2 Respuesta contiene contenido KB/SOW", has_kb_context, response_text[:200])

# ─── T2: PostToolUse hook — iteration_learn registra acciones ────────
print()
print("[T2] PostToolUse: iteration_learn actualiza last_learning.txt")
time.sleep(3)
notify_mtime_after  = NOTIFY_FILE.stat().st_mtime  if NOTIFY_FILE.exists() else 0
notify_lines_after  = len(NOTIFY_FILE.read_text(encoding="utf-8").strip().split("\n")) if NOTIFY_FILE.exists() else 0

# La segunda llamada crea una nueva sesion → gap grande → flush iteracion anterior
print("  (segunda llamada para forzar flush de iteracion...)")
r2 = call_claude("muestra el conteo de entradas en la knowledge base con python knowledge_base.py stats")
time.sleep(5)

notify_mtime_after2 = NOTIFY_FILE.stat().st_mtime if NOTIFY_FILE.exists() else 0
notify_lines_after2 = len(NOTIFY_FILE.read_text(encoding="utf-8").strip().split("\n")) if NOTIFY_FILE.exists() else 0

check("T2.1 last_learning.txt fue modificado", notify_mtime_after2 > notify_mtime_before,
      f"mtime: {notify_mtime_before} -> {notify_mtime_after2}")
check("T2.2 Se agregaron lineas al log", notify_lines_after2 > notify_lines_before,
      f"lineas: {notify_lines_before} -> {notify_lines_after2}")

if NOTIFY_FILE.exists():
    last_line = NOTIFY_FILE.read_text(encoding="utf-8").strip().split("\n")[-1]
    print(f"  ultima linea: {last_line}")
    check("T2.3 Formato correcto (GUARDADO/DEDUP-SKIP iter N)",
          "iter" in last_line and ("GUARDADO" in last_line or "DEDUP" in last_line),
          last_line)

# ─── T3: Stop hook — auto_learn_hook captura sesion ────────────────
print()
print("[T3] Stop hook: auto_learn_hook guarda sesion en session_history")
time.sleep(5)
history_mtime_after = HISTORY_FILE.stat().st_mtime if HISTORY_FILE.exists() else 0
check("T3.1 session_history.json fue modificado", history_mtime_after > history_mtime_before,
      f"mtime: {history_mtime_before} -> {history_mtime_after}")

if HISTORY_FILE.exists():
    try:
        h = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        sessions = h if isinstance(h, list) else h.get("sessions", [])
        check("T3.2 Hay al menos 1 sesion guardada", len(sessions) >= 1,
              f"count={len(sessions)}")
        if sessions:
            last_s = sessions[-1]
            check("T3.3 Ultima sesion tiene campo 'summary'", "summary" in last_s or "resumen" in last_s,
                  str(last_s)[:150])
    except Exception as e:
        check("T3.2 session_history.json parseable", False, str(e))

# ─── T4: Notificacion "Experiencia ganada xN" ──────────────────────
print()
print("[T4] Notificacion 'Experiencia ganada xN' visible para Claude")
# El hook escribe en stdout del PostToolUse → Claude lo recibe como contexto
# Verificamos que el archivo de learning fue escrito (precondicion)
check("T4.1 last_learning.txt existe con contenido",
      NOTIFY_FILE.exists() and NOTIFY_FILE.stat().st_size > 0)

# Verificar que Claude lee la notificacion (CLAUDE.md lo instruye)
r3 = call_claude("ejecuta: tail -1 ~/.adaptive_cli/last_learning.txt y reporta el resultado exacto")
r3_text = r3.get("result", "")
check("T4.2 Claude puede leer last_learning.txt",
      "iter" in r3_text.lower() or "guardado" in r3_text.lower() or "GUARDADO" in r3_text or "CMD" in r3_text,
      r3_text[:200])

# ─── T5: UserPromptSubmit session_start_kb inyecta historial ────────
print()
print("[T5] session_start_kb inyecta contexto de sesiones previas")
r4 = call_claude("que se hizo en la ultima sesion de trabajo?")
r4_text = r4.get("result", "")
check("T5.1 Claude responde sobre sesion anterior", len(r4_text) > 50, r4_text[:150])
has_session_context = any(kw in r4_text.lower() for kw in [
    "sesion", "session", "anterior", "ultima", "historial", "trabajo", "kb", "hook"
])
check("T5.2 Respuesta incluye contexto de sesion previa", has_session_context, r4_text[:200])

# ─── RESUMEN ────────────────────────────────────────────────────────
print()
print("=" * 60)
total = len(PASS) + len(FAIL)
print(f"  RESULTADO: {len(PASS)}/{total} PASS")
if FAIL:
    print(f"  FALLOS: {', '.join(FAIL)}")
print("=" * 60)

exit(0 if not FAIL else 1)
