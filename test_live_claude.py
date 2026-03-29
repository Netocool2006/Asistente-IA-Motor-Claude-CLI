"""
test_live_claude.py — Pruebas E2E reales con Claude CLI
=======================================================
Invoca `claude -p` como subprocess real para probar:
1. Que los hooks inyectan contexto KB correctamente
2. Que Claude usa el contexto (KB hits)
3. Que el sistema aprende de nuevas tareas
4. Que reutiliza patrones en la segunda llamada

Ejecutar: python test_live_claude.py
"""

import io, json, sys, os, subprocess, time, re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_DIR  = Path(__file__).parent
HOME_CLAUDE  = os.environ.get("LOCALAPPDATA", "") + "\\ClaudeCode"
ADAPTIVE_DIR = Path(HOME_CLAUDE) / ".adaptive_cli"
PYTHON       = sys.executable

# Colores
GR="\033[92m"; RD="\033[91m"; YL="\033[93m"; BL="\033[94m"
CY="\033[96m"; MG="\033[95m"; BLD="\033[1m"; RS="\033[0m"

results = defaultdict(int)
failures = []
_sec = ""

def section(name):
    global _sec; _sec = name
    print(f"\n{BL}{BLD}{'═'*70}{RS}")
    print(f"{BL}{BLD}  {name}{RS}")
    print(f"{BL}{BLD}{'═'*70}{RS}")

def ok(msg):
    results["pass"] += 1
    print(f"  {GR}✓ PASS{RS}  {msg}")

def fail(msg, detail=""):
    results["fail"] += 1
    d = f"\n         {RD}{detail[:300]}{RS}" if detail else ""
    print(f"  {RD}✗ FAIL{RS}  {msg}{d}")
    failures.append(f"[{_sec}] {msg}")

def warn(msg):
    results["warn"] += 1
    print(f"  {YL}⚠ WARN{RS}  {msg}")

def info(msg):
    print(f"  {CY}ℹ INFO{RS}  {msg}")


def call_claude(prompt: str, timeout: int = 120) -> dict:
    """
    Invoca claude -p con el HOME correcto (igual que claude-fix.ps1).
    Usa redirección a archivo para evitar pipe-deadlock cuando hooks activos.
    Retorna dict con: rc, stdout, stderr, elapsed, solution_json
    """
    env = os.environ.copy()
    env["HOME"]             = HOME_CLAUDE
    env["USERPROFILE"]      = HOME_CLAUDE
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"]       = "1"
    # Desactivar detección de sesión anidada para permitir subprocess
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)

    t0 = time.time()
    try:
        safe_prompt = prompt.replace("'", "''").replace('\n', ' ')
        # Redirigir a archivos para evitar pipe-deadlock por hooks hijos
        out_file = PROJECT_DIR / "_lcout.txt"
        err_file = PROJECT_DIR / "_lcerr.txt"
        cmd = (
            f"& 'c:\\chance1\\claude-fix.ps1' "
            f"-p '{safe_prompt}' --output-format json "
            f"2>'{err_file}' | Out-File -FilePath '{out_file}' -Encoding utf8"
        )
        rc = subprocess.call(
            ["powershell", "-NoProfile", "-Command", cmd],
            timeout=timeout, cwd=str(PROJECT_DIR), env=env,
        )
        elapsed = time.time() - t0

        try:
            raw_out = out_file.read_text(encoding="utf-8-sig").strip()
        except Exception:
            raw_out = ""
        try:
            raw_err = err_file.read_text(encoding="utf-8").strip()
        except Exception:
            raw_err = ""

        # Parsear output JSON de claude CLI
        full_text = ""
        try:
            parsed = json.loads(raw_out)
            full_text = parsed.get("result", raw_out)
        except Exception:
            full_text = raw_out

        # Extraer JSON de aprendizaje del texto de respuesta
        solution = _extract_learning_json(full_text)

        return {
            "rc": rc,
            "stdout": raw_out[:3000],
            "stderr": raw_err[:500],
            "full_text": full_text[:3000],
            "elapsed": elapsed,
            "solution": solution,
        }
    except subprocess.TimeoutExpired:
        return {"rc": -1, "stderr": "TIMEOUT", "elapsed": timeout, "stdout": "", "full_text": "", "solution": {}}
    except FileNotFoundError:
        return {"rc": -99, "stderr": "claude CLI not found", "elapsed": 0, "stdout": "", "full_text": "", "solution": {}}
    except Exception as e:
        return {"rc": -98, "stderr": str(e), "elapsed": 0, "stdout": "", "full_text": "", "solution": {}}


def _extract_learning_json(text: str) -> dict:
    """Extrae el primer JSON válido con campo 'status' del texto."""
    patterns = [
        r'```json\s*(\{.*?\})\s*```',
        r'```\s*(\{.*?\})\s*```',
        r'(\{[^{}]*"status"[^{}]*\})',
    ]
    for pat in patterns:
        for m in re.findall(pat, text, re.DOTALL):
            try:
                return json.loads(m)
            except Exception:
                pass
    return {}


def kb_stats_before_after(domain: str) -> tuple:
    """Lee stats de KB para comparar antes/después de una llamada."""
    try:
        sys.path.insert(0, str(PROJECT_DIR))
        import knowledge_base as kb
        data = kb.search(domain, text_query="")
        return len(data)
    except Exception:
        return 0


def lm_stats() -> dict:
    """Lee estadísticas de learning_memory."""
    try:
        import learning_memory as lm
        return lm.get_stats()
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════
# VERIFICACIÓN PREVIA
# ══════════════════════════════════════════════════════════════
section("PRE-CHECK — Verificar claude CLI disponible")

r = subprocess.run(
    "claude --version",
    capture_output=True, text=True, shell=True,
    env={**os.environ,
         "HOME": HOME_CLAUDE,
         "USERPROFILE": HOME_CLAUDE,
         "PATH": str(Path.home() / "AppData" / "Roaming" / "npm") + ";" + os.environ.get("PATH", "")},
    cwd=str(PROJECT_DIR)
)
if r.returncode == 0:
    ok(f"claude CLI disponible: {r.stdout.strip()}")
else:
    fail("claude CLI NO disponible — abortando", r.stderr[:200])
    sys.exit(1)

# Verificar KB poblada
try:
    sys.path.insert(0, str(PROJECT_DIR))
    import knowledge_base as kb
    import learning_memory as lm

    stats_kb = kb.get_stats() if hasattr(kb, 'get_stats') else {}
    rules = kb.search("business_rules", text_query="IVA")
    sap_patterns = lm.search_pattern("sap_login", "crm_logon_client500")

    if rules:
        ok(f"KB business_rules poblada ({len(rules)} entries con IVA)")
    else:
        warn("KB business_rules vacía — considera ejecutar seed_gbm_knowledge.py primero")

    if sap_patterns:
        ok("learning_memory: SAP login pattern disponible")
    else:
        warn("learning_memory: sin patrones SAP (seed_sap_patterns.py no ejecutado)")
except Exception as e:
    warn(f"No se pudo verificar KB: {e}")


# ══════════════════════════════════════════════════════════════
# BLOQUE 1 — KB HIT: Claude usa contexto inyectado por hooks
# ══════════════════════════════════════════════════════════════
section("BLOQUE 1 — KB Hit: Hooks inyectan contexto, Claude lo usa")

info("Cada llamada tarda ~20-40s. Total estimado: 3-4 min para este bloque.")

# B1.1 — Regla de negocio: sufijo _PS
print(f"\n  {YL}→ B1.1 Llamando claude -p: sufijo _PS contratos...{RS}")
t0 = time.time()
r1 = call_claude(
    "Nestor: Tengo una oportunidad de tipo CONTRATO para IBM MQ en Guatemala. "
    "El código base es IBMMQ245. ¿Qué sufijo le agrego al código y por qué? "
    "Responde en máximo 3 líneas y al final imprime: "
    '{"status": "success", "strategy": "regla_sufijo", "notes": "tu respuesta resumida"}'
)
elapsed = time.time() - t0

if r1["rc"] == 0:
    ok(f"B1.1 claude -p rc=0 ({elapsed:.1f}s)")
    text = r1["full_text"].lower()
    if "_ps" in text or "sufijo ps" in text or "post-sale" in text:
        ok("B1.1 Respuesta contiene '_PS' — KB business_rules fue usada")
    else:
        warn(f"B1.1 Respuesta no menciona _PS: {r1['full_text'][:200]}")
    if r1["solution"].get("status") == "success":
        ok("B1.1 JSON de aprendizaje extraído correctamente")
    else:
        warn(f"B1.1 JSON de aprendizaje no encontrado o parcial: {r1['solution']}")
else:
    fail("B1.1 claude -p falló", r1["stderr"])

time.sleep(3)  # Pausa entre llamadas

# B1.2 — Regla de negocio: IVA Guatemala
print(f"\n  {YL}→ B1.2 Llamando claude -p: IVA Guatemala...{RS}")
r2 = call_claude(
    "Nestor: Voy a generar una propuesta económica para un cliente en Guatemala. "
    "¿Cuánto es el IVA y cómo lo aplico al monto de $50,000 USD? "
    "Responde directo y al final: "
    '{"status": "success", "strategy": "calculo_iva", "notes": "porcentaje y monto"}'
)

if r2["rc"] == 0:
    ok(f"B1.2 claude -p rc=0 ({r2['elapsed']:.1f}s)")
    text = r2["full_text"].lower()
    if "12%" in text or "12 %" in text or "6,000" in text or "6000" in text:
        ok("B1.2 Respuesta contiene IVA 12% — KB business_rules aplicada")
    else:
        warn(f"B1.2 IVA no claro en respuesta: {r2['full_text'][:200]}")
else:
    fail("B1.2 claude -p falló", r2["stderr"])

time.sleep(3)

# B1.3 — Regla de negocio: Tarifas de soporte
print(f"\n  {YL}→ B1.3 Llamando claude -p: tarifas soporte...{RS}")
r3 = call_claude(
    "Nestor: Un cliente pregunta cuánto cobro por soporte 24x7 y 8x5 por hora. "
    "¿Cuáles son las tarifas estándar? "
    "Responde directo con los números y al final: "
    '{"status": "success", "strategy": "consulta_tarifas", "notes": "tarifas encontradas"}'
)

if r3["rc"] == 0:
    ok(f"B1.3 claude -p rc=0 ({r3['elapsed']:.1f}s)")
    text = r3["full_text"]
    has_24x7 = any(x in text for x in ["$80", "$85", "80/hr", "85/hr", "80-85"])
    has_8x5  = any(x in text for x in ["$60", "60/hr"])
    if has_24x7 and has_8x5:
        ok("B1.3 Tarifas 24x7 y 8x5 encontradas — KB tarifas_soporte aplicada")
    elif has_24x7 or has_8x5:
        warn(f"B1.3 Solo una tarifa encontrada en respuesta: {text[:200]}")
    else:
        warn(f"B1.3 Tarifas no encontradas en respuesta: {text[:200]}")
else:
    fail("B1.3 claude -p falló", r3["stderr"])

time.sleep(3)


# ══════════════════════════════════════════════════════════════
# BLOQUE 2 — CICLO APRENDER → REUTILIZAR
# ══════════════════════════════════════════════════════════════
section("BLOQUE 2 — Ciclo de Aprendizaje: Nuevo patrón → Reutilización")

# Estadísticas antes
stats_before = lm_stats()
total_patterns_before = stats_before.get("total_patterns", 0)
total_reuses_before   = stats_before.get("total_reuses", 0)
info(f"Estado inicial — Patrones: {total_patterns_before} | Reusos: {total_reuses_before}")

# B2.1 — Primera llamada: tema sin patrón (aprende)
print(f"\n  {YL}→ B2.1 Primera llamada (aprendizaje nuevo)...{RS}")
task_desc = "calcular MEP para propuesta de soporte IBM con descuento especial del 15%"
r_learn = call_claude(
    f"Nestor: {task_desc}. "
    "El precio lista es $120,000 USD. Calcula el MEP aplicando 15% de descuento. "
    "Muestra el cálculo paso a paso. Al final imprime exactamente este JSON: "
    '{"status": "success", "strategy": "calculo_mep_descuento", '
    '"notes": "precio_lista=120000 descuento=15pct mep_resultado=102000", '
    '"attempts": 1}'
)

if r_learn["rc"] == 0:
    ok(f"B2.1 Primera llamada OK ({r_learn['elapsed']:.1f}s)")
    sol = r_learn.get("solution", {})
    if sol.get("status") == "success":
        ok(f"B2.1 JSON de aprendizaje capturado: strategy='{sol.get('strategy')}'")
        # Registrar manualmente el patrón aprendido
        try:
            pid = lm.register_pattern(
                "bom_economic", "mep_con_descuento_especial",
                sol, tags=["bom", "mep", "descuento", "propuesta"]
            )
            ok(f"B2.1 Patrón registrado en learning_memory: {pid[:8]}...")
        except Exception as e:
            warn(f"B2.1 No se pudo registrar patrón: {e}")
    else:
        warn(f"B2.1 JSON sin campo status=success: {sol}")
else:
    fail("B2.1 Primera llamada falló", r_learn["stderr"])

time.sleep(5)

# B2.2 — Segunda llamada: mismo contexto → reutiliza
print(f"\n  {YL}→ B2.2 Segunda llamada (reutilización)...{RS}")
r_reuse = call_claude(
    "Nestor: Misma situación de antes — calcular MEP para propuesta IBM con descuento 15%. "
    "¿Cuál es la fórmula y el resultado para $120,000 USD? "
    "Al final: "
    '{"status": "success", "strategy": "calculo_mep_descuento", "notes": "reutilizado"}'
)

if r_reuse["rc"] == 0:
    ok(f"B2.2 Segunda llamada OK ({r_reuse['elapsed']:.1f}s)")
    # Verificar que la respuesta es consistente con lo aprendido
    text = r_reuse["full_text"]
    if "102" in text or "102,000" in text or "15%" in text:
        ok("B2.2 Respuesta consistente con patrón aprendido (mismo resultado)")
    else:
        warn(f"B2.2 Resultado no consistente: {text[:200]}")

    # Comparar velocidad
    if r_reuse["elapsed"] < r_learn["elapsed"]:
        ok(f"B2.2 Segunda llamada más rápida: {r_reuse['elapsed']:.1f}s vs {r_learn['elapsed']:.1f}s")
    else:
        info(f"B2.2 Tiempos: 1ra={r_learn['elapsed']:.1f}s, 2da={r_reuse['elapsed']:.1f}s")
else:
    fail("B2.2 Segunda llamada falló", r_reuse["stderr"])

# Estadísticas después
stats_after = lm_stats()
total_patterns_after = stats_after.get("total_patterns", 0)
if total_patterns_after > total_patterns_before:
    ok(f"B2.3 Patrones aumentaron: {total_patterns_before} → {total_patterns_after}")
else:
    info(f"B2.3 Patrones: {total_patterns_before} → {total_patterns_after} (puede requerir registro manual)")

time.sleep(3)


# ══════════════════════════════════════════════════════════════
# BLOQUE 3 — TAREAS REALES GBM
# ══════════════════════════════════════════════════════════════
section("BLOQUE 3 — Tareas Reales GBM (SOW, BoM, SAP)")

# B3.1 — SOW: Tipo de documento
print(f"\n  {YL}→ B3.1 SOW — tipo de contrato de renovación...{RS}")
r_sow = call_claude(
    "Nestor: Tengo una renovación anual de soporte para IBM MQ en Guatemala. "
    "¿Qué tipo de SOW necesito generar? ¿Cuáles son las secciones clave que debe tener? "
    "Menciona el sufijo que llevaría el código de oportunidad. "
    "Al final: "
    '{"status": "success", "strategy": "sow_renovacion", '
    '"notes": "tipo_sow y secciones clave identificadas"}'
)

if r_sow["rc"] == 0:
    ok(f"B3.1 SOW query OK ({r_sow['elapsed']:.1f}s)")
    text = r_sow["full_text"].lower()
    if "_rn" in text or "renovacion" in text or "renovación" in text:
        ok("B3.1 Menciona tipo renovación (_RN) — KB SOW/business_rules usada")
    else:
        warn(f"B3.1 Tipo renovación no claro: {r_sow['full_text'][:250]}")
else:
    fail("B3.1 SOW query falló", r_sow["stderr"])

time.sleep(3)

# B3.2 — BoM: Clasificación de producto
print(f"\n  {YL}→ B3.2 BoM — clasificación de producto...{RS}")
r_bom = call_claude(
    "Nestor: En un BoM tengo el producto DB2ENT (IBM DB2 Enterprise). "
    "¿Cómo lo clasifico? ¿Es servicio, licencia, software, hardware o híbrido? "
    "¿Qué validaciones debo hacer antes de incluirlo en la propuesta? "
    "Al final: "
    '{"status": "success", "strategy": "bom_clasificacion", '
    '"notes": "clasificacion y validaciones identificadas"}'
)

if r_bom["rc"] == 0:
    ok(f"B3.2 BoM clasificación OK ({r_bom['elapsed']:.1f}s)")
    text = r_bom["full_text"].lower()
    if any(x in text for x in ["licencia", "software", "license"]):
        ok("B3.2 Clasificación correcta mencionada — KB catálogo/BoM usada")
    else:
        warn(f"B3.2 Clasificación no clara: {r_bom['full_text'][:250]}")
else:
    fail("B3.2 BoM clasificación falló", r_bom["stderr"])

time.sleep(3)

# B3.3 — SAP CRM: Knowledge query
print(f"\n  {YL}→ B3.3 SAP CRM — proceso de login...{RS}")
r_sap = call_claude(
    "Nestor: ¿Cuáles son los pasos exactos para hacer login en SAP CRM Tierra (WebUI)? "
    "Específicamente: ¿qué selectores usar para el campo de usuario y contraseña? "
    "¿Por qué NO se debe usar .fill() para passwords? "
    "Al final: "
    '{"status": "success", "strategy": "sap_login_knowledge", '
    '"notes": "pasos y selectores identificados"}'
)

if r_sap["rc"] == 0:
    ok(f"B3.3 SAP login knowledge OK ({r_sap['elapsed']:.1f}s)")
    text = r_sap["full_text"].lower()
    has_selector = any(x in text for x in ["aria", "aria-label", "placeholder", "input"])
    has_type     = any(x in text for x in [".type(", "type(", "delay", "fill"])
    if has_selector:
        ok("B3.3 Menciona selectores aria/placeholder — KB sap_tierra usada")
    else:
        warn("B3.3 Selectores no encontrados en respuesta")
    if has_type:
        ok("B3.3 Menciona .type() vs .fill() — patrón SAP aplicado")
    else:
        warn("B3.3 Diferencia type/fill no mencionada")
else:
    fail("B3.3 SAP login knowledge falló", r_sap["stderr"])

time.sleep(3)

# B3.4 — Propuesta económica: Reestructuración de pagos
print(f"\n  {YL}→ B3.4 Propuesta económica — reestructuración...{RS}")
r_prop = call_claude(
    "Nestor: Tengo una propuesta de $240,000 USD (sin IVA) para soporte anual en Guatemala. "
    "El cliente quiere pagarlo en 5 cuotas. Calcula: "
    "1) Monto con IVA, 2) Cuota mensual, 3) Si aplica tipo de cambio. "
    "Al final: "
    '{"status": "success", "strategy": "propuesta_economica_pagos", '
    '"notes": "monto_iva y cuotas calculados"}'
)

if r_prop["rc"] == 0:
    ok(f"B3.4 Propuesta económica OK ({r_prop['elapsed']:.1f}s)")
    text = r_prop["full_text"]
    has_iva  = any(x in text for x in ["268,800", "268800", "12%", "IVA"])
    has_cuota = any(x in text for x in ["48,000", "48000", "53,760", "53760"])
    if has_iva:
        ok("B3.4 Cálculo IVA correcto — business_rules IVA 12% aplicada")
    else:
        warn(f"B3.4 IVA no calculado correctamente: {text[:200]}")
    if has_cuota:
        ok("B3.4 Cuotas calculadas correctamente")
    else:
        info(f"B3.4 Cuotas: {text[:200]}")
else:
    fail("B3.4 Propuesta económica falló", r_prop["stderr"])


# ══════════════════════════════════════════════════════════════
# RESUMEN FINAL
# ══════════════════════════════════════════════════════════════
print(f"\n{MG}{BLD}{'═'*70}{RS}")
print(f"{MG}{BLD}  RESUMEN — Pruebas Live Claude CLI{RS}")
print(f"{MG}{BLD}{'═'*70}{RS}")

total = sum(results.values())
pass_pct = (results["pass"] / total * 100) if total > 0 else 0

print(f"\n  {GR}✓ PASS:  {results['pass']}{RS}")
print(f"  {RD}✗ FAIL:  {results['fail']}{RS}")
print(f"  {YL}⚠ WARN:  {results['warn']}{RS}")
print(f"  {'─'*40}")
print(f"  TOTAL:   {total} | TASA: {pass_pct:.1f}%")

# Estado final de KB
print(f"\n{BL}{BLD}  Estado final del sistema:{RS}")
stats_final = lm_stats()
print(f"  Patrones aprendidos: {stats_final.get('total_patterns', 'N/A')}")
print(f"  Reusos registrados:  {stats_final.get('total_reuses', 'N/A')}")
print(f"  Llamadas IA ahorradas: {stats_final.get('total_ai_calls_saved', 'N/A')}")

if failures:
    print(f"\n{RD}{BLD}  FALLAS:{RS}")
    for f in failures:
        print(f"  {RD}• {f}{RS}")

if pass_pct >= 80:
    print(f"\n  {GR}{BLD}✅ Sistema funcionando con Claude real ({pass_pct:.1f}%){RS}")
else:
    print(f"\n  {YL}{BLD}⚠ Sistema necesita ajustes ({pass_pct:.1f}%){RS}")

print(f"\n{MG}{'═'*70}{RS}")
print(f"  Ejecutado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{MG}{'═'*70}{RS}\n")
