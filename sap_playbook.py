"""
sap_playbook.py — Playbook operativo para SAP CRM WebUI
========================================================
Sistema de aprendizaje persistente para automatización SAP.

Diseñado para:
- Guardar patrones por pantalla/campo/acción con selectores exactos
- Tracking de técnicas exitosas Y fallidas (blacklist)
- Confidence scoring con decay temporal
- Lookup instantáneo por key semántica (sap.opportunity.items.quantity)
- Helpers JS persistidos y versionados
- Frame paths aprendidos por pantalla
- Integración con Claude in Chrome y JS Injection

Uso desde Claude CLI:
    from sap_playbook import lookup, learn, fail, get_helpers, get_blacklist

Uso como CLI:
    python sap_playbook.py lookup "sap.opportunity.items.insert"
    python sap_playbook.py stats
    python sap_playbook.py export
"""

import json
import time
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

# ── Config ────────────────────────────────────────────────────
def _resolve_data_dir():
    import os
    for env in ["HOME", "LOCALAPPDATA"]:
        v = os.environ.get(env)
        if v:
            c = Path(v) / (".adaptive_cli" if env == "HOME" else "ClaudeCode/.adaptive_cli")
            if c.exists(): return c
    c = Path.home() / ".adaptive_cli"; c.mkdir(parents=True, exist_ok=True); return c

DB_DIR = _resolve_data_dir()
DB_PATH = DB_DIR / "sap_playbook.db"

# Decay: patterns pierden confianza si no se usan en X días
CONFIDENCE_DECAY_DAYS = 30
CONFIDENCE_DECAY_RATE = 0.1  # pierde 10% por periodo sin uso

# ── Database ──────────────────────────────────────────────────

_conn = None


def _get_db() -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        return _conn
    DB_DIR.mkdir(parents=True, exist_ok=True)
    _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    _conn.execute("PRAGMA journal_mode=WAL")
    _conn.execute("PRAGMA synchronous=NORMAL")
    _conn.row_factory = sqlite3.Row
    _init_schema(_conn)
    return _conn


def _init_schema(db: sqlite3.Connection):
    """Crea tablas si no existen."""
    db.executescript("""
        -- Patrones exitosos (lo que SÍ funciona)
        CREATE TABLE IF NOT EXISTS patterns (
            key TEXT PRIMARY KEY,
            screen TEXT NOT NULL,
            action TEXT NOT NULL,
            field TEXT DEFAULT '',
            technique TEXT NOT NULL,
            tool TEXT NOT NULL,
            selector TEXT DEFAULT '',
            frame_path TEXT DEFAULT '',
            steps TEXT DEFAULT '[]',
            code_snippet TEXT DEFAULT '',
            preconditions TEXT DEFAULT '',
            success_signals TEXT DEFAULT '',
            fail_signals TEXT DEFAULT '',
            fallback_key TEXT DEFAULT '',
            confidence REAL DEFAULT 1.0,
            uses INTEGER DEFAULT 1,
            successes INTEGER DEFAULT 1,
            failures INTEGER DEFAULT 0,
            last_used TEXT,
            last_success TEXT,
            created TEXT,
            updated TEXT,
            notes TEXT DEFAULT '',
            tags TEXT DEFAULT '[]'
        );

        -- Técnicas fallidas (lo que NO funciona — blacklist)
        CREATE TABLE IF NOT EXISTS blacklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            screen TEXT NOT NULL,
            action TEXT NOT NULL,
            field TEXT DEFAULT '',
            technique TEXT NOT NULL,
            reason TEXT NOT NULL,
            error_detail TEXT DEFAULT '',
            created TEXT,
            still_valid INTEGER DEFAULT 1
        );

        -- Helpers JS reutilizables
        CREATE TABLE IF NOT EXISTS js_helpers (
            name TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            description TEXT DEFAULT '',
            sap_specific INTEGER DEFAULT 0,
            version INTEGER DEFAULT 1,
            last_used TEXT,
            created TEXT,
            updated TEXT
        );

        -- Frame paths por pantalla
        CREATE TABLE IF NOT EXISTS frame_paths (
            screen TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            js_access TEXT DEFAULT '',
            confidence REAL DEFAULT 1.0,
            last_verified TEXT,
            notes TEXT DEFAULT ''
        );

        -- Log de intentos (para análisis)
        CREATE TABLE IF NOT EXISTS attempt_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT,
            screen TEXT,
            action TEXT,
            technique TEXT,
            success INTEGER,
            duration_ms INTEGER DEFAULT 0,
            error TEXT DEFAULT '',
            timestamp TEXT
        );

        -- Índice para búsqueda rápida
        CREATE INDEX IF NOT EXISTS idx_patterns_screen ON patterns(screen);
        CREATE INDEX IF NOT EXISTS idx_patterns_action ON patterns(action);
        CREATE INDEX IF NOT EXISTS idx_blacklist_screen ON blacklist(screen, action);
        CREATE INDEX IF NOT EXISTS idx_attempt_log_key ON attempt_log(key);
    """)
    db.commit()


# ── Lookup (PRIMERA cosa que debe hacer el agente) ────────────

def lookup(key: str = None, screen: str = None, action: str = None,
           field: str = None) -> dict:
    """
    Busca patrón aplicable. Retorna el mejor match con confidence.

    Uso:
        lookup("sap.opportunity.items.insert.product_id")
        lookup(screen="opportunity", action="insert_item")
        lookup(screen="opportunity", action="fill", field="quantity")
    """
    db = _get_db()
    now = datetime.now().isoformat()

    # Búsqueda por key exacta
    if key:
        row = db.execute("SELECT * FROM patterns WHERE key = ?", (key,)).fetchone()
        if row:
            pattern = dict(row)
            pattern["steps"] = json.loads(pattern["steps"])
            pattern["tags"] = json.loads(pattern["tags"])
            # Aplicar decay
            pattern["confidence"] = _calc_confidence(pattern)
            # Verificar blacklist
            pattern["blacklisted_alternatives"] = _get_blacklist(
                pattern["screen"], pattern["action"], pattern.get("field", ""))
            return {"found": True, "pattern": pattern}

    # Búsqueda por screen + action + field
    if screen:
        query = "SELECT * FROM patterns WHERE screen = ?"
        params = [screen]
        if action:
            query += " AND action = ?"
            params.append(action)
        if field:
            query += " AND field = ?"
            params.append(field)
        query += " ORDER BY confidence DESC, successes DESC LIMIT 5"

        rows = db.execute(query, params).fetchall()
        if rows:
            results = []
            for row in rows:
                p = dict(row)
                p["steps"] = json.loads(p["steps"])
                p["tags"] = json.loads(p["tags"])
                p["confidence"] = _calc_confidence(p)
                results.append(p)
            return {"found": True, "patterns": results, "best": results[0]}

    # Búsqueda fuzzy por key parcial
    if key:
        rows = db.execute(
            "SELECT * FROM patterns WHERE key LIKE ? ORDER BY confidence DESC LIMIT 5",
            (f"%{key}%",)
        ).fetchall()
        if rows:
            results = []
            for row in rows:
                p = dict(row)
                p["steps"] = json.loads(p["steps"])
                p["tags"] = json.loads(p["tags"])
                p["confidence"] = _calc_confidence(p)
                results.append(p)
            return {"found": True, "patterns": results, "best": results[0]}

    return {"found": False, "blacklist": _get_blacklist(screen or "", action or "", field or "")}


def _calc_confidence(pattern: dict) -> float:
    """Calcula confidence con decay temporal."""
    base = pattern.get("confidence", 1.0)
    last_used = pattern.get("last_used", "")
    if not last_used:
        return base

    try:
        last = datetime.fromisoformat(last_used)
        days_ago = (datetime.now() - last).days
        periods = days_ago / CONFIDENCE_DECAY_DAYS
        decayed = base * ((1 - CONFIDENCE_DECAY_RATE) ** periods)
        return round(max(0.1, decayed), 3)
    except (ValueError, TypeError):
        return base


# ── Learn (guardar patrón exitoso) ────────────────────────────

def learn(key: str, screen: str, action: str, technique: str, tool: str,
          field: str = "", selector: str = "", frame_path: str = "",
          steps: list = None, code_snippet: str = "", preconditions: str = "",
          success_signals: str = "", fail_signals: str = "",
          fallback_key: str = "", notes: str = "", tags: list = None):
    """
    Registra un patrón exitoso.

    Uso:
        learn(
            key="sap.opportunity.items.insert.product_id",
            screen="opportunity_items",
            action="insert_item",
            technique="js_simulateType_then_enter",
            tool="javascript_tool",
            field="product_id",
            selector="input[id*='orderedprod']",
            frame_path="window.frames[0].frames[1]",
            steps=["locate empty orderedprod input", "simulateType(input, pid)", "simulateEnter(input)", "wait 2s"],
            code_snippet="var inp = f.document.querySelector('input[id*=orderedprod]'); simulateType(inp, 'LLML245'); simulateEnter(inp);",
            preconditions="items tab open, insert clicked",
            success_signals="product resolved, description appears",
            fail_signals="input not found, no resolution after 5s",
            fallback_key="sap.opportunity.items.insert.product_id.claude_type",
            notes="JS es más rápido que Claude type para Product ID"
        )
    """
    db = _get_db()
    now = datetime.now().isoformat()

    existing = db.execute("SELECT * FROM patterns WHERE key = ?", (key,)).fetchone()

    if existing:
        # Update: incrementar uses, successes, actualizar confidence
        new_successes = existing["successes"] + 1
        new_uses = existing["uses"] + 1
        new_confidence = min(1.0, new_successes / new_uses)
        db.execute("""
            UPDATE patterns SET
                technique = ?, tool = ?, selector = ?, frame_path = ?,
                steps = ?, code_snippet = ?, preconditions = ?,
                success_signals = ?, fail_signals = ?, fallback_key = ?,
                confidence = ?, uses = ?, successes = ?,
                last_used = ?, last_success = ?, updated = ?,
                notes = ?, tags = ?
            WHERE key = ?
        """, (technique, tool, selector, frame_path,
              json.dumps(steps or [], ensure_ascii=False), code_snippet,
              preconditions, success_signals, fail_signals, fallback_key,
              new_confidence, new_uses, new_successes,
              now, now, now,
              notes, json.dumps(tags or [], ensure_ascii=False), key))
    else:
        db.execute("""
            INSERT INTO patterns (key, screen, action, field, technique, tool,
                selector, frame_path, steps, code_snippet, preconditions,
                success_signals, fail_signals, fallback_key,
                confidence, uses, successes, failures,
                last_used, last_success, created, updated, notes, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (key, screen, action, field, technique, tool,
              selector, frame_path,
              json.dumps(steps or [], ensure_ascii=False), code_snippet,
              preconditions, success_signals, fail_signals, fallback_key,
              1.0, 1, 1, 0,
              now, now, now, now, notes,
              json.dumps(tags or [], ensure_ascii=False)))

    # Log del intento exitoso
    db.execute("""
        INSERT INTO attempt_log (key, screen, action, technique, success, timestamp)
        VALUES (?, ?, ?, ?, 1, ?)
    """, (key, screen, action, technique, now))

    db.commit()
    return {"status": "learned", "key": key, "confidence": 1.0}


# ── Fail (registrar técnica fallida) ──────────────────────────

def fail(key: str = "", screen: str = "", action: str = "",
         technique: str = "", reason: str = "", error_detail: str = "",
         field: str = "", blacklist: bool = True):
    """
    Registra un fallo. Si blacklist=True, agrega a la blacklist.

    Uso:
        fail(
            screen="opportunity_items",
            action="fill_quantity",
            technique="js_simulateType",
            reason="SAP no reconoce valor escrito por JS puro",
            blacklist=True
        )
    """
    db = _get_db()
    now = datetime.now().isoformat()

    # Actualizar pattern si existe
    if key:
        existing = db.execute("SELECT * FROM patterns WHERE key = ?", (key,)).fetchone()
        if existing:
            new_failures = existing["failures"] + 1
            new_uses = existing["uses"] + 1
            new_confidence = max(0.1, existing["successes"] / new_uses)
            db.execute("""
                UPDATE patterns SET failures = ?, uses = ?, confidence = ?,
                    last_used = ?, updated = ?
                WHERE key = ?
            """, (new_failures, new_uses, new_confidence, now, now, key))

    # Agregar a blacklist
    if blacklist and technique:
        db.execute("""
            INSERT INTO blacklist (screen, action, field, technique, reason,
                error_detail, created)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (screen, action, field, technique, reason, error_detail, now))

    # Log del intento fallido
    db.execute("""
        INSERT INTO attempt_log (key, screen, action, technique, success,
            error, timestamp)
        VALUES (?, ?, ?, ?, 0, ?, ?)
    """, (key, screen, action, technique, reason, now))

    db.commit()
    return {"status": "recorded", "blacklisted": blacklist}


def _get_blacklist(screen: str, action: str, field: str = "") -> list:
    """Obtiene técnicas en blacklist para una pantalla/acción."""
    db = _get_db()
    query = "SELECT technique, reason FROM blacklist WHERE still_valid = 1"
    params = []
    if screen:
        query += " AND screen = ?"
        params.append(screen)
    if action:
        query += " AND action = ?"
        params.append(action)
    rows = db.execute(query, params).fetchall()
    return [{"technique": r["technique"], "reason": r["reason"]} for r in rows]


# ── JS Helpers ────────────────────────────────────────────────

def save_helper(name: str, code: str, description: str = "",
                sap_specific: bool = False):
    """Guarda un helper JS reutilizable."""
    db = _get_db()
    now = datetime.now().isoformat()
    existing = db.execute("SELECT * FROM js_helpers WHERE name = ?", (name,)).fetchone()
    if existing:
        db.execute("""
            UPDATE js_helpers SET code = ?, description = ?,
                sap_specific = ?, version = version + 1,
                last_used = ?, updated = ?
            WHERE name = ?
        """, (code, description, int(sap_specific), now, now, name))
    else:
        db.execute("""
            INSERT INTO js_helpers (name, code, description, sap_specific,
                version, last_used, created, updated)
            VALUES (?, ?, ?, ?, 1, ?, ?, ?)
        """, (name, code, description, int(sap_specific), now, now, now))
    db.commit()


def get_helpers(sap_only: bool = False) -> list:
    """Obtiene helpers JS disponibles."""
    db = _get_db()
    if sap_only:
        rows = db.execute("SELECT * FROM js_helpers WHERE sap_specific = 1").fetchall()
    else:
        rows = db.execute("SELECT * FROM js_helpers").fetchall()
    return [dict(r) for r in rows]


def get_helper(name: str) -> dict:
    """Obtiene un helper JS por nombre."""
    db = _get_db()
    row = db.execute("SELECT * FROM js_helpers WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


# ── Frame Paths ───────────────────────────────────────────────

def save_frame_path(screen: str, path: str, js_access: str = "",
                     notes: str = ""):
    """Guarda frame path aprendido para una pantalla."""
    db = _get_db()
    now = datetime.now().isoformat()
    db.execute("""
        INSERT OR REPLACE INTO frame_paths (screen, path, js_access,
            confidence, last_verified, notes)
        VALUES (?, ?, ?, 1.0, ?, ?)
    """, (screen, path, js_access, now, notes))
    db.commit()


def get_frame_path(screen: str) -> dict:
    """Obtiene frame path para una pantalla."""
    db = _get_db()
    row = db.execute("SELECT * FROM frame_paths WHERE screen = ?",
                     (screen,)).fetchone()
    return dict(row) if row else None


# ── Stats ─────────────────────────────────────────────────────

def get_stats() -> dict:
    """Estadísticas del playbook."""
    db = _get_db()
    patterns = db.execute("SELECT COUNT(*) as c FROM patterns").fetchone()["c"]
    blacklisted = db.execute(
        "SELECT COUNT(*) as c FROM blacklist WHERE still_valid = 1"
    ).fetchone()["c"]
    helpers = db.execute("SELECT COUNT(*) as c FROM js_helpers").fetchone()["c"]
    frames = db.execute("SELECT COUNT(*) as c FROM frame_paths").fetchone()["c"]
    attempts = db.execute("SELECT COUNT(*) as c FROM attempt_log").fetchone()["c"]

    # Success rate
    total_success = db.execute(
        "SELECT COUNT(*) as c FROM attempt_log WHERE success = 1"
    ).fetchone()["c"]
    success_rate = total_success / attempts if attempts > 0 else 0

    # Patterns por pantalla
    screens = db.execute(
        "SELECT screen, COUNT(*) as c FROM patterns GROUP BY screen ORDER BY c DESC"
    ).fetchall()

    # Top patterns por uso
    top = db.execute(
        "SELECT key, uses, confidence FROM patterns ORDER BY uses DESC LIMIT 10"
    ).fetchall()

    return {
        "patterns": patterns,
        "blacklisted": blacklisted,
        "js_helpers": helpers,
        "frame_paths": frames,
        "total_attempts": attempts,
        "success_rate": round(success_rate, 3),
        "by_screen": {r["screen"]: r["c"] for r in screens},
        "top_patterns": [{"key": r["key"], "uses": r["uses"],
                          "confidence": r["confidence"]} for r in top],
    }


# ── Export para contexto de Claude ────────────────────────────

def export_for_context(max_patterns: int = 50) -> str:
    """
    Exporta playbook en formato texto para inyectar en contexto de Claude.
    Incluye: patterns activos, blacklist, helpers JS, frame paths.
    """
    db = _get_db()
    lines = []
    lines.append("=" * 60)
    lines.append("  SAP PLAYBOOK — Patrones Operativos")
    lines.append("=" * 60)

    stats = get_stats()
    lines.append(f"  {stats['patterns']} patrones, {stats['blacklisted']} blacklisted, "
                 f"{stats['js_helpers']} helpers, success rate: {stats['success_rate']:.0%}")
    lines.append("")

    # Patterns por pantalla
    rows = db.execute("""
        SELECT * FROM patterns ORDER BY screen, action, confidence DESC
        LIMIT ?
    """, (max_patterns,)).fetchall()

    current_screen = ""
    for row in rows:
        p = dict(row)
        if p["screen"] != current_screen:
            current_screen = p["screen"]
            lines.append(f"  [{current_screen.upper()}]")

        conf = _calc_confidence(p)
        lines.append(f"    {p['key']} (conf:{conf:.0%}, uses:{p['uses']})")
        lines.append(f"      Tecnica: {p['technique']} via {p['tool']}")
        if p["selector"]:
            lines.append(f"      Selector: {p['selector']}")
        if p["frame_path"]:
            lines.append(f"      Frame: {p['frame_path']}")
        if p["code_snippet"]:
            lines.append(f"      Code: {p['code_snippet'][:200]}")
        steps = json.loads(p["steps"])
        if steps:
            lines.append(f"      Pasos: {' → '.join(steps[:6])}")
        if p["notes"]:
            lines.append(f"      Nota: {p['notes'][:150]}")
        lines.append("")

    # Blacklist
    bl = db.execute(
        "SELECT * FROM blacklist WHERE still_valid = 1 ORDER BY screen"
    ).fetchall()
    if bl:
        lines.append("  [BLACKLIST — NO usar estas técnicas]")
        for b in bl:
            lines.append(f"    {b['screen']}/{b['action']}: "
                         f"NO {b['technique']} — {b['reason']}")
        lines.append("")

    # Helpers JS
    helpers = db.execute("SELECT * FROM js_helpers ORDER BY name").fetchall()
    if helpers:
        lines.append("  [JS HELPERS disponibles]")
        for h in helpers:
            lines.append(f"    {h['name']}: {h['description']}")
            lines.append(f"      {h['code'][:200]}")
        lines.append("")

    # Frame paths
    frames = db.execute("SELECT * FROM frame_paths ORDER BY screen").fetchall()
    if frames:
        lines.append("  [FRAME PATHS aprendidos]")
        for f in frames:
            lines.append(f"    {f['screen']}: {f['path']}")
            if f["js_access"]:
                lines.append(f"      JS: {f['js_access']}")
        lines.append("")

    return "\n".join(lines)


# ── Seed con conocimiento base ────────────────────────────────

def seed_base_knowledge():
    """Carga el conocimiento base que ya tenemos sobre SAP."""
    # Helpers JS obligatorios
    save_helper("simulateType", """
function simulateType(inp, text) {
    inp.focus();
    inp.value = text;
    inp.dispatchEvent(new Event('input', {bubbles: true}));
    inp.dispatchEvent(new Event('change', {bubbles: true}));
}""", "Escribe texto en input SAP por DOM", sap_specific=True)

    save_helper("simulateEnter", """
function simulateEnter(inp) {
    var opts = {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true};
    inp.dispatchEvent(new KeyboardEvent('keydown', opts));
    inp.dispatchEvent(new KeyboardEvent('keypress', opts));
    inp.dispatchEvent(new KeyboardEvent('keyup', opts));
}""", "Dispara Enter en input SAP por DOM", sap_specific=True)

    save_helper("simulateTab", """
function simulateTab(el) {
    var opts = {key:'Tab', code:'Tab', keyCode:9, which:9, bubbles:true};
    el.dispatchEvent(new KeyboardEvent('keydown', opts));
    el.dispatchEvent(new KeyboardEvent('keyup', opts));
}""", "Simula Tab por DOM (ADVERTENCIA: no siempre mueve foco real en SAP)", sap_specific=True)

    save_helper("findSapInput", """
function findSapInput(frame, idPartial) {
    var d = frame.document || frame;
    var inputs = d.querySelectorAll('input[id*=\"' + idPartial + '\"]');
    return Array.from(inputs).filter(i => i.offsetParent !== null);
}""", "Busca inputs SAP por id parcial dentro de un frame", sap_specific=True)

    save_helper("getSapFrame", """
function getSapFrame(depth) {
    var f = window;
    for (var i = 0; i < depth.length; i++) {
        f = f.frames[depth[i]];
    }
    return f;
}""", "Navega frames SAP por array de índices [0, 1, ...]", sap_specific=True)

    # Patrones base de lo que ya sabemos
    learn(
        key="sap.login.password",
        screen="login", action="fill_password",
        technique="type_with_delay", tool="claude_chrome_type",
        selector="input[type='password']",
        steps=["locate password input by type", "type with delay=50ms", "never use fill()"],
        notes="NUNCA .fill() para passwords en SAP. IDs dinámicos, usar type selector.",
        tags=["login", "critical"]
    )

    learn(
        key="sap.general.field_fill",
        screen="any", action="fill_field",
        technique="click_clear_type_tab", tool="hybrid",
        steps=["click field", "clear with triple-click or fill('')", "type value with delay=30ms", "press Tab"],
        code_snippet="click(field); fill(''); type(value, delay=30); press('Tab')",
        success_signals="field value updated, next field focused",
        fail_signals="value not accepted, no Tab validation",
        notes="Tab es CRITICO: dispara validación server-side SAP. Sin Tab, SAP no procesa el valor.",
        tags=["fields", "critical", "universal"]
    )

    learn(
        key="sap.navigation.iframe",
        screen="any", action="navigate_iframe",
        technique="wait_domcontentloaded", tool="javascript_tool",
        frame_path="window.frames[0]",
        steps=["detect iframe", "wait for domcontentloaded", "access frame document"],
        notes="SAP usa iframes anidados. Siempre esperar domcontentloaded antes de operar.",
        tags=["iframe", "navigation", "critical"]
    )

    learn(
        key="sap.opportunity.items.insert.product_id",
        screen="opportunity_items", action="insert_item",
        technique="js_simulateType_then_enter", tool="javascript_tool",
        field="product_id",
        selector="input[id*='orderedprod']",
        steps=["locate empty orderedprod input", "simulateType(input, pid)",
               "simulateEnter(input)", "wait 2-3s for SAP resolution"],
        code_snippet="var inp = findSapInput(frame, 'orderedprod'); simulateType(inp[0], pid); simulateEnter(inp[0]);",
        preconditions="items tab open, Insert button clicked, new row visible",
        success_signals="product description appears, net value calculated",
        fail_signals="input not found, no resolution after 5s, error message",
        fallback_key="sap.opportunity.items.insert.product_id.claude_type",
        notes="JS es más rápido que Claude type para Product ID. Enter dispara resolución SAP.",
        tags=["items", "insert", "product_id"]
    )

    # Blacklist: técnicas que NO funcionan
    fail(screen="opportunity_items", action="fill_quantity",
         technique="js_simulateType_pure",
         reason="SAP no reconoce valor escrito por JS puro en campo Quantity. Requiere foco real.",
         blacklist=True)

    fail(screen="opportunity_items", action="move_focus",
         technique="js_simulateTab",
         reason="simulateTab por JS no mueve foco real en SAP. Usar Claude Chrome key Tab.",
         blacklist=True)

    fail(screen="any", action="fill_quantity",
         technique="js_polling_setInterval",
         reason="Polling con setInterval causa loops infinitos en SAP.",
         blacklist=True)

    fail(screen="any", action="fill_quantity",
         technique="click_by_coordinates",
         reason="Click por coordenadas en Quantity es frágil, cambia con resolución/zoom.",
         blacklist=True)

    print("Playbook SAP seeded con conocimiento base")


# ── CLI ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Uso:")
        print("  python sap_playbook.py seed          Cargar conocimiento base")
        print("  python sap_playbook.py stats         Estadísticas")
        print("  python sap_playbook.py export         Exportar para contexto")
        print('  python sap_playbook.py lookup "key"   Buscar patrón')
        print("  python sap_playbook.py helpers        Listar helpers JS")
        print("  python sap_playbook.py blacklist      Listar técnicas fallidas")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "seed":
        seed_base_knowledge()

    elif cmd == "stats":
        s = get_stats()
        print(json.dumps(s, indent=2, ensure_ascii=False))

    elif cmd == "export":
        print(export_for_context())

    elif cmd == "lookup":
        key = sys.argv[2] if len(sys.argv) > 2 else ""
        result = lookup(key=key)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    elif cmd == "helpers":
        for h in get_helpers():
            print(f"\n[{h['name']}] v{h['version']} {'(SAP)' if h['sap_specific'] else ''}")
            print(f"  {h['description']}")
            print(f"  {h['code'][:200]}")

    elif cmd == "blacklist":
        db = _get_db()
        rows = db.execute("SELECT * FROM blacklist WHERE still_valid = 1").fetchall()
        for r in rows:
            print(f"  [{r['screen']}/{r['action']}] NO {r['technique']}")
            print(f"    Razón: {r['reason']}")
