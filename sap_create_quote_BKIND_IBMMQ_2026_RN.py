"""
sap_create_quote_BKIND_IBMMQ_2026_RN.py
========================================
Crea Quote tipo Contrato en la oportunidad BKIND-IBMMQ-2026_RN.

Datos:
    Tipo        : Contrato (renovación anual soporte IBM MQ)
    Nombre      : BKIND-IBMMQ-2026_RN Quote
    Fecha inicio: hoy (2026-03-22)
    Fecha fin   : 2027-03-22 (12 meses)
    Monto       : $112,608 USD

Ejecutar con:
    python sap_create_quote_BKIND_IBMMQ_2026_RN.py

El script imprime las instrucciones JSON completas para Claude Chrome.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sap_actions.sap_create_quote import SapCreateQuote

# ── Parámetros específicos de esta oportunidad ────────────────────────────
OPP_ID   = "BKIND-IBMMQ-2026_RN"
Q_TYPE   = "contrato"
Q_NAME   = "BKIND-IBMMQ-2026_RN Quote"
D_START  = "2026-03-22"   # hoy
D_END    = "2027-03-22"   # 12 meses exactos
AMOUNT   = 112608          # USD — monto propuesta económica aprobada
CURRENCY = "USD"

print("=" * 65)
print(f"  SAP CRM Tierra — Crear Quote Contrato")
print(f"  Oportunidad : {OPP_ID}")
print(f"  Quote Name  : {Q_NAME}")
print(f"  Tipo        : {Q_TYPE.upper()}")
print(f"  Inicio      : {D_START}")
print(f"  Fin         : {D_END}")
print(f"  Monto       : ${AMOUNT:,} {CURRENCY}")
print("=" * 65)

# ── Generar instrucciones ─────────────────────────────────────────────────
action = SapCreateQuote()
res = action.run(
    quote_type=Q_TYPE,
    name=Q_NAME,
    date_start=D_START,
    date_end=D_END,
    amount=AMOUNT,
    currency=CURRENCY,
)

if not res["success"]:
    print(f"\n[ERROR] {res.get('error')}")
    sys.exit(1)

# ── Imprimir flujo completo ───────────────────────────────────────────────
instructions = res["data"]["instructions"]

print("\n" + "─" * 65)
print("  FLUJO PLAYWRIGHT / CLAUDE CHROME")
print("─" * 65 + "\n")

for i, block in enumerate(instructions["steps"], 1):
    desc = block.get("description", f"Paso {i}")
    print(f"{'━'*60}")
    print(f"  {desc}")
    if "note" in block:
        print(f"\n  NOTA: {block['note']}")
    substeps = block.get("substeps", [])
    for j, step in enumerate(substeps, 1):
        tool   = step.get("tool", "")
        s_desc = step.get("description", "")
        wait   = step.get("wait_after", 0)
        print(f"    {j}. [{tool}] {s_desc}", end="")
        if wait:
            print(f"  (wait {wait}ms)")
        else:
            print()
        # Si tiene JS, mostrar resumen del selector
        if tool == "javascript_tool":
            code = step.get("params", {}).get("code", "")
            # Extraer primera línea significativa del JS
            for line in code.splitlines():
                line = line.strip()
                if "querySelectorAll" in line:
                    print(f"       → {line.strip()}")
                    break

print(f"\n{'━'*60}")
print("\n  ADVERTENCIAS:")
for w in instructions.get("warnings", []):
    print(f"  ⚠  {w}")

print(f"\n{'─'*60}")
print("  DIFERENCIA POR TIPO DE QUOTE:")
comp = instructions.get("type_comparison", {})
for tipo, info in comp.items():
    print(f"\n  [{tipo.upper()}]")
    print(f"    Pantallas extra : {', '.join(info['pantallas_extra'])}")
    print(f"    Monto           : {info['monto']}")
    print(f"    Uso             : {info['uso']}")

print(f"\n{'─'*60}")
print("  RESUMEN JSON (para orquestador):")
summary = {
    "status": "success",
    "task_type": "sap_crear_quote_contrato",
    "strategy": "aria_label_js_fill_with_tab_validation",
    "opp_id": OPP_ID,
    "quote_params": res["data"]["params_used"],
    "notes": res["data"]["notes"],
    "business_rules_applied": [
        "sufijo_RN_renovaciones",
        "tipo_contrato_para_renovaciones",
        "Tab_despues_cada_campo_validacion_server_side",
        "monto_en_header_contrato_no_en_items",
    ],
    "type_differences": {
        "contrato_vs_manual": "Contrato tiene campos de vigencia (ValidFrom/ValidTo), Billing Type, monto en header. Manual solo campos base + monto por ítem.",
        "contrato_vs_estandar": "Contrato precio libre. Estándar calcula precio desde price list automáticamente.",
    },
    "warnings": instructions.get("warnings", []),
}
print(json.dumps(summary, ensure_ascii=False, indent=2))
