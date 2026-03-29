"""
session_start_kb.py — Hook SessionStart: inyecta TODO el conocimiento local en contexto
========================================================================================
Se ejecuta AUTOMATICAMENTE al iniciar cualquier sesion de Claude Code CLI.
Su stdout se inyecta directamente en el contexto de Claude.

CARGA:
1. ULTIMA SESION — resumen detallado (qué se hizo, errores, soluciones)
2. HISTORIAL — últimas 10 sesiones en resumen compacto
3. LEARNING MEMORY — TODOS los patrones aprendidos con detalle
4. BUSINESS RULES — TODAS las reglas de negocio
5. KB ACTIVA — entries con hits/uso real (detalle completo)
6. KB INACTIVA — entries sin uso (solo conteo por dominio)
7. INSTRUCCIONES — cómo usar este contexto
"""

import sys
import json
import re
import time
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_DIR))

SESSION_HISTORY_FILE = Path.home() / ".adaptive_cli" / "session_history.json"
RECENT_HOURS = 1  # Ventana de contexto: ultima hora de trabajo


def filter_recent_sessions(history: list) -> list:
    """
    Filtra sesiones de la ultima hora.
    Los registros se guardan en UTC (campo time: "HH:MM:SS UTC").
    Comparamos todo en UTC para evitar desfase por zona horaria.
    Si no hay nada reciente, devuelve la ultima sesion para mantener continuidad.
    """
    from datetime import timezone
    cutoff = datetime.now(timezone.utc) - timedelta(hours=RECENT_HOURS)
    recent = []
    for s in history:
        try:
            raw = f"{s.get('date', '')} {s.get('time', '')}".replace(" UTC", "").strip()
            dt = datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                recent.append(s)
        except Exception:
            pass
    if not recent and history:
        recent = [history[-1]]
    return recent


def load_session_history() -> list:
    """Carga historial de sesiones."""
    if SESSION_HISTORY_FILE.exists():
        try:
            with open(SESSION_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, list) else []
        except Exception:
            return []
    return []


def format_last_session(session: dict) -> list:
    """
    Formatea la última sesión con detalle ACCIONABLE.
    Los campos vienen de auto_learn_hook.py:
      user_messages, files_read, files_edited, files_created,
      commands_run, errors, decisions, learning_json, metrics
    """
    lines = []
    lines.append("=" * 60)
    lines.append("  >>> ULTIMA SESION <<<")
    lines.append("=" * 60)
    lines.append(f"  Fecha: {session.get('date', '?')} {session.get('time', '?')}")
    lines.append("")

    # Resumen
    summary = session.get("summary", "")
    if summary and "sin mensajes" not in summary.lower():
        lines.append(f"  RESUMEN: {summary[:600]}")
        lines.append("")

    # Qué pidió el usuario (campos reales del hook)
    user_msgs = session.get("user_messages", []) or session.get("user_requests", [])
    if user_msgs:
        lines.append("  LO QUE PIDIO EL USUARIO:")
        for r in user_msgs[:10]:
            lines.append(f"    - {r[:200]}")
        lines.append("")

    # Archivos tocados (campos directos, no anidados en actions_taken)
    files_edited = session.get("files_edited", [])
    files_created = session.get("files_created", [])
    # También buscar en formato viejo
    actions = session.get("actions_taken", {})
    if not files_edited:
        files_edited = actions.get("files_edited", [])
    if not files_created:
        files_created = actions.get("files_created", [])

    if files_edited:
        lines.append("  ARCHIVOS EDITADOS:")
        for f in files_edited[:15]:
            lines.append(f"    * {f}")
        lines.append("")
    if files_created:
        lines.append("  ARCHIVOS CREADOS:")
        for f in files_created[:10]:
            lines.append(f"    + {f}")
        lines.append("")

    # Decisiones técnicas — MUY valiosas para continuidad
    decisions = session.get("decisions", [])
    if decisions:
        lines.append("  DECISIONES TECNICAS (por qué se hizo así):")
        for d in decisions[:10]:
            lines.append(f"    >> {d[:250]}")
        lines.append("")

    # Errores encontrados
    errors = session.get("errors", [])
    if errors:
        lines.append("  ERRORES Y SOLUCIONES:")
        for e in errors[:8]:
            lines.append(f"    [{e.get('type', '?')}] {e.get('detail', '')[:300]}")
        lines.append("")

    # Aprendizaje explícito (JSON que Claude imprime al final)
    learning = session.get("learning_json") or session.get("learning_captured", {})
    if isinstance(learning, dict) and learning.get("explicit_json"):
        learning = learning["explicit_json"]
    if isinstance(learning, dict) and learning.get("status"):
        lines.append("  APRENDIZAJE REGISTRADO:")
        lines.append(f"    Tipo: {learning.get('task_type', '?')}")
        lines.append(f"    Estrategia: {learning.get('strategy', '?')}")
        if learning.get("notes"):
            lines.append(f"    Notas: {learning['notes'][:400]}")
        if learning.get("business_rules_applied"):
            lines.append(f"    Reglas aplicadas: {', '.join(learning['business_rules_applied'])}")
        lines.append("")

    # Métricas
    metrics = session.get("metrics", {})
    if metrics and metrics.get("total_messages", 0) > 0:
        lines.append(f"  METRICAS: {metrics.get('user_messages', 0)} msgs usuario, "
                      f"{metrics.get('files_touched', 0)} archivos, "
                      f"{metrics.get('commands_count', 0)} comandos, "
                      f"{metrics.get('errors_count', 0)} errores")
        lines.append("")

    return lines


def format_session_history(history: list) -> list:
    """Formatea el historial en formato compacto. Solo sesiones con contenido real."""
    lines = []
    if len(history) <= 1:
        return lines

    lines.append("-" * 60)
    lines.append("  HISTORIAL SESIONES ANTERIORES")
    lines.append("-" * 60)

    # Últimas 10 sesiones (sin la última que ya se mostró)
    older = history[:-1][-10:]
    shown = 0
    for s in reversed(older):
        # Saltar sesiones vacías
        metrics = s.get("metrics", {})
        if metrics.get("total_messages", 0) < 5 and metrics.get("user_messages", 0) == 0:
            continue

        date = s.get("date", "?")
        time_str = s.get("time", "?")
        summary = s.get("summary", "")[:200]

        # Usar campos reales del hook
        user_msgs = s.get("user_messages", []) or s.get("user_requests", [])
        req_text = "; ".join(r[:80] for r in user_msgs[:3]) if user_msgs else ""

        files_edited = s.get("files_edited", [])
        decisions = s.get("decisions", [])
        errors = s.get("errors", [])

        lines.append(f"  [{date} {time_str}]")
        if summary and "sin mensajes" not in summary.lower():
            lines.append(f"    {summary}")
        if req_text:
            lines.append(f"    Pidio: {req_text}")
        if files_edited:
            lines.append(f"    Edito: {', '.join(Path(f).name for f in files_edited[:5])}")
        if decisions:
            lines.append(f"    Decidio: {'; '.join(d[:80] for d in decisions[:2])}")
        if errors:
            lines.append(f"    Errores: {'; '.join(e.get('detail','')[:80] for e in errors[:2])}")
        lines.append("")
        shown += 1

    if shown == 0:
        lines.append("  (Sin sesiones anteriores con contenido)")
        lines.append("")

    return lines


def format_learning_memory() -> list:
    """Exporta TODOS los patrones de learning memory con detalle completo."""
    lines = []
    try:
        from learning_memory import export_for_claude_context, get_stats
        lm_stats = get_stats()
        total_p = lm_stats.get("total_patterns", 0)
        total_r = lm_stats.get("total_reuses", 0)
        avg_sr = lm_stats.get("avg_success_rate", 0)

        lines.append("-" * 60)
        lines.append(f"  LEARNING MEMORY — {total_p} patrones, {total_r} reusos, {avg_sr*100:.0f}% exito")
        lines.append("-" * 60)

        if total_p > 0:
            by_type = lm_stats.get("patterns_by_type", {})
            lines.append(f"  Distribucion: {json.dumps(by_type, ensure_ascii=False)}")
            lines.append("")

            # Exportar TODOS los patrones (sin límite práctico)
            export = export_for_claude_context(limit=5)
            if export and "No hay patrones" not in export:
                lines.append(export)
        lines.append("")
    except Exception as e:
        lines.append(f"  Learning Memory: error cargando ({e})")
        lines.append("")

    return lines


def format_business_rules() -> list:
    """Carga reglas de negocio ACCIONABLES con ejemplos y excepciones."""
    lines = []
    try:
        from knowledge_base import _load_domain

        data = _load_domain("business_rules")
        entries = data.get("entries", {})

        # Filtrar solo reglas con contenido real
        actionable = {}
        skipped = 0
        for eid, entry in entries.items():
            key = entry.get("key", "?")
            # Saltar ruido
            if "deep_" in key:
                skipped += 1
                continue
            fact = entry.get("fact", {})
            rule = fact.get("rule", "")
            if rule and len(rule) > 20:
                actionable[eid] = entry
            else:
                skipped += 1

        lines.append("-" * 60)
        lines.append(f"  BUSINESS RULES — {len(actionable)} reglas accionables"
                      + (f" ({skipped} filtradas)" if skipped else ""))
        lines.append("-" * 60)

        # Agrupar por categoría para mejor lectura
        categories = {}
        for eid, entry in actionable.items():
            key = entry.get("key", "?")
            fact = entry.get("fact", {})
            applies_to = fact.get("applies_to", "General")

            # Categorizar por applies_to o por prefijo del key
            cat = applies_to[:40] if applies_to else "General"
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(entry)

        for cat, cat_entries in sorted(categories.items()):
            lines.append(f"")
            lines.append(f"  [{cat}]")
            for entry in cat_entries:
                fact = entry.get("fact", {})
                key = entry.get("key", "?")
                rule = fact.get("rule", "")
                exceptions = fact.get("exceptions", "")
                examples = fact.get("examples", [])

                lines.append(f"    {key}: {rule[:350]}")
                if exceptions:
                    lines.append(f"      Excepcion: {exceptions[:150]}")
                for ex in examples[:2]:
                    inp = ex.get("input", "?")
                    out = ex.get("output", "?")
                    ctx = ex.get("context", "")
                    lines.append(f"      Ej: {inp} -> {out}" + (f" ({ctx})" if ctx else ""))

        lines.append("")

    except Exception as e:
        lines.append(f"  Business Rules: error cargando ({e})")
        lines.append("")

    return lines


def _is_actionable(entry: dict) -> bool:
    """Determina si una entry tiene contenido accionable (no vacía/ruido)."""
    if entry.get("type") == "pattern":
        sol = entry.get("solution", {})
        has_strategy = bool(sol.get("strategy", "").strip())
        has_content = bool(sol.get("notes", "").strip()) or bool(sol.get("code_snippet", "").strip())
        return has_strategy and has_content
    elif entry.get("type") == "fact":
        fact = entry.get("fact", {})
        return bool(fact.get("rule", "").strip()) and len(fact.get("rule", "")) > 20
    return False


def _format_pattern_detail(entry: dict, max_code: int = 300, max_notes: int = 400) -> list:
    """Formatea un pattern con TODO el detalle necesario para ejecutar directo."""
    lines = []
    sol = entry.get("solution", {})
    key = entry.get("key", "?")
    tags = entry.get("tags", [])

    lines.append(f"    [{key}]")
    lines.append(f"      Estrategia: {sol.get('strategy', 'N/A')}")

    # Código — es lo más valioso, dar más espacio
    code = sol.get("code_snippet", "")
    if code:
        lines.append(f"      Codigo: {code[:max_code]}")

    # Notas — incluir completas, aquí está el "cómo" y el "por qué"
    notes = sol.get("notes", "")
    if notes:
        lines.append(f"      Nota: {notes[:max_notes]}")

    # Tags para búsqueda rápida
    if tags:
        lines.append(f"      Tags: {', '.join(tags[:8])}")

    return lines


def _format_fact_detail(entry: dict) -> list:
    """Formatea un fact con ejemplos y excepciones."""
    lines = []
    fact = entry.get("fact", {})
    key = entry.get("key", "?")

    lines.append(f"    [{key}]")
    lines.append(f"      Regla: {fact.get('rule', 'N/A')[:400]}")

    applies = fact.get("applies_to", "")
    if applies:
        lines.append(f"      Aplica: {applies[:150]}")

    exceptions = fact.get("exceptions", "")
    if exceptions:
        lines.append(f"      Excepcion: {exceptions[:150]}")

    # Ejemplos — muy valiosos para aplicar la regla
    examples = fact.get("examples", [])
    for ex in examples[:3]:
        inp = ex.get("input", "?")
        out = ex.get("output", "?")
        ctx = ex.get("context", "")
        lines.append(f"      Ej: {inp} -> {out}" + (f" ({ctx})" if ctx else ""))

    return lines


def format_sap_playbook() -> list:
    """Carga el SAP Playbook operativo si existe."""
    lines = []
    try:
        sys.path.insert(0, str(PROJECT_DIR))
        from sap_playbook import export_for_context, get_stats
        stats = get_stats()
        if stats.get("patterns", 0) > 0:
            export = export_for_context()
            if export:
                lines.append(export)
    except ImportError:
        pass  # sap_playbook.py no existe aún
    except Exception as e:
        lines.append(f"  SAP Playbook: error cargando ({e})")
        lines.append("")
    return lines


def format_kb_index() -> list:
    """
    Lazy-loading: solo muestra índice de dominios con conteo de entries.
    NO carga el contenido. Se busca on-demand cuando se necesita.
    """
    lines = []
    try:
        from knowledge_base import DOMAINS, _load_domain

        lines.append("-" * 60)
        lines.append("  KNOWLEDGE BASE — Índice (lazy-load)")
        lines.append("-" * 60)
        lines.append("  Para buscar: python knowledge_base.py export --query \"<tema>\"")
        lines.append("  Cross-domain: python knowledge_base.py cross-search --query \"<tema>\"")
        lines.append("")

        total = 0
        for domain_name in DOMAINS:
            if domain_name == "sessions":
                continue
            data = _load_domain(domain_name)
            entries = data.get("entries", {})
            count = len(entries)
            if count == 0:
                continue
            desc = DOMAINS[domain_name]["description"]
            lines.append(f"  [{domain_name.upper()}] {count} entries — {desc[:60]}")
            total += count

        lines.append("")
        lines.append(f"  TOTAL en disco: {total} entries (NO cargadas — buscar on-demand)")
        lines.append("")

    except Exception as e:
        lines.append(f"  KB index: error ({e})")
        lines.append("")

    return lines


def recover_crashed_session() -> list:
    """
    Detecta si la sesión anterior terminó sin guardar (crash).
    Compara el timestamp de STATE_FILE con la última entrada en session_history.
    Si STATE_FILE es más reciente, recupera las acciones del ACTIONS_LOG.
    NO modifica ningún archivo existente si no hay crash.
    """
    STATE_FILE  = Path.home() / ".adaptive_cli" / "iteration_state.json"
    ACTIONS_LOG = Path.home() / ".adaptive_cli" / "iteration_actions.jsonl"

    try:
        if not STATE_FILE.exists() or not ACTIONS_LOG.exists():
            return []

        state   = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        old_sid = state.get("sid", "")
        last_ts = state.get("last_ts", 0)

        if not old_sid or not last_ts:
            return []

        # Solo crash relevante si fue en las últimas 24h
        if time.time() - last_ts > 86400:
            return []

        # Verificar si ya fue guardado normalmente en session_history
        history = load_session_history()
        if history:
            last_saved = history[-1]
            try:
                saved_dt = datetime.strptime(
                    f"{last_saved.get('date', '')} {last_saved.get('time', '')}",
                    "%Y-%m-%d %H:%M:%S"
                )
                state_dt = datetime.fromtimestamp(last_ts)
                if saved_dt >= state_dt:
                    return []  # Se guardó correctamente después del último tool use
            except Exception:
                pass

        # Leer acciones no guardadas del ACTIONS_LOG
        recovered = []
        try:
            with open(ACTIONS_LOG, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        a = json.loads(line)
                        if a.get("_sid") == old_sid:
                            recovered.append(a)
                    except Exception:
                        pass
        except Exception:
            return []

        if not recovered:
            return []

        # Construir resumen de la sesión recuperada
        files_touched = list(set(a.get("file", "") for a in recovered if a.get("file")))
        tools_used    = [a.get("tool", "") for a in recovered]
        last_actions  = [a.get("action", "") for a in recovered[-5:] if a.get("action")]

        lines = []
        lines.append("  ⚠ SESION RECUPERADA (crash detectado):")
        lines.append(f"  {len(recovered)} acciones de la sesión anterior no fueron guardadas.")
        if files_touched:
            lines.append(f"  Archivos trabajados: {', '.join(Path(f).name for f in files_touched[:8])}")
        if last_actions:
            lines.append("  Ultimas acciones antes del crash:")
            for a in last_actions:
                lines.append(f"    - {a[:120]}")
        lines.append("")

        # Guardar como sesión recuperada en session_history para no perder el trabajo
        recovery_entry = {
            "date":         datetime.now().strftime("%Y-%m-%d"),
            "time":         datetime.now().strftime("%H:%M:%S"),
            "summary":      f"[RECUPERADA] {len(recovered)} acciones de sesión que terminó sin guardar",
            "user_messages": [],
            "files_edited":  [a.get("file", "") for a in recovered if a.get("tool") == "Edit" and a.get("file")],
            "files_created": [a.get("file", "") for a in recovered if a.get("tool") == "Write" and a.get("file")],
            "errors":        [],
            "decisions":     [],
            "metrics": {
                "total_messages": len(recovered),
                "user_messages":  0,
                "files_touched":  len(files_touched),
                "commands_count": sum(1 for t in tools_used if t == "Bash"),
                "errors_count":   0,
            },
            "_recovered": True,
            "_original_sid": old_sid,
        }
        history.append(recovery_entry)
        SESSION_HISTORY_FILE.write_text(
            json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # Marcar STATE_FILE como procesado para no recuperar dos veces
        state["_recovered"] = True
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        return lines

    except Exception:
        return []


def main():
    lines = []

    # ═══════════════════════════════════════════════════════════
    # HEADER
    # ═══════════════════════════════════════════════════════════
    lines.append("=" * 60)
    lines.append("  CONTEXTO AUTOMATICO — Ultima hora de trabajo")
    lines.append("=" * 60)
    lines.append("")

    # ═══════════════════════════════════════════════════════════
    # 0) CRASH RECOVERY — acciones no guardadas + último estado
    # ═══════════════════════════════════════════════════════════
    crash_lines = []

    # Nuevo: recuperar acciones del JSONL si la sesión anterior crasheó
    recovered = recover_crashed_session()
    if recovered:
        crash_lines.extend(recovered)

    # Existente: último mensaje del usuario y última acción de Claude
    last_msg_file    = Path.home() / ".adaptive_cli" / "last_user_message.txt"
    last_action_file = Path.home() / ".adaptive_cli" / "last_claude_action.txt"
    if last_msg_file.exists():
        try:
            content = last_msg_file.read_text(encoding="utf-8").strip()
            if content:
                msg_text = "\n".join(content.split("\n")[1:]).strip()
                if msg_text:
                    crash_lines.append(f"  Tu ultimo mensaje: {msg_text[:300]}")
        except Exception:
            pass
    if last_action_file.exists():
        try:
            content = last_action_file.read_text(encoding="utf-8").strip()
            if content:
                action_lines = content.split("\n")
                crash_lines.append(f"  Yo estaba en: {action_lines[0]}")
                for al in action_lines[1:]:
                    crash_lines.append(f"    {al.strip()}")
        except Exception:
            pass
    if crash_lines:
        lines.append("  >>> CRASH RECOVERY <<<")
        lines.extend(crash_lines)
        lines.append("")

    # ═══════════════════════════════════════════════════════════
    # 1) SESIONES RECIENTES — ultima hora de trabajo
    # ═══════════════════════════════════════════════════════════
    history = load_session_history()
    recent  = filter_recent_sessions(history) if history else []

    if recent:
        last = recent[-1]

        # Health check de captura
        last_metrics   = last.get("metrics", {})
        last_total_msgs = last_metrics.get("total_messages", 0)
        last_user_msgs  = last_metrics.get("user_messages", 0)
        last_files      = last_metrics.get("files_touched", 0)
        last_cmds       = last_metrics.get("commands_count", 0)
        last_extracted  = last_user_msgs + last_files + last_cmds

        if last_total_msgs > 10 and last_extracted == 0:
            lines.append("!" * 60)
            lines.append("  HOOK HEALTH CHECK: FALLO DE CAPTURA")
            lines.append(f"  Sesion anterior: {last_total_msgs} msgs pero "
                         f"0 capturados. Revisar auto_learn_hook.py")
            lines.append("!" * 60)
            lines.append("")
        elif last_total_msgs > 5:
            lines.append(f"  [Hook OK | {last_user_msgs} msgs, "
                         f"{last_files} archivos, {last_cmds} cmds]")
            lines.append("")

        # Detalle de la ultima sesion
        lines.extend(format_last_session(last))

        # Sesiones anteriores dentro de la ultima hora (max 3)
        if len(recent) > 1:
            older = recent[:-1][-3:]
            lines.append("-" * 60)
            lines.append(f"  SESIONES ANTERIORES (ultima hora: {len(older)} sesiones)")
            lines.append("-" * 60)
            for s in reversed(older):
                date    = s.get("date", "?")
                time_s  = s.get("time", "?")
                summary = s.get("summary", "")[:150]
                errors  = s.get("errors", [])
                lines.append(f"  [{date} {time_s}] {summary}")
                if errors:
                    lines.append(f"    Errores: {'; '.join(e.get('detail','')[:80] for e in errors[:2])}")
            lines.append("")

    else:
        lines.append("  [Sin sesiones en la ultima hora]")
        lines.append("")

    # ═══════════════════════════════════════════════════════════
    # 2) PATRONES APRENDIDOS — top 5, el resto se busca on-demand
    # ═══════════════════════════════════════════════════════════
    lines.extend(format_learning_memory())

    # ═══════════════════════════════════════════════════════════
    # 5) ARCHIVOS CLAVE + INSTRUCCIONES
    # ═══════════════════════════════════════════════════════════
    lines.append("-" * 60)
    lines.append("  ARCHIVOS CLAVE DEL PROYECTO")
    lines.append("-" * 60)
    lines.append("  dashboard.py — Flask backend (API endpoints)")
    lines.append("  dashboard_web/devin_mirror/index.html — Frontend (mirror devin.ai)")
    lines.append("  brand_mirror.py — Rebuild script del mirror")
    lines.append("  knowledge_base.py — KB multi-dominio (13 dominios)")
    lines.append("  sap_playbook.py — SAP CRM automation (patrones, blacklist, JS helpers)")
    lines.append("  learning_memory.py — Patrones aprendidos")
    lines.append("  ingest_documents.py — Ingestion de documentos")
    lines.append("  Backup en: C:/Chance1/backup_Asistente/")
    lines.append("")
    lines.append("=" * 60)
    lines.append("  INSTRUCCIONES CRITICAS — LEER ANTES DE CADA TAREA")
    lines.append("=" * 60)
    lines.append("  1. El contexto de arriba ES tu memoria reciente (ultima hora).")
    lines.append("  2. Al recibir cada tarea, la experiencia relevante ya viene inyectada.")
    lines.append("  3. NO repitas errores previos: los patrones muestran que fallo antes.")
    lines.append("  4. REGLA MID-EXECUTION: si a medio trabajo encuentras algo nuevo o")
    lines.append("     diferente que no esta en tu contexto inicial, PRIMERO consulta")
    lines.append("     el KB local antes de usar tu entrenamiento:")
    lines.append("       python \"C:\\Chance1\\Asistente IA\\knowledge_base.py\" export --query \"<tema>\"")
    lines.append("     Si el KB no tiene nada, entonces usa tu entrenamiento.")
    lines.append("     Esto evita reinventar soluciones que ya existen localmente.")
    lines.append("  5. Si resuelves algo nuevo a medio proceso, al terminar quedara")
    lines.append("     guardado automaticamente para la proxima vez.")
    lines.append("=" * 60)

    # ═══════════════════════════════════════════════════════════
    # 6) MEMORIA CROSS-SESIÓN — sesiones relevantes al tema actual
    # ═══════════════════════════════════════════════════════════
    try:
        last_msg_path = Path.home() / ".adaptive_cli" / "last_user_message.txt"
        if last_msg_path.exists():
            last_msg_text = last_msg_path.read_text(encoding="utf-8").strip()
            # Extraer keywords del último mensaje (ignorar primera línea de timestamp)
            msg_lines = last_msg_text.split("\n")
            msg_body  = " ".join(msg_lines[1:]) if len(msg_lines) > 1 else last_msg_text
            kws = re.findall(r'\b[a-zA-Z]{4,}\b', msg_body.lower())
            query = " ".join(kws[:6])
            if query:
                from episodic_index import search as ep_search
                cross_results = ep_search(query, limit=3)
                if cross_results:
                    lines.append("-" * 60)
                    lines.append("  MEMORIA CROSS-SESION — sesiones previas relevantes al tema")
                    lines.append("-" * 60)
                    for r in cross_results:
                        d = r.get("date", "?")
                        dom = r.get("domain", "?")
                        s = r.get("summary", "")[:150]
                        snip = r.get("snippet", "")[:120]
                        lines.append(f"  [{d}/{dom}] {s}")
                        if snip:
                            lines.append(f"    ...{snip}...")
                    lines.append("")
    except Exception:
        pass

    # Imprimir todo a stdout
    output = "\n".join(lines)
    sys.stdout.buffer.write(output.encode("utf-8", errors="replace"))
    sys.stdout.buffer.write(b"\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
