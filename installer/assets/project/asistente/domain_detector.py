"""
domain_detector.py — Detección híbrida de dominios
===================================================
Detecta el dominio de un texto usando los DOMAIN_HINTS del clasificador
existente + keywords aprendidas de interacciones reales.

API pública:
  detect(text)                     → str  (dominio detectado o "general")
  suggest(text)                    → list (candidatos posibles)
  learn_domain_keywords(domain, keywords) → None (acumula keywords)
  get_domain_hints()               → dict (todos los hints cargados)

Usado por:
  ingest_knowledge.py → detect()  para auto-asignar dominio al ingerir
  on_user_message.py  → (vía domain_hints.json)
"""

import json
import re
import sys
from pathlib import Path

BASE_DIR    = Path.home() / ".adaptive_cli"
HINTS_FILE  = BASE_DIR / "knowledge" / "domain_hints.json"
DOMAINS_FILE = BASE_DIR / "knowledge" / "domains.json"
BUILTIN_FILE = BASE_DIR / "knowledge" / "domains_builtin.json"

# Threshold: >= 2 keywords en común → auto-asignar con confianza
AUTO_THRESHOLD = 2
# 1 keyword → sugerir (no auto-asignar)
SUGGEST_THRESHOLD = 1

STOP_WORDS = {
    "el", "la", "los", "las", "un", "una", "de", "del", "en", "que",
    "y", "a", "por", "con", "para", "es", "se", "no", "lo", "le", "su",
    "me", "te", "si", "mi", "tu", "al", "hay", "ya", "pero", "como",
    "the", "an", "in", "of", "to", "is", "it", "for", "and", "or",
    "puedo", "quiero", "hacer", "haz", "dame", "muestra", "dime",
    "necesito", "ver", "este", "esta", "esto", "cuando", "donde",
}


def _extract_words(text: str) -> list:
    words = re.findall(r'\b[a-zA-Z0-9_áéíóúñ]{3,}\b', text.lower())
    return [w for w in words if w not in STOP_WORDS]


def _load_known_domains() -> list:
    """Retorna lista de todos los dominios conocidos (builtin + dinámicos)."""
    domains = []
    for f in [BUILTIN_FILE, DOMAINS_FILE]:
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                domains.extend(data.keys())
            except Exception:
                pass
    return list(set(domains))


def get_domain_hints() -> dict:
    """Retorna todos los hints aprendidos desde disco."""
    if not HINTS_FILE.exists():
        return {}
    try:
        return json.loads(HINTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _score_domains(words: list) -> dict:
    """Puntúa cada dominio conocido contra las palabras del texto."""
    hints = get_domain_hints()
    word_set = set(words)
    scores = {}
    for domain, kw_weights in hints.items():
        score = sum(w for kw, w in kw_weights.items() if kw in word_set)
        if score > 0:
            scores[domain] = score
    return scores


def detect(text: str) -> str:
    """
    Detecta el dominio del texto.
    - >= AUTO_THRESHOLD keywords en común → retorna dominio
    - < threshold → retorna "general"
    """
    if not text or not text.strip():
        return "general"
    words = _extract_words(text)
    scores = _score_domains(words)
    if not scores:
        return "general"
    best_domain = max(scores, key=scores.__getitem__)
    if scores[best_domain] >= AUTO_THRESHOLD:
        return best_domain
    return "general"


def suggest(text: str) -> list:
    """
    Retorna lista de dominios candidatos (score >= SUGGEST_THRESHOLD).
    Útil para el modo híbrido: mostrar opciones al usuario.
    """
    if not text or not text.strip():
        return []
    words = _extract_words(text)
    scores = _score_domains(words)
    candidates = [d for d, s in scores.items() if s >= SUGGEST_THRESHOLD]
    candidates.sort(key=lambda d: -scores[d])
    return candidates[:5]


def learn_domain_keywords(domain: str, keywords: list, weight: int = 1):
    """
    Acumula keywords para un dominio. Persiste en domain_hints.json.
    Llamar después de confirmación explícita del usuario o cuando
    el motor aprende qué keywords corresponden a qué dominio.
    """
    if not domain or not keywords:
        return
    HINTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    hints = get_domain_hints()
    if domain not in hints:
        hints[domain] = {}
    for kw in keywords:
        kw = kw.lower().strip()
        if kw and kw not in STOP_WORDS and len(kw) >= 2:
            # Acumular: si ya existe el keyword, tomar el mayor peso
            hints[domain][kw] = max(hints[domain].get(kw, 0), weight)
    HINTS_FILE.write_text(
        json.dumps(hints, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )


def auto_learn_from_session(domain: str, text: str):
    """
    Extrae keywords del texto y las asocia al dominio confirmado.
    Llamar desde session_end cuando se conoce el dominio real de la sesión.
    """
    if not domain or domain == "general" or not text:
        return
    words = _extract_words(text)
    # Solo palabras "sustantivas" (>= 4 chars) como keywords
    keywords = [w for w in words if len(w) >= 4][:30]
    if keywords:
        learn_domain_keywords(domain, keywords, weight=1)


if __name__ == "__main__":
    # CLI: python domain_detector.py "texto a clasificar"
    text = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""
    if text:
        print(f"Dominio detectado: {detect(text)}")
        candidates = suggest(text)
        if candidates:
            print(f"Candidatos: {candidates}")
    else:
        print("Uso: python domain_detector.py \"texto a clasificar\"")
        hints = get_domain_hints()
        print(f"Dominios con hints aprendidos: {list(hints.keys())}")
