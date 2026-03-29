"""
save_session.py — Plan B: guardar resumen de sesion manualmente
================================================================
Si el hook Stop no captura el transcript, Claude puede llamar este script
antes de cerrar para guardar un resumen manual de lo que se hizo.

Uso:
    python save_session.py "resumen de lo que se hizo" --requests "lo que pidio el usuario" --errors "errores encontrados" --decisions "decisiones tomadas" --files-edited "archivo1.py,archivo2.py"

    O modo interactivo (pipe JSON):
    echo '{"summary": "...", "user_messages": [...]}' | python save_session.py --json
"""

import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone

SESSION_HISTORY_FILE = Path.home() / ".adaptive_cli" / "session_history.json"
MAX_SESSIONS = 20


def load_history() -> list:
    SESSION_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SESSION_HISTORY_FILE.exists():
        try:
            with open(SESSION_HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_history(history: list):
    SESSION_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    history = history[-MAX_SESSIONS:]
    tmp = SESSION_HISTORY_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    tmp.replace(SESSION_HISTORY_FILE)


def main():
    parser = argparse.ArgumentParser(description="Guardar resumen de sesion manualmente")
    parser.add_argument("summary", nargs="?", default="", help="Resumen de la sesion")
    parser.add_argument("--requests", default="", help="Lo que pidio el usuario (separado por |)")
    parser.add_argument("--errors", default="", help="Errores encontrados (separado por |)")
    parser.add_argument("--decisions", default="", help="Decisiones tomadas (separado por |)")
    parser.add_argument("--files-read", default="", help="Archivos leidos (separado por ,)")
    parser.add_argument("--files-edited", default="", help="Archivos editados (separado por ,)")
    parser.add_argument("--files-created", default="", help="Archivos creados (separado por ,)")
    parser.add_argument("--json", action="store_true", help="Leer JSON completo desde stdin")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)

    if args.json:
        try:
            record = json.loads(sys.stdin.read())
        except json.JSONDecodeError:
            print("Error: JSON invalido en stdin")
            sys.exit(1)
        # Asegurar campos minimos
        record.setdefault("session_id", now.strftime("manual_%Y%m%d_%H%M%S"))
        record.setdefault("date", now.strftime("%Y-%m-%d"))
        record.setdefault("time", now.strftime("%H:%M:%S UTC"))
        record.setdefault("source", "manual_save")
    else:
        record = {
            "session_id": now.strftime("manual_%Y%m%d_%H%M%S"),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S UTC"),
            "source": "manual_save",
            "summary": args.summary or "Sesion guardada manualmente",
            "user_messages": [r.strip() for r in args.requests.split("|") if r.strip()] if args.requests else [],
            "files_read": [f.strip() for f in args.files_read.split(",") if f.strip()] if args.files_read else [],
            "files_edited": [f.strip() for f in args.files_edited.split(",") if f.strip()] if args.files_edited else [],
            "files_created": [f.strip() for f in args.files_created.split(",") if f.strip()] if args.files_created else [],
            "errors": [{"type": "reported", "detail": e.strip()} for e in args.errors.split("|") if e.strip()] if args.errors else [],
            "decisions": [d.strip() for d in args.decisions.split("|") if d.strip()] if args.decisions else [],
            "commands_run": [],
            "searches": [],
            "learning_json": None,
            "metrics": {
                "total_messages": 0,
                "user_messages": 0,
                "errors_count": 0,
                "files_touched": 0,
                "commands_count": 0,
                "decisions_count": 0,
            },
        }

    # Importar merge logic del hook principal
    hook_dir = Path(__file__).parent / ".claude" / "hooks"
    sys.path.insert(0, str(hook_dir))
    try:
        from auto_learn_hook import find_existing_session, _merge_sessions
        has_merge = True
    except ImportError:
        has_merge = False

    history = load_history()

    if has_merge:
        idx = find_existing_session(history, record)
        if idx >= 0:
            history[idx] = _merge_sessions(history[idx], record)
            action = f"Merge con sesion existente (idx={idx}, merges={history[idx].get('merge_count', 1)})"
        else:
            history.append(record)
            action = "Nueva sesion agregada"
    else:
        history.append(record)
        action = "Nueva sesion agregada (sin merge disponible)"

    save_history(history)

    print(f"{action}")
    print(f"Sesion: {record['session_id']}")
    print(f"Historial: {len(history)} sesiones")
    print(f"Archivo: {SESSION_HISTORY_FILE}")


if __name__ == "__main__":
    main()
