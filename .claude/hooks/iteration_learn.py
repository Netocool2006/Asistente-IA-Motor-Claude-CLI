"""
iteration_learn.py — PostToolUse Hook: aprendizaje PLENO por iteracion
======================================================================
Se dispara despues de CADA uso de herramienta. Detecta nueva iteracion
(= nuevo mensaje del usuario) por gap temporal >15s entre tool uses.

CAPTURA TODO con contexto real:
  - Lecturas: que archivo, que se encontro (resumen)
  - Ediciones: que cambio y por que
  - Busquedas: que se busco, cuantos resultados
  - Comandos: que se ejecuto, si funciono
  - Browser: que acciones se tomaron

DEDUPLICACION: fingerprint por combinacion de tools+archivos.
NOTIFICACION: escribe archivo de status que Claude puede leer.

Recibe en stdin (PostToolUse):
  - tool_name, tool_input, tool_result, session_id, cwd
"""

import sys
import json
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime

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

PROJECT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_DIR))

STATE_FILE        = DATA_DIR / "iteration_state.json"
ACTIONS_LOG       = DATA_DIR / "iteration_actions.jsonl"  # append-only
NOTIFY_FILE       = DATA_DIR / "last_learning.txt"
FINGERPRINTS_FILE = DATA_DIR / "iter_fingerprints.json"
FAILURES_FILE     = DATA_DIR / "pattern_failures.json"
DEBUG_LOG         = DATA_DIR / "hook_debug.log"

# Gap entre tool uses que indica nueva iteracion (usuario envio nuevo mensaje)
ITERATION_GAP_SECS = 15

# Cuantos explores consecutivos sin actuar = territorio nuevo → busqueda proactiva
EXPLORE_THRESHOLD = 3

try:
    from knowledge_base import add_pattern, _load_all_domains
    HAS_KB = bool(_load_all_domains())
except Exception:
    HAS_KB = False


def debug_log(msg):
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] [iter] {msg}\n")
    except Exception:
        pass


def load_state():
    try:
        with file_lock("iteration_state"):
            if STATE_FILE.exists():
                data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                if isinstance(data, dict) and "sid" in data:
                    return data
    except Exception:
        pass
    return {"sid": "", "actions": [], "iteration": 0, "last_ts": 0}


def save_state(state):
    """Guarda solo metadatos livianos (sid, iteration, last_ts).
    Las acciones van al JSONL append-only — sin lock, sin reescribir todo."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Guardar estado sin las acciones (esas van en el JSONL)
        light = {k: v for k, v in state.items() if k != "actions"}
        with file_lock("iteration_state"):
            STATE_FILE.write_text(json.dumps(light, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def append_action(action: dict, session_id: str, iteration: int):
    """Escribe una accion al log JSONL. O(1), sin lock, sin reescribir."""
    try:
        ACTIONS_LOG.parent.mkdir(parents=True, exist_ok=True)
        action["_sid"]  = session_id
        action["_iter"] = iteration
        with open(ACTIONS_LOG, "a", encoding="utf-8") as f:
            f.write(json.dumps(action, ensure_ascii=False) + "\n")
    except Exception:
        pass


def load_actions_for_session(session_id: str, iteration: int) -> list:
    """Lee del JSONL solo las acciones de esta sesion e iteracion."""
    actions = []
    try:
        if not ACTIONS_LOG.exists():
            return []
        with open(ACTIONS_LOG, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    a = json.loads(line)
                    if a.get("_sid") == session_id and a.get("_iter") == iteration:
                        actions.append(a)
                except Exception:
                    pass
    except Exception:
        pass
    return actions


def trim_actions_log(max_lines: int = 5000):
    """Rota el JSONL si crece demasiado — conserva las ultimas N lineas."""
    try:
        if not ACTIONS_LOG.exists():
            return
        lines = ACTIONS_LOG.read_text(encoding="utf-8").splitlines()
        if len(lines) > max_lines:
            ACTIONS_LOG.write_text("\n".join(lines[-max_lines:]) + "\n", encoding="utf-8")
    except Exception:
        pass


# ================================================================
#  CAPTURA DE CONTEXTO REAL
# ================================================================

def extract_context(tool_name, tool_input, tool_result):
    """Extrae contexto REAL de cada accion."""
    result_text = ""
    if isinstance(tool_result, str):
        result_text = tool_result
    elif isinstance(tool_result, dict):
        result_text = tool_result.get("content", "") or tool_result.get("output", "")
        if isinstance(result_text, list):
            result_text = " ".join(
                b.get("text", "") for b in result_text
                if isinstance(b, dict) and b.get("type") == "text"
            )
    result_text = str(result_text)

    ctx = {"tool": tool_name, "t": datetime.now().isoformat()}

    if tool_name == "Read":
        fp = tool_input.get("file_path", "?")
        ctx["file"] = fp
        ctx["action"] = f"Leyo {Path(fp).name}"
        preview = result_text[:300].replace("\n", " ").strip()
        if preview:
            ctx["found"] = preview

    elif tool_name == "Edit":
        fp = tool_input.get("file_path", "?")
        old = tool_input.get("old_string", "")[:100]
        new = tool_input.get("new_string", "")[:100]
        ctx["file"] = fp
        ctx["action"] = f"Edito {Path(fp).name}"
        ctx["change"] = f"{old[:60].replace(chr(10), ' ').replace(chr(13), '')} -> {new[:60].replace(chr(10), ' ').replace(chr(13), '')}"

    elif tool_name == "Write":
        fp = tool_input.get("file_path", "?")
        content_preview = tool_input.get("content", "")[:150]
        ctx["file"] = fp
        ctx["action"] = f"Creo {Path(fp).name}"
        ctx["preview"] = content_preview.replace("\n", " ")[:100]

    elif tool_name == "Bash":
        cmd = tool_input.get("command", "?")[:120]
        ctx["action"] = f"Ejecuto: {cmd}"
        if "error" in result_text.lower()[:200] or "traceback" in result_text.lower()[:200]:
            ctx["result"] = "ERROR: " + result_text[:150].replace("\n", " ")
        else:
            ctx["result"] = result_text[:150].replace("\n", " ").strip()

    elif tool_name == "Grep":
        pattern = tool_input.get("pattern", "?")
        path = tool_input.get("path", ".")
        ctx["action"] = f"Busco '{pattern}' en {Path(path).name if path != '.' else 'proyecto'}"
        lines = result_text.strip().split("\n") if result_text.strip() else []
        ctx["results_count"] = len(lines)
        if lines:
            ctx["sample"] = lines[0][:100]

    elif tool_name == "Glob":
        pattern = tool_input.get("pattern", "?")
        ctx["action"] = f"Glob: {pattern}"
        lines = result_text.strip().split("\n") if result_text.strip() else []
        ctx["results_count"] = len(lines)

    elif tool_name == "Agent":
        desc = tool_input.get("description", "?")
        ctx["action"] = f"Agente: {desc}"
        ctx["result"] = result_text[:200].replace("\n", " ").strip()

    elif "mcp__claude-in-chrome" in tool_name:
        short = tool_name.split("__")[-1]
        ctx["action"] = f"Browser: {short}"
        url = tool_input.get("url", "")
        if url:
            ctx["url"] = url[:100]
        text = tool_input.get("text", "") or tool_input.get("value", "")
        if text:
            ctx["input"] = str(text)[:80]

    else:
        ctx["action"] = f"{tool_name}"
        if tool_input:
            ctx["input_preview"] = str(tool_input)[:100]

    return ctx


# ================================================================
#  DOMINIO Y DEDUPLICACION
# ================================================================

def detect_domain(actions):
    domain_hints = {
        # sap_tierra
        "sap": "sap_tierra", "playbook": "sap_tierra", "oportunidad": "sap_tierra",
        "crm": "sap_tierra", "tierra": "sap_tierra", "playwright": "sap_tierra",
        "webclient": "sap_tierra", "iframe": "sap_tierra", "aria-label": "sap_tierra",
        "logon": "sap_tierra", "quote": "sap_tierra",
        # sap_nube
        "nube": "sap_nube", "s4hana": "sap_nube", "fiori": "sap_nube",
        # sow
        "sow": "sow", "propuesta": "sow", "contrato": "sow", "alcance": "sow",
        "entregable": "sow", "practica": "sow", "statement of work": "sow",
        # bom
        "bom": "bom", "listado": "bom", "material": "bom", "partnum": "bom",
        "part_num": "bom", "cantidad": "bom", "sku": "bom",
        # monday
        "monday": "monday", "pipeline": "monday", "bitacora": "monday", "tablero": "monday",
        # outlook
        "outlook": "outlook", "correo": "outlook", "email": "outlook",
        "adjunto": "outlook", "bandeja": "outlook", "smtp": "outlook",
        # business_rules
        "iva": "business_rules", "tarifa": "business_rules", "sufijo_ps": "business_rules",
        "mep": "business_rules", "liability": "business_rules", "vigencia": "business_rules",
        # catalog
        "catalogo": "catalog", "part number": "catalog", "numero de parte": "catalog",
        # sessions / episodic
        "session_history": "sessions", "episodic": "sessions",
        # files (system/infra — explicit, lowest priority)
        "brand_mirror": "files", "dashboard": "files", "index.html": "files",
        "hook": "files", "knowledge": "files", "file_search": "files",
        "learning": "files", "mirror": "files",
    }
    all_text = " ".join(
        a.get("action", "") + " " + a.get("file", "") + " " + a.get("found", "")
        for a in actions
    ).lower()
    scores = {}
    # Weight: business domains count double vs infrastructure
    infra_domains = {"files"}
    for hint, domain in domain_hints.items():
        if hint in all_text:
            weight = 1 if domain in infra_domains else 2
            scores[domain] = scores.get(domain, 0) + weight
    return max(scores, key=scores.get) if scores else "files"


def _make_fingerprint(actions):
    """Fingerprint unico por iteracion. Incluye accion + detalle, no solo tool:file."""
    parts = []
    for a in actions:
        # Usar action completo (incluye comando, archivo, patron de busqueda)
        detail = a.get("action", a.get("tool", ""))[:80]
        parts.append(detail)
    # Ordenar para que el orden no importe, pero mantener detalle
    return "|".join(sorted(parts))


def _load_fingerprints():
    try:
        if FINGERPRINTS_FILE.exists():
            data = json.loads(FINGERPRINTS_FILE.read_text(encoding="utf-8"))
            cutoff = time.time() - 7200  # 2 horas
            return {k: v for k, v in data.items() if v > cutoff}
    except Exception:
        pass
    return {}


def _save_fingerprint(fp):
    try:
        with file_lock("iter_fingerprints"):
            data = _load_fingerprints()
            data[fp] = time.time()
            FINGERPRINTS_FILE.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


# ================================================================
#  GUARDAR EN KB CON CONTEXTO RICO
# ================================================================

def kb_save(actions, iteration_num):
    """Guarda experiencia COMPLETA de una iteracion. Con deduplicacion."""
    if not HAS_KB or not actions:
        return False, ""

    # Deduplicar
    fp = _make_fingerprint(actions)
    if fp in _load_fingerprints():
        debug_log(f"Dedup: skip iter {iteration_num}, fingerprint exists")
        return False, ""

    # Clasificar
    reads = [a for a in actions if a["tool"] == "Read"]
    edits = [a for a in actions if a["tool"] == "Edit"]
    writes = [a for a in actions if a["tool"] == "Write"]
    commands = [a for a in actions if a["tool"] == "Bash"]
    searches = [a for a in actions if a["tool"] in ("Grep", "Glob")]
    browser = [a for a in actions if "chrome" in a.get("tool", "")]

    # Resumen legible
    parts = []
    if reads:
        file_names = list(set(Path(a.get("file", "?")).name for a in reads if a.get("file")))
        parts.append(f"Leyo: {', '.join(file_names[:5])}")
        for a in reads[:3]:
            found = a.get("found", "")
            if found:
                parts.append(f"  > {Path(a.get('file','?')).name}: {found[:120]}")
    if edits:
        for a in edits[:5]:
            change = a.get("change", "")
            parts.append(f"Edito {Path(a.get('file','?')).name}: {change[:100]}")
    if writes:
        for a in writes[:3]:
            parts.append(f"Creo {Path(a.get('file','?')).name}: {a.get('preview','')[:80]}")
    if commands:
        for a in commands[:3]:
            result = a.get("result", "")
            if result:
                parts.append(f"CMD: {a.get('action','')} > {result[:80]}")
            else:
                parts.append(a.get("action", ""))
    if searches:
        for a in searches[:3]:
            count = a.get("results_count", 0)
            parts.append(f"{a.get('action','')} ({count} resultados)")
    if browser:
        parts.append(f"{len(browser)} acciones browser")

    summary = " | ".join(parts) if parts else "Interaccion de texto"
    domain = detect_domain(actions)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    key = f"iter_{timestamp}_i{iteration_num}"
    all_files = list(set(a.get("file", "") for a in actions if a.get("file")))

    # Notas con contexto rico
    notes_parts = [f"Iteracion {iteration_num}:"]
    for a in actions[:15]:
        action = a.get("action", "")
        found = a.get("found", "")
        change = a.get("change", "")
        result = a.get("result", "")
        detail = action
        if found:
            detail += f" > encontro: {found[:80]}"
        elif change:
            detail += f" > cambio: {change[:80]}"
        elif result:
            detail += f" > {result[:80]}"
        notes_parts.append(f"  {detail}")

    # Leer contexto del tipo de mensaje para etiquetar correctamente
    msg_type = "instruction"
    had_kb   = False
    try:
        _mtf = DATA_DIR / "hook_state" / "msg_type.json"
        if _mtf.exists():
            _mc  = json.loads(_mtf.read_text(encoding="utf-8"))
            msg_type = _mc.get("type", "instruction")
            had_kb   = _mc.get("has_kb", False)
    except Exception:
        pass

    if had_kb and (edits or writes or commands):
        strategy   = "differential_capture"
        extra_note = "[DIFERENCIAL] Complemento a KB existente."
    elif not had_kb and (edits or writes or commands):
        strategy   = "new_experience_capture"
        extra_note = "[NUEVO] Sin conocimiento previo en KB."
    elif msg_type == "informing":
        strategy   = "context_capture"
        extra_note = "[CONTEXTO] Informacion recibida del usuario."
    else:
        strategy   = "auto_iteration_capture"
        extra_note = ""

    if extra_note:
        notes_parts.insert(1, extra_note)

    try:
        add_pattern(domain, key, {
            "strategy": strategy,
            "notes": "\n".join(notes_parts)[:1500],
            "auto_learned": True,
            "source": "post_tool_hook",
            "msg_type": msg_type,
            "had_kb_match": had_kb,
            "files_touched": all_files[:10],
            "activity": {
                "reads": len(reads), "edits": len(edits), "writes": len(writes),
                "commands": len(commands), "searches": len(searches),
                "browser": len(browser), "total": len(actions),
            },
            "iteration": iteration_num,
        }, tags=["auto-learned", "iteration", domain, strategy.split("_")[0]])

        _save_fingerprint(fp)
        debug_log(f"KB saved iter {iteration_num}: {len(actions)} actions, domain={domain}")
        return True, summary
    except Exception as e:
        debug_log(f"KB save failed: {e}")
        return False, ""


# ================================================================
#  NOTIFICACION — archivo que Claude puede leer como prueba
# ================================================================

def write_notification(iteration_num, action_count, summary, domain, saved):
    """
    Escribe archivo de notificacion que sirve como prueba visible
    de que el aprendizaje se esta acumulando.
    """
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    status = "GUARDADO" if saved else "DEDUP-SKIP"

    # Leer historial de notificaciones (ultimas 20)
    lines = []
    try:
        if NOTIFY_FILE.exists():
            lines = NOTIFY_FILE.read_text(encoding="utf-8").strip().split("\n")
            lines = lines[-19:]  # mantener ultimas 19, agregar 1 nueva
    except Exception:
        pass

    # Sanitizar: una sola linea, sin newlines ni caracteres problematicos
    clean_summary = summary[:120].replace("\n", " ").replace("\r", "").encode("ascii", "replace").decode("ascii")
    new_line = f"[{now}] {status} iter {iteration_num} | KB/{domain} | {action_count} acciones | {clean_summary}"
    lines.append(new_line)

    try:
        with file_lock("last_learning"):
            NOTIFY_FILE.write_text("\n".join(lines), encoding="utf-8")
    except Exception:
        pass


# ================================================================
#  FLUSH (llamado por Stop hook)
# ================================================================

def flush_pending():
    """Lee acciones del JSONL para la iteracion actual y guarda en KB."""
    state = load_state()
    sid   = state.get("sid", "")
    itr   = state.get("iteration", 1)
    if not sid:
        return False
    actions = load_actions_for_session(sid, itr)
    if actions:
        saved, summary = kb_save(actions, itr)
        domain = detect_domain(actions)
        write_notification(itr, len(actions), summary, domain, saved)
        if saved:
            debug_log(f"Flush: saved iter {itr} ({len(actions)} actions)")
            state["exp_count"] = state.get("exp_count", 0) + 1
            n = state["exp_count"]
            save_state(state)
            sys.stdout.write(f"\n  Iteracion Guardada  |  Experiencia ganada x{n}\n")
            sys.stdout.flush()
        trim_actions_log()
        return saved
    return False


# ================================================================
#  BUSQUEDA EN KB TRAS FALLO — el corazon del "no repitas el error"
# ================================================================

# ================================================================
#  FAILURE CONTEXT DIFERENCIAL — por qué falla el 13%
# ================================================================

def _capture_failure_context(pattern_key: str, tool_input: dict, error_text: str):
    """
    Guarda el contexto cuando un patrón conocido falla de todas formas.
    Acumula: extensión de archivo, hora, directorio, primer error.
    Con 3+ fallos del mismo patrón, correlaciona qué tienen en común.
    """
    try:
        ctx = {
            "ts":       datetime.now().isoformat(),
            "file_ext": Path(tool_input.get("file_path", "?")).suffix or "none",
            "hour":     datetime.now().hour,
            "weekday":  datetime.now().weekday(),
            "error":    error_text[:80],
        }
        FAILURES_FILE.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if FAILURES_FILE.exists():
            try:
                data = json.loads(FAILURES_FILE.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        key_list = data.get(pattern_key, [])
        key_list.append(ctx)
        data[pattern_key] = key_list[-20:]  # max 20 fallos por patrón
        FAILURES_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _get_failure_annotation(pattern_key: str) -> str:
    """
    Si el patrón falla repetidamente con el mismo contexto,
    retorna una anotación: 'falla frecuente con .xlsx (4/5 veces)'.
    """
    try:
        if not FAILURES_FILE.exists():
            return ""
        data = json.loads(FAILURES_FILE.read_text(encoding="utf-8"))
        failures = data.get(pattern_key, [])
        if len(failures) < 3:
            return ""

        # Correlacionar extensión de archivo
        from collections import Counter
        exts = [f.get("file_ext", "") for f in failures if f.get("file_ext") not in ("", "none", "?")]
        if exts:
            top_ext, count = Counter(exts).most_common(1)[0]
            if count >= 3:
                return f" [⚠ falla {count}x con {top_ext}]"

        # Correlacionar hora del día
        hours = [f.get("hour", -1) for f in failures]
        if hours:
            avg_hour = sum(hours) / len(hours)
            if all(abs(h - avg_hour) < 3 for h in hours):
                return f" [⚠ falla frecuente ~{int(avg_hour)}h]"

        return f" [⚠ {len(failures)} fallos registrados]"
    except Exception:
        return ""


ERROR_SIGNALS = [
    "traceback", "error:", "exception:", "failed", "errno",
    "not found", "permission denied", "syntaxerror", "importerror",
    "modulenotfounderror", "filenotfounderror", "typeerror",
    "cannot", "invalid", "refused", "timed out",
]


def _is_failure(tool_name: str, tool_result, exit_code) -> bool:
    """Determina si el tool fallo."""
    if exit_code is not None and exit_code != 0:
        return True
    result_lower = str(tool_result)[:600].lower()
    return any(sig in result_lower for sig in ERROR_SIGNALS)


def search_kb_on_failure(tool_name: str, tool_input: dict, tool_result) -> str:
    """
    Cuando un tool falla, busca en KB y learning_memory si ya vimos
    ese error antes y tenemos un fix probado.

    Su output va a stdout → Claude lo ve ANTES de reintentar.
    "Si ya te caiste ahi, no vuelvas a caerte."
    """
    if tool_name not in ("Bash", "Edit", "Write"):
        return ""

    error_text = str(tool_result)[:800].lower()
    cmd        = str(tool_input.get("command", tool_input.get("file_path", "")))[:200].lower()

    # Extraer palabras clave del error (las mas largas y especificas)
    error_words = set(re.findall(r'\b[a-z_][a-z0-9_]{3,}\b', error_text))
    error_words -= {"none", "true", "false", "line", "file", "self", "with",
                    "from", "import", "return", "print", "open", "read"}

    if not error_words:
        return ""

    found_lines = []

    # 1. Buscar en learning_memory (patrones error→solucion)
    try:
        from learning_memory import _load_memory
        mem        = _load_memory()
        candidates = []

        for pid, p in mem["patterns"].items():
            sol        = p.get("solution", {})
            searchable = " ".join([
                sol.get("error_command", ""),
                " ".join(str(m) for m in sol.get("error_messages", [])),
                sol.get("notes", ""),
                sol.get("fix_command", ""),
                p.get("context_key", ""),
            ]).lower()

            score = sum(1 for w in error_words if w in searchable)
            if score >= 2:  # al menos 2 palabras del error coinciden
                candidates.append((score, p))

        if candidates:
            candidates.sort(key=lambda x: (-x[0], -x[1]["stats"].get("success_rate", 0)))
            score, best = candidates[0]
            sol         = best.get("solution", {})
            sr          = best["stats"].get("success_rate", 0)
            pattern_key = best.get("context_key", best.get("task_type", "unknown"))
            fix         = sol.get("fix_command") or sol.get("notes", "")

            # Capturar contexto diferencial — ¿qué era distinto esta vez?
            _capture_failure_context(pattern_key, tool_input, error_text[:200])
            failure_note = _get_failure_annotation(pattern_key)

            if fix:
                found_lines.append(
                    f"⚠ [KB/fix] ESTE ERROR YA OCURRIÓ — "
                    f"fix con {sr*100:.0f}% de éxito{failure_note}. APLICAR:\n  {fix[:300]}"
                )
                if sol.get("strategy"):
                    found_lines.append(f"  Estrategia probada: {sol['strategy']}")
    except Exception:
        pass

    # 2. Buscar en knowledge_base (patrones de dominio)
    if not found_lines:
        try:
            from knowledge_base import cross_domain_search
            query   = " ".join(list(error_words)[:6])
            results = cross_domain_search(text_query=query)
            for dom, entries in results.items():
                for e in entries[:1]:
                    sol   = e.get("solution", {})
                    notes = sol.get("notes", "")[:200]
                    if notes and len(notes) > 20:
                        found_lines.append(f"[KB/{dom}] Referencia: {notes}")
                        break
                if found_lines:
                    break
        except Exception:
            pass

    return "\n".join(found_lines)


# ================================================================
#  DETECCION DE TERRITORIO NUEVO — exploracion prolongada sin error
# ================================================================

def _is_exploration(tool_name: str) -> bool:
    """Read / Grep / Glob = Claude esta mirando, no actuando."""
    return tool_name in ("Read", "Grep", "Glob")


def _is_action(tool_name: str) -> bool:
    """Edit / Write / Bash = Claude actuo → resetea racha de exploracion."""
    return tool_name in ("Edit", "Write", "Bash")


def _adaptive_explore_threshold(explored_files: list) -> int:
    """
    Umbral adaptativo: no todos los explores son 'territorio nuevo'.

    - Si el prompt del usuario contiene intención de revisión (revisa, audita...)
      → umbral = 8 (Claude leerá muchos archivos intencionalmente)
    - Si todos los explores son en el mismo directorio
      → umbral = 6 (scan secuencial de un directorio = intencional)
    - Por defecto: EXPLORE_THRESHOLD (3)
    """
    threshold = EXPLORE_THRESHOLD
    try:
        last_msg_file = DATA_DIR / "last_user_message.txt"
        if last_msg_file.exists():
            last_msg = last_msg_file.read_text(encoding="utf-8").lower()
            REVIEW_WORDS = {
                "revisa", "analiza", "audita", "review", "audit",
                "inspect", "lee todos", "recorre", "lista todos",
                "check all", "scan", "busca en", "find all",
            }
            if any(w in last_msg for w in REVIEW_WORDS):
                threshold = 8
    except Exception:
        pass

    # Todos los explores en el mismo directorio = scan intencional, no exploración
    if explored_files and threshold < 6:
        dirs = set(str(Path(f).parent) for f in explored_files if f)
        if len(dirs) <= 1:
            threshold = 6

    return threshold


def search_kb_for_territory(action_record: dict, recent_files: list) -> str:
    """
    Busca en KB cuando Claude lleva EXPLORE_THRESHOLD explores consecutivos
    sin hacer nada — indica territorio nuevo sin error explícito.

    Extrae keywords del contexto actual (archivo, patron de busqueda, hallazgo)
    y los cruza contra todos los dominios del KB.

    Su output va a stdout → Claude lo ve antes de decidir el siguiente tool.
    "Revisa tu mapa antes de seguir explorando terreno desconocido."
    """
    try:
        from knowledge_base import cross_domain_search

        _STOP = {
            "none", "true", "false", "line", "file", "self", "with",
            "from", "import", "return", "print", "open", "read",
            "found", "action", "tool", "the", "and", "for", "that",
            "this", "into", "have", "been", "are", "was",
        }

        topic_parts = []

        # Archivo que se esta leyendo
        if action_record.get("file"):
            fname = Path(action_record["file"]).stem.lower()
            if len(fname) > 3:
                topic_parts.append(fname)
            parent = Path(action_record["file"]).parent.name.lower()
            if parent and parent not in (".", ""):
                topic_parts.append(parent)

        # Patron de la busqueda o accion
        if action_record.get("action"):
            words = re.findall(r'\b[a-zA-Z][a-z]{3,}\b', action_record["action"])
            topic_parts.extend(w.lower() for w in words[:4])

        # Primeras palabras del hallazgo
        if action_record.get("found"):
            words = re.findall(r'\b[a-zA-Z][a-z]{3,}\b', action_record["found"][:300])
            topic_parts.extend(w.lower() for w in words[:4])

        # Nombres de archivos leidos recientemente como contexto adicional
        for fp in recent_files[-3:]:
            fname = Path(fp).stem.lower()
            if len(fname) > 3:
                topic_parts.append(fname)

        keywords = [w for w in topic_parts if w not in _STOP][:8]
        if not keywords:
            return ""

        query   = " ".join(keywords)
        results = cross_domain_search(text_query=query)

        lines = []
        for dom, entries in results.items():
            for e in entries[:1]:
                if e.get("type") == "pattern":
                    sol      = e.get("solution", {})
                    notes    = sol.get("notes", "")[:200]
                    strategy = sol.get("strategy", "")
                    if notes and len(notes) > 20:
                        lines.append(f"[KB/{dom}] {strategy or 'referencia'}: {notes}")
                elif e.get("type") == "fact":
                    fact = e.get("fact", {})
                    rule = fact.get("rule", "")[:200]
                    if rule and len(rule) > 20:
                        lines.append(f"[KB/{dom}] regla: {rule}")
                if lines:
                    break
            if len(lines) >= 2:
                break

        return "\n".join(lines)
    except Exception:
        return ""


# ================================================================
#  MAIN — PostToolUse handler
# ================================================================

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--flush":
        flush_pending()
        sys.exit(0)

    try:
        data = json.loads(sys.stdin.read())
    except Exception:
        sys.exit(0)

    tool_name   = data.get("tool_name", "")
    tool_input  = data.get("tool_input", {})
    tool_result = data.get("tool_result", "")
    exit_code   = data.get("exit_code")
    session_id  = data.get("session_id", "")

    # ── PRIMERO: si fallo, buscar fix en KB antes de que Claude reintente ──
    if _is_failure(tool_name, tool_result, exit_code):
        hint = search_kb_on_failure(tool_name, tool_input, tool_result)
        if hint:
            sys.stdout.write(hint + "\n")
            sys.stdout.flush()

    state = load_state()
    action_record_preview = extract_context(tool_name, tool_input, tool_result)

    # ── TERRITORIO NUEVO: racha de exploracion sin accion ──────────────────
    # Umbral adaptativo: detecta si el prompt indica revisión intencional
    # y ajusta el umbral para no disparar en scans legítimos de muchos archivos.
    if _is_exploration(tool_name):
        # Timing: gap < 2s entre reads = scan secuencial rápido (intencional, no exploración)
        _read_now = time.time()
        _last_read = state.get("last_read_ts", 0)
        _gap = _read_now - _last_read if _last_read > 0 else 99.0
        state["last_read_ts"] = _read_now
        if _gap >= 2.0:  # Pausa real = exploración con duda, incrementar racha
            state["explore_streak"] = state.get("explore_streak", 0) + 1
        # else: scan rápido secuencial = intencional, no contar
        fp_val = action_record_preview.get("file", "")
        if fp_val:
            seen = state.get("explored_files", [])
            if fp_val not in seen:
                seen.append(fp_val)
                state["explored_files"] = seen[-20:]
    elif _is_action(tool_name):
        state["explore_streak"] = 0
        state["last_read_ts"] = 0  # reset al actuar
        state["territory_searched"] = False  # reset: nueva acción, nueva oportunidad

    effective_threshold = _adaptive_explore_threshold(state.get("explored_files", []))
    already_searched    = state.get("territory_searched", False)

    if state.get("explore_streak", 0) == effective_threshold and not already_searched:
        recent_files   = state.get("explored_files", [])
        territory_hint = search_kb_for_territory(action_record_preview, recent_files)
        if territory_hint:
            header = (f"⚠ MAPA KB — {effective_threshold} explores sin actuar "
                      f"(territorio nuevo detectado):\n")
            sys.stdout.write(header + territory_hint + "\n")
            sys.stdout.flush()
        state["territory_searched"] = True  # disparar solo una vez por racha

    now = time.time()

    # Nueva sesion -> reset estado liviano (explore_streak ya calculado arriba)
    if state.get("sid") != session_id:
        debug_log(f"New session: {session_id[:20]}")
        state = {
            "sid": session_id, "iteration": 1, "last_ts": now,
            "explore_streak": state.get("explore_streak", 0),
            "explored_files": state.get("explored_files", []),
        }
        save_state(state)

    last_ts = state.get("last_ts", 0)
    gap     = now - last_ts if last_ts > 0 else 0

    # Gap grande = nueva iteracion → flush la anterior al KB
    if gap > ITERATION_GAP_SECS:
        prev_iter = state.get("iteration", 1)
        # Cargar acciones de la iteracion anterior desde JSONL (rapido, solo esa iter)
        prev_actions = load_actions_for_session(session_id, prev_iter)
        if prev_actions and prev_iter >= 1:
            saved, summary = kb_save(prev_actions, prev_iter)
            domain         = detect_domain(prev_actions)
            write_notification(prev_iter, len(prev_actions), summary, domain, saved)
            debug_log(f"Flushed iter {prev_iter}: {len(prev_actions)} actions, domain={domain}")
            if saved:
                state["exp_count"] = state.get("exp_count", 0) + 1
                n = state["exp_count"]
                sys.stdout.write(f"\n  Iteracion Guardada  |  Experiencia ganada x{n}\n")
                sys.stdout.flush()

        state["iteration"] = prev_iter + 1
        debug_log(f"New iteration (gap={gap:.0f}s) -> {state['iteration']}")

    # Primer tool use: asegurar iteration=1
    if state.get("iteration", 0) == 0:
        state["iteration"] = 1

    # ── ESCRITURA RAPIDA: solo 1 append al JSONL ──────────────
    append_action(action_record_preview, session_id, state["iteration"])

    # ── FEEDBACK VISIBLE: siempre mostrar qué se capturó ──────
    _tool = action_record_preview.get("tool", tool_name)
    _is_err = _is_failure(tool_name, tool_result, exit_code)
    _action_desc = action_record_preview.get("action", "")[:60]
    _file_desc = action_record_preview.get("file", "")
    if _file_desc:
        _file_desc = Path(_file_desc).name

    if _is_err:
        # Extraer tipo de error del output
        _err_type = ""
        for _line in str(tool_result).split("\n"):
            if "Error" in _line or "Exception" in _line:
                _err_type = _line.strip()[:80]
                break
        sys.stdout.write(f"  [!] Error capturado: {_err_type or _action_desc}\n")
    elif _tool in ("Edit", "Write"):
        sys.stdout.write(f"  [+] Cambio registrado: {_file_desc}\n")
    elif _tool == "Bash":
        sys.stdout.write(f"  [>] Accion registrada: {_action_desc}\n")
    # Read/Grep/Glob: silencioso (son exploraciones, no generan ruido)
    sys.stdout.flush()

    # Estado liviano: solo sid + iteration + timestamp (sin lista de acciones)
    state["last_ts"] = now
    save_state(state)

    # Rotar JSONL ocasionalmente (no en cada call, solo cada ~100 calls)
    if int(now) % 100 == 0:
        trim_actions_log()


if __name__ == "__main__":
    main()
