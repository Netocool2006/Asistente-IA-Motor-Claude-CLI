"""
kb_maintenance.py — Mantenimiento del Knowledge Base
=====================================================
Implementa "olvido activo real" (limitación 6):
  - Archiva patrones no accedidos en 90 días con success_rate < 0.3
  - Rota el JSONL de acciones si crece demasiado
  - Compacta el historial de sesiones (mantiene las últimas 200)
  - Muestra estadísticas del estado del KB

Uso:
  python kb_maintenance.py --dry-run    # Ver qué se haría sin cambios
  python kb_maintenance.py --run        # Ejecutar mantenimiento
  python kb_maintenance.py --stats      # Solo estadísticas
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

def _resolve_data_dir():
    import os
    for env in ["HOME", "LOCALAPPDATA"]:
        v = os.environ.get(env)
        if v:
            c = Path(v) / (".adaptive_cli" if env == "HOME" else "ClaudeCode/.adaptive_cli")
            if c.exists(): return c
    c = Path.home() / ".adaptive_cli"; c.mkdir(parents=True, exist_ok=True); return c

ADAPTIVE_DIR       = _resolve_data_dir()
KB_ARCHIVE_FILE    = ADAPTIVE_DIR / "kb_archived.json"
SESSION_HISTORY    = ADAPTIVE_DIR / "session_history.json"
ACTIONS_LOG        = ADAPTIVE_DIR / "iteration_actions.jsonl"
EPISODIC_DB        = ADAPTIVE_DIR / "episodic.db"

DRY_RUN = "--dry-run" in sys.argv
VERBOSE = "--verbose" in sys.argv or "-v" in sys.argv


def log(msg: str):
    sys.stdout.buffer.write(
        f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n".encode("utf-8", errors="replace")
    )
    sys.stdout.buffer.flush()


def archive_low_quality_patterns(dry_run: bool = True) -> dict:
    """
    Archiva patrones con:
      - success_rate < 0.3 (falla más de 70%)
      - No accedidos en 90 días
      - Con al menos 5 usos (suficientes datos)

    Los patrones archivados se mueven a kb_archived.json
    (no se eliminan — olvido suave, no destrucción).
    """
    try:
        from knowledge_base import _load_all_domains, _load_domain, DOMAINS
    except ImportError:
        log("ERROR: No se puede importar knowledge_base.py")
        return {}

    cutoff_date = datetime.now() - timedelta(days=90)
    stats = {"checked": 0, "archived": 0, "domains": {}}
    archived_data = {}

    try:
        if KB_ARCHIVE_FILE.exists():
            archived_data = json.loads(KB_ARCHIVE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass

    all_domains = list(DOMAINS.keys())

    for domain_name in all_domains:
        try:
            data = _load_domain(domain_name)
        except Exception:
            continue

        entries   = data.get("entries", {})
        to_remove = []
        domain_archived = 0

        for eid, entry in entries.items():
            stats["checked"] += 1

            # Solo procesar patrones auto-aprendidos (no reglas de negocio manuales)
            sol = entry.get("solution", {})
            if not sol.get("auto_learned", False):
                continue

            # Calcular métricas
            accessed_str = sol.get("last_accessed", "")
            access_count = sol.get("access_count", 0)

            # Determinar cuándo fue el último acceso
            if accessed_str:
                try:
                    last_acc = datetime.fromisoformat(accessed_str)
                except Exception:
                    last_acc = datetime.now() - timedelta(days=180)  # asume viejo
            else:
                # Sin timestamp de acceso = muy viejo
                last_acc = datetime.now() - timedelta(days=180)

            # success_rate — buscar en tags/stats del patrón
            sr = sol.get("success_rate", 1.0)  # default: asumir bueno si no hay dato

            # Criterio de archivado: viejo + poco éxito + suficientes datos
            days_old = (datetime.now() - last_acc).days
            should_archive = (
                days_old > 90
                and sr < 0.3
                and access_count >= 5
            )

            if should_archive:
                if VERBOSE:
                    log(f"  → Archivar [{domain_name}] {entry.get('key','?')}: "
                        f"sr={sr:.0%}, {days_old}d sin acceso, {access_count} usos")
                to_remove.append(eid)
                archived_data.setdefault(domain_name, {})[eid] = entry
                domain_archived += 1

        if to_remove and not dry_run:
            # Reescribir domain sin los archivados
            for eid in to_remove:
                del entries[eid]
            # Guardar domain actualizado
            domain_file = PROJECT_DIR / f"kb_{domain_name}.json"
            if not domain_file.exists():
                # Buscar el archivo real
                possible = list(PROJECT_DIR.glob(f"*{domain_name}*.json"))
                if possible:
                    domain_file = possible[0]
            # Solo si encontramos el archivo
            if domain_file.exists():
                domain_file.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
                )

        if domain_archived > 0:
            stats["archived"] += domain_archived
            stats["domains"][domain_name] = domain_archived
            log(f"  [{domain_name}]: {domain_archived} patrones a archivar"
                + (" (dry-run)" if dry_run else " (archivados)"))

    if archived_data and not dry_run:
        KB_ARCHIVE_FILE.write_text(
            json.dumps(archived_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        log(f"Archivo: {KB_ARCHIVE_FILE}")

    return stats


def compact_session_history(keep: int = 200, dry_run: bool = True) -> int:
    """
    Compacta el historial de sesiones manteniendo las últimas N sesiones.
    Las más antiguas se eliminan si ya están indexadas en FTS5.
    """
    if not SESSION_HISTORY.exists():
        return 0

    try:
        with open(SESSION_HISTORY, "r", encoding="utf-8") as f:
            history = json.load(f)
    except Exception:
        return 0

    total = len(history)
    if total <= keep:
        log(f"Session history: {total} sesiones, no hay que compactar (límite={keep})")
        return 0

    to_remove = total - keep
    log(f"Session history: {total} sesiones, compactando {to_remove} más antiguas...")

    if not dry_run:
        trimmed = history[-keep:]
        tmp = SESSION_HISTORY.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(trimmed, f, indent=2, ensure_ascii=False)
        tmp.replace(SESSION_HISTORY)

    return to_remove


def rotate_actions_log(max_lines: int = 5000, dry_run: bool = True) -> int:
    """Rota el JSONL de acciones si supera el límite."""
    if not ACTIONS_LOG.exists():
        return 0

    lines = ACTIONS_LOG.read_text(encoding="utf-8").splitlines()
    total = len(lines)
    if total <= max_lines:
        log(f"Actions log: {total} líneas, no hay que rotar (límite={max_lines})")
        return 0

    excess = total - max_lines
    log(f"Actions log: {total} líneas, rotando {excess} más antiguas...")

    if not dry_run:
        ACTIONS_LOG.write_text("\n".join(lines[-max_lines:]) + "\n", encoding="utf-8")

    return excess


def _p(msg: str = ""):
    sys.stdout.buffer.write((msg + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()


def show_stats():
    """Muestra estadísticas del estado completo del sistema."""
    _p("\n" + "=" * 60)
    _p("  ESTADO DEL SISTEMA ADAPTATIVO")
    _p("=" * 60)

    # KB stats
    try:
        from knowledge_base import _load_all_domains, _load_domain, DOMAINS
        total_entries = 0
        for dn in DOMAINS:
            d = _load_domain(dn)
            cnt = len(d.get("entries", {}))
            total_entries += cnt
        _p(f"\n  Knowledge Base: {total_entries} entries en {len(DOMAINS)} dominios")
    except Exception as e:
        _p(f"\n  Knowledge Base: error ({e})")

    # Learning memory
    try:
        from learning_memory import get_stats
        lm = get_stats()
        _p(f"  Learning Memory: {lm.get('total_patterns',0)} patrones, "
              f"{lm.get('total_reuses',0)} reusos, "
              f"{lm.get('avg_success_rate',0)*100:.0f}% éxito")
    except Exception as e:
        _p(f"  Learning Memory: error ({e})")

    # Session history
    if SESSION_HISTORY.exists():
        try:
            with open(SESSION_HISTORY, "r", encoding="utf-8") as f:
                h = json.load(f)
            oldest = h[0].get("date", "?") if h else "?"
            newest = h[-1].get("date", "?") if h else "?"
            _p(f"  Session History: {len(h)} sesiones ({oldest} → {newest})")
        except Exception:
            _p("  Session History: error")
    else:
        _p("  Session History: vacío")

    # Episodic FTS5
    try:
        from episodic_index import get_stats as ep_stats
        ep = ep_stats()
        _p(f"  Episodic FTS5: {ep.get('total',0)} sesiones indexadas "
              f"({ep.get('oldest','?')} → {ep.get('newest','?')})")
    except Exception as e:
        _p(f"  Episodic FTS5: error ({e})")

    # Actions log
    if ACTIONS_LOG.exists():
        lines = ACTIONS_LOG.read_text(encoding="utf-8").splitlines()
        _p(f"  Actions Log: {len(lines)} líneas")
    else:
        _p("  Actions Log: vacío")

    # Markov
    markov_file = ADAPTIVE_DIR / "domain_markov.json"
    if markov_file.exists():
        try:
            markov = json.loads(markov_file.read_text(encoding="utf-8"))
            transitions = sum(len(v) for v in markov.values())
            _p(f"  Markov Chain: {len(markov)} dominios fuente, {transitions} transiciones")
        except Exception:
            pass

    # Co-ocurrencia
    cooccur = ADAPTIVE_DIR / "domain_cooccurrence.json"
    if cooccur.exists():
        try:
            co = json.loads(cooccur.read_text(encoding="utf-8"))
            _p(f"  Co-ocurrencia: {len(co)} dominios registrados")
        except Exception:
            pass

    _p("\n" + "=" * 60)


def main():
    if "--stats" in sys.argv or (len(sys.argv) == 1):
        show_stats()
        return

    _p(f"\nModo: {'DRY-RUN (sin cambios)' if DRY_RUN else 'EJECUTANDO'}")
    _p("-" * 40)

    log("Archivando patrones de baja calidad...")
    stats = archive_low_quality_patterns(dry_run=DRY_RUN)
    log(f"  Total: {stats.get('archived', 0)} archivados de {stats.get('checked', 0)} revisados")

    log("Compactando historial de sesiones...")
    removed = compact_session_history(keep=200, dry_run=DRY_RUN)
    if removed:
        log(f"  {removed} sesiones antiguas eliminadas")

    log("Rotando log de acciones...")
    rotated = rotate_actions_log(max_lines=5000, dry_run=DRY_RUN)
    if rotated:
        log(f"  {rotated} líneas rotadas")

    if DRY_RUN:
        _p("\nPara aplicar los cambios: python kb_maintenance.py --run")

    show_stats()


if __name__ == "__main__":
    main()
