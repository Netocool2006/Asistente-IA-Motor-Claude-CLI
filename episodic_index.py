"""
episodic_index.py — Memoria episódica cross-sesión con SQLite FTS5
==================================================================
Indexa session_history.json en SQLite FTS5 para búsqueda full-text
de sesiones anteriores por keywords.

API pública:
  index_session(record)    — indexa/actualiza una sesión
  search(query, limit=3)   — FTS5 search, retorna [{date, domain, snippet}]
  rebuild_from_history()   — reconstruye desde session_history.json
  get_stats()              — estadísticas del índice

Usado por:
  on_user_message.py  → search()        (inyecta contexto de sesiones pasadas)
  auto_learn_hook.py  → index_session() (indexa al cerrar cada sesión)
"""

import json
import sqlite3
import re
from pathlib import Path
from datetime import datetime

def _resolve_data_dir():
    import os
    for env in ["HOME", "LOCALAPPDATA"]:
        v = os.environ.get(env)
        if v:
            c = Path(v) / (".adaptive_cli" if env == "HOME" else "ClaudeCode/.adaptive_cli")
            if c.exists(): return c
    c = Path.home() / ".adaptive_cli"; c.mkdir(parents=True, exist_ok=True); return c

_DATA_DIR    = _resolve_data_dir()
DB_PATH      = _DATA_DIR / "episodic_index.db"
HISTORY_FILE = _DATA_DIR / "session_history.json"


# ── Conexión y esquema ─────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_schema(conn: sqlite3.Connection):
    """
    Tabla FTS5 standalone (almacena su propio contenido).
    Más simple y confiable que content= mode con triggers.
    """
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions_meta (
            session_id  TEXT PRIMARY KEY,
            date        TEXT,
            domain      TEXT,
            body        TEXT,
            indexed_at  TEXT
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS sessions_fts
        USING fts5(session_id, date, domain, body, tokenize='unicode61');
    """)
    conn.commit()


# ── Construcción del texto indexable ──────────────────────────

def _build_body(record: dict) -> str:
    """
    Construye el texto indexable de una sesión combinando todos los campos
    relevantes: summary, mensajes de usuario, decisiones, errores, archivos.
    """
    parts = []

    summary = record.get("summary", "")
    if summary:
        parts.append(summary[:400])

    skip_prefixes = (
        "This session is being continued", "Summary:", "<task-notification",
        "<system-reminder", "<available-deferred-tools",
    )
    for msg in record.get("user_messages", [])[:20]:
        if isinstance(msg, str) and msg.strip():
            m = msg.strip()
            if len(m) > 3 and not any(m.startswith(p) for p in skip_prefixes):
                parts.append(m[:200])

    for dec in record.get("decisions", [])[:10]:
        if isinstance(dec, str):
            parts.append(dec[:150])

    for err in record.get("errors", [])[:5]:
        if isinstance(err, dict):
            d = err.get("detail", "")
            if d:
                parts.append(d[:150])
        elif isinstance(err, str) and err:
            parts.append(err[:150])

    for f in list(record.get("files_edited", []))[:10] + list(record.get("files_created", []))[:10]:
        if f:
            parts.append(Path(f).name)

    cwd = record.get("cwd", "")
    if cwd:
        parts.append(Path(cwd).name)

    return " | ".join(p for p in parts if p.strip())[:3000]


def _detect_domain(record: dict) -> str:
    """Extrae el dominio dominante del registro."""
    domain = record.get("domain", "")
    if domain:
        return domain
    text = " ".join(
        record.get("user_messages", []) +
        record.get("files_edited", []) +
        record.get("files_created", [])
    ).lower()
    for kw, dom in [
        ("playwright", "sap_tierra"), ("sap", "sap_tierra"), ("crm", "sap_tierra"),
        ("sow", "sow"), ("propuesta", "sow"), ("contrato", "sow"),
        ("bom", "bom"), ("listado", "bom"), ("material", "bom"),
        ("monday", "monday"), ("pipeline", "monday"),
        ("outlook", "outlook"), ("correo", "outlook"),
    ]:
        if kw in text:
            return dom
    return "files"


# ── API pública ────────────────────────────────────────────────

def index_session(record: dict):
    """
    Indexa o actualiza una sesión.
    Usa DELETE + INSERT para garantizar consistencia en ambas tablas.
    """
    session_id = record.get("session_id", "")
    if not session_id:
        return

    date   = record.get("date", "")
    if not date and record.get("timestamp"):
        date = record["timestamp"][:10]
    domain = _detect_domain(record)
    body   = _build_body(record)
    now    = datetime.now().isoformat()

    if not body.strip():
        return

    try:
        conn = _connect()
        _ensure_schema(conn)

        # Eliminar entrada previa (meta + fts)
        conn.execute("DELETE FROM sessions_fts WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM sessions_meta WHERE session_id = ?", (session_id,))

        # Insertar nueva
        conn.execute(
            "INSERT INTO sessions_meta (session_id, date, domain, body, indexed_at) VALUES (?,?,?,?,?)",
            (session_id, date, domain, body, now)
        )
        conn.execute(
            "INSERT INTO sessions_fts (session_id, date, domain, body) VALUES (?,?,?,?)",
            (session_id, date, domain, body)
        )

        conn.commit()
        conn.close()
    except Exception:
        pass


def search(query: str, limit: int = 3) -> list:
    """
    Búsqueda FTS5 sobre sesiones anteriores.
    Retorna [{date, domain, snippet}] ordenada por relevancia BM25.
    """
    if not query or not query.strip():
        return []
    if not DB_PATH.exists():
        return []

    try:
        conn = _connect()
        _ensure_schema(conn)

        # Sanitizar: solo palabras alfanuméricas, espacios para AND implícito
        tokens = re.findall(r'[a-zA-Z0-9áéíóúñüÁÉÍÓÚÑÜ_]{2,}', query)
        if not tokens:
            conn.close()
            return []
        # OR entre tokens: BM25 rankea primero los que tienen más matches
        safe_query = " OR ".join(tokens)

        rows = conn.execute(
            """
            SELECT date, domain,
                   snippet(sessions_fts, 3, '«', '»', '...', 12) AS snip
            FROM sessions_fts
            WHERE body MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (safe_query, limit)
        ).fetchall()

        conn.close()
        return [
            {"date": r["date"] or "?", "domain": r["domain"] or "?", "snippet": r["snip"] or ""}
            for r in rows
        ]

    except Exception:
        return []


def rebuild_from_history() -> int:
    """
    Reconstruye el índice completo desde session_history.json.
    Borra la DB existente y re-indexa todas las sesiones.
    """
    if not HISTORY_FILE.exists():
        return 0
    try:
        history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return 0
    if not isinstance(history, list):
        return 0

    # Reset limpio — unlink preferido, fallback a DROP TABLE si Windows tiene el archivo bloqueado
    if DB_PATH.exists():
        try:
            DB_PATH.unlink()
        except OSError:
            try:
                conn = _connect()
                conn.executescript(
                    "DROP TABLE IF EXISTS sessions_fts; DROP TABLE IF EXISTS sessions_meta;"
                )
                conn.commit()
                conn.close()
            except Exception:
                pass

    count = 0
    for record in history:
        if isinstance(record, dict) and record.get("session_id"):
            index_session(record)
            count += 1
    return count


def get_stats() -> dict:
    """Estadísticas del índice."""
    if not DB_PATH.exists():
        return {"indexed_sessions": 0, "db_size_kb": 0}
    try:
        conn = _connect()
        _ensure_schema(conn)
        n = conn.execute("SELECT COUNT(*) FROM sessions_meta").fetchone()[0]
        conn.close()
        size_kb = round(DB_PATH.stat().st_size / 1024, 1)
        return {"indexed_sessions": n, "db_size_kb": size_kb}
    except Exception:
        return {"indexed_sessions": 0, "db_size_kb": 0}


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "rebuild":
        n = rebuild_from_history()
        print(f"Rebuilt: {n} sessions indexed")
        print(get_stats())
    elif cmd == "search":
        q = " ".join(sys.argv[2:])
        results = search(q, limit=5)
        if results:
            for r in results:
                print(f"[{r['date']}/{r['domain']}] {r['snippet']}")
        else:
            print("Sin resultados")
    else:
        print(get_stats())
