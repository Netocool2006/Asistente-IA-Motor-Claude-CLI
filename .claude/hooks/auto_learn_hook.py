"""
auto_learn_hook.py — Hook Stop: captura sesion completa al terminar Claude
==========================================================================
Se dispara con el evento "Stop" de Claude Code CLI.

RECIBE en stdin JSON con:
  - session_id: identificador de sesion
  - transcript_path: ruta a archivo JSONL con conversacion COMPLETA
  - last_assistant_message: ultimo mensaje de Claude
  - cwd: directorio de trabajo
  - hook_event_name: "Stop"
  - stop_hook_active: bool (evitar loops)

Lo que captura:
  - Resumen DETALLADO de toda la conversacion (del transcript JSONL)
  - Errores encontrados y corregidos
  - Archivos tocados (read, edit, write)
  - Comandos ejecutados y resultados
  - Decisiones tecnicas
  - JSON de aprendizaje explicito (si Claude lo incluyo)

Guarda en: ~/.adaptive_cli/session_history.json (todas las sesiones, sin limite)
"""

import sys
import json
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from _paths import DATA_DIR

# ── File Locking ──────────────────────────────────────────────
LOCK_DIR = DATA_DIR / "locks"


@contextmanager
def file_lock(name: str, timeout: float = 5.0):
    """Lock cross-platform — Windows: msvcrt, Linux/Mac: fcntl."""
    LOCK_DIR.mkdir(parents=True, exist_ok=True)
    lockfile = LOCK_DIR / f"{name}.lock"
    fd = None
    acquired = False
    import sys as _sys

    try:
        fd = open(lockfile, "w")
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            try:
                if _sys.platform == "win32":
                    import msvcrt
                    msvcrt.locking(fd.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except (OSError, IOError):
                time.sleep(0.05)

        yield acquired
    finally:
        if fd:
            try:
                if acquired:
                    if _sys.platform == "win32":
                        import msvcrt
                        msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
            except (OSError, IOError):
                pass
            fd.close()

# Agregar el directorio del proyecto al path
PROJECT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_DIR))

# Archivos
SESSION_HISTORY_FILE  = DATA_DIR / "session_history.json"
CO_OCCUR_FILE         = DATA_DIR / "domain_cooccurrence.json"
MARKOV_FILE           = DATA_DIR / "domain_markov.json"
INJECTION_FILE        = DATA_DIR / "last_injection.json"
HINT_EFFECT_FILE      = DATA_DIR / "hint_effectiveness.json"
DEBUG_LOG             = DATA_DIR / "hook_debug.log"
ITER_ACTIONS_FILE     = DATA_DIR / "iteration_actions.jsonl"
MAX_SESSIONS         = None  # Sin limite — el disco es el unico limite

try:
    from knowledge_base import add_pattern, add_fact, _load_all_domains
    DOMAINS = _load_all_domains()
except ImportError:
    DOMAINS = {}


# ══════════════════════════════════════════════════════════════
#  LECTURA DEL TRANSCRIPT JSONL
# ══════════════════════════════════════════════════════════════

def read_transcript(transcript_path: str) -> list:
    """
    Lee el archivo JSONL del transcript completo.
    El formato real de Claude Code es:
      {"type": "user", "message": {"role": "user", "content": ...}}
      {"type": "assistant", "message": {"role": "assistant", "content": [...]}}
    Desanidamos obj["message"] para que el resto de funciones
    puedan usar msg.get("role") y msg.get("content") directamente.
    """
    messages = []
    path = Path(transcript_path)
    if not path.exists():
        return messages

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    # La estructura real tiene los mensajes anidados en obj["message"]
                    if "message" in obj and isinstance(obj["message"], dict):
                        inner = obj["message"]
                        if "role" in inner and "content" in inner:
                            messages.append(inner)
                    # Fallback: si ya tiene role/content en raiz (formato viejo)
                    elif "role" in obj and "content" in obj:
                        messages.append(obj)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass

    return messages


def extract_text_from_messages(messages: list) -> str:
    """Extrae todo el texto legible de los mensajes del transcript."""
    parts = []
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        # content puede ser string o lista de bloques
        if isinstance(content, str):
            parts.append(f"[{role}] {content}")
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(f"[{role}] {block.get('text', '')}")
                    elif block.get("type") == "tool_use":
                        tool = block.get("name", "?")
                        tool_input = json.dumps(block.get("input", {}), ensure_ascii=False)[:300]
                        parts.append(f"[{role}/tool:{tool}] {tool_input}")
                    elif block.get("type") == "tool_result":
                        result_text = str(block.get("content", ""))[:500]
                        parts.append(f"[tool_result] {result_text}")
                elif isinstance(block, str):
                    parts.append(f"[{role}] {block}")

    return "\n".join(parts)


# ══════════════════════════════════════════════════════════════
#  EXTRACCION DE INFORMACION
# ══════════════════════════════════════════════════════════════

def extract_user_messages(messages: list) -> list:
    """Extrae los mensajes del usuario (lo que pidio). Filtra notificaciones del sistema."""
    user_msgs = []
    # Prefijos de mensajes automáticos del sistema (no del usuario real)
    system_prefixes = ("<task-notification", "<system-reminder", "<available-deferred-tools")

    for msg in messages:
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str) and len(content.strip()) > 3:
                text = content.strip()
                if not any(text.startswith(p) for p in system_prefixes):
                    user_msgs.append(text[:500])
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text = block.get("text", "").strip()
                        if len(text) > 3 and not any(text.startswith(p) for p in system_prefixes):
                            user_msgs.append(text[:500])
    return user_msgs


def extract_tool_usage(messages: list) -> dict:
    """Extrae uso de herramientas: archivos leidos, editados, creados, comandos."""
    tools = {
        "files_read": [],
        "files_edited": [],
        "files_created": [],
        "commands_run": [],
        "searches": [],
    }
    # Sets separados por categoría (un archivo puede ser leído Y editado)
    seen_read = set()
    seen_edit = set()
    seen_write = set()
    seen_cmds = set()

    for msg in messages:
        content = msg.get("content", "")
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue

            tool_name = block.get("name", "")
            tool_input = block.get("input", {})

            if tool_name == "Read":
                fp = tool_input.get("file_path", "")
                if fp and fp not in seen_read:
                    seen_read.add(fp)
                    tools["files_read"].append(fp)

            elif tool_name == "Edit":
                fp = tool_input.get("file_path", "")
                if fp and fp not in seen_edit:
                    seen_edit.add(fp)
                    tools["files_edited"].append(fp)

            elif tool_name == "Write":
                fp = tool_input.get("file_path", "")
                if fp and fp not in seen_write:
                    seen_write.add(fp)
                    tools["files_created"].append(fp)

            elif tool_name == "Bash":
                cmd = tool_input.get("command", "")
                if cmd and cmd not in seen_cmds:
                    seen_cmds.add(cmd)
                    tools["commands_run"].append(cmd[:300])

            elif tool_name in ("Grep", "Glob"):
                pattern = tool_input.get("pattern", "")
                if pattern:
                    tools["searches"].append(f"{tool_name}: {pattern}")

    return tools


def extract_tool_usage_from_iter_actions(session_id: str) -> dict:
    """
    Fallback: lee iteration_actions.jsonl (escrito por PostToolUse en tiempo real)
    y extrae tool usage para el session_id dado.
    Esto resuelve el timing bug donde el transcript no tiene tool_use blocks
    al momento en que el Stop hook dispara (sesiones cortas).
    """
    tools = {
        "files_read": [],
        "files_edited": [],
        "files_created": [],
        "commands_run": [],
        "searches": [],
    }
    if not ITER_ACTIONS_FILE.exists() or not session_id:
        return tools

    seen_read  = set()
    seen_edit  = set()
    seen_write = set()
    seen_cmds  = set()

    try:
        with open(ITER_ACTIONS_FILE, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    a = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not a.get("_sid", "").startswith(session_id[:8]):
                    continue

                tool = a.get("tool", "")
                fp   = a.get("file", "")
                cmd  = a.get("action", "")

                if tool == "Read" and fp:
                    if fp not in seen_read:
                        seen_read.add(fp)
                        tools["files_read"].append(fp)
                elif tool == "Edit" and fp:
                    if fp not in seen_edit:
                        seen_edit.add(fp)
                        tools["files_edited"].append(fp)
                elif tool == "Write" and fp:
                    if fp not in seen_write:
                        seen_write.add(fp)
                        tools["files_created"].append(fp)
                elif tool == "Bash" and cmd:
                    short_cmd = cmd[:300]
                    if short_cmd not in seen_cmds:
                        seen_cmds.add(short_cmd)
                        tools["commands_run"].append(short_cmd)
                elif tool in ("Grep", "Glob") and cmd:
                    tools["searches"].append(cmd[:150])
    except Exception as e:
        pass  # No bloquear si falla

    return tools


def merge_tool_usage(from_transcript: dict, from_iter: dict) -> dict:
    """Fusiona tool usage del transcript con el del iter_actions (sin duplicados)."""
    merged = {
        "files_read":    list(dict.fromkeys(from_transcript["files_read"]    + from_iter["files_read"])),
        "files_edited":  list(dict.fromkeys(from_transcript["files_edited"]  + from_iter["files_edited"])),
        "files_created": list(dict.fromkeys(from_transcript["files_created"] + from_iter["files_created"])),
        "commands_run":  list(dict.fromkeys(from_transcript["commands_run"]  + from_iter["commands_run"])),
        "searches":      list(dict.fromkeys(from_transcript["searches"]      + from_iter["searches"])),
    }
    return merged


def extract_errors_from_messages(messages: list) -> list:
    """
    Extrae errores RELEVANTES del proyecto (no errores triviales de herramientas).
    Filtra: tabs no found, task not found, EOF bash, y otros errores de infra.
    """
    errors = []
    # Errores triviales que no aportan contexto
    TRIVIAL_PATTERNS = [
        "no longer exists",           # tab cerrado
        "No tab available",           # browser sin tab
        "No task found",              # task ID viejo
        "unexpected EOF",             # bash syntax
        "command not found",          # herramienta no instalada
        "charmap_encode",             # cp1252 encoding consola Windows
        "tool_use_error",             # error genérico de tool
        "Permission denied",          # permisos (se reintenta)
    ]

    for msg in messages:
        content = msg.get("content", "")
        if not isinstance(content, list):
            continue

        for block in content:
            if not isinstance(block, dict):
                continue

            # Tool results con errores (filtrar triviales)
            if block.get("type") == "tool_result" and block.get("is_error"):
                error_text = str(block.get("content", ""))[:400]
                if any(trivial in error_text for trivial in TRIVIAL_PATTERNS):
                    continue
                errors.append({"type": "tool_error", "detail": error_text})

            # Buscar en texto de respuestas — solo errores del proyecto
            if block.get("type") == "text":
                text = block.get("text", "")
                for match in re.findall(
                    r'(?:Error|Traceback|Failed|FAILED)[\s:]+(.{20,300})', text
                ):
                    detail = match.strip()[:300]
                    if any(trivial in detail for trivial in TRIVIAL_PATTERNS):
                        continue
                    errors.append({"type": "error_in_response", "detail": detail})

    return errors[:10]


def extract_learning_json_from_messages(messages: list) -> dict:
    """Busca JSON de aprendizaje en los mensajes de Claude."""
    for msg in reversed(messages):
        if msg.get("role") != "assistant":
            continue

        content = msg.get("content", "")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = " ".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )

        # Buscar JSON de aprendizaje
        patterns = [
            r'```json\s*(\{[^`]*?"status"[^`]*?\})\s*```',
            r'(\{[^{}]*"status"\s*:\s*"(?:success|modified|partial|failed)"[^{}]*\})',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    data = json.loads(match)
                    if "status" in data:
                        return data
                except json.JSONDecodeError:
                    continue

    return None


def extract_decisions_from_messages(messages: list) -> list:
    """Extrae decisiones tecnicas de las respuestas de Claude."""
    decisions = []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue

        content = msg.get("content", "")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = " ".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )

        # Buscar frases de decision
        for match in re.findall(
            r'(?:voy a|decid[ií]|el fix es|la soluci[oó]n es|the fix is|going to|la estrategia es|'
            r'propon[go]|recomiendo|mejor opci[oó]n|hay que|deber[ií]amos)\s+(.{10,200})',
            text, re.IGNORECASE
        ):
            if match.strip() not in decisions:
                decisions.append(match.strip()[:200])

    return decisions[:15]


def build_conversation_summary(user_messages: list) -> str:
    """Construye un resumen de la conversacion basado en los mensajes del usuario."""
    if not user_messages:
        return "Sesion sin mensajes del usuario"

    # Filtrar mensajes del sistema/context compaction
    real_msgs = []
    for msg in user_messages:
        # Saltar context compaction summaries y system messages
        if msg.startswith("This session is being continued"):
            continue
        if msg.startswith("Summary:"):
            continue
        if len(msg) > 400:  # Mensajes muy largos suelen ser dumps del sistema
            msg = msg[:150] + "..."
        clean = msg.replace("\n", " ").strip()[:150]
        if clean:
            real_msgs.append(clean)

    if not real_msgs:
        return "Sesion sin mensajes del usuario"

    return " → ".join(real_msgs[:8])[:600]


# ══════════════════════════════════════════════════════════════
#  SESSION HISTORY
# ══════════════════════════════════════════════════════════════

def load_session_history() -> list:
    SESSION_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with file_lock("session_history"):
        if SESSION_HISTORY_FILE.exists():
            try:
                with open(SESSION_HISTORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
    return []


def save_session_history(history: list):
    SESSION_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Sin corte — se guardan todas las sesiones. Limite = disco.
    with file_lock("session_history"):
        tmp = SESSION_HISTORY_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        tmp.replace(SESSION_HISTORY_FILE)


def _merge_lists(existing: list, new: list) -> list:
    """Merge dos listas sin duplicados, preservando orden."""
    seen = set()
    merged = []
    for item in existing + new:
        # Para dicts (errores), usar el detail como key
        if isinstance(item, dict):
            key = item.get("detail", item.get("type", str(item)))
        else:
            key = str(item)
        if key not in seen:
            seen.add(key)
            merged.append(item)
    return merged


def _merge_sessions(existing: dict, new: dict) -> dict:
    """
    Merge incremental: enriquece un registro existente con datos nuevos.
    - Listas: union sin duplicados
    - Strings: conserva el mas largo/detallado
    - Metrics: toma el maximo de cada campo
    - learning_json: conserva el que tenga datos
    """
    merged = existing.copy()

    # Listas: merge sin duplicados
    list_fields = [
        "user_messages", "files_read", "files_edited", "files_created",
        "commands_run", "searches", "errors", "decisions"
    ]
    for field in list_fields:
        old_list = existing.get(field, [])
        new_list = new.get(field, [])
        if new_list:
            merged[field] = _merge_lists(old_list, new_list)

    # Summary: conservar el mas largo
    old_summary = existing.get("summary", "")
    new_summary = new.get("summary", "")
    if len(new_summary) > len(old_summary):
        merged["summary"] = new_summary

    # learning_json: conservar el que tenga datos
    if new.get("learning_json") and not existing.get("learning_json"):
        merged["learning_json"] = new["learning_json"]

    # Metrics: tomar el maximo
    old_metrics = existing.get("metrics", {})
    new_metrics = new.get("metrics", {})
    merged_metrics = {}
    for key in set(list(old_metrics.keys()) + list(new_metrics.keys())):
        merged_metrics[key] = max(old_metrics.get(key, 0), new_metrics.get(key, 0))
    merged["metrics"] = merged_metrics

    # Marcar que fue mergeado
    merged["merged"] = True
    merged["merge_count"] = existing.get("merge_count", 1) + 1

    return merged


def find_existing_session(history: list, new_record: dict) -> int:
    """
    Busca si ya existe un registro para esta sesion.
    Detecta por: session_id, o misma fecha + overlap en user_messages.
    Retorna el indice en history, o -1 si no existe.
    """
    new_id = new_record.get("session_id", "")
    new_date = new_record.get("date", "")
    new_msgs = set(m[:80] for m in new_record.get("user_messages", []))

    for i, existing in enumerate(history):
        existing_id = existing.get("session_id", "")

        # Match exacto por session_id (ignorando prefijo manual_)
        clean_new = new_id.replace("manual_", "")
        clean_existing = existing_id.replace("manual_", "")
        if clean_new and clean_existing and clean_new == clean_existing:
            return i

        # Match por fecha + overlap de mensajes del usuario (>50% coincidencia)
        if new_date and existing.get("date", "") == new_date and new_msgs:
            existing_msgs = set(m[:80] for m in existing.get("user_messages", []))
            if existing_msgs:
                overlap = len(new_msgs & existing_msgs)
                total = max(len(new_msgs), len(existing_msgs))
                if total > 0 and overlap / total > 0.4:
                    return i

    return -1


def save_or_merge_session(new_record: dict):
    """
    Guarda una sesion. Si ya existe una similar, hace merge incremental.
    Si es nueva, la agrega.
    """
    history = load_session_history()
    idx = find_existing_session(history, new_record)

    if idx >= 0:
        # Merge: enriquecer la existente con datos nuevos
        history[idx] = _merge_sessions(history[idx], new_record)
        debug_log(f"Session merged with existing at index {idx} "
                  f"(merge_count={history[idx].get('merge_count', 1)})")
    else:
        # Nueva sesion
        history.append(new_record)
        debug_log(f"New session added. History now has {len(history)} sessions")

    save_session_history(history)


def debug_log(message: str):
    """Log de debug para diagnosticar problemas con el hook."""
    try:
        DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {message}\n")
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════
#  REGISTRO EN KB
# ══════════════════════════════════════════════════════════════

def register_learning_in_kb(learning: dict):
    """Registra JSON de aprendizaje explícito en la KB."""
    if not DOMAINS:
        return

    domain = learning.get("domain", "business_rules")
    task_type = learning.get("task_type", "auto_learned")

    if domain not in DOMAINS:
        domain = "business_rules"

    key = f"auto_{task_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    solution = {
        "strategy": learning.get("strategy", "auto_captured"),
        "code_snippet": learning.get("code_snippet", "")[:2000],
        "notes": learning.get("notes", ""),
        "auto_learned": True,
        "source": "hook_stop_event",
    }
    tags = learning.get("tags", [task_type, domain, "auto_learned"])

    try:
        add_pattern(domain, key, solution, tags=tags)
        debug_log(f"KB: registered explicit learning {key} in {domain}")
    except Exception as e:
        debug_log(f"KB: failed to register pattern: {e}")


# ══════════════════════════════════════════════════════════════
#  AUTO-LEARNING: extrae aprendizaje del transcript sin JSON explícito
# ══════════════════════════════════════════════════════════════

# Mapeo de archivos/paths a dominios de KB
DOMAIN_HINTS = {
    "sap_": "sap_tierra",
    "sap_playbook": "sap_tierra",
    "sap_actions": "sap_tierra",
    "brand_mirror": "files",
    "dashboard": "files",
    "index.html": "files",
    "knowledge_base": "files",
    "file_search": "files",
    "learning_memory": "files",
    "ingest_": "files",
    "sow": "sow",
    "bom": "bom",
    "monday": "monday",
    "outlook": "outlook",
    "pptx": "pptx",
    "hook": "files",
}


def detect_domain(files_edited: list, files_created: list, user_messages: list) -> str:
    """Detecta el dominio de KB basado en archivos tocados y mensajes del usuario."""
    all_files = files_edited + files_created
    # Contar hits por dominio
    domain_scores = {}
    for f in all_files:
        f_lower = f.lower().replace("\\", "/")
        for hint, domain in DOMAIN_HINTS.items():
            if hint in f_lower:
                domain_scores[domain] = domain_scores.get(domain, 0) + 1

    # También buscar en mensajes del usuario
    all_text = " ".join(user_messages).lower()
    keyword_domains = {
        "sap": "sap_tierra", "oportunidad": "sap_tierra", "quote": "sap_tierra",
        "sow": "sow", "propuesta": "sow",
        "bom": "bom", "listado": "bom",
        "dashboard": "files", "mirror": "files", "brand": "files",
        "monday": "monday", "pipeline": "monday",
        "outlook": "outlook", "correo": "outlook",
    }
    for kw, domain in keyword_domains.items():
        if kw in all_text:
            domain_scores[domain] = domain_scores.get(domain, 0) + 1

    if domain_scores:
        return max(domain_scores, key=domain_scores.get)
    return "files"


def extract_conversation_pairs(messages: list) -> list:
    """
    Extrae pares pregunta-respuesta con el POR QUE de cada accion.
    Formato: [{user: "lo que pidio", assistant_summary: "lo que hice y por que", files: [...]}]
    """
    pairs = []
    system_prefixes = ("<task-notification", "<system-reminder", "<available-deferred-tools")

    current_user = None
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")

        if role == "user":
            text = ""
            if isinstance(content, str):
                text = content.strip()
            elif isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "text":
                        text = b.get("text", "").strip()
                        break

            # Filtrar mensajes del sistema
            if text and len(text) > 5 and not any(text.startswith(p) for p in system_prefixes):
                current_user = text[:300]

        elif role == "assistant" and current_user:
            # Extraer texto de la respuesta (el razonamiento)
            assistant_text = ""
            files_touched = []
            if isinstance(content, str):
                assistant_text = content[:400]
            elif isinstance(content, list):
                text_parts = []
                for b in content:
                    if isinstance(b, dict):
                        if b.get("type") == "text":
                            text_parts.append(b.get("text", ""))
                        elif b.get("type") == "tool_use":
                            fp = b.get("input", {}).get("file_path", "")
                            if fp:
                                files_touched.append(Path(fp).name)
                assistant_text = " ".join(text_parts)[:400]

            if assistant_text and len(assistant_text) > 20:
                pairs.append({
                    "user": current_user,
                    "assistant": assistant_text,
                    "files": files_touched[:5],
                })
            current_user = None

    return pairs


def detect_all_active_domains(files_edited: list, files_created: list,
                              user_messages: list) -> list:
    """
    Detecta TODOS los dominios activos en la sesión (no solo el dominante).
    Necesario para registrar co-ocurrencia entre dominios.
    """
    all_files = files_edited + files_created
    domain_scores: dict = {}
    for f in all_files:
        f_lower = f.lower().replace("\\", "/")
        for hint, domain in DOMAIN_HINTS.items():
            if hint in f_lower:
                domain_scores[domain] = domain_scores.get(domain, 0) + 1

    all_text = " ".join(user_messages).lower()
    keyword_domains = {
        "sap": "sap_tierra", "oportunidad": "sap_tierra", "quote": "sap_tierra",
        "sow": "sow", "propuesta": "sow", "contrato": "sow",
        "bom": "bom", "listado": "bom", "material": "bom",
        "monday": "monday", "pipeline": "monday",
        "outlook": "outlook", "correo": "outlook",
        "pdf": "files", "excel": "files", "script": "files",
    }
    for kw, domain in keyword_domains.items():
        if kw in all_text:
            domain_scores[domain] = domain_scores.get(domain, 0) + 1

    return [d for d, s in domain_scores.items() if s > 0]


def record_domain_cooccurrence(domains: list):
    """
    Registra qué dominios aparecieron juntos en esta sesión.
    Construye una tabla de co-ocurrencia que on_user_message usa para
    predecir contexto relevante antes de que el usuario lo pida.
    """
    if len(domains) < 2:
        return
    try:
        CO_OCCUR_FILE.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if CO_OCCUR_FILE.exists():
            data = json.loads(CO_OCCUR_FILE.read_text(encoding="utf-8"))
        for d1 in domains:
            for d2 in domains:
                if d1 != d2:
                    data.setdefault(d1, {})[d2] = data.get(d1, {}).get(d2, 0) + 1
        CO_OCCUR_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        debug_log(f"Co-occurrence updated for domains: {domains}")
    except Exception as e:
        debug_log(f"Co-occurrence update failed: {e}")


def detect_domains_in_order(files_edited: list, files_created: list,
                             user_messages: list) -> list:
    """
    Retorna dominios en orden de primera aparición en la sesión.
    Necesario para Markov ordinal (sow → bom → files, no simetrico).
    """
    seen = []
    # Archivos en orden cronológico (así llegan del transcript)
    for f in files_edited + files_created:
        f_lower = f.lower().replace("\\", "/")
        for hint, domain in DOMAIN_HINTS.items():
            if hint in f_lower and domain not in seen:
                seen.append(domain)
                break
    # Luego keywords del texto de usuario (en orden de aparición)
    kw_order = [
        ("sap", "sap_tierra"), ("oportunidad", "sap_tierra"), ("quote", "sap_tierra"),
        ("sow", "sow"), ("propuesta", "sow"),
        ("bom", "bom"), ("listado", "bom"),
        ("monday", "monday"), ("pipeline", "monday"),
        ("outlook", "outlook"), ("correo", "outlook"),
        ("pdf", "files"), ("excel", "files"), ("script", "files"),
    ]
    all_text = " ".join(user_messages).lower()
    for kw, domain in kw_order:
        if kw in all_text and domain not in seen:
            seen.append(domain)
    return seen


def record_domain_sequence(domains_ordered: list):
    """
    Registra transiciones ordenadas entre dominios (cadena de Markov).
    Ejemplo: [sow, bom, files] → guarda sow→bom y bom→files con frecuencia.
    Permite predicción de 2 pasos en on_user_message.py.
    """
    if len(domains_ordered) < 2:
        return
    try:
        MARKOV_FILE.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if MARKOV_FILE.exists():
            data = json.loads(MARKOV_FILE.read_text(encoding="utf-8"))
        for i in range(len(domains_ordered) - 1):
            d1 = domains_ordered[i]
            d2 = domains_ordered[i + 1]
            data.setdefault(d1, {})[d2] = data.get(d1, {}).get(d2, 0) + 1
        MARKOV_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        debug_log(f"Markov sequence: {' → '.join(domains_ordered)}")
    except Exception as e:
        debug_log(f"Markov record failed: {e}")


# ── Extracción de momentos episódicos verbatim ────────────────

EPISODIC_SIGNALS = [
    r'(?:descubrí que|encontré que|resulta que|la causa es|root cause|causa raíz)\s+(.{20,250})',
    r'(?:para la próxima vez|next time|recordar que|importante notar)\s*[:\-]?\s*(.{20,250})',
    r'(?:el problema era|el error fue|the issue was|el bug era)\s+(.{20,250})',
    r'(?:la solución clave|key insight|insight clave|lo que funcionó|lo que resolvió)\s*[:\-]?\s*(.{20,250})',
    r'(?:nunca usar|siempre usar|never use|always use)\s+(.{20,250})',
]


def extract_reasoning_traces(messages: list) -> list:
    """
    Extrae el razonamiento de Claude ANTES de cada tool call.
    El bloque type='text' que precede a type='tool_use' ES el pensamiento.

    Ej: "Veo que el selector cambia dinámicamente, debo usar aria-label"
        → tool_use: Bash playwright ...

    Este texto captura el PORQUÉ, no solo el QUÉ.
    Se indexa en FTS5 para recuperación cross-sesión de razonamiento.
    """
    traces = []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        if not isinstance(content, list):
            continue

        pending_text = ""
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = block.get("text", "").strip()
                if len(text) > 30:  # ignorar textos triviales
                    pending_text = text
            elif block.get("type") == "tool_use" and pending_text:
                traces.append({
                    "reasoning": pending_text[:400],
                    "tool": block.get("name", "?"),
                    "action_summary": str(block.get("input", {}))[:120],
                })
                pending_text = ""

    return traces[:12]  # top 12 traces por sesión


def extract_episodic_moments(messages: list) -> list:
    """
    Extrae frases memorables VERBATIM de las respuestas de Claude.
    Son los 'momentos aha' de la sesión — lo que hace que esta sesión
    sea recordable y recuperable en el futuro.
    """
    moments = []
    seen: set = set()
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = " ".join(
                b.get("text", "") for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            )
        for pattern in EPISODIC_SIGNALS:
            for match in re.findall(pattern, text, re.IGNORECASE | re.DOTALL):
                clean = match.strip()[:250].replace("\n", " ")
                if len(clean) > 20 and clean not in seen:
                    seen.add(clean)
                    moments.append(clean)
    return moments[:8]


def audit_hint_usage(messages: list) -> dict:
    """
    Verifica si Claude usó los patrones inyectados en esta sesión.
    Lee last_injection.json (escrito por on_user_message.py) y compara
    contra el texto completo de las respuestas del asistente.

    Acumula en hint_effectiveness.json para adaptar formato con el tiempo:
    - Si usage_rate < 0.3 en 5+ sesiones → el formato actual no funciona
    - Permite detectar qué tipo de hint Claude obedece vs ignora
    """
    try:
        if not INJECTION_FILE.exists():
            return {}

        injection = json.loads(INJECTION_FILE.read_text(encoding="utf-8"))

        # Texto completo de todas las respuestas del asistente
        assistant_text = " ".join(
            b.get("text", "")
            for m in messages
            if m.get("role") == "assistant"
            for b in (m.get("content") if isinstance(m.get("content"), list) else [])
            if isinstance(b, dict) and b.get("type") == "text"
        ).lower()

        if not assistant_text:
            return {}

        keywords = injection.get("keywords", [])
        domains  = injection.get("domains", [])
        intent   = injection.get("intent", "general")

        used_kw  = [k for k in keywords if k.lower() in assistant_text]
        used_dom = [d for d in domains if d.replace("_", " ") in assistant_text
                    or d.replace("_tierra", "").replace("_nube", "") in assistant_text]

        usage_rate = len(used_kw) / max(len(keywords), 1)

        record = {
            "ts":           datetime.now().isoformat(),
            "usage_rate":   round(usage_rate, 2),
            "used_kw":      used_kw,
            "ignored_dom":  [d for d in domains if d not in used_dom],
            "intent":       intent,
            "had_lm":       injection.get("has_lm", False),
            "had_kb":       injection.get("has_kb", False),
            "had_ep":       injection.get("has_ep", False),
        }

        # Acumular histórico
        eff: dict = {}
        if HINT_EFFECT_FILE.exists():
            try:
                eff = json.loads(HINT_EFFECT_FILE.read_text(encoding="utf-8"))
            except Exception:
                eff = {}

        history = eff.get("history", [])
        history.append(record)
        history = history[-100:]  # últimas 100 sesiones

        avg  = sum(h["usage_rate"] for h in history) / len(history)
        eff["history"]        = history
        eff["avg_usage_rate"] = round(avg, 2)
        eff["sessions_count"] = len(history)
        # Alerta si el promedio baja de 30%
        eff["alert_low_usage"] = avg < 0.30 and len(history) >= 5

        HINT_EFFECT_FILE.write_text(
            json.dumps(eff, ensure_ascii=False), encoding="utf-8"
        )
        debug_log(f"Hint audit: usage_rate={usage_rate:.0%}, "
                  f"used={used_kw}, ignored_domains={record['ignored_dom']}")
        return record

    except Exception as e:
        debug_log(f"Hint audit failed: {e}")
        return {}


def auto_extract_learning(session_record: dict, messages: list = None) -> bool:
    """
    Extrae aprendizaje automatico de la sesion con contexto RICO:
    no solo QUE se hizo sino POR QUE se hizo.
    Usa pares pregunta-respuesta del transcript para capturar razonamiento.
    """
    if not DOMAINS:
        debug_log("KB: DOMAINS not available, skipping auto-extract")
        return False

    files_edited = session_record.get("files_edited", [])
    files_created = session_record.get("files_created", [])
    user_messages = session_record.get("user_messages", [])
    decisions = session_record.get("decisions", [])
    errors = session_record.get("errors", [])
    summary = session_record.get("summary", "")

    # Solo guardar si hubo trabajo real
    if not files_edited and not files_created:
        debug_log("KB auto: no files edited/created, skipping")
        return False
    if len(user_messages) < 2:
        debug_log("KB auto: less than 2 user messages, skipping")
        return False

    domain = detect_domain(files_edited, files_created, user_messages)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    key = f"session_auto_{timestamp}"

    # Construir notas con POR QUE (pares pregunta-respuesta)
    notes_parts = []

    # Trazas de razonamiento — el PORQUÉ detrás de cada acción
    if messages:
        reasoning = extract_reasoning_traces(messages)
        if reasoning:
            notes_parts.append("Razonamiento (texto antes de cada tool call):")
            for t in reasoning[:5]:
                tool = t.get("tool", "?")
                why  = t.get("reasoning", "")[:200].replace("\n", " ")
                notes_parts.append(f"  [{tool}] {why}")

    # Momentos episódicos verbatim — lo que hace esta sesión memorable/buscable
    if messages:
        episodic = extract_episodic_moments(messages)
        if episodic:
            notes_parts.append("Momentos clave (verbatim):")
            for m in episodic[:5]:
                notes_parts.append(f"  ✓ {m}")
            # Guardar también como fact episódico en domain sessions (buscable por on_user_message)
            try:
                add_fact("sessions", f"episodic_{timestamp}", {
                    "rule": "; ".join(episodic[:3]),
                    "applies_to": f"sesión {timestamp}, dominio {domain}",
                    "confidence": "observed",
                    "source": "auto_episodic_extraction",
                }, tags=["episodic", "auto-learned", domain])
                debug_log(f"KB episodic: {len(episodic)} moments saved in sessions domain")
            except Exception as ep_err:
                debug_log(f"KB episodic save failed: {ep_err}")

    # Extraer pares conversacionales si tenemos los mensajes completos
    if messages:
        pairs = extract_conversation_pairs(messages)
        if pairs:
            notes_parts.append("Interacciones clave:")
            for p in pairs[-6:]:  # ultimas 6 interacciones
                user_q = p["user"][:100].replace("\n", " ")
                assistant_a = p["assistant"][:150].replace("\n", " ")
                notes_parts.append(f"  P: {user_q}")
                notes_parts.append(f"  R: {assistant_a}")
                if p["files"]:
                    notes_parts.append(f"  Archivos: {', '.join(p['files'])}")

    # Resumen general
    if summary:
        notes_parts.append(f"Resumen: {summary[:200]}")
    if files_edited:
        notes_parts.append(f"Editados: {', '.join(Path(f).name for f in files_edited[:8])}")
    if files_created:
        notes_parts.append(f"Creados: {', '.join(Path(f).name for f in files_created[:8])}")
    if decisions:
        notes_parts.append(f"Decisiones (por que): {'; '.join(decisions[:5])}")
    if errors:
        error_details = [e.get("detail", "")[:80] for e in errors[:3]]
        notes_parts.append(f"Errores resueltos: {'; '.join(error_details)}")

    solution = {
        "strategy": "auto_captured_from_session",
        "notes": "\n".join(notes_parts)[:2000],
        "auto_learned": True,
        "source": "hook_stop_auto_extract",
        "files_touched": (files_edited + files_created)[:10],
        "domain_detected": domain,
    }
    tags = ["auto-learned", "session", domain]

    try:
        add_pattern(domain, key, solution, tags=tags)
        debug_log(f"KB auto: saved {key} in {domain} "
                  f"({len(files_edited)} edits, {len(files_created)} creates)")
        return True
    except Exception as e:
        debug_log(f"KB auto: failed: {e}")
        return False


# ══════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════

def main():
    try:
        raw_input = sys.stdin.read()
        input_data = json.loads(raw_input)
    except (json.JSONDecodeError, Exception) as e:
        debug_log(f"STDIN parse error: {e}")
        debug_log(f"STDIN raw (first 500): {raw_input[:500] if 'raw_input' in dir() else 'N/A'}")
        sys.exit(0)

    # Log de debug: que campos recibimos
    debug_log(f"Hook Stop fired. Fields: {list(input_data.keys())}")

    # Evitar loops
    if input_data.get("stop_hook_active"):
        debug_log("stop_hook_active=True, skipping to avoid loop")
        sys.exit(0)

    session_id = input_data.get("session_id", "unknown")
    transcript_path = input_data.get("transcript_path", "")
    last_message = input_data.get("last_assistant_message", "")
    cwd = input_data.get("cwd", "")
    now = datetime.now(timezone.utc)

    debug_log(f"session_id={session_id}")
    debug_log(f"transcript_path={transcript_path}")
    debug_log(f"last_message length={len(last_message)}")

    # ═══════════════════════════════════════════════════════════
    # LEER TRANSCRIPT COMPLETO
    # ═══════════════════════════════════════════════════════════
    messages = []
    if transcript_path:
        messages = read_transcript(transcript_path)
        debug_log(f"Transcript: {len(messages)} messages loaded")
    else:
        debug_log("No transcript_path received, using last_message only")

    # Si no hay transcript, construir lista minima con last_message
    if not messages and last_message:
        messages = [{"role": "assistant", "content": last_message}]

    if not messages:
        debug_log("No messages to process, exiting")
        sys.exit(0)

    # ═══════════════════════════════════════════════════════════
    # EXTRAER TODA LA INFORMACION
    # ═══════════════════════════════════════════════════════════
    user_messages = extract_user_messages(messages)
    tool_usage = extract_tool_usage(messages)
    errors = extract_errors_from_messages(messages)
    learning = extract_learning_json_from_messages(messages)
    decisions = extract_decisions_from_messages(messages)
    summary = build_conversation_summary(user_messages)

    # Fallback: si el transcript no tiene tools (timing bug en sesiones cortas),
    # leer desde iteration_actions.jsonl que PostToolUse escribe en tiempo real
    transcript_tools_total = (len(tool_usage["files_read"]) + len(tool_usage["files_edited"])
                              + len(tool_usage["files_created"]) + len(tool_usage["commands_run"]))
    if transcript_tools_total == 0:
        iter_tools = extract_tool_usage_from_iter_actions(session_id)
        iter_total = (len(iter_tools["files_read"]) + len(iter_tools["files_edited"])
                      + len(iter_tools["files_created"]) + len(iter_tools["commands_run"]))
        if iter_total > 0:
            tool_usage = merge_tool_usage(tool_usage, iter_tools)
            debug_log(f"Tools fallback from iter_actions: {len(iter_tools['files_read'])} reads, "
                      f"{len(iter_tools['files_edited'])} edits, "
                      f"{len(iter_tools['files_created'])} creates, "
                      f"{len(iter_tools['commands_run'])} commands")
    else:
        # Sesion larga: fusion para asegurar que no se pierda nada del iter_actions
        iter_tools = extract_tool_usage_from_iter_actions(session_id)
        tool_usage = merge_tool_usage(tool_usage, iter_tools)

    debug_log(f"Extracted: {len(user_messages)} user msgs, "
              f"{len(errors)} errors, {len(decisions)} decisions")
    debug_log(f"Tools (final): {len(tool_usage['files_read'])} reads, "
              f"{len(tool_usage['files_edited'])} edits, "
              f"{len(tool_usage['files_created'])} creates, "
              f"{len(tool_usage['commands_run'])} commands")

    # ═══════════════════════════════════════════════════════════
    # VALIDACION: detectar si el parser esta fallando silenciosamente
    # ═══════════════════════════════════════════════════════════
    total_extracted = (len(user_messages) + len(tool_usage['files_read'])
                       + len(tool_usage['files_edited'])
                       + len(tool_usage['commands_run']))
    if len(messages) > 10 and total_extracted == 0:
        debug_log("!!!! ALERTA: transcript tiene %d mensajes pero se extrajo 0 de todo. "
                  "El parser probablemente no entiende el formato del transcript. "
                  "Revisar read_transcript() y la estructura del JSONL." % len(messages))
        # Guardar muestra del transcript para diagnostico
        try:
            sample_path = DEBUG_LOG.parent / "transcript_sample_debug.jsonl"
            with open(sample_path, "w", encoding="utf-8") as sf:
                # Guardar primeros 5 mensajes raw del JSONL para inspección
                with open(transcript_path, "r", encoding="utf-8") as tf:
                    for i, line in enumerate(tf):
                        if i >= 5:
                            break
                        sf.write(line)
            debug_log(f"Sample saved to {sample_path} for debugging")
        except Exception as e:
            debug_log(f"Could not save sample: {e}")
    elif len(messages) > 10:
        debug_log(f"VALIDACION OK: {total_extracted} datos extraidos de {len(messages)} mensajes")

    # ═══════════════════════════════════════════════════════════
    # CONSTRUIR REGISTRO DE SESION
    # ═══════════════════════════════════════════════════════════
    session_record = {
        "session_id": session_id,
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S UTC"),
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "cwd": cwd,

        # Resumen narrativo
        "summary": summary,

        # Todo lo que pidio el usuario (cada mensaje) — sin limite bajo
        "user_messages": user_messages[:50],

        # Archivos y comandos
        "files_read": tool_usage["files_read"][:30],
        "files_edited": tool_usage["files_edited"][:30],
        "files_created": tool_usage["files_created"][:30],
        "commands_run": tool_usage["commands_run"][:30],
        "searches": tool_usage["searches"][:20],

        # Errores con detalle
        "errors": errors,

        # Decisiones tecnicas
        "decisions": decisions,

        # Aprendizaje explicito
        "learning_json": learning,

        # Trazas de razonamiento (texto antes de tool calls)
        "reasoning_traces": extract_reasoning_traces(messages) if messages else [],

        # Metricas
        "metrics": {
            "total_messages": len(messages),
            "user_messages": len(user_messages),
            "errors_count": len(errors),
            "files_touched": (len(tool_usage["files_read"])
                              + len(tool_usage["files_edited"])
                              + len(tool_usage["files_created"])),
            "commands_count": len(tool_usage["commands_run"]),
            "decisions_count": len(decisions),
        },
    }

    # ═══════════════════════════════════════════════════════════
    # GUARDAR O MERGE SESSION HISTORY
    # ═══════════════════════════════════════════════════════════
    try:
        save_or_merge_session(session_record)
    except Exception as e:
        debug_log(f"Failed to save/merge session: {e}")

    # ═══════════════════════════════════════════════════════════
    # REGISTRAR APRENDIZAJE EN KB
    # ═══════════════════════════════════════════════════════════

    # 1. Si hay JSON explícito de aprendizaje, registrarlo
    if learning and learning.get("status") in ("success", "partial", "modified"):
        register_learning_in_kb(learning)
        debug_log("KB: explicit learning JSON registered")

    # 2. Registrar co-ocurrencia Y secuencia Markov de dominios
    active_domains = detect_all_active_domains(
        tool_usage["files_edited"], tool_usage["files_created"], user_messages
    )
    if len(active_domains) >= 2:
        record_domain_cooccurrence(active_domains)
        # Markov ordinal: registra el ORDEN de aparición (sow→bom, no simétrico)
        ordered_domains = detect_domains_in_order(
            tool_usage["files_edited"], tool_usage["files_created"], user_messages
        )
        record_domain_sequence(ordered_domains)

    # 3. SIEMPRE: auto-extraer aprendizaje con contexto conversacional (POR QUE)
    auto_saved = auto_extract_learning(session_record, messages=messages)
    if auto_saved:
        debug_log("KB: auto-learning extracted and saved")
    else:
        debug_log("KB: auto-learning skipped (no edits or too short)")

    # 4. Flush última iteración pendiente del PostToolUse hook
    try:
        from iteration_learn import flush_pending
        flushed = flush_pending()
        if flushed:
            debug_log("KB: flushed pending iteration edits")
    except Exception as e:
        debug_log(f"KB: flush iteration failed: {e}")

    # 5. Indexar sesión en FTS5 (memoria episódica cross-sesión)
    try:
        sys.path.insert(0, str(PROJECT_DIR))
        from episodic_index import index_session as _ep_index
        _ep_index(session_record)
        debug_log("Episodic FTS5: session indexed")
    except Exception as e:
        debug_log(f"Episodic FTS5 index failed: {e}")

    # 6. Audit de efectividad de hints — ¿Claude usó lo que inyectamos?
    if messages:
        audit_record = audit_hint_usage(messages)
        if audit_record:
            rate = audit_record.get("usage_rate", 0)
            debug_log(f"Hint effectiveness: {rate:.0%} usage rate this session")

    # Limpiar crash recovery — sesión terminó limpia, no hay crash
    for fname in ("last_user_message.txt", "last_claude_action.txt"):
        try:
            p = DATA_DIR / fname
            if p.exists():
                p.unlink()
        except Exception:
            pass

    debug_log("Hook Stop completed successfully")
    sys.exit(0)


if __name__ == "__main__":
    main()
