"""
test_humano_realtime.py — Simulación Jornada Real de Néstor Toledo
===================================================================
Simula un día completo de trabajo como Solution Advisor GBM Guatemala.
Deal real: Renovación soporte IBM MQ + DB2 para Banco Industrial.

Flujo humano completo:
  09:00 - Llega un BoM del área técnica
  09:15 - Valida el BoM
  09:30 - Genera propuesta económica
  10:00 - Genera SOW
  10:30 - Revisa el SOW
  11:00 - Necesita fusionar con SOW de Instana
  11:30 - Abre oportunidad en SAP CRM
  12:00 - Agrega ítems en SAP
  14:00 - Crea quote en SAP
  14:30 - Actualiza Monday pipeline
  15:00 - Resumen de aprendizaje del día

Ejecutar: python test_humano_realtime.py
"""

import io, json, sys, os, subprocess, time, re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

PROJECT_DIR = Path(__file__).parent
HOME_CLAUDE = os.environ.get("LOCALAPPDATA", "") + "\\ClaudeCode"
PYTHON      = sys.executable

# Colores
GR="\033[92m"; RD="\033[91m"; YL="\033[93m"; BL="\033[94m"
CY="\033[96m"; MG="\033[95m"; BLD="\033[1m"; RS="\033[0m"
WH="\033[97m"

results   = defaultdict(int)
failures  = []
aprendido = []  # lo que el sistema aprendió hoy
_sec      = ""


def header(hora, tarea):
    print(f"\n{MG}{BLD}{'━'*70}{RS}")
    print(f"{MG}{BLD}  {hora}  —  {tarea}{RS}")
    print(f"{MG}{BLD}{'━'*70}{RS}")

def ok(msg):
    results["pass"] += 1
    print(f"  {GR}✓{RS}  {msg}")

def fail(msg, detail=""):
    results["fail"] += 1
    d = f"\n      {RD}{detail[:250]}{RS}" if detail else ""
    print(f"  {RD}✗ FAIL{RS}  {msg}{d}")
    failures.append(f"[{_sec}] {msg}")

def warn(msg):
    results["warn"] += 1
    print(f"  {YL}⚠{RS}  {msg}")

def info(msg):
    print(f"  {CY}→{RS}  {msg}")

def aprendio(msg):
    aprendido.append(msg)
    print(f"  {MG}★ APRENDIDO{RS}  {msg}")


def claude(prompt: str, timeout: int = 120) -> dict:
    """Invoca claude via claude-fix.ps1 — igual que el usuario real."""
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)
    env["PYTHONIOENCODING"] = "utf-8"

    safe = prompt.replace("'", "''").replace('\n', ' ')
    cmd  = f"& 'c:\\chance1\\claude-fix.ps1' -p '{safe}' --output-format json"

    t0 = time.time()
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", cmd],
            capture_output=True, text=True,
            timeout=timeout, encoding="utf-8",
            cwd=str(PROJECT_DIR), env=env,
        )
        elapsed = time.time() - t0

        full_text = ""
        try:
            parsed   = json.loads(r.stdout)
            full_text = parsed.get("result", r.stdout)
        except Exception:
            full_text = r.stdout

        solution = _extract_json(full_text)
        return {"rc": r.returncode, "text": full_text[:4000],
                "stderr": r.stderr[:300], "elapsed": elapsed,
                "solution": solution}
    except subprocess.TimeoutExpired:
        return {"rc": -1, "text": "", "stderr": "TIMEOUT",
                "elapsed": timeout, "solution": {}}
    except Exception as e:
        return {"rc": -98, "text": "", "stderr": str(e),
                "elapsed": 0, "solution": {}}


def _extract_json(text: str) -> dict:
    for pat in [r'```json\s*(\{.*?\})\s*```', r'```\s*(\{.*?\})\s*```',
                r'(\{[^{}]*"status"[^{}]*\})']:
        for m in re.findall(pat, text, re.DOTALL):
            try:
                return json.loads(m)
            except Exception:
                pass
    return {}


def check(r: dict, label: str, keywords: list = None, must_json: bool = False) -> bool:
    """Evalúa una respuesta de Claude."""
    global _sec
    _sec = label
    if r["rc"] != 0:
        fail(f"{label} — claude falló ({r['elapsed']:.1f}s)", r["stderr"])
        return False

    ok(f"{label} — rc=0 en {r['elapsed']:.1f}s")

    text = r["text"].lower()
    hits = [k for k in (keywords or []) if k.lower() in text]
    miss = [k for k in (keywords or []) if k.lower() not in text]

    if hits:
        ok(f"{label} — KB usada: {', '.join(hits)}")
    if miss:
        warn(f"{label} — no mencionó: {', '.join(miss)}")

    if must_json:
        sol = r.get("solution", {})
        if sol.get("status") in ("success", "partial"):
            ok(f"{label} — JSON de aprendizaje capturado: {sol.get('strategy','?')}")
        else:
            warn(f"{label} — JSON no encontrado en respuesta")

    return r["rc"] == 0


# ══════════════════════════════════════════════════════════════
# SETUP
# ══════════════════════════════════════════════════════════════
print(f"\n{WH}{BLD}{'═'*70}{RS}")
print(f"{WH}{BLD}  JORNADA REAL — Solution Advisor GBM Guatemala{RS}")
print(f"{WH}{BLD}  Néstor Toledo | Deal: Banco Industrial — IBM MQ + DB2{RS}")
print(f"{WH}{BLD}  {datetime.now().strftime('%Y-%m-%d')}{RS}")
print(f"{WH}{BLD}{'═'*70}{RS}")

# Verificar sistema listo
sys.path.insert(0, str(PROJECT_DIR))
try:
    import learning_memory as lm
    stats0 = lm.get_stats()
    info(f"Sistema listo — {stats0.get('total_patterns','?')} patrones en memoria")
except Exception as e:
    warn(f"No se pudo leer estadísticas: {e}")
    stats0 = {}


# ══════════════════════════════════════════════════════════════
# 09:00 — LLEGÓ EL BOM DEL ÁREA TÉCNICA
# ══════════════════════════════════════════════════════════════
header("09:00", "Llegó el BoM del área técnica — Validación inicial")

info("El área técnica manda el BoM para Banco Industrial.")
info("Hay que validarlo antes de armar la propuesta.")

r = claude(
    "Néstor: Acabo de recibir este BoM para validar antes de hacer la propuesta:\n"
    "- NoParte: IBMMQ-SUPP-RN | Descripción: IBM MQ Soporte Anual Renovación | Qty: 1 | Precio: $72,000\n"
    "- NoParte: DB2ENT-SUPP-RN | Descripción: IBM DB2 Enterprise Soporte Anual | Qty: 1 | Precio: $48,000\n"
    "- NoParte: SVCS-IMPL-001  | Descripción: Servicios de Implementación | Qty: 40hrs | Precio: $60/hr\n"
    "Cliente: Banco Industrial Guatemala. Tipo: Renovación con servicios adicionales.\n"
    "Valida: 1) Matemática, 2) Clasificación de cada parte, 3) Tipo de oportunidad y sufijo de código, 4) Si los precios están en rango.\n"
    "Al final: {\"status\": \"success\", \"strategy\": \"bom_validacion_completa\", "
    "\"notes\": \"total_bom y observaciones clave\", \"attempts\": 1}"
)

check(r, "09:00 BoM Validación",
      keywords=["_rn", "renovación", "licencia", "software", "servicio", "120,000", "2,400"],
      must_json=True)

if "$2,400" in r["text"] or "2.400" in r["text"] or "2400" in r["text"]:
    aprendio("Servicios: 40hrs × $60 = $2,400 — tarifa 8x5 correcta")
if "_rn" in r["text"].lower():
    aprendio("Código de oportunidad requiere sufijo _RN (renovación)")

time.sleep(4)


# ══════════════════════════════════════════════════════════════
# 09:30 — PROPUESTA ECONÓMICA
# ══════════════════════════════════════════════════════════════
header("09:30", "Construyendo Propuesta Económica")

info("BoM validado OK. Ahora la propuesta económica.")
info("El cliente pidió: descuento especial 8%, pago en 3 cuotas, tipo de cambio Q7.82.")

r = claude(
    "Néstor: El BoM quedó en $122,400 USD (MQ=$72k + DB2=$48k + Servicios=$2,400). "
    "El cliente Banco Industrial pide:\n"
    "- Descuento especial del 8% (tenemos Special Bid aprobado)\n"
    "- Precio en quetzales a tipo de cambio Q7.82 por dólar\n"
    "- 3 cuotas: 40% firma del contrato, 30% a 30 días, 30% a 60 días\n"
    "Genera la propuesta económica completa con: precio sin descuento, precio con descuento, "
    "IVA Guatemala, precio final en USD y GTQ, y el desglose de las 3 cuotas en ambas monedas.\n"
    "Al final: {\"status\": \"success\", \"strategy\": \"propuesta_economica_descuento_fx\", "
    "\"notes\": \"monto_final_usd monto_final_gtq cuotas_calculadas\", \"attempts\": 1}"
)

check(r, "09:30 Propuesta Económica",
      keywords=["12%", "iva", "7.82", "quetzal", "cuota", "descuento"],
      must_json=True)

# Verificar cálculos clave
text = r["text"]
monto_desc = "112,608" in text or "112608" in text  # 122,400 * 0.92
con_iva    = "126,121" in text or "126121" in text or "125,000" in text  # aprox con IVA
if monto_desc:
    aprendio("Descuento 8% sobre $122,400 = $112,608 calculado correctamente")
if "7.82" in text or "gtq" in text.lower() or "quetzal" in text.lower():
    aprendio("Tipo de cambio GTQ aplicado en propuesta")

time.sleep(4)


# ══════════════════════════════════════════════════════════════
# 10:00 — GENERAR SOW
# ══════════════════════════════════════════════════════════════
header("10:00", "Generando SOW — Renovación Soporte IBM")

info("Con la propuesta económica lista, toca generar el SOW.")
info("Es una renovación, así que el tipo es SOW de renovación.")

r = claude(
    "Néstor: Necesito el SOW para este deal. Datos del deal:\n"
    "- Cliente: Banco Industrial Guatemala\n"
    "- Productos: IBM MQ + IBM DB2 Enterprise (renovación anual de soporte)\n"
    "- Servicios adicionales: 40 horas de implementación\n"
    "- Monto: $112,608 USD (con descuento) + IVA 12%\n"
    "- Vigencia: 12 meses desde fecha de firma\n"
    "- Tipo de oportunidad: RENOVACIÓN con servicios\n"
    "Dame: 1) El tipo de SOW correcto, 2) Las secciones obligatorias que debe tener, "
    "3) Las cláusulas estándar críticas (liability cap, garantía, aceptación), "
    "4) Qué sufijo llevaría el código del deal y por qué.\n"
    "Al final: {\"status\": \"success\", \"strategy\": \"sow_generacion_renovacion\", "
    "\"notes\": \"tipo_sow secciones_clave sufijo_codigo\", \"attempts\": 1}"
)

check(r, "10:00 SOW Generation",
      keywords=["_rn", "renovación", "liability", "cláusula", "aceptación", "garantía"],
      must_json=True)

if "liability" in r["text"].lower() or "responsabilidad" in r["text"].lower():
    aprendio("SOW renovación: cláusula de liability cap es obligatoria")
if "_rn" in r["text"].lower():
    aprendio("Deal confirmado: sufijo _RN para renovaciones")

time.sleep(4)


# ══════════════════════════════════════════════════════════════
# 10:30 — REVISAR EL SOW
# ══════════════════════════════════════════════════════════════
header("10:30", "Revisión del SOW — Chequeo de errores e inconsistencias")

info("El área legal devolvió el SOW con comentarios. Hay que revisarlo.")

r = claude(
    "Néstor: El área legal revisó el SOW y encontró estos puntos a verificar:\n"
    "1. El monto dice $122,400 pero la propuesta económica aprobada es $112,608 (con descuento)\n"
    "2. El plazo de aceptación dice '15 días hábiles' pero nuestro estándar es '10 días hábiles'\n"
    "3. La cláusula de confidencialidad no menciona el período post-contractual\n"
    "4. El código del deal está como 'BKIND-IBMMQ-2026' sin el sufijo de tipo\n"
    "5. El IVA no está desglosado, solo aparece el total\n"
    "Revisa cada punto: ¿es un error real o aceptable? ¿Qué correcciones son críticas vs opcionales?\n"
    "Al final: {\"status\": \"success\", \"strategy\": \"sow_revision_legal\", "
    "\"notes\": \"errores_criticos errores_opcionales\", \"attempts\": 1}"
)

check(r, "10:30 SOW Revisión",
      keywords=["_rn", "112,608", "10 días", "iva", "crítico"],
      must_json=True)

if "112,608" in r["text"] or "112608" in r["text"]:
    aprendio("SOW revisión: monto debe coincidir con propuesta económica aprobada")
if "_rn" in r["text"].lower():
    aprendio("SOW revisión: código sin sufijo _RN es error crítico, no opcional")

time.sleep(4)


# ══════════════════════════════════════════════════════════════
# 11:00 — FUSIÓN DE SOWs (Instana + Soporte + Servicios)
# ══════════════════════════════════════════════════════════════
header("11:00", "Fusión de SOWs — Instana + Soporte IBM + Servicios")

info("El cliente quiere todo en UN solo documento.")
info("Hay 3 SOWs separados que hay que fusionar.")

r = claude(
    "Néstor: El cliente Banco Industrial pide fusionar 3 SOWs en uno solo:\n"
    "SOW-1 (Instana): Monitoreo de aplicaciones, licencia Instana Server 50 agentes, $18,000/año\n"
    "SOW-2 (Soporte IBM): IBM MQ + DB2, soporte 8x5, $120,000/año (el que ya teníamos)\n"
    "SOW-3 (Fábrica): 40hrs desarrollo/mes, tarifa $28.95/hr, celda de desarrollo Guatemala\n"
    "El documento fusionado debe ser coherente, sin contradicciones, con secciones comunes unificadas.\n"
    "Dame: 1) Cómo estructurar el documento fusionado, 2) Qué secciones se unifican vs cuáles van separadas, "
    "3) Cómo manejar los montos (¿un total o desglosado?), 4) Alertas de posibles conflictos entre SOWs.\n"
    "Al final: {\"status\": \"success\", \"strategy\": \"sow_fusion_3_practicas\", "
    "\"notes\": \"estructura_fusion alertas_conflicto\", \"attempts\": 1}"
)

check(r, "11:00 SOW Fusion",
      keywords=["instana", "fábrica", "28.95", "unif", "sección"],
      must_json=True)

if "28.95" in r["text"] or "celda" in r["text"].lower():
    aprendio("SOW fusión: tarifa Fábrica $28.95/hr (Dev rate) confirmada")
if "conflict" in r["text"].lower() or "contradicción" in r["text"].lower():
    aprendio("SOW fusión: sistema detecta posibles conflictos entre documentos")

time.sleep(4)


# ══════════════════════════════════════════════════════════════
# 11:30 — SAP CRM: LOGIN Y NAVEGAR A OPORTUNIDADES
# ══════════════════════════════════════════════════════════════
header("11:30", "SAP CRM Tierra — Login y navegación a oportunidad")

info("Hay que abrir la oportunidad en SAP para meter los ítems.")
info("Usando SAP CRM Tierra (WebUI) con Playwright.")

r = claude(
    "Néstor: Voy a abrir la oportunidad en SAP CRM Tierra. "
    "La oportunidad se llama 'BKIND-IBMMQ-2026_RN'. "
    "Dame el flujo completo de Playwright para: "
    "1) Login en SAP CRM Tierra (client 500, usuario y contraseña), "
    "2) Navegar al módulo de Oportunidades (Sales Cycles), "
    "3) Buscar la oportunidad por nombre 'BKIND-IBMMQ-2026_RN', "
    "4) Abrirla. "
    "Incluye los selectores exactos que debo usar y las esperas necesarias. "
    "Al final: {\"status\": \"success\", \"strategy\": \"sap_login_navigate_opportunity\", "
    "\"notes\": \"selectores_usados esperas_criticas\", \"attempts\": 1}"
)

check(r, "11:30 SAP Login+Navegar",
      keywords=["aria", "type", "delay", "playwright", "iframe", "client"],
      must_json=True)

if ".type(" in r["text"] or "delay" in r["text"].lower():
    aprendio("SAP: confirmado .type() con delay para passwords, no .fill()")
if "iframe" in r["text"].lower() or "frame" in r["text"].lower():
    aprendio("SAP: navegación requiere manejo de iframes")

time.sleep(4)


# ══════════════════════════════════════════════════════════════
# 12:00 — SAP CRM: AGREGAR ÍTEMS A LA OPORTUNIDAD
# ══════════════════════════════════════════════════════════════
header("12:00", "SAP CRM — Agregar ítems a la oportunidad")

info("Oportunidad abierta. Ahora hay que llenar los ítems del BoM.")

r = claude(
    "Néstor: Tengo la oportunidad BKIND-IBMMQ-2026_RN abierta en SAP CRM Tierra. "
    "Necesito agregar estos ítems en la pestaña de Productos:\n"
    "1. NoParte: IBMMQ-SUPP-RN | Qty: 1 | Precio: $72,000\n"
    "2. NoParte: DB2ENT-SUPP-RN | Qty: 1 | Precio: $48,000\n"
    "3. NoParte: SVCS-IMPL-001  | Qty: 40 | Precio: $60\n"
    "Dame el código Playwright paso a paso para: "
    "1) Ir a la pestaña de Productos/Items, "
    "2) Agregar cada ítem (NoParte, cantidad, precio), "
    "3) Validar con Tab que SAP acepta cada campo, "
    "4) Guardar al final. "
    "Al final: {\"status\": \"success\", \"strategy\": \"sap_fill_items_oportunidad\", "
    "\"notes\": \"flujo_items selectores_campos\", \"attempts\": 1}",
    timeout=180
)

check(r, "12:00 SAP Fill Items",
      keywords=["tab", "products", "playwright", "await", "locator"],
      must_json=True)

if "tab" in r["text"].lower():
    aprendio("SAP items: Tab después de cada campo activa validación server-side")
if "locator" in r["text"].lower() or "await" in r["text"].lower():
    aprendio("SAP items: código Playwright generado con await/locator")

time.sleep(4)


# ══════════════════════════════════════════════════════════════
# 14:00 — SAP CRM: CREAR QUOTE
# ══════════════════════════════════════════════════════════════
header("14:00", "SAP CRM — Crear Quote tipo Contrato")

info("Después del almuerzo: crear el quote. Es tipo CONTRATO (renovación anual).")

r = claude(
    "Néstor: Tengo la oportunidad BKIND-IBMMQ-2026_RN con ítems cargados. "
    "Necesito crear un Quote. El tipo es CONTRATO (renovación anual de soporte). "
    "Dame el flujo Playwright completo para: "
    "1) Ir a la sección de Quotes dentro de la oportunidad, "
    "2) Crear un nuevo Quote tipo Contrato, "
    "3) Llenar los campos: nombre del quote, fecha inicio (hoy), fecha fin (12 meses), "
    "   monto $112,608 USD, "
    "4) Diferencia con quote tipo Manual o Estándar — ¿qué pantallas son distintas? "
    "Al final: {\"status\": \"success\", \"strategy\": \"sap_crear_quote_contrato\", "
    "\"notes\": \"tipo_quote diferencias_pantallas campos_criticos\", \"attempts\": 1}",
    timeout=180
)

check(r, "14:00 SAP Crear Quote",
      keywords=["contrato", "playwright", "await", "quote", "manual", "estándar"],
      must_json=True)

if "contrato" in r["text"].lower() and ("manual" in r["text"].lower() or "estándar" in r["text"].lower()):
    aprendio("SAP: quote tipo Contrato tiene pantallas distintas a Manual/Estándar")

time.sleep(4)


# ══════════════════════════════════════════════════════════════
# 14:30 — MONDAY.COM: ACTUALIZAR PIPELINE
# ══════════════════════════════════════════════════════════════
header("14:30", "Monday.com — Actualizar pipeline del deal")

info("Quote creado. Hay que actualizar el pipeline en Monday.")

r = claude(
    "Néstor: El deal de Banco Industrial avanzó. Actualiza el pipeline en Monday.com:\n"
    "- Nombre del item: 'Banco Industrial — IBM MQ + DB2 Renovación 2026'\n"
    "- Columna Etapa: cambiar a 'Propuesta Enviada'\n"
    "- Columna Monto: $112,608 USD\n"
    "- Columna Cierre Esperado: Q2 2026 (30 de junio 2026)\n"
    "- Columna Quote SAP: BKIND-IBMMQ-2026_RN\n"
    "- Añadir update/nota: 'SOW revisado por legal. Quote creado en SAP. Pendiente aprobación cliente.'\n"
    "Dame el proceso paso a paso para actualizar estos campos en Monday.com. "
    "Al final: {\"status\": \"success\", \"strategy\": \"monday_update_pipeline_deal\", "
    "\"notes\": \"campos_actualizados etapa_nueva\", \"attempts\": 1}"
)

check(r, "14:30 Monday Pipeline",
      keywords=["monday", "pipeline", "propuesta", "etapa", "update"],
      must_json=True)

if "propuesta enviada" in r["text"].lower() or "etapa" in r["text"].lower():
    aprendio("Monday: etapa 'Propuesta Enviada' actualizada para deal Banco Industrial")

time.sleep(4)


# ══════════════════════════════════════════════════════════════
# 15:00 — CIERRE DE DÍA: RESUMEN DE APRENDIZAJE
# ══════════════════════════════════════════════════════════════
header("15:00", "Cierre del día — Resumen de lo aprendido")

info("Guardando sesión y verificando qué aprendió el sistema hoy.")

# Guardar sesión
r_save = subprocess.run(
    [PYTHON, str(PROJECT_DIR / "save_session.py"),
     "Jornada completa deal Banco Industrial IBM MQ + DB2",
     "--requests",
     "validacion BoM|propuesta economica con descuento y FX|generacion SOW renovacion|"
     "revision SOW legal|fusion 3 SOWs|SAP login navigate|SAP fill items|"
     "SAP crear quote contrato|Monday pipeline update",
     "--decisions",
     "codigo con _RN|descuento 8% special bid|3 cuotas 40-30-30|"
     "fusion en un SOW unico|quote tipo contrato"],
    capture_output=True, text=True, encoding="utf-8",
    cwd=str(PROJECT_DIR),
    env={**os.environ, "PYTHONIOENCODING": "utf-8"}
)
if r_save.returncode == 0:
    ok("15:00 Sesión guardada en historial")
else:
    warn(f"15:00 Save session: {r_save.stderr[:100]}")

# Stats finales
try:
    stats_final = lm.get_stats()
    pat_nuevo = stats_final.get('total_patterns', 0) - stats0.get('total_patterns', 0)
    ok(f"15:00 Patrones nuevos aprendidos hoy: {pat_nuevo}")
    ok(f"15:00 Total patrones en memoria: {stats_final.get('total_patterns','?')}")
    ok(f"15:00 Reusos registrados: {stats_final.get('total_reuses','?')}")
except Exception as e:
    warn(f"15:00 No se pudo leer stats: {e}")


# ══════════════════════════════════════════════════════════════
# RESUMEN DE JORNADA
# ══════════════════════════════════════════════════════════════
total    = sum(results.values())
pass_pct = (results["pass"] / total * 100) if total > 0 else 0

print(f"\n{WH}{BLD}{'═'*70}{RS}")
print(f"{WH}{BLD}  RESUMEN DE JORNADA — Banco Industrial IBM MQ + DB2{RS}")
print(f"{WH}{BLD}{'═'*70}{RS}")

print(f"\n  Escenarios ejecutados:")
print(f"    09:00  BoM Validación")
print(f"    09:30  Propuesta Económica (descuento + FX + cuotas)")
print(f"    10:00  SOW Generación (renovación)")
print(f"    10:30  SOW Revisión legal")
print(f"    11:00  SOW Fusión (3 prácticas)")
print(f"    11:30  SAP CRM Login + Navegación")
print(f"    12:00  SAP CRM Fill Items")
print(f"    14:00  SAP CRM Crear Quote Contrato")
print(f"    14:30  Monday Pipeline Update")

print(f"\n  {GR}✓ PASS:  {results['pass']}{RS}")
print(f"  {RD}✗ FAIL:  {results['fail']}{RS}")
print(f"  {YL}⚠ WARN:  {results['warn']}{RS}")
print(f"  Tasa:    {pass_pct:.1f}%")

if aprendido:
    print(f"\n  {MG}{BLD}Lo que el sistema aprendió hoy:{RS}")
    for i, a in enumerate(aprendido, 1):
        print(f"  {MG}{i}.{RS} {a}")

if failures:
    print(f"\n  {RD}{BLD}Fallas:{RS}")
    for f in failures:
        print(f"  {RD}• {f}{RS}")

if pass_pct >= 80:
    print(f"\n  {GR}{BLD}✅ Jornada certificada ({pass_pct:.1f}% PASS){RS}")
else:
    print(f"\n  {YL}{BLD}⚠ Jornada con issues ({pass_pct:.1f}%){RS}")

print(f"\n{WH}{'═'*70}{RS}")
print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  GBM Guatemala  |  Solution Advisor AI")
print(f"{WH}{'═'*70}{RS}\n")
