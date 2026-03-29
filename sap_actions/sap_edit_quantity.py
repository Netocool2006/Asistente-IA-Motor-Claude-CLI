"""
sap_edit_quantity.py — Accion: Editar cantidades de items existentes
====================================================================
Requiere que Edit List ya este activo (los inputs quantity editables).

Uso CLI:
    python sap_actions/sap_edit_quantity.py --items '{"SWS_AI_SUPP":1,"SWS_AI_ASSI":1}'
    python sap_actions/sap_edit_quantity.py --all 1

Uso desde orquestador:
    from sap_actions.sap_edit_quantity import SapEditQuantity
    res = SapEditQuantity().run(items={"SWS_AI_SUPP": 1}, all_qty=None)
    res = SapEditQuantity().run(all_qty=1)  # todas a 1

Reglas:
    - Tab despues de cada campo es CRITICO (dispara validacion server-side)
    - Delay entre items (800ms) para que SAP procese cada cambio
    - Verificar resultado despues con sap_inspect_items.py
"""

import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from base import SapAction, result, print_result


# ── JS template para editar quantities ──────────────────────
# Sustituir <<<QTY_MAP>>> con JSON: {"1":"5","2":"1","3":"1","4":"1"}
#   key = row index (btadmini_table[N])
#   value = nueva cantidad
# O sustituir <<<ALL_QTY>>> con un valor para setear TODOS los items
JS_EDIT_QUANTITY = """
(function() {{
    var f, d;
    try {{ f = window.frames[0].frames[1]; d = f.document; }}
    catch(e) {{ return JSON.stringify({{error: 'frames: ' + e.message}}); }}

    var allQty = {all_qty};
    var qtyMap = {qty_map};

    var qtyInputs = d.querySelectorAll("input[id*='btadmini_table'][id*='quantity']");
    if (qtyInputs.length === 0) {{
        return JSON.stringify({{error: 'No quantity inputs found. Is Edit List active?'}});
    }}

    var results = [];
    var delay = 0;
    var editableInputs = [];

    for (var i = 0; i < qtyInputs.length; i++) {{
        var inp = qtyInputs[i];
        if (inp.getBoundingClientRect().width <= 0) continue;
        if (inp.disabled || inp.readOnly) continue;
        if (!inp.value && inp.value !== '0') continue;  // skip empty new rows

        var match = inp.id.match(/btadmini_table\\[(\\d+)\\]/);
        var rowIdx = match ? match[1] : String(i + 1);

        var newQty = null;
        if (allQty !== null) {{
            newQty = String(allQty);
        }} else if (qtyMap && qtyMap[rowIdx]) {{
            newQty = String(qtyMap[rowIdx]);
        }}

        if (newQty !== null) {{
            editableInputs.push({{inp: inp, rowIdx: rowIdx, oldQty: inp.value, newQty: newQty}});
        }}
    }}

    // Edit sequentially with delays
    for (var j = 0; j < editableInputs.length; j++) {{
        (function(idx) {{
            setTimeout(function() {{
                var item = editableInputs[idx];
                var inp = item.inp;
                inp.focus();
                inp.value = '';
                inp.value = item.newQty;
                inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                // Tab para validacion SAP
                var tabOpts = {{key: 'Tab', code: 'Tab', keyCode: 9, which: 9, bubbles: true}};
                inp.dispatchEvent(new KeyboardEvent('keydown', tabOpts));
                inp.dispatchEvent(new KeyboardEvent('keyup', tabOpts));
                results.push({{
                    row: item.rowIdx,
                    oldQty: item.oldQty,
                    newQty: item.newQty,
                    inputId: inp.id,
                    status: 'ok'
                }});
                if (idx === editableInputs.length - 1) {{
                    window.__qtyEditResult = JSON.stringify({{
                        done: true,
                        edited: results.length,
                        total: editableInputs.length,
                        results: results
                    }});
                }}
            }}, idx * 800);
        }})(j);
    }}

    if (editableInputs.length === 0) {{
        return JSON.stringify({{error: 'No items matched for editing', qtyInputsFound: qtyInputs.length}});
    }}

    return 'Editing ' + editableInputs.length + ' quantities... poll window.__qtyEditResult';
}})();
"""

JS_EDIT_POLL = """
(function() {
    var r = window.__qtyEditResult;
    if (r) return r;
    return JSON.stringify({status: "running", message: "Edit in progress..."});
})();
"""


class SapEditQuantity(SapAction):
    action_name = "edit_quantity"
    screen = "opportunity_items"
    playbook_key = "sap.opportunity.items.edit.quantity"

    def execute(self, items: dict = None, all_qty: int = None, **kwargs) -> dict:
        """
        items: dict mapping product_id or row_index -> new quantity
               ej: {"SWS_AI_SUPP": 1} o {"1": 5, "2": 10}
        all_qty: si se pasa, setea TODAS las cantidades a este valor
        """
        if all_qty is None and not items:
            return result(False, self.action_name,
                          error="Falta items dict o all_qty")

        # Build qty_map (row_index -> qty) or use all_qty
        all_qty_js = str(all_qty) if all_qty is not None else "null"
        qty_map_js = json.dumps(items) if items else "null"

        js_code = JS_EDIT_QUANTITY.format(
            all_qty=all_qty_js,
            qty_map=qty_map_js
        )

        instructions = {
            "steps": [
                {
                    "tool": "javascript_tool",
                    "params": {"code": js_code},
                    "description": "Editar cantidades en items de oportunidad"
                },
                {
                    "tool": "javascript_tool",
                    "params": {"code": JS_EDIT_POLL},
                    "wait_before": 4000,
                    "repeat_until": "done",
                    "repeat_interval": 2000,
                    "description": "Poll resultado de edicion"
                }
            ],
            "prerequisites": [
                "Edit List debe estar ACTIVO (inputs quantity visibles y editables)",
                "Si no esta activo, primero click en Edit List button (id*='V97_but2')"
            ],
            "warnings": [
                "Tab despues de cada campo es CRITICO para validacion SAP",
                "Delay 800ms entre items para que SAP procese",
                "Verificar con sap_inspect_items.py despues de editar"
            ]
        }

        return result(
            success=True,
            action=self.action_name,
            data={
                "instructions": instructions,
                "technique": "js_sequential_edit_with_tab",
                "method": "javascript_tool",
                "selector": "input[id*='btadmini_table'][id*='quantity']",
                "code": js_code,
                "poll_code": JS_EDIT_POLL,
                "notes": f"all_qty={all_qty}, items={items}",
                "params_used": {"items": items, "all_qty": all_qty}
            }
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SAP Edit Quantity")
    parser.add_argument("--items", type=str, default=None,
                        help='JSON map: {"row_or_pid": qty} ej: {"1":5,"3":1}')
    parser.add_argument("--all", type=int, default=None, dest="all_qty",
                        help="Set ALL quantities to this value")
    args = parser.parse_args()

    items_dict = json.loads(args.items) if args.items else None
    action = SapEditQuantity()
    print_result(action.run(items=items_dict, all_qty=args.all_qty))
