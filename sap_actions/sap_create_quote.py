"""
sap_create_quote.py — Accion: Crear un Quote en una oportunidad SAP CRM Tierra
===============================================================================
Estando en la oportunidad abierta, navega al bloque Quotes y crea un nuevo
quote del tipo especificado (contrato | manual | estandar).

Uso CLI:
    python sap_actions/sap_create_quote.py \\
        --type contrato \\
        --name "BKIND-IBMMQ-2026_RN Quote" \\
        --date_start 2026-03-22 \\
        --date_end 2027-03-22 \\
        --amount 112608

Uso desde orquestador:
    from sap_actions.sap_create_quote import SapCreateQuote
    res = SapCreateQuote().run(
        quote_type="contrato",
        name="BKIND-IBMMQ-2026_RN Quote",
        date_start="2026-03-22",
        date_end="2027-03-22",
        amount=112608
    )

Diferencias entre tipos de Quote:
    CONTRATO  — Para renovaciones/soporte. Requiere fechas de vigencia (inicio/fin),
                monto fijo, y selección de tipo de facturación. El dropdown de tipo
                muestra "Contract" / "Contrato". Genera un documento de renovación
                vinculado al contrato marco. Pantallas extra: Billing Type, Contract Type.

    MANUAL    — Cotización libre, sin vínculo a contrato. Precio se ingresa
                manualmente por ítem. Sin campo de contrato marco. Más simple.
                Usado para proyectos nuevos o demos.

    ESTANDAR  — Linked a price list del catálogo. SAP calcula precio automático
                desde los ítems y la lista de precios asignada. Menos campos manuales.
                Usado cuando el cliente tiene un price agreement vigente.

Reglas de negocio:
    - Oportunidad _RN → quote tipo Contrato
    - Oportunidad _PS → quote tipo Contrato (soporte post-venta)
    - Proyecto         → quote tipo Manual o Estándar
    - Tab después de cada campo (dispara validación server-side SAP)
    - Fechas en formato SAP: MM/DD/YYYY (WebUI Tierra) — verificar locale
    - Monto: solo números sin símbolo $ ni comas (SAP los formatea)
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent))
from base import SapAction, result, print_result, TYPE_DELAY


def _format_date_sap(date_str: str) -> str:
    """
    Convierte YYYY-MM-DD a formato SAP WebUI: MM/DD/YYYY
    SAP CRM Tierra (WebUI) usa MM/DD/YYYY en campo de fecha.
    """
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        return d.strftime("%m/%d/%Y")
    except ValueError:
        return date_str  # devolver tal cual si ya viene en otro formato


def _add_12_months(date_str: str) -> str:
    """Calcula fecha fin = inicio + 12 meses (aproximado con 365 dias)."""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        end = d.replace(year=d.year + 1)
        return end.strftime("%Y-%m-%d")
    except ValueError:
        return date_str


# ─────────────────────────────────────────────────────────────────────────────

class SapCreateQuote(SapAction):
    action_name = "create_quote"
    screen = "opportunity_quotes"
    playbook_key = "sap.opportunity.quote.create"

    def execute(
        self,
        quote_type: str = "contrato",
        name: str = "",
        date_start: str = "",
        date_end: str = "",
        amount: float = 0,
        currency: str = "USD",
        **kwargs
    ) -> dict:

        # ── Validaciones ──────────────────────────────────────────
        qt = quote_type.lower().strip()
        if qt not in ("contrato", "manual", "estandar", "standard"):
            return result(False, self.action_name,
                          error=f"Tipo de quote inválido: {quote_type}. Usar: contrato | manual | estandar")

        if not name:
            return result(False, self.action_name, error="Falta el nombre del quote")

        if not date_start:
            date_start = datetime.now().strftime("%Y-%m-%d")

        if not date_end:
            date_end = _add_12_months(date_start)

        # Formato SAP
        sap_date_start = _format_date_sap(date_start)
        sap_date_end   = _format_date_sap(date_end)

        # El monto va sin decimales si es entero
        amount_str = str(int(amount)) if amount == int(amount) else str(amount)

        # ── Selector del tipo en el dropdown ─────────────────────
        # SAP CRM Tierra muestra el dropdown con textos en inglés o español
        # según configuración del usuario. Cubrimos ambos.
        type_labels = {
            "contrato":  ["Contract", "Contrato", "Renewal Contract"],
            "manual":    ["Manual", "Manual Quote"],
            "estandar":  ["Standard", "Estándar", "Standard Quote"],
            "standard":  ["Standard", "Estándar", "Standard Quote"],
        }
        dropdown_options = type_labels.get(qt, ["Contract"])

        # ── Instrucciones Playwright/Claude Chrome ────────────────
        instructions = {
            "steps": [

                # ── BLOQUE 1: Navegar al tab Quotes ──────────────
                {
                    "description": "BLOQUE 1 — Navegar al tab Quotes dentro de la oportunidad",
                    "substeps": [
                        {
                            "tool": "find",
                            "params": {"text": "Quotes", "element_type": "tab"},
                            "fallback_find": {"text": "Cotizaciones", "element_type": "tab"},
                            "description": "Buscar tab Quotes / Cotizaciones en la oportunidad"
                        },
                        {
                            "tool": "computer",
                            "params": {"action": "click"},
                            "wait_after": 2000,
                            "description": "Click tab Quotes — esperar carga del bloque"
                        },
                    ]
                },

                # ── BLOQUE 2: Click New Quote ─────────────────────
                {
                    "description": "BLOQUE 2 — Crear nuevo quote",
                    "substeps": [
                        {
                            "tool": "find",
                            "params": {"text": "New", "element_type": "button"},
                            "fallback_find": {"text": "Create", "element_type": "button"},
                            "description": "Botón New / Create en el bloque Quotes"
                        },
                        {
                            "tool": "computer",
                            "params": {"action": "click"},
                            "wait_after": 2500,
                            "description": "Click New — SAP abre form de nuevo quote (puede ser popup o inline)"
                        },
                    ]
                },

                # ── BLOQUE 3: Seleccionar tipo de Quote ──────────
                {
                    "description": f"BLOQUE 3 — Seleccionar tipo: {quote_type.upper()}",
                    "note": (
                        "DIFERENCIA CLAVE por tipo:\n"
                        "  CONTRATO  → SAP muestra campos extra: Billing Type, Contract Type, fechas de vigencia\n"
                        "  MANUAL    → Solo campos base: nombre, fecha, monto manual por ítem\n"
                        "  ESTANDAR  → Precio desde price list automático, menos campos manuales"
                    ),
                    "substeps": [
                        {
                            "tool": "find",
                            "params": {
                                "aria_label_contains": "Type",
                                "element_type": "select"
                            },
                            "fallback_find": {
                                "aria_label_contains": "Quote Type",
                                "element_type": "select"
                            },
                            "description": "Localizar dropdown de tipo de quote"
                        },
                        {
                            "tool": "computer",
                            "params": {"action": "click"},
                            "description": "Click para abrir dropdown"
                        },
                        {
                            "tool": "find",
                            "params": {
                                "text_options": dropdown_options,
                                "element_type": "option"
                            },
                            "description": f"Seleccionar '{dropdown_options[0]}' del dropdown (o equivalente en español)"
                        },
                        {
                            "tool": "computer",
                            "params": {"action": "click"},
                            "wait_after": 2000,
                            "description": f"Click opción {quote_type} — SAP recarga form con campos adicionales"
                        },
                    ]
                },

                # ── BLOQUE 4: Llenar nombre/descripción ──────────
                {
                    "description": f"BLOQUE 4 — Nombre del quote: {name}",
                    "substeps": [
                        {
                            "tool": "javascript_tool",
                            "params": {
                                "code": f"""
                                (function() {{
                                    var frame = window.frames[0];
                                    var doc = frame ? (frame.document || frame) : document;

                                    // Buscar campo de nombre/descripcion del quote
                                    var candidates = [
                                        ...doc.querySelectorAll('input[id*="description"]'),
                                        ...doc.querySelectorAll('input[id*="name"]'),
                                        ...doc.querySelectorAll('input[aria-label*="Description"]'),
                                        ...doc.querySelectorAll('input[aria-label*="Name"]'),
                                        ...doc.querySelectorAll('input[aria-label*="Quote Name"]'),
                                    ];
                                    var visible = candidates.filter(i => i.offsetParent !== null);
                                    if (visible.length > 0) {{
                                        var inp = visible[0];
                                        inp.focus();
                                        inp.value = '{name}';
                                        inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                                        inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                                        return 'filled name: {name}';
                                    }}
                                    return 'name field not found';
                                }})();
                                """
                            },
                            "wait_after": 1000,
                            "description": f"Llenar nombre del quote via JS: {name}"
                        },
                        {
                            "tool": "keyboard",
                            "params": {"key": "Tab"},
                            "wait_after": 1000,
                            "description": "Tab para confirmar nombre"
                        },
                    ]
                },

                # ── BLOQUE 5: Fecha inicio ────────────────────────
                {
                    "description": f"BLOQUE 5 — Fecha inicio: {sap_date_start}",
                    "substeps": [
                        {
                            "tool": "javascript_tool",
                            "params": {
                                "code": f"""
                                (function() {{
                                    var frame = window.frames[0];
                                    var doc = frame ? (frame.document || frame) : document;

                                    var candidates = [
                                        ...doc.querySelectorAll('input[id*="validfrom"]'),
                                        ...doc.querySelectorAll('input[id*="startdate"]'),
                                        ...doc.querySelectorAll('input[aria-label*="Valid From"]'),
                                        ...doc.querySelectorAll('input[aria-label*="Start Date"]'),
                                        ...doc.querySelectorAll('input[aria-label*="Fecha Inicio"]'),
                                    ];
                                    var visible = candidates.filter(i => i.offsetParent !== null);
                                    if (visible.length > 0) {{
                                        var inp = visible[0];
                                        inp.focus();
                                        inp.value = '{sap_date_start}';
                                        inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                                        inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                                        return 'filled start date: {sap_date_start}';
                                    }}
                                    return 'start date field not found';
                                }})();
                                """
                            },
                            "wait_after": 1000,
                            "description": f"Llenar fecha inicio via JS: {sap_date_start}"
                        },
                        {
                            "tool": "keyboard",
                            "params": {"key": "Tab"},
                            "wait_after": 1500,
                            "description": "Tab para confirmar fecha inicio (SAP valida formato)"
                        },
                    ]
                },

                # ── BLOQUE 6: Fecha fin ───────────────────────────
                {
                    "description": f"BLOQUE 6 — Fecha fin: {sap_date_end}",
                    "substeps": [
                        {
                            "tool": "javascript_tool",
                            "params": {
                                "code": f"""
                                (function() {{
                                    var frame = window.frames[0];
                                    var doc = frame ? (frame.document || frame) : document;

                                    var candidates = [
                                        ...doc.querySelectorAll('input[id*="validto"]'),
                                        ...doc.querySelectorAll('input[id*="enddate"]'),
                                        ...doc.querySelectorAll('input[aria-label*="Valid To"]'),
                                        ...doc.querySelectorAll('input[aria-label*="End Date"]'),
                                        ...doc.querySelectorAll('input[aria-label*="Fecha Fin"]'),
                                    ];
                                    var visible = candidates.filter(i => i.offsetParent !== null);
                                    if (visible.length > 0) {{
                                        var inp = visible[0];
                                        inp.focus();
                                        inp.value = '{sap_date_end}';
                                        inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                                        inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                                        return 'filled end date: {sap_date_end}';
                                    }}
                                    return 'end date field not found';
                                }})();
                                """
                            },
                            "wait_after": 1000,
                            "description": f"Llenar fecha fin via JS: {sap_date_end}"
                        },
                        {
                            "tool": "keyboard",
                            "params": {"key": "Tab"},
                            "wait_after": 1500,
                            "description": "Tab para confirmar fecha fin"
                        },
                    ]
                },

                # ── BLOQUE 7: Monto (solo para tipo Contrato) ────
                # Para Manual/Estándar, el monto se calcula desde los ítems
                *(
                    [{
                        "description": f"BLOQUE 7 — Monto total: {amount_str} {currency}",
                        "note": "Solo aplica en tipo CONTRATO donde se ingresa monto global directamente",
                        "substeps": [
                            {
                                "tool": "javascript_tool",
                                "params": {
                                    "code": f"""
                                    (function() {{
                                        var frame = window.frames[0];
                                        var doc = frame ? (frame.document || frame) : document;

                                        var candidates = [
                                            ...doc.querySelectorAll('input[id*="netval"]'),
                                            ...doc.querySelectorAll('input[id*="amount"]'),
                                            ...doc.querySelectorAll('input[id*="total"]'),
                                            ...doc.querySelectorAll('input[aria-label*="Net Value"]'),
                                            ...doc.querySelectorAll('input[aria-label*="Amount"]'),
                                            ...doc.querySelectorAll('input[aria-label*="Total"]'),
                                        ];
                                        var visible = candidates.filter(i =>
                                            i.offsetParent !== null && !i.readOnly
                                        );
                                        if (visible.length > 0) {{
                                            var inp = visible[0];
                                            inp.focus();
                                            inp.value = '{amount_str}';
                                            inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                                            inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                                            return 'filled amount: {amount_str}';
                                        }}
                                        return 'amount field not found or read-only (normal en Standard/Manual — viene de items)';
                                    }})();
                                    """
                                },
                                "wait_after": 1000,
                                "description": f"Llenar monto: {amount_str} {currency}"
                            },
                            {
                                "tool": "keyboard",
                                "params": {"key": "Tab"},
                                "wait_after": 1500,
                                "description": "Tab para confirmar monto"
                            },
                        ]
                    }]
                    if qt == "contrato" else
                    [{
                        "description": f"BLOQUE 7 — Monto: aplica para tipo Manual/Estándar desde items",
                        "note": f"Tipo {quote_type}: el monto se calcula automáticamente desde los ítems cargados. No se ingresa manualmente aquí."
                    }]
                ),

                # ── BLOQUE 8: Guardar ─────────────────────────────
                {
                    "description": "BLOQUE 8 — Guardar el quote",
                    "substeps": [
                        {
                            "tool": "find",
                            "params": {"text": "Save", "element_type": "button"},
                            "fallback_find": {"aria_label_contains": "Save"},
                            "description": "Botón Save del quote"
                        },
                        {
                            "tool": "computer",
                            "params": {"action": "click"},
                            "wait_after": 3000,
                            "description": "Click Save — esperar confirmación SAP"
                        },
                        {
                            "tool": "find",
                            "params": {
                                "text_options": ["saved", "guardado", "success", name],
                                "element_type": "any"
                            },
                            "description": "Verificar mensaje de éxito o que el quote aparece en la lista"
                        },
                    ]
                },
            ],

            "warnings": [
                "BLACKLISTED: No usar js_simulateType_pure para fechas — usar JS + Tab para activar validador de formato SAP",
                "BLACKLISTED: No rellenar monto en tipo Manual/Estándar — SAP lo calcula desde items",
                f"Formato fecha SAP Tierra (WebUI): MM/DD/YYYY — fecha start={sap_date_start}, end={sap_date_end}",
                "Si SAP muestra campos extra (Billing Type, Contract Type) después de seleccionar 'Contrato', dejar en default o preguntar a Néstor",
                "El form de nuevo quote puede abrirse en popup o inline según configuración SAP — adaptar si es popup",
            ],

            "type_comparison": {
                "contrato": {
                    "pantallas_extra": ["Billing Type (Facturación)", "Contract Type (Marco/Individual)", "Valid From / Valid To", "Renewal Date"],
                    "monto": "se ingresa directamente en el header del quote",
                    "uso": "Renovaciones de soporte, mantenimiento anual",
                },
                "manual": {
                    "pantallas_extra": ["ninguna — form básico"],
                    "monto": "se ingresa por ítem en el tab Items del quote",
                    "uso": "Proyectos nuevos, propuestas libres",
                },
                "estandar": {
                    "pantallas_extra": ["Price List (lista de precios asignada)"],
                    "monto": "calculado automáticamente desde price list + items",
                    "uso": "Clientes con price agreement vigente",
                },
            },

            "validation": {
                "description": f"Quote '{name}' tipo {quote_type} visible en lista de Quotes",
                "success_indicators": [name, quote_type.capitalize(), sap_date_start, amount_str],
            }
        }

        return result(
            success=True,
            action=self.action_name,
            data={
                "instructions": instructions,
                "technique": "js_fill_aria_label_with_tab_validation",
                "method": "javascript_tool",
                "selector": "input[id*='validfrom'], input[id*='netval'], input[id*='description']",
                "code": "simulateType(inp, value); Tab;",
                "notes": (
                    f"Quote tipo={quote_type}, nombre='{name}', "
                    f"start={sap_date_start}, end={sap_date_end}, amount={amount_str} {currency}. "
                    f"Tipo CONTRATO requiere seleccionar dropdown + campos de vigencia. "
                    f"Diferencia clave vs Manual: monto en header; vs Estándar: precio libre vs price list."
                ),
                "params_used": {
                    "quote_type": quote_type,
                    "name": name,
                    "date_start": sap_date_start,
                    "date_end": sap_date_end,
                    "amount": amount_str,
                    "currency": currency,
                }
            }
        )


# ── CLI standalone ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SAP Create Quote")
    parser.add_argument("--type", dest="quote_type", default="contrato",
                        choices=["contrato", "manual", "estandar"],
                        help="Tipo de quote")
    parser.add_argument("--name", required=True, help="Nombre/descripción del quote")
    parser.add_argument("--date_start", default="",
                        help="Fecha inicio YYYY-MM-DD (default: hoy)")
    parser.add_argument("--date_end", default="",
                        help="Fecha fin YYYY-MM-DD (default: inicio + 12 meses)")
    parser.add_argument("--amount", type=float, default=0,
                        help="Monto total (solo para tipo contrato)")
    parser.add_argument("--currency", default="USD")
    args = parser.parse_args()

    action = SapCreateQuote()
    print_result(action.run(
        quote_type=args.quote_type,
        name=args.name,
        date_start=args.date_start,
        date_end=args.date_end,
        amount=args.amount,
        currency=args.currency,
    ))
