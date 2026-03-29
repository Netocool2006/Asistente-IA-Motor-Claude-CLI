"""
adaptive_executor.py — Ejecutor Adaptativo con Memoria
======================================================
Orquesta la lógica principal:
1. Recibe una tarea (ej: "login SAP CRM")
2. Consulta la memoria local (learning_memory.py)
3. Si hay patrón → ejecuta directamente SIN llamar a la IA
4. Si NO hay patrón → llama a Claude CLI, captura la solución, la registra
5. Si falla un patrón existente → re-invoca la IA, actualiza el patrón

Integración con Claude Code CLI:
    claude -p "$(python adaptive_executor.py prepare sap_login crm_logon)"
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from learning_memory import (
    search_pattern,
    register_pattern,
    record_reuse,
    update_pattern,
    export_for_claude_context,
    get_stats,
)

# ── Configuración ──────────────────────────────────────────────
CLAUDE_CLI = "claude"  # Ajustar si tu path es diferente
MAX_RETRIES = 3
CONFIDENCE_THRESHOLD = 0.6  # Si success_rate < esto, re-evaluar con IA


def prepare_prompt(task_type: str, context_key: str, user_request: str) -> str:
    """
    Prepara el prompt óptimo para Claude CLI.
    Si hay patrones aprendidos, los inyecta como contexto.
    Si no hay, genera un prompt de exploración.
    """
    pattern = search_pattern(task_type, context_key)
    learned_context = export_for_claude_context(task_type, limit=5)

    if pattern and pattern["stats"]["success_rate"] >= CONFIDENCE_THRESHOLD:
        # ── MODO RÁPIDO: ya sabemos cómo resolver esto ──
        sol = pattern["solution"]
        prompt = f"""CONTEXTO: Ya resolvimos una tarea similar antes. 
Usa esta solución probada como base (éxito: {pattern['stats']['success_rate']*100:.0f}%):

Estrategia: {sol.get('strategy', 'N/A')}
Código base:
```python
{sol.get('code_snippet', '# Sin snippet previo')}
```
Notas previas: {sol.get('notes', 'Ninguna')}
Selectores que funcionaron: {json.dumps(sol.get('selector_chain', []))}

TAREA ACTUAL: {user_request}

INSTRUCCIONES:
- Reutiliza el patrón anterior como punto de partida
- Si necesitas ajustar algo, hazlo pero explica qué cambió y por qué
- Al final, imprime un JSON con la estructura:
  {{"status": "success"|"modified"|"failed", "solution_used": "...", "changes": "..."}}
"""
    else:
        # ── MODO EXPLORACIÓN: territorio nuevo ──
        prompt = f"""TAREA: {user_request}

PATRONES APRENDIDOS PREVIAMENTE (referencia):
{learned_context}

INSTRUCCIONES IMPORTANTES:
1. Resuelve la tarea paso a paso
2. Si encuentras errores, corrígelos y documenta qué falló
3. Al final, imprime un JSON resumen con esta estructura:
{{
    "status": "success"|"partial"|"failed",
    "strategy": "nombre_corto_de_tu_enfoque",
    "selector_chain": ["selectores CSS/aria que usaste"],
    "code_snippet": "el código clave que funcionó (max 500 chars)",
    "notes": "qué aprendiste, qué NO funcionó y por qué",
    "attempts": numero_de_intentos,
    "time_seconds": tiempo_aproximado
}}

Este JSON se guardará en memoria local para reutilizar la próxima vez.
Sé específico en 'notes' — es lo que tu yo futuro leerá para no repetir errores.
"""

    return prompt


def execute_with_claude(prompt: str, timeout: int = 600) -> dict:
    """
    Ejecuta un prompt via Claude Code CLI y captura el resultado.
    """
    try:
        result = subprocess.run(
            [CLAUDE_CLI, "-p", prompt, "--output-format", "json"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            return {
                "status": "error",
                "error": result.stderr[:500],
                "stdout": result.stdout[:500],
            }

        # Intentar parsear el JSON de la respuesta de Claude
        output = result.stdout
        # Buscar el JSON en la salida (puede haber texto antes/después)
        try:
            # Claude CLI con --output-format json devuelve JSON estructurado
            parsed = json.loads(output)
            # Extraer el texto de la respuesta
            response_text = parsed.get("result", output)
        except json.JSONDecodeError:
            response_text = output

        # Intentar extraer el JSON resumen que le pedimos a Claude
        solution_json = _extract_json_from_text(response_text)

        return {
            "status": "success",
            "full_output": response_text[:5000],
            "solution": solution_json,
        }

    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": f"Excedió {timeout}s"}
    except FileNotFoundError:
        return {"status": "error", "error": f"CLI '{CLAUDE_CLI}' no encontrado"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _extract_json_from_text(text: str) -> dict:
    """Extrae el primer bloque JSON válido del texto de Claude."""
    import re

    # Buscar JSON en bloques de código
    json_patterns = [
        r'```json\s*(\{.*?\})\s*```',
        r'```\s*(\{.*?\})\s*```',
        r'(\{[^{}]*"status"[^{}]*\})',
    ]

    for pattern in json_patterns:
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match)
            except json.JSONDecodeError:
                continue

    return {"status": "unknown", "notes": "No se pudo extraer JSON de la respuesta"}


def run_adaptive(
    task_type: str,
    context_key: str,
    user_request: str,
    tags: list[str] = None,
    dry_run: bool = False,
):
    """
    Flujo principal: buscar → ejecutar → aprender.

    Args:
        task_type:     Categoría (ej: "sap_login", "crm_field_fill")
        context_key:   Contexto específico (ej: "crm_logon_page", "opportunity_form")
        user_request:  Lo que el usuario quiere lograr
        tags:          Tags para indexar
        dry_run:       Si True, solo muestra el prompt sin ejecutar
    """
    print(f"\n{'='*60}")
    print(f"🧠 Adaptive CLI — {task_type}::{context_key}")
    print(f"{'='*60}")

    # Paso 1: Consultar memoria
    existing = search_pattern(task_type, context_key, tags)
    if existing:
        sr = existing["stats"]["success_rate"]
        reuses = existing["stats"]["reuses"]
        print(f"✅ Patrón encontrado (éxito: {sr*100:.0f}%, reusos: {reuses})")
        if sr >= CONFIDENCE_THRESHOLD:
            print(f"   → Modo RÁPIDO: reutilizando solución probada")
        else:
            print(f"   → Modo CAUTELOSO: patrón con baja confianza, se re-evaluará")
    else:
        print(f"🆕 Sin patrón previo → Modo EXPLORACIÓN")

    # Paso 2: Preparar prompt
    prompt = prepare_prompt(task_type, context_key, user_request)

    if dry_run:
        print(f"\n📝 PROMPT GENERADO (dry-run):\n")
        print(prompt)
        return

    # Paso 3: Ejecutar
    start_time = time.time()
    print(f"\n⏳ Ejecutando via Claude CLI...")
    result = execute_with_claude(prompt)
    elapsed = time.time() - start_time
    print(f"   Tiempo: {elapsed:.1f}s")

    # Paso 4: Procesar resultado y aprender
    if result["status"] == "success" and result.get("solution"):
        sol = result["solution"]
        sol_status = sol.get("status", "unknown")

        if sol_status in ("success", "modified"):
            if existing:
                # Actualizar patrón existente
                if sol_status == "modified":
                    update_pattern(
                        existing["id"],
                        sol,
                        reason=f"Ajustado en ejecución ({elapsed:.0f}s)"
                    )
                    print(f"🔄 Patrón actualizado con mejoras")
                record_reuse(existing["id"], success=True)
                print(f"📊 Reuso exitoso registrado")
            else:
                # Registrar patrón nuevo
                sol["time_to_solve_seconds"] = elapsed
                pid = register_pattern(
                    task_type=task_type,
                    context_key=context_key,
                    solution=sol,
                    tags=tags or [],
                    error_context=None,
                )
                print(f"💾 Nuevo patrón registrado: {pid}")

            print(f"✅ Tarea completada exitosamente")

        elif sol_status == "failed":
            if existing:
                record_reuse(existing["id"], success=False, notes=sol.get("notes", ""))
                print(f"❌ Patrón falló — success_rate actualizado")
            print(f"❌ Tarea falló: {sol.get('notes', 'sin detalle')}")

    elif result["status"] == "error":
        print(f"💥 Error de ejecución: {result.get('error', 'desconocido')}")
        if existing:
            record_reuse(existing["id"], success=False, notes=result.get("error", ""))

    elif result["status"] == "timeout":
        print(f"⏰ Timeout — considerar dividir la tarea")

    # Paso 5: Resumen
    print(f"\n{'─'*60}")
    stats = get_stats()
    print(f"📈 Patrones totales: {stats['total_patterns']} | "
          f"Reusos: {stats['total_reuses']} | "
          f"Llamadas IA ahorradas: {stats['total_ai_calls_saved']}")
    print(f"{'='*60}\n")

    return result


# ── CLI ────────────────────────────────────────────────────────

def main():
    """
    Modos de uso:

        # Ejecutar tarea adaptativa
        python adaptive_executor.py run sap_login crm_logon "Haz login en SAP CRM" --tags sap,login

        # Solo ver qué prompt generaría (sin ejecutar)
        python adaptive_executor.py prepare sap_login crm_logon "Haz login en SAP CRM"

        # Ver estadísticas
        python adaptive_executor.py stats

        # Exportar contexto para copiar/pegar
        python adaptive_executor.py export sap_login
    """
    import argparse

    parser = argparse.ArgumentParser(description="Adaptive CLI Executor")
    sub = parser.add_subparsers(dest="command")

    # run
    p_run = sub.add_parser("run", help="Ejecutar tarea con aprendizaje")
    p_run.add_argument("task_type", help="Categoría de la tarea")
    p_run.add_argument("context_key", help="Contexto específico")
    p_run.add_argument("request", help="Descripción de la tarea")
    p_run.add_argument("--tags", default="", help="Tags separados por coma")
    p_run.add_argument("--dry-run", action="store_true", help="Solo mostrar prompt")

    # prepare (solo genera el prompt)
    p_prep = sub.add_parser("prepare", help="Solo generar prompt")
    p_prep.add_argument("task_type")
    p_prep.add_argument("context_key")
    p_prep.add_argument("request")

    # stats
    sub.add_parser("stats", help="Ver estadísticas")

    # export
    p_exp = sub.add_parser("export", help="Exportar patrones como texto")
    p_exp.add_argument("task_type", nargs="?", default=None)

    args = parser.parse_args()

    if args.command == "run":
        tags = [t.strip() for t in args.tags.split(",") if t.strip()]
        run_adaptive(args.task_type, args.context_key, args.request, tags, args.dry_run)

    elif args.command == "prepare":
        prompt = prepare_prompt(args.task_type, args.context_key, args.request)
        print(prompt)

    elif args.command == "stats":
        print(json.dumps(get_stats(), indent=2, ensure_ascii=False))

    elif args.command == "export":
        print(export_for_claude_context(args.task_type))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
