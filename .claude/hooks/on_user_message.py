"""
on_user_message.py — UserPromptSubmit Hook: experiencia relevante por tarea
============================================================================
Se dispara cuando el usuario envia un mensaje.
Su stdout se inyecta como contexto ANTES de que Claude procese el mensaje.

FLUJO:
  1. Lee el prompt del usuario desde stdin
  2. Clasificador Python puro detecta dominios (multi-dominio si tarea mixta)
  3. Cache: si mismo tema reciente, respuesta instantanea sin re-clasificar
  4. Busca en learning_memory los patrones de ESE tema (errores, soluciones)
  5. Busca en knowledge_base las recetas de ESE tema
  6. Inyecta solo lo relevante

Sin API keys. Sin servicios externos. Todo local.
"No me tropiezo dos veces con la misma piedra"
"""

import sys
import json
import math
import re
from pathlib import Path
from datetime import datetime

# Siempre apunta a Asistente IA sin importar desde donde se abrio el CLI
PROJECT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from _paths import DATA_DIR

LAST_MSG_FILE    = DATA_DIR / "last_user_message.txt"
NOTIFY_FILE      = DATA_DIR / "last_learning.txt"
CLASSIFY_CACHE   = DATA_DIR / "classify_cache.json"
CO_OCCUR_FILE    = DATA_DIR / "domain_cooccurrence.json"
MARKOV_FILE      = DATA_DIR / "domain_markov.json"
PROMPT_HIST_FILE = DATA_DIR / "prompt_history.jsonl"
INJECTION_FILE   = DATA_DIR / "last_injection.json"
MSG_TYPE_FILE    = DATA_DIR / "hook_state" / "msg_type.json"
KB_FILE_CACHE    = {}  # {filepath: (mtime, data)} — cache en proceso, costo cero

CACHE_TTL_SECS   = 7200  # clasificacion valida 2 horas
CACHE_OVERLAP_TH = 0.55  # 55% keywords en comun = cache hit


# ── Cache de clasificacion (disco, TTL 2h) ────────────────────

def _kw_overlap(a: list, b: list) -> float:
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    return len(sa & sb) / len(sa | sb)


def _read_classify_cache(keywords: list):
    try:
        if not CLASSIFY_CACHE.exists():
            return None
        c   = json.loads(CLASSIFY_CACHE.read_text(encoding="utf-8"))
        age = (datetime.now() - datetime.fromisoformat(c["ts"])).total_seconds()
        if age > CACHE_TTL_SECS:
            return None
        if _kw_overlap(keywords, c.get("keywords", [])) >= CACHE_OVERLAP_TH:
            return {"domains": c["domains"], "keywords": c["keywords"]}
    except Exception:
        pass
    return None


def _write_classify_cache(domains: list, keywords: list):
    try:
        CLASSIFY_CACHE.parent.mkdir(parents=True, exist_ok=True)
        CLASSIFY_CACHE.write_text(
            json.dumps({"domains": domains, "keywords": keywords,
                        "ts": datetime.now().isoformat()}, ensure_ascii=False),
            encoding="utf-8"
        )
    except Exception:
        pass


# ── Cache de archivos KB (mtime) ──────────────────────────────

def _load_json_cached(path: Path) -> dict:
    """Lee JSON solo si el archivo cambio — evita re-parsear en cada llamada."""
    key = str(path)
    try:
        mtime = path.stat().st_mtime
        if key in KB_FILE_CACHE and KB_FILE_CACHE[key][0] == mtime:
            return KB_FILE_CACHE[key][1]
        data = json.loads(path.read_text(encoding="utf-8"))
        KB_FILE_CACHE[key] = (mtime, data)
        return data
    except Exception:
        return {}


# ── Memory recall detection ───────────────────────────────────

MEMORY_RECALL_PATTERNS = [
    r"recuerdas?\s+(lo\s+)?(ultimo|último|que\s+estab)",
    r"(en\s+qu[eé]|qu[eé])\s+estab[as]+\s+(haciendo|trabajando)",
    r"(qu[eé]|c[oó]mo)\s+(estab[as]+|qued[oó])\s+",
    r"\b(ultimo|último)\s+(que\s+)?(hiciste|estabas|trabajamos|vimos)\b",
    r"\bqu[eé]\s+(estaba[sz]?|ten[íi]as?)\s+pendiente\b",
    r"\bsigue\s+(con|desde)\s+(lo\s+)?(anterior|ultimo|último)\b",
    r"\bcontinu[aá]\s+(desde\s+)?(donde|lo)\b",
    r"\ba?\s*qu[eé]\s+nos\s+quedamos\b",
    r"\bde\s+qu[eé]\s+(estab[aá]mos|hablamos|tratamos)\b",
]


def is_memory_recall(prompt: str) -> bool:
    text = prompt.lower()
    for pat in MEMORY_RECALL_PATTERNS:
        if re.search(pat, text):
            return True
    return False


def get_latest_session_summary() -> str:
    """Retorna la nota de la sesión episódica más reciente del KB."""
    try:
        kb_dir = DATA_DIR / "knowledge"
        best_key = ""
        best_notes = ""
        for patterns_file in kb_dir.glob("*/patterns.json"):
            try:
                data = json.loads(patterns_file.read_text(encoding="utf-8"))
                for _, val in data.get("entries", {}).items():
                    if not isinstance(val, dict):
                        continue
                    key = val.get("key", "")
                    if "session_auto_" not in key and "session_complete" not in key:
                        continue
                    if key > best_key:
                        sol = val.get("solution", {})
                        notes = sol.get("notes", "") if isinstance(sol, dict) else ""
                        if notes.strip():
                            best_key = key
                            best_notes = notes
            except Exception:
                continue
        if best_key and best_notes:
            ts = best_key.replace("session_auto_", "").replace("_", "-", 2) if "session_auto_" in best_key else best_key
            return f"[{ts}] {best_notes[:400]}"
    except Exception:
        pass
    return ""


# ── Stop words ────────────────────────────────────────────────

STOP_WORDS = {
    "el", "la", "los", "las", "un", "una", "de", "del", "en", "que",
    "y", "a", "por", "con", "para", "es", "se", "no", "lo", "le", "su",
    "me", "te", "si", "mi", "tu", "al", "hay", "ya", "pero", "como",
    "the", "an", "in", "of", "to", "is", "it", "for", "and", "or",
    "puedo", "quiero", "hacer", "haz", "dame", "muestra", "dime",
    "necesito", "ver", "este", "esta", "esto", "cuando", "donde",
    "algo", "mas", "muy", "bien", "ok", "eso", "asi", "cual", "que",
}

# ── Clasificador multi-dominio (Python puro) ──────────────────
# Cada dominio tiene keywords con PESO:
#   peso 2 = muy especifico (casi unico de ese dominio)
#   peso 1 = comun (puede aparecer en varios)
#
# Si una tarea menciona keywords de 2+ dominios con score >= 50% del maximo,
# se retornan TODOS — eso maneja "jabalina + correr" naturalmente.

# Sin hints hardcodeados — se cargan desde ~/.adaptive_cli/knowledge/domain_hints.json
# Crecer con: from domain_detector import learn_domain_keywords
# o automáticamente vía auto_learn_from_session() en cada sesión
DOMAIN_HINTS = {}


def extract_keywords(text: str) -> list:
    words = re.findall(r'\b[a-zA-Z0-9_áéíóúñ]{3,}\b', text.lower())
    return [w for w in words if w not in STOP_WORDS][:25]


def classify_domains(keywords: list) -> list:
    """
    Clasificador multi-dominio con scoring ponderado. Sin API. Instantaneo.

    - Cada keyword suma el peso de su dominio
    - Se retornan todos los dominios con score >= 50% del maximo
      (eso captura tareas mixtas: SOW + BOM = ambos dominios)
    - Dominios dinamicos (creados por el sistema) se agregan automaticamente
    """
    # Cargar dominios dinámicos + sus keywords aprendidas desde disco
    try:
        from knowledge_base import _load_all_domains
        all_domains = _load_all_domains()
        # Cargar keywords aprendidas por domain_detector
        hints_file = DATA_DIR / "knowledge" / "domain_hints.json"
        learned_hints = {}
        if hints_file.exists():
            try:
                learned_hints = json.loads(hints_file.read_text(encoding="utf-8"))
            except Exception:
                pass
        else:
            # Primer arranque: crear archivo vacío (se llena con el uso)
            hints_file.parent.mkdir(parents=True, exist_ok=True)
            hints_file.write_text("{}", encoding="utf-8")
        for dname in all_domains:
            if dname not in DOMAIN_HINTS:
                if dname in learned_hints:
                    DOMAIN_HINTS[dname] = learned_hints[dname]
                else:
                    DOMAIN_HINTS[dname] = {dname.replace("_", ""): 2, dname: 3}
    except Exception:
        pass

    text   = " ".join(keywords)
    scores = {}

    # IDF: keywords que aparecen en pocos dominios tienen mayor peso discriminatorio
    kw_domain_count: dict = {}
    for hints in DOMAIN_HINTS.values():
        for kw in hints:
            kw_domain_count[kw] = kw_domain_count.get(kw, 0) + 1
    n_domains = max(len(DOMAIN_HINTS), 1)

    for domain, hint_weights in DOMAIN_HINTS.items():
        score = 0.0
        for kw, w in hint_weights.items():
            if kw in text:
                # IDF suavizado: keyword raro en dominios = mayor peso
                df  = kw_domain_count.get(kw, 1)
                idf = math.log((n_domains + 1) / (df + 1)) + 1.0
                score += w * idf
        if score > 0:
            scores[domain] = score

    if not scores:
        return []

    max_score = max(scores.values())
    threshold = max(1, max_score * 0.50)  # 50% del maximo = relevante

    relevant = sorted(
        [(d, s) for d, s in scores.items() if s >= threshold],
        key=lambda x: -x[1]
    )
    return [d for d, _ in relevant[:3]]


# ── Crash recovery ────────────────────────────────────────────

def save_last_user_message(hook_input: dict):
    try:
        prompt = hook_input.get("prompt", "").strip()
        if not prompt:
            return
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        LAST_MSG_FILE.parent.mkdir(parents=True, exist_ok=True)
        LAST_MSG_FILE.write_text(
            f"[{ts}] session:{hook_input.get('session_id', '')}\n{prompt}\n",
            encoding="utf-8"
        )
    except Exception:
        pass


# ── Búsqueda en Learning Memory ───────────────────────────────

def search_lm(keywords: list, domains: list) -> str:
    """
    Busca patrones aprendidos (errores + soluciones) para los dominios
    detectados. Tarea mixta = busca en todos los dominios relevantes.
    """
    try:
        from learning_memory import export_for_claude_context, get_stats, _load_memory
        if get_stats().get("total_patterns", 0) == 0:
            return ""

        results = []

        # Buscar por cada dominio
        for domain in domains:
            export = export_for_claude_context(task_type=domain, limit=2)
            if export and "No hay patrones" not in export:
                results.append(f"[{domain}]\n{export}")

        if results:
            return "\n".join(results)

        # Fallback: buscar por keywords en todos los patrones
        mem        = _load_memory()
        candidates = []
        for pid, p in mem["patterns"].items():
            searchable = " ".join([
                " ".join(p.get("tags", [])),
                p.get("task_type", ""),
                p.get("context_key", ""),
            ]).lower()
            if any(kw in searchable for kw in keywords[:6]):
                candidates.append(p)

        if candidates:
            candidates.sort(key=lambda x: x["stats"].get("success_rate", 0), reverse=True)
            lines = []
            for p in candidates[:4]:
                sol = p.get("solution", {})
                sr  = p["stats"].get("success_rate", 0)
                lines.append(f"  ✓ [{p['task_type']}] éxito {sr*100:.0f}% — USAR ESTE APPROACH:")
                if sol.get("notes"):
                    lines.append(f"    {sol['notes'][:200]}")
                if sol.get("code_snippet"):
                    lines.append(f"    código: {sol['code_snippet'][:150]}")
            return "\n".join(lines)
    except Exception:
        pass
    return ""


# ── Búsqueda en Knowledge Base ────────────────────────────────

def search_kb(keywords: list, domains: list) -> str:
    """
    Busca recetas en los dominios detectados.
    B: "general" siempre incluido (base transversal).
    A: si hay < 2 entradas en dominios específicos, fallback a cross_search sin filtro.
    """
    try:
        from knowledge_base import cross_domain_search

        query   = " ".join(keywords[:8])
        results = cross_domain_search(text_query=query, domains=domains or None)

        lines = []
        total_entries = 0
        for dom, entries in results.items():
            if not entries:
                continue
            total_entries += len(entries)
            lines.append(f"  [{dom}]")
            for e in entries[:2]:
                key = e.get("key", "?")
                if e.get("type") == "pattern":
                    sol      = e.get("solution", {})
                    strategy = sol.get("strategy", "")
                    notes    = sol.get("notes", "")[:200]
                    if strategy:
                        lines.append(f"    {key}: {strategy}")
                        if notes:
                            lines.append(f"      {notes}")
                elif e.get("type") == "fact":
                    fact = e.get("fact", {})
                    rule = fact.get("rule", "")[:200]
                    if rule:
                        lines.append(f"    APLICAR → {key}: {rule}")
                        for ex in fact.get("examples", [])[:2]:
                            lines.append(f"      ej: {ex.get('input','?')} → {ex.get('output','?')}")

        # A: fallback cross_search si hay pocos resultados en dominios detectados
        if total_entries < 2:
            fallback = cross_domain_search(text_query=query, domains=None)
            for dom, entries in fallback.items():
                if dom in (domains or []) or not entries:
                    continue  # ya incluido arriba
                lines.append(f"  [{dom}]")
                for e in entries[:1]:
                    key = e.get("key", "?")
                    if e.get("type") == "pattern":
                        sol = e.get("solution", {})
                        if sol.get("strategy"):
                            lines.append(f"    {key}: {sol['strategy']}")
                            if sol.get("notes"):
                                lines.append(f"      {sol['notes'][:200]}")
                    elif e.get("type") == "fact":
                        fact = e.get("fact", {})
                        if fact.get("rule"):
                            lines.append(f"    APLICAR → {key}: {fact['rule'][:200]}")

        return "\n".join(lines)
    except Exception:
        pass
    return ""


# ── Co-dominio predictivo (paso 1) + Markov (paso 2) ─────────

def get_co_domains(domains: list) -> list:
    """
    Lee la tabla de co-ocurrencia histórica y retorna el dominio que más
    frecuentemente aparece junto con los dominios detectados.
    Ej: si el tema es 'sow', históricamente 'bom' aparece junto → inyecta también.
    """
    try:
        if not CO_OCCUR_FILE.exists():
            return []
        data = json.loads(CO_OCCUR_FILE.read_text(encoding="utf-8"))
        extra = []
        for dom in domains:
            co = data.get(dom, {})
            if not co:
                continue
            top = max(co, key=lambda k: co[k])
            if top not in domains and top not in extra:
                extra.append(top)
        return extra[:1]  # max 1 co-dominio para no saturar contexto
    except Exception:
        return []


def get_markov_next(domains: list, co_domains: list) -> list:
    """
    Predicción 2 pasos adelante con cadena de Markov ordinal.
    Dado el dominio actual, predice el SIGUIENTE dominio más probable.
    Diferencia vs co-ocurrencia: Markov es DIRIGIDO (sow→bom, no bom→sow).
    """
    try:
        if not MARKOV_FILE.exists():
            return []
        data = json.loads(MARKOV_FILE.read_text(encoding="utf-8"))
        all_known = set(domains + co_domains)
        predictions = []
        for dom in domains:
            transitions = data.get(dom, {})
            if not transitions:
                continue
            # El siguiente más probable que no esté ya en contexto
            candidates = [(k, v) for k, v in transitions.items() if k not in all_known]
            if candidates:
                next_dom = max(candidates, key=lambda x: x[1])[0]
                if next_dom not in predictions:
                    predictions.append(next_dom)
        return predictions[:1]
    except Exception:
        return []


def search_episodic(keywords: list, limit: int = 3) -> str:
    """
    Busca en el índice FTS5 de sesiones anteriores.
    Retorna snippets de sesiones relevantes cross-sesión.
    """
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        from episodic_index import search as ep_search
        query = " ".join(keywords[:6])
        results = ep_search(query, limit=limit)
        if not results:
            return ""
        lines = []
        for r in results:
            date = r.get("date", "?")
            domain = r.get("domain", "?")
            snippet = r.get("snippet", "")[:150]
            lines.append(f"  [{date}/{domain}] {snippet}")
        return "\n".join(lines)
    except Exception:
        return ""


# ── Intent classification + Prompt momentum ───────────────────

INTENT_PATTERNS = {
    "crear":       ["crea", "genera", "nuevo", "construye", "arma", "escribe", "redacta",
                    "make", "create", "new", "draft", "plantilla", "template"],
    "revisar":     ["revisa", "checa", "verifica", "audita", "valida",
                    "review", "check", "audit", "analiza", "inspecciona"],
    "depurar":     ["error", "falla", "no funciona", "roto", "fix", "arregla", "broken",
                    "debug", "fallo", "exception", "traceback", "problema"],
    "automatizar": ["automatiza", "script", "hook", "proceso", "pipeline",
                    "auto", "schedule", "cron", "repite"],
    "entender":    ["explica", "cómo", "por qué", "dime", "explain",
                    "how", "qué es", "describe", "detalla"],
}

INTENT_CONTEXT = {
    "crear":       "Priorizar templates y estructuras del KB.",
    "revisar":     "Priorizar checklists y patrones de validación.",
    "depurar":     "Priorizar patrones de error y fixes probados.",
    "automatizar": "Priorizar scripts y hooks existentes.",
    "entender":    "Priorizar documentación y ejemplos del KB.",
    "general":     "",
}


def detect_intent(prompt: str) -> str:
    """Detecta intención principal: crear / revisar / depurar / automatizar / entender."""
    text = prompt.lower()
    scores = {intent: sum(1 for p in patterns if p in text)
              for intent, patterns in INTENT_PATTERNS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "general"


def update_prompt_history(prompt: str, domains: list, intent: str):
    """Historial rolling de los últimos 5 prompts para detectar momentum."""
    try:
        PROMPT_HIST_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry = json.dumps({
            "ts":      datetime.now().isoformat(),
            "domains": domains,
            "intent":  intent,
            "head":    prompt[:80],
        }, ensure_ascii=False)
        lines = []
        if PROMPT_HIST_FILE.exists():
            lines = PROMPT_HIST_FILE.read_text(encoding="utf-8").splitlines()
        lines.append(entry)
        PROMPT_HIST_FILE.write_text("\n".join(lines[-5:]), encoding="utf-8")
    except Exception:
        pass


def get_momentum(current_domains: list) -> str:
    """
    Detecta si el usuario está en deep_work (mismo dominio repetido)
    o context_switch (cambio de dominio).
    """
    try:
        if not PROMPT_HIST_FILE.exists():
            return "neutral"
        lines = PROMPT_HIST_FILE.read_text(encoding="utf-8").splitlines()
        if len(lines) < 2:
            return "neutral"
        recent = [json.loads(l) for l in lines[-3:] if l.strip()]
        domain_matches = sum(
            1 for h in recent
            if any(d in h.get("domains", []) for d in current_domains)
        )
        return "deep_work" if domain_matches >= 2 else "context_switch"
    except Exception:
        return "neutral"


# ── Clasificacion de tipo de mensaje ─────────────────────────

_INSTRUCTION_VERBS = {
    "crea", "genera", "agrega", "añade", "quita", "borra", "elimina",
    "modifica", "actualiza", "cambia", "instala", "conecta", "ejecuta",
    "implementa", "arregla", "limpia", "construye", "arma", "escribe",
    "sube", "despliega", "configura", "edita", "mueve", "renombra",
    "haz", "hazlo", "aplica", "procede",
    "make", "create", "add", "remove", "delete", "update", "fix", "run",
    "build", "deploy", "install", "connect", "execute", "generate",
}

_INFORMING_PATTERNS = [
    r"\bfyi\b", r"\bsabe\s+que\b", r"\bnota\b", r"\brecuerda\s+que\b",
    r"\bte\s+(cuento|informo|digo|aviso)\b", r"\bpara\s+que\s+sepas\b",
    r"\besto\s+(es|fue|paso)\b", r"\bten\s+en\s+cuenta\b",
    r"\bcontexto\b.*:", r"\bimportante\b.*:",
]

_INFORMATIONAL_PATTERNS = [
    r"^(que|qu[eé]|cual|cu[aá]l|quien|qui[eé]n)\s+(es|son|fue|significa|hace|pasa)",
    r"^(como|c[oó]mo)\s+(funciona|se\s+usa|es\s+que|se\s+hace)",
    r"^(por\s+que|por\s+qu[eé]|cuando|d[oó]nde|cuanto)",
    r"^(explica|describe|dime|muestra|dame\s+info|que\s+es)",
    r"^(puedes\s+explicar|puedes\s+decirme|sabes\s+que)",
    r"\?$",
]


def classify_message_type(prompt: str) -> str:
    """
    Clasifica el mensaje:
      'instruction'   — tarea a ejecutar     → SIEMPRE grabar
      'informing'     — usuario da contexto  → grabar
      'informational' — pregunta pura        → NO grabar (salvo sin KB)
    """
    text  = prompt.lower().strip()
    words = set(re.findall(r'\b\w+\b', text))

    if words & _INSTRUCTION_VERBS:
        return "instruction"
    if re.search(r'\b(si\s+procede|go\s+ahead|adelante|hazlo|done|listo\s+para)\b', text):
        return "instruction"

    for pat in _INFORMING_PATTERNS:
        if re.search(pat, text):
            return "informing"

    for pat in _INFORMATIONAL_PATTERNS:
        if re.search(pat, text):
            return "informational"

    if text.endswith("?") or text.startswith("?"):
        return "informational"

    if len(text.split()) <= 6:
        return "informational"

    return "instruction"


def save_msg_type(msg_type: str, prompt: str, domains: list, has_kb: bool):
    """Guarda tipo del mensaje para que post_action_learn sepa si grabar."""
    try:
        MSG_TYPE_FILE.parent.mkdir(parents=True, exist_ok=True)
        MSG_TYPE_FILE.write_text(json.dumps({
            "type":    msg_type,
            "prompt":  prompt[:200],
            "domains": domains,
            "has_kb":  has_kb,
            "ts":      datetime.now().isoformat(),
        }, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def save_injection_record(domains: list, keywords: list,
                          has_lm: bool, has_kb: bool, has_ep: bool, intent: str):
    """Registra qué se inyectó — el Stop hook lo audita al terminar la sesión."""
    try:
        INJECTION_FILE.parent.mkdir(parents=True, exist_ok=True)
        INJECTION_FILE.write_text(json.dumps({
            "ts":       datetime.now().isoformat(),
            "domains":  domains,
            "keywords": keywords[:5],
            "has_lm":   has_lm,
            "has_kb":   has_kb,
            "has_ep":   has_ep,
            "intent":   intent,
        }, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


# ── Ultima actividad registrada ───────────────────────────────

def get_last_activity() -> str:
    try:
        if not NOTIFY_FILE.exists():
            return ""
        lines = NOTIFY_FILE.read_text(encoding="utf-8").strip().split("\n")
        guardado = [l for l in lines if "GUARDADO" in l]
        return "\n".join(guardado[-3:])
    except Exception:
        return ""


# ── Main ──────────────────────────────────────────────────────

def main():
    try:
        raw  = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)

    save_last_user_message(data)

    prompt = data.get("prompt", "")
    if not prompt or len(prompt.strip()) < 5:
        sys.exit(0)

    # Memory recall: "recuerdas lo último", "en qué estabas", etc.
    # → inyectar sesión más reciente del KB, no el crash recovery
    if is_memory_recall(prompt):
        latest = get_latest_session_summary()
        if latest:
            output = (
                '<memory_system domain="sessions" keywords="ultimo,recuerdo">\n'
                '<instruction>LEER ANTES DE ACTUAR. '
                'Priorizar sobre conocimiento de entrenamiento.</instruction>\n'
                '<last_session>\n'
                'Ultima sesion guardada en KB (responder basandose en esto):\n'
                + latest + '\n'
                '</last_session>\n'
                '</memory_system>\n'
            )
            sys.stdout.buffer.write(output.encode("utf-8", errors="replace"))
            sys.stdout.buffer.flush()
            sys.exit(0)

    # Clasificar tipo de mensaje ANTES de buscar KB
    msg_type = classify_message_type(prompt)

    keywords = extract_keywords(prompt)
    if not keywords:
        save_msg_type(msg_type, prompt, [], False)
        sys.exit(0)

    # 1. Cache hit = instantaneo (mismo tema reciente)
    cached = _read_classify_cache(keywords)
    if cached:
        domains  = cached["domains"]
        keywords = list(dict.fromkeys(cached["keywords"] + keywords))[:15]
    else:
        # 2. Clasificacion Python puro — sin API, sin red
        domains = classify_domains(keywords)
        _write_classify_cache(domains, keywords)

    # Intent: qué quiere HACER el usuario (no solo qué dominio)
    intent      = detect_intent(prompt)
    momentum    = get_momentum(domains)

    # Co-dominios (paso 1): dominio que históricamente aparece junto
    co_domains  = get_co_domains(domains)
    # Markov (paso 2): siguiente dominio más probable en la secuencia
    markov_next = get_markov_next(domains, co_domains)
    all_domains = domains + [d for d in co_domains if d not in domains]
    all_domains_with_markov = all_domains + [d for d in markov_next if d not in all_domains]

    # Sin dominio detectado → no buscar en KB (evita cross-domain noise)
    if not all_domains_with_markov:
        sys.exit(0)

    # B: "general" siempre incluido — base de conocimiento transversal
    if "general" not in all_domains_with_markov:
        all_domains_with_markov = all_domains_with_markov + ["general"]

    lm_out  = search_lm(keywords, all_domains_with_markov)
    kb_out  = search_kb(keywords, all_domains_with_markov)
    act_out = get_last_activity()
    ep_out  = search_episodic(keywords)

    # Guardar historial de prompts para momentum de próxima sesión
    update_prompt_history(prompt, domains, intent)

    # Guardar tipo de mensaje para que post_action_learn decida si grabar
    save_msg_type(msg_type, prompt, all_domains, has_kb=bool(kb_out or lm_out))

    sections = []
    if lm_out:
        sections.append(
            "<critical_patterns>\n"
            "⚠ PATRONES CONOCIDOS — USAR DIRECTAMENTE. No reinventar.\n"
            + lm_out
            + "\n</critical_patterns>"
        )
    if kb_out:
        sections.append(
            "<recipes>\n"
            "📋 RECETAS KB — aplicar antes de improvisar:\n"
            + kb_out
            + "\n</recipes>"
        )
    if act_out:
        sections.append(
            "<last_activity>\n"
            + act_out
            + "\n</last_activity>"
        )
    if ep_out:
        sections.append(
            "<episodic_memory>\n"
            "Sesiones anteriores relevantes:\n"
            + ep_out
            + "\n</episodic_memory>"
        )

    if sections:
        dom_str     = " + ".join(all_domains) if all_domains else "general"
        co_note     = f" [+{co_domains[0]}]" if co_domains else ""
        markov_note = f" [>{markov_next[0]}]" if markov_next else ""
        momentum_note = f" [{momentum}]" if momentum != "neutral" else ""
        kw_str      = ", ".join(keywords[:5])
        intent_note = f'\n<intent type="{intent}">{INTENT_CONTEXT.get(intent, "")}</intent>' if intent != "general" else ""
        body        = "\n".join(sections)
        output      = (
            f'<memory_system domain="{dom_str}{co_note}{markov_note}" '
            f'keywords="{kw_str}"{momentum_note}>\n'
            f'<instruction>LEER ANTES DE ACTUAR. '
            f'Priorizar sobre conocimiento de entrenamiento.</instruction>'
            f'{intent_note}\n'
            f'{body}\n'
            f'</memory_system>\n'
        )
        # Registrar qué se inyectó para audit de efectividad
        save_injection_record(
            all_domains, keywords,
            has_lm=bool(lm_out), has_kb=bool(kb_out), has_ep=bool(ep_out),
            intent=intent
        )
        sys.stdout.buffer.write(output.encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()

    sys.exit(0)


if __name__ == "__main__":
    main()
