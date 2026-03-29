"""
learning_memory.py — Motor de Memoria Adaptativa para Claude Code CLI
=====================================================================
Sistema de aprendizaje incremental local que registra:
- Patrones de interacción exitosos (selectores, secuencias, workarounds)
- Errores encontrados y sus soluciones
- Contexto de ejecución (URL, tipo de campo, timestamps)

Flujo: intentar → fallar → corregir → registrar → reutilizar
La IA solo se invoca cuando NO hay patrón local que aplique.
"""

import json
import os
import re
import hashlib
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Configuración ──────────────────────────────────────────────
MEMORY_DIR = Path.home() / ".adaptive_cli"
LOCK_DIR = MEMORY_DIR / "locks"

# ── Task Attempts & Error→Fix ──────────────────────────────────
ATTEMPTS_FILE       = MEMORY_DIR / "task_attempts.json"
PENDING_ERRORS_FILE = MEMORY_DIR / "pending_errors.json"

CONFIDENCE_THRESHOLD  = 0.6
ERROR_FIX_WINDOW_SECS = 600   # 10 min para correlacionar error → fix
MAX_PENDING_ERRORS    = 15

ERROR_PATTERNS = [
    r"Traceback \(most recent call last\)",
    r"Error:|ERROR:|Exception:",
    r"ModuleNotFoundError|ImportError|FileNotFoundError",
    r"Permission denied|command not found",
    r"exit code [1-9]",
    r"No such file or directory",
    r"SyntaxError|TypeError|ValueError|KeyError|AttributeError",
    r"FAILED|FAIL|fatal:",
    r"Cannot|cannot|Could not|could not",
    r"refused|denied|timeout|timed out",
]

SUCCESS_PATTERNS = [
    r"exit code 0",
    r"OK|completado|exitosa|correcto|successfully",
    r"Running on http://",
    r"created|installed|updated|saved|done",
    r"\d+ (?:files?|archivos?|rows?|items?|results?)",
]


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
MEMORY_FILE = MEMORY_DIR / "learned_patterns.json"
EXECUTION_LOG = MEMORY_DIR / "execution_log.jsonl"  # append-only log


def _ensure_dirs():
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def _load_memory() -> dict:
    """Carga la base de patrones aprendidos (con lock)."""
    _ensure_dirs()
    with file_lock("learned_patterns"):
        if MEMORY_FILE.exists():
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    return {
        "version": "1.0",
        "patterns": {},      # pattern_id → PatternEntry
        "tag_index": {},      # tag → [pattern_ids]
        "stats": {
            "total_patterns": 0,
            "total_reuses": 0,
            "total_ai_calls_saved": 0,
        },
    }


def _save_memory(mem: dict):
    _ensure_dirs()
    with file_lock("learned_patterns"):
        tmp = MEMORY_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(mem, f, indent=2, ensure_ascii=False)
        tmp.replace(MEMORY_FILE)


def _pattern_id(task_type: str, context_key: str) -> str:
    """Genera ID determinístico para un patrón."""
    raw = f"{task_type}::{context_key}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _normalize_key(text: str) -> str:
    """Normaliza un comando/tarea para matching — elimina ruido de paths, números, strings."""
    t = text.strip().lower()
    t = re.sub(r'["\'].*?["\']', '""', t)   # normalizar strings entre comillas
    t = re.sub(r'\b\d+\b', 'N', t)           # normalizar números
    t = re.sub(r'[/\\]\S+', '/PATH', t)      # normalizar paths
    t = re.sub(r'\s+', ' ', t)               # normalizar whitespace
    return t.strip()


def _similarity(a: str, b: str) -> float:
    """Similitud Jaccard sobre bigramas. Rápido y sin dependencias."""
    def bigrams(s):
        return set(s[i:i+2] for i in range(len(s) - 1))
    ba, bb = bigrams(a), bigrams(b)
    if not ba and not bb:
        return 1.0
    if not ba or not bb:
        return 0.0
    return len(ba & bb) / len(ba | bb)


def _append_log(entry: dict):
    """Escribe una línea al log de ejecución (append-only)."""
    _ensure_dirs()
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    with open(EXECUTION_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── API Pública ────────────────────────────────────────────────

def search_pattern(
    task_type: str,
    context_key: str,
    tags: Optional[list[str]] = None,
) -> Optional[dict]:
    """
    Busca un patrón aprendido que coincida con la tarea actual.

    Args:
        task_type:    Categoría de la tarea (ej: "sap_login", "selector_iframe",
                      "crm_field_fill", "api_retry")
        context_key:  Identificador específico del contexto (ej: URL, field name,
                      error message hash)
        tags:         Tags opcionales para búsqueda difusa

    Returns:
        PatternEntry si encuentra match, None si es territorio nuevo.
    """
    mem = _load_memory()
    pid = _pattern_id(task_type, context_key)

    # 1) Búsqueda exacta por ID
    if pid in mem["patterns"]:
        pattern = mem["patterns"][pid]
        pattern["stats"]["lookups"] += 1
        pattern["stats"]["last_lookup"] = datetime.now(timezone.utc).isoformat()
        _save_memory(mem)
        _append_log({
            "event": "pattern_hit",
            "pattern_id": pid,
            "task_type": task_type,
            "context_key": context_key,
        })
        return pattern

    # 2) Búsqueda difusa por tags (requiere 2+ tags específicos en común)
    GENERIC_TAGS = {"bash", "cmd", "powershell", "auto_learned", "error_fix", "claude", "shell"}
    if tags:
        specific_tags = [t for t in tags if t not in GENERIC_TAGS]
        if specific_tags:
            tag_counts: dict[str, int] = {}
            for tag in specific_tags:
                for cid in mem.get("tag_index", {}).get(tag, []):
                    tag_counts[cid] = tag_counts.get(cid, 0) + 1
            strong = [
                mem["patterns"][cid]
                for cid, count in tag_counts.items()
                if count >= 2 and cid in mem["patterns"]
            ]
            if strong:
                best = max(strong, key=lambda p: p["stats"].get("success_rate", 0))
                if best["stats"].get("success_rate", 0) >= CONFIDENCE_THRESHOLD:
                    _append_log({
                        "event": "pattern_fuzzy_hit",
                        "matched_pattern": best["id"],
                        "search_tags": tags,
                    })
                    return best

    # 3) Búsqueda por similitud de texto (score > 0.8)
    normalized = _normalize_key(context_key)
    best_match = None
    best_score = 0.0
    for p in mem["patterns"].values():
        score = _similarity(normalized, _normalize_key(p.get("context_key", "")))
        if score > 0.8 and score > best_score:
            best_score = score
            best_match = p
    if best_match and best_match["stats"].get("success_rate", 0) >= CONFIDENCE_THRESHOLD:
        _append_log({
            "event": "pattern_similarity_hit",
            "matched_pattern": best_match["id"],
            "similarity_score": round(best_score, 4),
        })
        return best_match

    # 4) No hay patrón → territorio nuevo
    _append_log({
        "event": "pattern_miss",
        "task_type": task_type,
        "context_key": context_key,
    })
    return None


def register_pattern(
    task_type: str,
    context_key: str,
    solution: dict,
    tags: Optional[list[str]] = None,
    error_context: Optional[dict] = None,
):
    """
    Registra un nuevo patrón aprendido después de resolver un problema.

    Args:
        task_type:      Categoría (ej: "sap_login")
        context_key:    Contexto específico
        solution:       Dict con la solución:
            {
                "strategy": "aria_label_fallback",
                "selector_chain": ["#loginBtn", "button[aria-label='Log On']"],
                "code_snippet": "await page.click('button[aria-label=\\'Log On\\']')",
                "notes": "El ID dinámico no sirve, usar aria-label",
                "attempts_to_solve": 3,
                "time_to_solve_seconds": 180,
            }
        tags:           Tags para indexar (ej: ["sap", "login", "playwright"])
        error_context:  Info del error original que provocó el aprendizaje
    """
    mem = _load_memory()
    pid = _pattern_id(task_type, context_key)
    now = datetime.now(timezone.utc).isoformat()

    entry = {
        "id": pid,
        "task_type": task_type,
        "context_key": context_key,
        "solution": solution,
        "tags": tags or [],
        "error_context": error_context,
        "created_at": now,
        "updated_at": now,
        "stats": {
            "lookups": 0,
            "reuses": 0,
            "success_rate": 1.0,  # arranca en 100% (recién probado y funcionó)
            "last_lookup": None,
            "last_reuse": None,
        },
    }

    mem["patterns"][pid] = entry
    mem["stats"]["total_patterns"] += 1

    # Actualizar índice de tags
    for tag in (tags or []):
        if tag not in mem["tag_index"]:
            mem["tag_index"][tag] = []
        if pid not in mem["tag_index"][tag]:
            mem["tag_index"][tag].append(pid)

    _save_memory(mem)
    _append_log({
        "event": "pattern_registered",
        "pattern_id": pid,
        "task_type": task_type,
        "solution_strategy": solution.get("strategy", "unknown"),
    })
    return pid


def record_reuse(pattern_id: str, success: bool, notes: str = ""):
    """
    Registra que se reutilizó un patrón y si funcionó.
    Actualiza el success_rate con promedio móvil.
    """
    mem = _load_memory()
    if pattern_id not in mem["patterns"]:
        return

    pattern = mem["patterns"][pattern_id]
    stats = pattern["stats"]
    now = datetime.now(timezone.utc).isoformat()

    stats["reuses"] += 1
    stats["last_reuse"] = now

    # Promedio móvil exponencial del success_rate (α=0.3)
    alpha = 0.3
    current_rate = stats["success_rate"]
    new_value = 1.0 if success else 0.0
    stats["success_rate"] = round(alpha * new_value + (1 - alpha) * current_rate, 4)

    if success:
        mem["stats"]["total_reuses"] += 1
        mem["stats"]["total_ai_calls_saved"] += 1

    pattern["updated_at"] = now
    _save_memory(mem)

    _append_log({
        "event": "pattern_reuse",
        "pattern_id": pattern_id,
        "success": success,
        "new_success_rate": stats["success_rate"],
        "notes": notes,
    })


def update_pattern(
    pattern_id: str,
    solution_updates: dict,
    reason: str = "",
):
    """
    Actualiza la solución de un patrón existente (evolución).
    Útil cuando el patrón base funcionó pero necesitó ajuste.
    """
    mem = _load_memory()
    if pattern_id not in mem["patterns"]:
        return False

    pattern = mem["patterns"][pattern_id]
    # Guardar versión anterior en historial
    if "history" not in pattern:
        pattern["history"] = []
    pattern["history"].append({
        "previous_solution": pattern["solution"].copy(),
        "changed_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    })

    pattern["solution"].update(solution_updates)
    pattern["updated_at"] = datetime.now(timezone.utc).isoformat()
    _save_memory(mem)

    _append_log({
        "event": "pattern_updated",
        "pattern_id": pattern_id,
        "reason": reason,
    })
    return True


def get_stats() -> dict:
    """Retorna estadísticas globales del sistema de memoria."""
    mem = _load_memory()
    patterns = mem["patterns"]

    if not patterns:
        return {"message": "Sin patrones registrados aún", **mem["stats"]}

    success_rates = [p["stats"]["success_rate"] for p in patterns.values()]
    most_reused = max(patterns.values(), key=lambda p: p["stats"]["reuses"])

    return {
        **mem["stats"],
        "avg_success_rate": round(sum(success_rates) / len(success_rates), 4),
        "most_reused_pattern": {
            "id": most_reused["id"],
            "task_type": most_reused["task_type"],
            "reuses": most_reused["stats"]["reuses"],
        },
        "patterns_by_type": _count_by_key(patterns, "task_type"),
    }


def export_for_claude_context(task_type: str = None, limit: int = 10) -> str:
    """
    Exporta patrones relevantes en formato texto para inyectar
    como contexto en el prompt de Claude Code CLI.

    Esto es lo que hace el puente: cuando Claude CLI necesita resolver
    algo, primero lee este resumen y decide si ya sabe cómo hacerlo.
    """
    mem = _load_memory()
    patterns = list(mem["patterns"].values())

    if task_type:
        patterns = [p for p in patterns if p["task_type"] == task_type]

    # Ordenar por relevancia: más exitosos y más usados primero
    patterns.sort(
        key=lambda p: (p["stats"]["success_rate"], p["stats"]["reuses"]),
        reverse=True,
    )
    patterns = patterns[:limit]

    if not patterns:
        return f"No hay patrones aprendidos para '{task_type or 'cualquier tipo'}'."

    lines = [
        "=== PATRONES APRENDIDOS (memoria local) ===",
        f"Total disponibles: {len(patterns)}",
        "",
    ]
    for p in patterns:
        sol = p["solution"]
        lines.append(f"## [{p['task_type']}] {p['context_key']}")
        lines.append(f"   Estrategia: {sol.get('strategy', 'N/A')}")
        if sol.get("selector_chain"):
            lines.append(f"   Selectores: {' → '.join(sol['selector_chain'])}")
        if sol.get("code_snippet"):
            lines.append(f"   Código: {sol['code_snippet'][:200]}")
        if sol.get("notes"):
            lines.append(f"   Nota: {sol['notes']}")
        lines.append(
            f"   Éxito: {p['stats']['success_rate']*100:.0f}% "
            f"| Reusos: {p['stats']['reuses']} "
            f"| Tags: {', '.join(p.get('tags', []))}"
        )
        lines.append("")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
#  TASK ATTEMPTS — Memoria de callejones sin salida
#  Registra TODOS los métodos intentados (fallidos + exitosos).
#  Ejemplo: "login SAP CRM"
#    intento 1: fill() directo          → FALLÓ  (campo no responde)
#    intento 2: click + type()          → FALLÓ  (timeout)
#    intento 3: type() con delay=50ms   → ÉXITO
#  Próxima sesión → va directo al intento 3, saltea los fallidos
# ══════════════════════════════════════════════════════════════

def _load_attempts() -> dict:
    if ATTEMPTS_FILE.exists():
        try:
            return json.loads(ATTEMPTS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_attempts(data: dict):
    tmp = ATTEMPTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(ATTEMPTS_FILE)


def _task_key(task_description: str) -> str:
    """Hash estable de la descripción de tarea normalizada."""
    t = task_description.strip().lower()
    t = re.sub(r'["\'].*?["\']', '', t)
    t = re.sub(r'\s+', ' ', t)
    return hashlib.sha256(t.encode()).hexdigest()[:16]


def record_attempt(
    task: str,
    method: str,
    success: bool,
    exit_code: int = -1,
    output_preview: str = "",
    duration_ms: int = 0,
    code_snippet: str = "",
    error_messages: list = None,
) -> dict:
    """
    Registra un intento de resolver una tarea (fallido o exitoso).

    Args:
        task:           Descripción de la tarea (ej: "login SAP CRM WebUI")
        method:         Nombre de la estrategia (ej: "type_con_delay", "fill_directo")
        success:        ¿Funcionó?
        exit_code:      Código de salida del proceso
        output_preview: Primeros chars del output
        duration_ms:    Tiempo que tardó
        code_snippet:   Código que se ejecutó
        error_messages: Lista de mensajes de error
    """
    key = _task_key(task)
    now = datetime.now(timezone.utc).isoformat()

    with file_lock("task_attempts"):
        db = _load_attempts()
        if key not in db:
            db[key] = {
                "task": task,
                "created_at": now,
                "attempts": [],
                "best_method": None,
            }

        entry = db[key]
        attempt_num = len(entry["attempts"]) + 1

        attempt = {
            "num": attempt_num,
            "method": method,
            "success": success,
            "exit_code": exit_code,
            "output_preview": output_preview[:200],
            "error_messages": (error_messages or [])[:5],
            "code_snippet": code_snippet[:500],
            "duration_ms": duration_ms,
            "timestamp": now,
            "score": 0.0,
        }

        if success:
            speed_score = max(0, 1.0 - (duration_ms / 30000))
            attempt["score"] = round(speed_score, 4)

        entry["attempts"].append(attempt)

        successful = [a for a in entry["attempts"] if a["success"]]
        failed     = [a for a in entry["attempts"] if not a["success"]]

        if successful:
            method_stats: dict = {}
            for a in entry["attempts"]:
                m = a["method"]
                if m not in method_stats:
                    method_stats[m] = {
                        "successes": 0, "failures": 0, "total_score": 0,
                        "last": a["timestamp"], "best_attempt": a,
                    }
                if a["success"]:
                    method_stats[m]["successes"] += 1
                    method_stats[m]["total_score"] += a["score"]
                    if a["score"] >= method_stats[m]["best_attempt"].get("score", 0):
                        method_stats[m]["best_attempt"] = a
                else:
                    method_stats[m]["failures"] += 1
                method_stats[m]["last"] = a["timestamp"]

            best_name = None
            best_rank = (-1.0, -1.0)
            for m, st in method_stats.items():
                total = st["successes"] + st["failures"]
                sr    = st["successes"] / total if total > 0 else 0
                avg   = st["total_score"] / st["successes"] if st["successes"] > 0 else 0
                if (sr, avg) > best_rank:
                    best_rank = (sr, avg)
                    best_name = m

            if best_name:
                best = method_stats[best_name]
                entry["best_method"] = {
                    "method": best_name,
                    "success_rate": best_rank[0],
                    "avg_score": best_rank[1],
                    "successes": best["successes"],
                    "failures": best["failures"],
                    "code_snippet": best["best_attempt"].get("code_snippet", ""),
                    "last_used": best["last"],
                }

        entry["updated_at"]     = now
        entry["total_attempts"] = len(entry["attempts"])
        entry["total_successes"] = len(successful)
        entry["total_failures"]  = len(failed)
        entry["failed_methods"]  = list({a["method"] for a in failed})

        _save_attempts(db)

    return {
        "attempt_num":     attempt_num,
        "total_attempts":  len(entry["attempts"]),
        "total_successes": len(successful),
        "total_failures":  len(failed),
        "best_method":     entry.get("best_method"),
        "failed_methods":  entry.get("failed_methods", []),
    }


def get_best_method(task: str) -> Optional[dict]:
    """
    Retorna el mejor método probado para una tarea, o None si no hay historial.

    El dict incluye:
      - method:        nombre de la mejor estrategia
      - success_rate:  float
      - code_snippet:  código que funcionó
      - failed_methods: lista de métodos que NO funcionaron
      - total_attempts: int
    """
    key = _task_key(task)
    db  = _load_attempts()
    entry = db.get(key)

    # Fallback: similitud de texto
    if not entry or not entry.get("best_method"):
        normalized = task.strip().lower()
        for v in db.values():
            if v.get("best_method") and _similarity(normalized, v["task"].lower()) > 0.6:
                entry = v
                break

    if not entry or not entry.get("best_method"):
        return None

    best = entry["best_method"]
    return {
        "method":          best["method"],
        "success_rate":    best.get("success_rate", 0),
        "avg_score":       best.get("avg_score", 0),
        "code_snippet":    best.get("code_snippet", ""),
        "successes":       best.get("successes", 0),
        "failed_methods":  entry.get("failed_methods", []),
        "total_attempts":  entry.get("total_attempts", 0),
        "total_successes": entry.get("total_successes", 0),
        "total_failures":  entry.get("total_failures", 0),
        "task":            entry.get("task", task),
    }


def format_task_context(task: str) -> str:
    """
    Genera texto de contexto para inyectar a Claude indicando:
    - Qué métodos YA FALLARON (para no repetirlos)
    - Cuál es el mejor método probado y el código que funcionó
    """
    best = get_best_method(task)
    if not best:
        return ""

    lines = ["HISTORIAL DE INTENTOS PARA ESTA TAREA:"]

    if best["failed_methods"]:
        lines.append(f"  METODOS QUE NO FUNCIONARON ({best['total_failures']} fallos):")
        for fm in best["failed_methods"]:
            lines.append(f"    X {fm}  <-- NO usar, ya falló antes")

    lines.append(
        f"  MEJOR METODO PROBADO ({best['successes']} éxitos, "
        f"tasa: {best['success_rate']*100:.0f}%):"
    )
    lines.append(f"    -> {best['method']}")
    if best["code_snippet"]:
        lines.append(f"    Código que funcionó:\n    {best['code_snippet'][:300]}")

    lines.append(
        f"  INSTRUCCION: Usa '{best['method']}' directamente. "
        "NO intentes los métodos fallidos."
    )
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
#  ERROR → FIX CORRELATION
#  Detecta errores en output y los correlaciona con el fix
#  que llegó después (ventana de 10 minutos).
# ══════════════════════════════════════════════════════════════

def _load_pending_errors() -> list:
    if PENDING_ERRORS_FILE.exists():
        try:
            return json.loads(PENDING_ERRORS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_pending_errors(errors: list):
    PENDING_ERRORS_FILE.write_text(
        json.dumps(errors[-MAX_PENDING_ERRORS:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def detect_errors(output: str) -> list:
    """Detecta patrones de error en el output de un comando."""
    errors = []
    for pattern in ERROR_PATTERNS:
        matches = re.findall(pattern, str(output), re.IGNORECASE)
        if matches:
            errors.extend(matches[:3])
    return errors


def detect_success(output: str, exit_code: int = None) -> bool:
    """Detecta si el output indica éxito."""
    if exit_code == 0:
        return True
    for pattern in SUCCESS_PATTERNS:
        if re.search(pattern, str(output), re.IGNORECASE):
            return True
    return False


def correlate_error_fix(
    command: str,
    output: str,
    exit_code: int,
    tags: list = None,
) -> dict:
    """
    Llama esto después de ejecutar un comando para aprendizaje automático.
    - Si el comando falló: encola el error para correlación futura
    - Si el comando tuvo éxito y hay un error previo en cola: registra el par error→fix

    Returns dict con {learned, pattern_id, error_fix, message}
    """
    now = datetime.now(timezone.utc)
    result = {"learned": False, "pattern_id": None, "error_fix": None, "message": ""}

    errors  = detect_errors(output)
    success = exit_code == 0 and not errors

    if success and detect_success(output, exit_code):
        pending = _load_pending_errors()
        if pending:
            last_error  = pending[-1]
            error_time  = datetime.fromisoformat(last_error["timestamp"])
            # Normalizar timezone para comparar
            if error_time.tzinfo is None:
                from datetime import timezone as _tz
                error_time = error_time.replace(tzinfo=_tz.utc)
            elapsed = (now - error_time).total_seconds()
            if elapsed <= ERROR_FIX_WINDOW_SECS:
                fix_solution = {
                    "strategy":            "auto_error_fix",
                    "error_command":       last_error["command"],
                    "error_messages":      last_error["errors"][:3],
                    "fix_command":         command,
                    "fix_output_preview":  output[:200],
                    "notes": (
                        f"Error: {last_error['command'][:60]} "
                        f"→ Fix: {command[:60]}"
                    ),
                    "auto_learned":        True,
                    "attempts_before_fix": len(pending),
                }
                pid = register_pattern(
                    task_type="error_fix",
                    context_key=_normalize_key(command),
                    solution=fix_solution,
                    tags=(tags or []) + ["auto_learned", "error_fix"],
                    error_context={"original_error": last_error},
                )
                _save_pending_errors([])
                result.update({
                    "learned":    True,
                    "pattern_id": pid,
                    "error_fix":  fix_solution,
                    "message": (
                        f"APRENDIDO: Después de {len(pending)} intento(s) fallido(s), "
                        f"'{command[:50]}' funcionó. Guardado."
                    ),
                })
                return result

    elif errors:
        pending = _load_pending_errors()
        pending.append({
            "command":        command,
            "errors":         errors[:3],
            "output_preview": output[:200],
            "exit_code":      exit_code,
            "timestamp":      now.isoformat(),
        })
        _save_pending_errors(pending)
        result["message"] = f"Error detectado ({len(errors)} patrón(es)). Esperando fix..."

    return result


# ── Utilidades internas ────────────────────────────────────────

def _count_by_key(patterns: dict, key: str) -> dict:
    counts = {}
    for p in patterns.values():
        val = p.get(key, "unknown")
        counts[val] = counts.get(val, 0) + 1
    return counts


# ── CLI rápido para inspección ─────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso: python learning_memory.py [stats|export|search <type> <key>]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "stats":
        print(json.dumps(get_stats(), indent=2, ensure_ascii=False))

    elif cmd == "export":
        task_filter = sys.argv[2] if len(sys.argv) > 2 else None
        print(export_for_claude_context(task_filter))

    elif cmd == "search":
        if len(sys.argv) < 4:
            print("Uso: python learning_memory.py search <task_type> <context_key>")
            sys.exit(1)
        result = search_pattern(sys.argv[2], sys.argv[3])
        if result:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("No se encontró patrón. Territorio nuevo.")

    elif cmd == "list":
        mem = _load_memory()
        for pid, p in mem["patterns"].items():
            print(f"  {pid}  {p['task_type']:20s}  {p['context_key'][:40]:40s}  "
                  f"éxito:{p['stats']['success_rate']*100:.0f}%  "
                  f"reusos:{p['stats']['reuses']}")

    elif cmd == "attempts":
        # Muestra historial de intentos para una tarea
        # Uso: python learning_memory.py attempts "descripcion de tarea"
        if len(sys.argv) < 3:
            print("Uso: python learning_memory.py attempts \"descripcion de tarea\"")
            sys.exit(1)
        result = get_best_method(sys.argv[2])
        if result:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print("Sin historial de intentos para esa tarea.")

    elif cmd == "context":
        # Genera contexto para Claude sobre intentos pasados
        # Uso: python learning_memory.py context "descripcion de tarea"
        if len(sys.argv) < 3:
            print("Uso: python learning_memory.py context \"descripcion de tarea\"")
            sys.exit(1)
        print(format_task_context(sys.argv[2]) or "Sin historial para esa tarea.")

    else:
        print(f"Comando desconocido: {cmd}")
        print("Comandos: stats | export [tipo] | search <type> <key> | list | attempts <tarea> | context <tarea>")
