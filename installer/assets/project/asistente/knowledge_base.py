"""
knowledge_base.py — Base de Conocimiento Multi-Dominio
=======================================================
Evolución de learning_memory.py:
- Dominios separados por área de negocio/técnica
- Cada dominio con su propio JSON
- Consultas cross-domain (la automatización puede preguntar reglas de negocio)
- Reglas de negocio como "facts" (no solo patrones de código)

Estructura en disco:
    ~/.adaptive_cli/
        knowledge/
            domains_builtin.json          ← Dominios editables por el usuario
            domains.json                  ← Dominios auto-creados en tiempo de ejecución
            <dominio>/patterns.json       ← Selectores, scripts, workarounds
            <dominio>/facts.json          ← Reglas, procesos, conocimiento declarativo
        execution_log.jsonl               ← Log global
"""

import json
import hashlib
import math
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Configuración ──────────────────────────────────────────────

BASE_DIR = Path.home() / ".adaptive_cli"
LOCK_DIR = BASE_DIR / "locks"


# ── File Locking (multi-instancia safe) ──────────────────────

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
KNOWLEDGE_DIR = BASE_DIR / "knowledge"
LOG_FILE = BASE_DIR / "execution_log.jsonl"

# Sin dominios hardcodeados — cada usuario construye los suyos.
# Primera ejecución: se crea domains_builtin.json vacío en disco (editable).
# Agregar dominios: python knowledge_base.py create-domain <nombre> "<descripcion>"
_DOMAINS_BUILTIN = {}


# Archivo donde se persisten los dominios creados dinamicamente
DOMAINS_FILE = KNOWLEDGE_DIR / "domains.json"


def _load_all_domains() -> dict:
    """
    Carga dominios desde disco.
    Primera ejecución: escribe los defaults builtin a domains_builtin.json (editable).
    Siempre: builtin (editable) + dynamics (auto-creados) = total.
    """
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    builtin_file = KNOWLEDGE_DIR / "domains_builtin.json"

    # Primera ejecución: seed en disco para que el usuario pueda editarlos
    if not builtin_file.exists():
        builtin_file.write_text(
            json.dumps(_DOMAINS_BUILTIN, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

    # Cargar builtin desde disco (editable)
    all_domains = {}
    try:
        all_domains = json.loads(builtin_file.read_text(encoding="utf-8"))
    except Exception:
        all_domains = dict(_DOMAINS_BUILTIN)

    # Agregar dominios creados dinámicamente (domains.json)
    if DOMAINS_FILE.exists():
        try:
            extra = json.loads(DOMAINS_FILE.read_text(encoding="utf-8"))
            all_domains.update(extra)
        except Exception:
            pass

    return all_domains


def _ensure_domain(name: str, description: str = "") -> dict:
    """
    Garantiza que el dominio existe. Si no, lo crea automaticamente en disco.
    Retorna el dict completo de todos los dominios (built-in + dinamicos).
    El disco es el limite — no hay numero maximo de dominios.
    """
    all_domains = _load_all_domains()
    if name not in all_domains:
        new_entry = {
            "description": description or f"Dominio auto-creado: {name}",
            "file": "patterns.json",
            "entry_type": "pattern",
            "auto_created": True,
        }
        # Persistir en disco
        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        current_extra = {}
        if DOMAINS_FILE.exists():
            try:
                current_extra = json.loads(DOMAINS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        current_extra[name] = new_entry
        DOMAINS_FILE.write_text(
            json.dumps(current_extra, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        all_domains[name] = new_entry
        _append_log({"event": "domain_created", "domain": name, "description": new_entry["description"]})

    # Crear directorio del dominio si no existe
    (KNOWLEDGE_DIR / name).mkdir(parents=True, exist_ok=True)
    return all_domains


def _ensure_dirs():
    """Crea directorios de todos los dominios conocidos (built-in + dinamicos)."""
    for domain in _load_all_domains():
        (KNOWLEDGE_DIR / domain).mkdir(parents=True, exist_ok=True)


def _domain_path(domain: str) -> Path:
    """Devuelve la ruta del archivo del dominio. Lo crea si no existe."""
    all_domains = _ensure_domain(domain)
    return KNOWLEDGE_DIR / domain / all_domains[domain]["file"]


def _load_domain(domain: str) -> dict:
    all_domains = _ensure_domain(domain)
    path = _domain_path(domain)
    with file_lock(f"kb_{domain}"):
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    return {
        "domain": domain,
        "description": all_domains[domain]["description"],
        "entries": {},
        "tag_index": {},
        "stats": {"total_entries": 0, "total_lookups": 0, "total_hits": 0},
    }


def _save_domain(domain: str, data: dict):
    _ensure_dirs()
    path = _domain_path(domain)
    with file_lock(f"kb_{domain}"):
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # Retry para WinError 5 (Access Denied en rename atomico en Windows)
        for _attempt in range(5):
            try:
                tmp.replace(path)
                break
            except OSError:
                if _attempt == 4:
                    raise
                import time as _t
                _t.sleep(0.01 * (2 ** _attempt))


def _entry_id(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:12]


MAX_LOG_LINES = 5000  # rotar cuando supere este limite

def _append_log(entry: dict):
    _ensure_dirs()
    entry["timestamp"] = datetime.now(timezone.utc).isoformat()
    with file_lock("execution_log"):
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        # Rotación: si el log crece demasiado, conservar solo las últimas N lineas
        try:
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) > MAX_LOG_LINES:
                with open(LOG_FILE, "w", encoding="utf-8") as f:
                    f.writelines(lines[-MAX_LOG_LINES:])
        except Exception:
            pass


# ══════════════════════════════════════════════════════════════
#  PATTERNS (automation, documents) — soluciones técnicas
# ══════════════════════════════════════════════════════════════

def add_pattern(
    domain: str,
    key: str,
    solution: dict,
    tags: list[str] = None,
    error_context: dict = None,
) -> str:
    """Registra un patrón técnico (selector, script, workaround)."""
    data = _load_domain(domain)
    eid = _entry_id(f"{domain}::{key}")
    now = datetime.now(timezone.utc).isoformat()

    data["entries"][eid] = {
        "id": eid,
        "type": "pattern",
        "key": key,
        "solution": solution,
        "tags": tags or [],
        "error_context": error_context,
        "created_at": now,
        "updated_at": now,
        "stats": {"lookups": 0, "reuses": 0, "success_rate": 1.0,
                  "last_accessed": now, "access_count": 0},
    }
    data["stats"]["total_entries"] += 1

    for tag in (tags or []):
        data["tag_index"].setdefault(tag, []).append(eid)

    _save_domain(domain, data)
    _append_log({"event": "pattern_added", "domain": domain, "key": key, "id": eid})
    return eid


# ══════════════════════════════════════════════════════════════
#  FACTS (business_rules, catalog) — conocimiento declarativo
# ══════════════════════════════════════════════════════════════

def add_fact(
    domain: str,
    key: str,
    fact: dict,
    tags: list[str] = None,
) -> str:
    """
    Registra un hecho/regla de negocio.

    fact = {
        "rule": "Los códigos de contrato llevan sufijo _PS",
        "applies_to": "oportunidades de tipo contrato",
        "examples": [
            {"input": "LLML245", "output": "LLML245_PS", "context": "contrato"},
            {"input": "LLML245", "output": "LLML245", "context": "proyecto"},
        ],
        "exceptions": "No aplica a renovaciones tipo _RN",
        "source": "Proceso interno GBM / Eduardo Rivas",
        "confidence": "verified",  # verified | observed | inferred
    }
    """
    data = _load_domain(domain)
    eid = _entry_id(f"{domain}::{key}")
    now = datetime.now(timezone.utc).isoformat()

    data["entries"][eid] = {
        "id": eid,
        "type": "fact",
        "key": key,
        "fact": fact,
        "tags": tags or [],
        "created_at": now,
        "updated_at": now,
        "stats": {"lookups": 0, "cited_in_tasks": 0,
                  "last_accessed": now, "access_count": 0},
    }
    data["stats"]["total_entries"] += 1

    for tag in (tags or []):
        data["tag_index"].setdefault(tag, []).append(eid)

    _save_domain(domain, data)
    _append_log({"event": "fact_added", "domain": domain, "key": key, "id": eid})
    return eid


def register_pattern(
    domain: str,
    context_key: str,
    solution: dict,
    tags: list = None,
    entry_type: str = "pattern",
) -> str:
    """
    Alias unificado para ingestar contenido en la KB.
    Delega a add_pattern o add_fact según entry_type.
    Usado por ingest_knowledge.py.
    """
    if entry_type == "fact":
        return add_fact(domain, context_key, solution, tags)
    return add_pattern(domain, context_key, solution, tags)


# ══════════════════════════════════════════════════════════════
#  BÚSQUEDA — single-domain y cross-domain
# ══════════════════════════════════════════════════════════════

def search(
    domain: str,
    key: str = None,
    tags: list[str] = None,
    text_query: str = None,
) -> list[dict]:
    """
    Busca en UN dominio.
    - key: búsqueda exacta por ID derivado del key
    - tags: búsqueda por tags
    - text_query: búsqueda fuzzy en keys, tags, y contenido
    """
    data = _load_domain(domain)
    results = []

    # Exacta por key
    if key:
        eid = _entry_id(f"{domain}::{key}")
        if eid in data["entries"]:
            entry = data["entries"][eid]
            entry["stats"]["lookups"] += 1
            entry["stats"]["access_count"] = entry["stats"].get("access_count", 0) + 1
            entry["stats"]["last_accessed"] = datetime.now(timezone.utc).isoformat()
            data["stats"]["total_hits"] += 1
            data["stats"]["total_lookups"] += 1
            _save_domain(domain, data)
            return [entry]

    # Por tags
    if tags:
        seen = set()
        for tag in tags:
            for eid in data["tag_index"].get(tag, []):
                if eid not in seen and eid in data["entries"]:
                    results.append(data["entries"][eid])
                    seen.add(eid)

    # Fuzzy por texto
    if text_query:
        query_lower = text_query.lower()
        query_words = set(re.split(r'\s+', query_lower))
        # Filtrar palabras muy cortas (ruido)
        query_words = {w for w in query_words if len(w) >= 3}
        if query_words:
            for eid, entry in data["entries"].items():
                if eid in {r["id"] for r in results}:
                    continue
                searchable = " ".join([
                    entry.get("key", ""),
                    " ".join(entry.get("tags", [])),
                    json.dumps(entry.get("solution", entry.get("fact", {})), ensure_ascii=False),
                ]).lower()
                # Match si cualquier palabra del query aparece en el contenido
                if any(word in searchable for word in query_words):
                    results.append(entry)

        # Ordenar por relevancia con decaimiento temporal
        # Patrones viejos y poco usados bajan en ranking (no se borran)
        if results:
            now_ts = datetime.now(timezone.utc)

            def _relevance_key(e):
                stats = e.get("stats", {})
                sr    = stats.get("success_rate", 1.0)
                last  = stats.get("last_accessed")
                if last:
                    try:
                        days  = max(0, (now_ts - datetime.fromisoformat(last)).days)
                        decay = math.exp(-0.01 * days)  # ~0.5 a los 70 días sin usarse
                    except Exception:
                        decay = 1.0
                else:
                    decay = 1.0  # entries nuevas = score completo
                return sr * decay

            results.sort(key=_relevance_key, reverse=True)

    # Actualizar last_accessed para todos los resultados retornados
    now_iso = datetime.now(timezone.utc).isoformat()
    for entry in results:
        eid = entry.get("id")
        if eid and eid in data["entries"]:
            data["entries"][eid]["stats"]["last_accessed"] = now_iso
            data["entries"][eid]["stats"]["access_count"] = (
                data["entries"][eid]["stats"].get("access_count", 0) + 1
            )

    data["stats"]["total_lookups"] += 1
    if results:
        data["stats"]["total_hits"] += 1
    _save_domain(domain, data)
    return results


def cross_domain_search(
    tags: list[str] = None,
    text_query: str = None,
    domains: list[str] = None,
) -> dict[str, list[dict]]:
    """
    Busca en MÚLTIPLES dominios simultáneamente.
    Retorna {domain: [entries]} para cada dominio con resultados.

    Esto es lo que permite que la automatización SAP consulte
    reglas de negocio sobre nomenclatura de códigos.
    """
    target_domains = domains or list(_load_all_domains().keys())
    results = {}

    for domain in target_domains:
        domain_results = search(domain, tags=tags, text_query=text_query)
        if domain_results:
            results[domain] = domain_results

    _append_log({
        "event": "cross_domain_search",
        "tags": tags,
        "text_query": text_query,
        "domains_searched": target_domains,
        "hits_per_domain": {d: len(r) for d, r in results.items()},
    })

    return results


# ══════════════════════════════════════════════════════════════
#  EXPORTACIÓN — para inyectar como contexto en Claude CLI
# ══════════════════════════════════════════════════════════════

def export_context(
    domain: str = None,
    tags: list[str] = None,
    text_query: str = None,
    limit: int = 10,
) -> str:
    """
    Genera texto legible para inyectar en el prompt de Claude.
    Si domain=None, busca en todos los dominios.
    """
    if domain:
        entries = search(domain, tags=tags, text_query=text_query)
        all_results = {domain: entries}
    else:
        all_results = cross_domain_search(tags=tags, text_query=text_query)

    if not any(all_results.values()):
        return "No se encontraron entradas relevantes en la base de conocimiento."

    lines = ["=== BASE DE CONOCIMIENTO GBM ===", ""]

    for dom, entries in all_results.items():
        if not entries:
            continue
        _all = _load_all_domains()
        lines.append(f"── {dom.upper()} ({_all.get(dom, {}).get('description', dom)}) ──")
        for entry in entries[:limit]:
            if entry["type"] == "pattern":
                sol = entry["solution"]
                lines.append(f"  [{entry['key']}]")
                lines.append(f"    Estrategia: {sol.get('strategy', 'N/A')}")
                if sol.get("code_snippet"):
                    lines.append(f"    Código: {sol['code_snippet'][:300]}")
                if sol.get("notes"):
                    lines.append(f"    Nota: {sol['notes']}")
                lines.append(f"    Éxito: {entry['stats'].get('success_rate', 'N/A')}")

            elif entry["type"] == "fact":
                fact = entry["fact"]
                lines.append(f"  [{entry['key']}]")
                lines.append(f"    Regla: {fact.get('rule', 'N/A')}")
                if fact.get("applies_to"):
                    lines.append(f"    Aplica a: {fact['applies_to']}")
                if fact.get("examples"):
                    for ex in fact["examples"][:3]:
                        lines.append(f"    Ejemplo: {ex.get('input', '?')} → {ex.get('output', '?')} ({ex.get('context', '')})")
                if fact.get("exceptions"):
                    lines.append(f"    Excepción: {fact['exceptions']}")
                conf = fact.get("confidence", "unknown")
                lines.append(f"    Confianza: {conf}")
            lines.append("")

    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
#  INGEST — carga masiva desde documentos
# ══════════════════════════════════════════════════════════════

def ingest_business_rules_from_text(text: str, source: str = "manual") -> list[str]:
    """
    Parsea texto semi-estructurado y extrae reglas de negocio.
    Formato esperado (una regla por bloque separado por línea vacía):

        REGLA: Los códigos de contrato llevan sufijo _PS
        APLICA: oportunidades tipo contrato
        EJEMPLO: LLML245 → LLML245_PS (contrato)
        EJEMPLO: LLML245 → LLML245 (proyecto)
        EXCEPCIÓN: No aplica a renovaciones _RN
        TAGS: nomenclatura, códigos, contrato, sufijo

    También acepta formato libre — cada párrafo se registra como un fact.
    """
    ids = []
    blocks = text.strip().split("\n\n")

    for block in blocks:
        lines = block.strip().split("\n")
        if not lines:
            continue

        # Intentar parsear formato estructurado
        fact = {"source": source, "confidence": "observed"}
        key_parts = []
        tags = []

        for line in lines:
            line = line.strip()
            upper = line.upper()

            if upper.startswith("REGLA:"):
                fact["rule"] = line[6:].strip()
                key_parts.append(fact["rule"][:50])
            elif upper.startswith("APLICA:") or upper.startswith("APLICA A:"):
                fact["applies_to"] = line.split(":", 1)[1].strip()
            elif upper.startswith("EJEMPLO:"):
                if "examples" not in fact:
                    fact["examples"] = []
                ex_text = line[8:].strip()
                # Parsear "input → output (context)"
                match = re.match(r"(.+?)\s*[→->]+\s*(.+?)(?:\s*\((.+?)\))?\s*$", ex_text)
                if match:
                    fact["examples"].append({
                        "input": match.group(1).strip(),
                        "output": match.group(2).strip(),
                        "context": (match.group(3) or "").strip(),
                    })
                else:
                    fact["examples"].append({"input": ex_text, "output": "", "context": ""})
            elif upper.startswith("EXCEPCIÓN:") or upper.startswith("EXCEPCION:"):
                fact["exceptions"] = line.split(":", 1)[1].strip()
            elif upper.startswith("TAGS:"):
                tags = [t.strip() for t in line[5:].split(",") if t.strip()]
            elif upper.startswith("CONFIANZA:") or upper.startswith("CONFIDENCE:"):
                fact["confidence"] = line.split(":", 1)[1].strip()
            else:
                # Línea sin prefijo → parte de la regla
                if "rule" not in fact:
                    fact["rule"] = line
                    key_parts.append(line[:50])
                else:
                    fact["rule"] += " " + line

        if "rule" in fact:
            key = "_".join(key_parts) if key_parts else f"rule_{len(ids)}"
            eid = add_fact("business_rules", key, fact, tags)
            ids.append(eid)

    return ids


def ingest_catalog_from_text(text: str, source: str = "manual") -> list[str]:
    """
    Parsea catálogo de productos. Formato:

        CÓDIGO: LLML245
        NOMBRE: SAP Licencia ML
        TIPO: contrato
        VARIANTES: LLML245_PS (post-sale), LLML245_RN (renovación)
        PRECIO: $60/hr (8x5), $80/hr (24x7)
        TAGS: sap, licencia, ml

    También acepta CSV-like: código,nombre,tipo,precio
    """
    ids = []
    blocks = text.strip().split("\n\n")

    for block in blocks:
        lines = block.strip().split("\n")
        if not lines:
            continue

        fact = {"source": source, "confidence": "verified"}
        key = ""
        tags = []

        for line in lines:
            line = line.strip()
            upper = line.upper()

            if upper.startswith("CÓDIGO:") or upper.startswith("CODIGO:"):
                code = line.split(":", 1)[1].strip()
                fact["code"] = code
                key = code
            elif upper.startswith("NOMBRE:"):
                fact["name"] = line.split(":", 1)[1].strip()
            elif upper.startswith("TIPO:"):
                fact["product_type"] = line.split(":", 1)[1].strip()
            elif upper.startswith("VARIANTES:") or upper.startswith("VARIANTS:"):
                variants_text = line.split(":", 1)[1].strip()
                fact["variants"] = [v.strip() for v in variants_text.split(",")]
            elif upper.startswith("PRECIO:") or upper.startswith("PRICE:"):
                fact["pricing"] = line.split(":", 1)[1].strip()
            elif upper.startswith("RELACIÓN:") or upper.startswith("RELACION:"):
                fact["relations"] = line.split(":", 1)[1].strip()
            elif upper.startswith("TAGS:"):
                tags = [t.strip() for t in line[5:].split(",") if t.strip()]
            else:
                fact.setdefault("notes", "")
                fact["notes"] += " " + line

        if key:
            fact["rule"] = f"Producto {key}: {fact.get('name', 'sin nombre')}"
            eid = add_fact("catalog", key, fact, tags)
            ids.append(eid)

    return ids


# ══════════════════════════════════════════════════════════════
#  STATS Y CLI
# ══════════════════════════════════════════════════════════════

def get_global_stats() -> dict:
    """Incluye dominios built-in Y dinamicos."""
    stats = {}
    for domain in _load_all_domains():
        data = _load_domain(domain)
        stats[domain] = {
            "entries": data["stats"]["total_entries"],
            "lookups": data["stats"]["total_lookups"],
            "hits": data["stats"].get("total_hits", 0),
        }
    stats["total"] = sum(s["entries"] for s in stats.values())
    return stats


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso:")
        print("  python knowledge_base.py list-domains")
        print("  python knowledge_base.py stats")
        print("  python knowledge_base.py search <domain> [--tags tag1,tag2] [--query texto]")
        print("  python knowledge_base.py cross-search [--tags tag1,tag2] [--query texto]")
        print("  python knowledge_base.py export [domain] [--tags tag1,tag2] [--query texto]")
        print("  python knowledge_base.py ingest-rules <file.txt>")
        print("  python knowledge_base.py ingest-catalog <file.txt>")
        print(f"\nDominios: {list(_load_all_domains().keys())}")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list-domains":
        domains = _load_all_domains()
        for name, info in domains.items():
            print(f"  {name:20s}  {info.get('description', '')[:60]}")

    elif cmd == "stats":
        print(json.dumps(get_global_stats(), indent=2))

    elif cmd == "search" and len(sys.argv) >= 3:
        domain = sys.argv[2]
        tags = None
        query = None
        i = 3
        while i < len(sys.argv):
            if sys.argv[i] == "--tags" and i + 1 < len(sys.argv):
                tags = [t.strip() for t in sys.argv[i + 1].split(",")]
                i += 2
            elif sys.argv[i] == "--query" and i + 1 < len(sys.argv):
                query = sys.argv[i + 1]
                i += 2
            else:
                i += 1
        results = search(domain, tags=tags, text_query=query)
        for r in results:
            print(json.dumps(r, indent=2, ensure_ascii=False))

    elif cmd == "cross-search":
        tags = None
        query = None
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--tags" and i + 1 < len(sys.argv):
                tags = [t.strip() for t in sys.argv[i + 1].split(",")]
                i += 2
            elif sys.argv[i] == "--query" and i + 1 < len(sys.argv):
                query = sys.argv[i + 1]
                i += 2
            else:
                i += 1
        results = cross_domain_search(tags=tags, text_query=query)
        for domain, entries in results.items():
            print(f"\n── {domain} ──")
            for r in entries:
                print(f"  [{r['key']}] {r.get('fact', r.get('solution', {})).get('rule', r.get('solution', {}).get('strategy', ''))}")

    elif cmd == "export":
        domain = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None
        tags = None
        query = None
        i = 3 if domain else 2
        while i < len(sys.argv):
            if sys.argv[i] == "--tags" and i + 1 < len(sys.argv):
                tags = [t.strip() for t in sys.argv[i + 1].split(",")]
                i += 2
            elif sys.argv[i] == "--query" and i + 1 < len(sys.argv):
                query = sys.argv[i + 1]
                i += 2
            else:
                i += 1
        print(export_context(domain, tags=tags, text_query=query))

    elif cmd == "ingest-rules" and len(sys.argv) >= 3:
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            text = f.read()
        ids = ingest_business_rules_from_text(text, source=sys.argv[2])
        print(f"✅ {len(ids)} reglas importadas")

    elif cmd == "ingest-catalog" and len(sys.argv) >= 3:
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            text = f.read()
        ids = ingest_catalog_from_text(text, source=sys.argv[2])
        print(f"✅ {len(ids)} productos importados")

    else:
        print(f"Comando desconocido: {cmd}")
