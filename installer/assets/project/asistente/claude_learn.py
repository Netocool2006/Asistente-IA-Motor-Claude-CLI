"""
claude_learn.py — Wrapper de Claude CLI con aprendizaje automático
==================================================================
En lugar de correr 'claude' directo, corré:
    python claude_learn.py "tu tarea aquí"

El wrapper:
1. Consulta la base de conocimiento local
2. Inyecta el contexto al prompt
3. Ejecuta Claude CLI
4. Captura la respuesta
5. Extrae el JSON resumen (si Claude lo incluyó)
6. Registra automáticamente el patrón en la base

Así el aprendizaje es AUTOMÁTICO — no tenés que copiar nada manualmente.

También funciona en modo interactivo:
    python claude_learn.py
    (abre Claude CLI normal, pero al cerrar te pregunta qué aprendió)
"""

import json
import subprocess
import sys
import re
import time
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent))
from knowledge_base import (
    add_pattern, add_fact, cross_domain_search,
    export_context, get_global_stats, DOMAINS,
)

CLAUDE_CLI = "claude"


def extract_learning_json(text: str) -> dict:
    """
    Busca el JSON resumen de aprendizaje en la salida de Claude.
    Claude debería imprimirlo al final de su respuesta.
    """
    patterns = [
        r'```json\s*(\{[^`]*?"status"[^`]*?\})\s*```',
        r'```\s*(\{[^`]*?"status"[^`]*?\})\s*```',
        r'(\{[^{}]*"status"\s*:\s*"(?:success|modified|partial|failed)"[^{}]*\})',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            try:
                data = json.loads(match)
                if "status" in data:
                    return data
            except json.JSONDecodeError:
                continue
    return None


def classify_task(user_input: str) -> tuple:
    """
    Intenta clasificar la tarea del usuario en un dominio y task_type.
    Retorna (domain, task_type, search_query).
    """
    text = user_input.lower()

    # Mapeo de palabras clave a dominios
    keyword_map = [
        (["sow", "propuesta", "alcance", "entregable"], "sow", "sow_generate"),
        (["revisar sow", "revisar propuesta", "contradicci", "incoherencia"], "sow", "sow_review"),
        (["fusionar", "fusión", "mezclar", "unir sow"], "sow", "sow_fusion"),
        (["bom", "bill of material", "cotización", "quote"], "bom", "bom_validate"),
        (["consolidar bom", "fusionar bom", "mezclar bom"], "bom", "bom_fusion"),
        (["propuesta económica", "precio", "mep", "pago"], "bom", "bom_to_proposal"),
        (["tipo de cambio", "tasa cambio"], "bom", "bom_fx_strategy"),
        (["login sap", "iniciar sesión sap", "entrar sap"], "sap_tierra", "sap_login"),
        (["item", "items", "oportunidad", "llenar", "código"], "sap_tierra", "sap_fill_items"),
        (["quote sap", "cotización sap"], "sap_tierra", "sap_quote_manual"),
        (["monday", "pipeline", "bitácora", "seguimiento"], "monday", "monday_update_pipeline"),
        (["presentación", "pptx", "powerpoint", "deck"], "pptx", "pptx_proposal_summary"),
        (["bau", "autorización", "proceso", "formulario"], "bpm_bau", "bau_fill_form"),
        (["correo", "outlook", "email", "adjuntar"], "outlook", "outlook_send"),
    ]

    for keywords, domain, task_type in keyword_map:
        if any(kw in text for kw in keywords):
            return domain, task_type, user_input

    return None, "general", user_input


def run_with_learning(user_input: str):
    """
    Flujo completo: consultar → ejecutar → aprender.
    """
    print()
    print("=" * 60)
    print("  Claude + Aprendizaje Automatico")
    print("=" * 60)

    # Paso 1: Clasificar la tarea
    domain, task_type, search_query = classify_task(user_input)
    print(f"  Tarea detectada: {task_type} (dominio: {domain or 'general'})")

    # Paso 2: Consultar base de conocimiento
    print(f"  Consultando base de conocimiento...")
    context = export_context(domain=domain, text_query=search_query, limit=5)

    if "No se encontraron" in context:
        print(f"  Sin contexto previo — modo exploración")
        context_block = ""
    else:
        lines = context.strip().split("\n")
        print(f"  Encontradas {len(lines)} líneas de contexto relevante")
        context_block = f"\n\nCONTEXTO DE LA BASE DE CONOCIMIENTO LOCAL:\n{context}\n"

    # Paso 3: Construir prompt con contexto
    full_prompt = f"""{user_input}
{context_block}
IMPORTANTE: Al finalizar, incluye un bloque JSON con este formato:
```json
{{
    "status": "success|partial|failed",
    "task_type": "{task_type}",
    "domain": "{domain or 'general'}",
    "strategy": "nombre_corto_de_tu_enfoque",
    "code_snippet": "código clave si aplica (max 500 chars)",
    "notes": "qué aprendiste, qué funcionó, qué no",
    "tags": ["tag1", "tag2"]
}}
```"""

    # Paso 4: Ejecutar Claude CLI
    print(f"  Ejecutando Claude CLI...")
    print("=" * 60)
    print()

    start_time = time.time()

    try:
        result = subprocess.run(
            [CLAUDE_CLI, "-p", full_prompt, "--output-format", "json"],
            capture_output=True, text=True, timeout=600,
            encoding="utf-8", errors="replace",
        )
        elapsed = time.time() - start_time

        if result.returncode != 0:
            print(f"\n[ERROR] Claude CLI falló: {result.stderr[:300]}")
            return

        # Parsear respuesta
        try:
            output = json.loads(result.stdout)
            response_text = output.get("result", result.stdout)
        except json.JSONDecodeError:
            response_text = result.stdout

        # Mostrar respuesta de Claude
        print(response_text[:5000])

    except subprocess.TimeoutExpired:
        print("\n[TIMEOUT] Claude tardó más de 10 minutos")
        return
    except FileNotFoundError:
        print(f"\n[ERROR] '{CLAUDE_CLI}' no encontrado. Verificar instalación.")
        return

    # Paso 5: Extraer aprendizaje y registrar
    print()
    print("=" * 60)
    print(f"  Tiempo: {elapsed:.1f}s")

    learning = extract_learning_json(response_text)

    if learning and learning.get("status") in ("success", "partial", "modified"):
        learned_domain = learning.get("domain", domain or "business_rules")
        learned_task = learning.get("task_type", task_type)
        key = f"{learned_task}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        solution = {
            "strategy": learning.get("strategy", "auto_learned"),
            "code_snippet": learning.get("code_snippet", ""),
            "notes": learning.get("notes", ""),
            "time_to_solve_seconds": elapsed,
            "auto_learned": True,
        }

        tags = learning.get("tags", [])
        if not tags:
            tags = [learned_task, learned_domain]

        # Verificar que el dominio existe
        if learned_domain not in DOMAINS:
            learned_domain = "business_rules"

        try:
            pid = add_pattern(learned_domain, key, solution, tags=tags)
            print(f"  APRENDIZAJE REGISTRADO: {pid}")
            print(f"    Dominio: {learned_domain}")
            print(f"    Estrategia: {learning.get('strategy', '?')}")
            print(f"    Notas: {learning.get('notes', '?')[:100]}")
        except Exception as e:
            print(f"  [WARN] No se pudo registrar: {e}")
    else:
        print(f"  Sin JSON de aprendizaje detectado en la respuesta")
        print(f"  (Claude no incluyó el bloque JSON resumen)")

    # Stats
    stats = get_global_stats()
    print(f"  Base de conocimiento: {stats.get('total', '?')} entradas")
    print("=" * 60)


def run_interactive_with_learning():
    """
    Modo interactivo: abre Claude CLI normal.
    Al cerrar, pregunta qué aprendió para registrar.
    """
    print()
    print("Abriendo Claude CLI en modo interactivo...")
    print("(Al terminar, te preguntaré qué aprendiste)")
    print()

    subprocess.run([CLAUDE_CLI], cwd=str(Path(__file__).parent))

    # Al cerrar, preguntar
    print()
    print("=" * 60)
    print("  Sesión terminada — Registro de aprendizaje")
    print("=" * 60)
    print()

    answer = input("Hubo algo nuevo que aprender? (s/n): ").strip().lower()
    if answer != "s":
        print("OK, sin registrar nada.")
        return

    domain = input("Dominio (sow/bom/sap_tierra/monday/business_rules/otro): ").strip()
    if domain not in DOMAINS:
        domain = "business_rules"

    strategy = input("Nombre corto de lo que aprendiste: ").strip()
    notes = input("Detalle (qué funcionó, qué no): ").strip()
    tags_str = input("Tags separados por coma: ").strip()
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]

    key = f"interactive_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    solution = {
        "strategy": strategy,
        "notes": notes,
        "auto_learned": False,
        "source": "sesión interactiva",
    }

    pid = add_pattern(domain, key, solution, tags=tags)
    print(f"\nRegistrado: {pid}")
    print(f"  Dominio: {domain}")
    print(f"  Estrategia: {strategy}")

    stats = get_global_stats()
    print(f"  Base total: {stats.get('total', '?')} entradas")


# ── CLI ────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Modo prompt directo: python claude_learn.py "hacer login SAP"
        user_input = " ".join(sys.argv[1:])
        run_with_learning(user_input)
    else:
        # Modo interactivo: python claude_learn.py
        run_interactive_with_learning()
