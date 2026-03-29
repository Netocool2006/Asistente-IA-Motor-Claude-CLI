"""
post_action_learn.py — Hook PostToolUse: captura conocimiento de cada accion
=============================================================================
Se dispara AUTOMATICAMENTE despues de cada uso de herramienta (Bash, Edit, Write).
Captura:
  - Comandos ejecutados y si tuvieron exito o fallaron
  - Archivos editados/creados y el contexto
  - Errores encontrados (tracebacks, exit codes != 0)
  - Soluciones aplicadas

Registra en:
  - execution_log.jsonl (todas las acciones)
  - knowledge_base.py (patrones significativos: errores corregidos, soluciones nuevas)
  - learning_memory.py (patrones error->solucion reutilizables)
"""

import sys
import json
import re
from pathlib import Path
from datetime import datetime, timezone

PROJECT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_DIR))

# Directorio para estado temporal entre invocaciones del hook
STATE_DIR           = Path.home() / ".adaptive_cli" / "hook_state"
STATE_FILE          = STATE_DIR / "last_actions.jsonl"
PENDING_ERRORS_FILE = STATE_DIR / "pending_errors.json"
MSG_TYPE_FILE       = STATE_DIR / "msg_type.json"

# Comandos triviales que no vale la pena registrar (solo los mas basicos)
TRIVIAL_PATTERNS = [
    r"^\s*(pwd|which|where)\s*$",  # solo los absolutamente triviales
]

# Patrones que indican error
ERROR_PATTERNS = [
    r"Traceback \(most recent call last\)",
    r"Error:|ERROR:|error:|Exception:|FAILED",
    r"ModuleNotFoundError|ImportError|FileNotFoundError",
    r"SyntaxError|IndentationError|TypeError|ValueError",
    r"Permission denied|Access denied",
    r"command not found|not recognized",
    r"exit code [1-9]",
    r"ENOENT|EACCES|ECONNREFUSED",
]

# Patrones que indican exito
SUCCESS_PATTERNS = [
    r"OK|ok|registrad|completado|creado|guardado|actualizado",
    r"successfully|exitosa|correcto|listo",
    r"\d+ (?:files?|archivos?|entradas?|patterns?|facts?)",
    r"Running on http://",
    r"exit code 0",
]


def _ensure_dirs():
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def _is_trivial(command):
    """Determina si un comando es trivial y no vale la pena registrar."""
    if not command:
        return True
    for pattern in TRIVIAL_PATTERNS:
        if re.match(pattern, command.strip(), re.IGNORECASE):
            return True
    return len(command.strip()) < 5


def _detect_errors(output):
    """Detecta patrones de error en el output."""
    errors = []
    for pattern in ERROR_PATTERNS:
        matches = re.findall(pattern, str(output), re.IGNORECASE)
        if matches:
            errors.extend(matches[:3])
    return errors


def _detect_success(output):
    """Detecta patrones de exito en el output."""
    for pattern in SUCCESS_PATTERNS:
        if re.search(pattern, str(output), re.IGNORECASE):
            return True
    return False


def _extract_key_info(tool_name, tool_input, tool_output, exit_code):
    """Extrae informacion clave de la accion para registrar."""
    info = {
        "tool": tool_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": exit_code == 0 if exit_code is not None else True,
    }

    if tool_name == "Bash":
        cmd = tool_input.get("command", "")
        info["command"] = cmd[:500]
        info["exit_code"] = exit_code
        info["errors"] = _detect_errors(tool_output)
        info["has_success_indicator"] = _detect_success(tool_output)
        # Extraer el script/programa principal
        parts = cmd.strip().split()
        if parts:
            info["program"] = parts[0]
            if "python" in parts[0].lower() and len(parts) > 1:
                info["script"] = parts[1]

    elif tool_name in ("Edit", "Write"):
        info["file"] = tool_input.get("file_path", "")
        info["success"] = "error" not in str(tool_output).lower()
        if tool_name == "Edit":
            old = tool_input.get("old_string", "")
            new = tool_input.get("new_string", "")
            info["change_summary"] = f"Replaced {len(old)} chars with {len(new)} chars"
            info["old_preview"] = old[:100]
            info["new_preview"] = new[:100]
        elif tool_name == "Write":
            info["change_summary"] = f"Created/overwrote file ({len(tool_input.get('content', ''))} chars)"

    elif tool_name == "Read":
        info["file"] = tool_input.get("file_path", "")
        info["success"] = True

    elif tool_name in ("Grep", "Glob"):
        info["pattern"] = tool_input.get("pattern", "")
        info["path"] = tool_input.get("path", "")
        info["results_preview"] = str(tool_output)[:200]
        info["success"] = True

    else:
        # Cualquier otra herramienta (MCP, Agent, etc.)
        info["input_preview"] = str(tool_input)[:200]
        info["output_preview"] = str(tool_output)[:200]

    return info


def _save_action(action_info):
    """Guarda la accion en el log de estado del hook."""
    _ensure_dirs()
    with open(STATE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(action_info, ensure_ascii=False) + "\n")


def _save_pending_error(error_info):
    """Guarda un error pendiente para correlacionar con su fix posterior."""
    _ensure_dirs()
    pending = []
    if PENDING_ERRORS_FILE.exists():
        try:
            with open(PENDING_ERRORS_FILE, "r", encoding="utf-8") as f:
                pending = json.load(f)
        except (json.JSONDecodeError, Exception):
            pending = []

    pending.append(error_info)
    # Mantener solo los ultimos 10 errores pendientes
    pending = pending[-10:]

    with open(PENDING_ERRORS_FILE, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)


def _check_error_resolution(action_info):
    """
    Verifica si esta accion exitosa resuelve un error pendiente.
    Si es asi, registra el patron error->solucion en Learning Memory.
    """
    # Edit/Write exitosos son su propio indicador de éxito (no tienen has_success_indicator)
    tool = action_info.get("tool", "")
    is_edit_write_success = tool in ("Edit", "Write") and action_info.get("success")
    if not action_info.get("success") or not (action_info.get("has_success_indicator") or is_edit_write_success):
        return

    if not PENDING_ERRORS_FILE.exists():
        return

    try:
        with open(PENDING_ERRORS_FILE, "r", encoding="utf-8") as f:
            pending = json.load(f)
    except (json.JSONDecodeError, Exception):
        return

    if not pending:
        return

    # Tomar el error mas reciente como el que se acaba de resolver
    last_error = pending[-1]
    error_age_check = last_error.get("timestamp", "")

    # Solo correlacionar si el error es reciente (menos de 10 min)
    try:
        error_time = datetime.fromisoformat(error_age_check)
        now = datetime.now(timezone.utc)
        if (now - error_time).total_seconds() > 600:
            return
    except (ValueError, TypeError):
        return

    # Registrar patron error->solucion
    try:
        from learning_memory import register_pattern

        error_cmd = last_error.get("command", "unknown")[:100]
        fix_cmd = action_info.get("command", "unknown")[:200]
        error_msgs = last_error.get("errors", [])

        context_key = f"fix_{hash(error_cmd) % 100000}"
        register_pattern(
            task_type="auto_error_fix",
            context_key=context_key,
            solution={
                "strategy": "auto_captured_fix",
                "error_command": error_cmd,
                "error_messages": error_msgs[:3],
                "fix_command": fix_cmd,
                "notes": f"Error en: {error_cmd[:80]}. Fix: {fix_cmd[:80]}",
                "auto_learned": True,
            },
            tags=["auto_learned", "error_fix", action_info.get("program", "unknown")],
            error_context={
                "original_errors": error_msgs,
                "original_command": error_cmd,
            },
        )

        # Limpiar el error pendiente resuelto
        pending.pop()
        with open(PENDING_ERRORS_FILE, "w", encoding="utf-8") as f:
            json.dump(pending, f, ensure_ascii=False, indent=2)

    except Exception:
        pass  # No bloquear si falla el registro


def _register_significant_action(action_info):
    """
    Registra acciones significativas en la KB.
    Solo registra: ediciones a archivos clave, ejecuciones de scripts del proyecto,
    comandos con errores significativos.
    """
    tool = action_info.get("tool", "")

    # Registrar ediciones a archivos del proyecto
    if tool in ("Edit", "Write"):
        file_path = action_info.get("file", "")
        key_files = ["dashboard.py", "index.html", "brand_mirror.py",
                     "knowledge_base.py", "learning_memory.py", "ingest_documents.py",
                     "settings.json"]
        if any(kf in file_path for kf in key_files):
            try:
                from knowledge_base import _append_log
                _append_log({
                    "event": "file_modified",
                    "file": file_path,
                    "change": action_info.get("change_summary", ""),
                    "success": action_info.get("success", True),
                })
            except Exception:
                pass

    # Registrar ejecuciones de scripts Python del proyecto
    if tool == "Bash" and action_info.get("script"):
        script = action_info["script"]
        project_scripts = ["dashboard.py", "knowledge_base.py", "learning_memory.py",
                          "ingest_documents.py", "brand_mirror.py", "seed_gbm_knowledge.py",
                          "seed_sap_patterns.py"]
        if any(ps in script for ps in project_scripts):
            try:
                from knowledge_base import _append_log
                _append_log({
                    "event": "script_executed",
                    "script": script,
                    "success": action_info.get("success", False),
                    "exit_code": action_info.get("exit_code"),
                    "errors": action_info.get("errors", [])[:3],
                })
            except Exception:
                pass


def _read_msg_type() -> dict:
    """Lee el tipo del ultimo mensaje del usuario."""
    try:
        if MSG_TYPE_FILE.exists():
            return json.loads(MSG_TYPE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {"type": "instruction", "has_kb": False}


def main():
    try:
        input_data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, Exception):
        sys.exit(0)

    tool_name   = input_data.get("tool_name", "")
    tool_input  = input_data.get("tool_input", {})
    tool_output = str(input_data.get("tool_result", input_data.get("tool_output", "")))
    exit_code   = input_data.get("exit_code")

    # Leer tipo de mensaje para decidir nivel de grabacion
    msg_ctx  = _read_msg_type()
    msg_type = msg_ctx.get("type", "instruction")
    had_kb   = msg_ctx.get("has_kb", False)

    is_modifying_tool = tool_name in ("Edit", "Write", "Bash")
    should_record = (
        msg_type in ("instruction", "informing")
        or is_modifying_tool
        or (msg_type == "informational" and not had_kb)
    )

    if not should_record:
        sys.exit(0)

    # Solo ignorar los absolutamente triviales
    if tool_name == "Bash" and _is_trivial(tool_input.get("command", "")):
        sys.exit(0)

    # Extraer informacion clave
    action_info = _extract_key_info(tool_name, tool_input, tool_output, exit_code)

    # Guardar accion en log local
    _save_action(action_info)

    # Si hubo error, guardar como pendiente de resolucion
    if action_info.get("errors") and not action_info.get("success", True):
        _save_pending_error(action_info)

    # Si fue exitoso, verificar si resuelve un error pendiente
    # Edit/Write exitosos son su propio indicador (no tienen has_success_indicator)
    _tool = action_info.get("tool", "")
    _is_success = action_info.get("success") and (
        action_info.get("has_success_indicator") or _tool in ("Edit", "Write")
    )
    if _is_success:
        _check_error_resolution(action_info)

    # Registrar acciones significativas en KB
    _register_significant_action(action_info)

    # Exit 0 = no bloquear nada
    sys.exit(0)


if __name__ == "__main__":
    main()
