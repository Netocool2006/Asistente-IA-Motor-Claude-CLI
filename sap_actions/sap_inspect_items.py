"""
sap_inspect_items.py — Accion: Leer items/productos de una oportunidad
=======================================================================
Lee la tabla de items en CUALQUIER modo (VIEW, EDIT, mixto).

Uso CLI:
    python sap_actions/sap_inspect_items.py

Uso desde orquestador:
    from sap_actions.sap_inspect_items import SapInspectItems
    res = SapInspectItems().run()

Estrategia: busca campos por ID PATTERN dentro de cada row (no por posicion).
SAP agrega TDs ocultos que desalinean indices; este approach es inmune.
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from base import SapAction, result, print_result


# ── JS que busca por ID pattern — inmune a columnas ocultas ──
JS_INSPECT_ITEMS = """
(function() {
    var f, d;
    try { f = window.frames[0].frames[1]; d = f.document; }
    catch(e) { return JSON.stringify({error: 'frames: ' + e.message}); }
    var items = [];
    var mode = 'unknown';
    var gt = function(el) {
        if (!el) return '';
        return (el.value || el.innerText || el.textContent || '').trim();
    };
    // ESTRATEGIA 1: prodtable rows — buscar campos por ID pattern
    var container = d.querySelector("div[id*='prodtable'][id*='bottom_div']")
                 || d.querySelector("div[id$='V97_prodtable']")
                 || d.querySelector("div[id*='prodtable']");
    if (container) {
        var trs = container.querySelectorAll("tr[id*='prodtable__']");
        for (var i = 1; i < trs.length; i++) {
            var tr = trs[i];
            var pidEl = tr.querySelector("span[id*='orderedprod'], input[id*='orderedprod']");
            var pid = gt(pidEl);
            if (!pid) continue;
            var qtyEl = tr.querySelector("span[id*='quantity'], input[id*='quantity']");
            var descEl = tr.querySelector("span[id*='description'], input[id*='description']");
            var prodEl = tr.querySelector("span[id*='product_name'], span[id*='PRODUCT_NAME']");
            var crcyEl = tr.querySelector("span[id*='currency'], input[id*='currency']");
            var unitEl = tr.querySelector("span[id*='.unit'], input[id*='.unit']");
            var netEl = tr.querySelector("span[id*='net_value'], input[id*='net_value']");
            mode = qtyEl && qtyEl.tagName === 'INPUT' ? 'edit' : 'view';
            items.push({
                row: i, product_id: pid, product: gt(prodEl) || gt(descEl),
                quantity: gt(qtyEl), unit: gt(unitEl),
                net_value: gt(netEl), currency: gt(crcyEl)
            });
        }
    }
    // ESTRATEGIA 2: btadmini fallback
    if (items.length === 0) {
        var qtyInputs = d.querySelectorAll("input[id*='btadmini_table'][id*='quantity']");
        if (qtyInputs.length > 0) {
            mode = 'edit';
            for (var q = 0; q < qtyInputs.length; q++) {
                var inp = qtyInputs[q];
                if (!inp.value && inp.value !== '0') continue;
                var match = inp.id.match(/btadmini_table\\[(\\d+)\\]/);
                var rowIdx = match ? match[1] : '?';
                var tr2 = inp.closest("tr");
                var pEl = tr2 ? (tr2.querySelector("span[id*='orderedprod']")
                            || tr2.querySelector("input[id*='orderedprod']")) : null;
                items.push({row: parseInt(rowIdx) || (q+1), product_id: gt(pEl),
                            quantity: inp.value, qty_input_id: inp.id,
                            editable: !inp.disabled && !inp.readOnly});
            }
        }
    }
    // Edit List button
    var editBtn = null;
    var allA = d.querySelectorAll("a");
    for (var a = 0; a < allA.length; a++) {
        if ((allA[a].innerText||'').trim() === 'Edit List') {
            var id = allA[a].id || '';
            if (id.includes('V97') || id.includes('C27')) { editBtn = id; break; }
        }
    }
    return JSON.stringify({mode: mode, itemCount: items.length, items: items, editListButton: editBtn});
})();
"""


class SapInspectItems(SapAction):
    action_name = "inspect_items"
    screen = "opportunity_items"
    playbook_key = "sap.opportunity.items.inspect"

    def execute(self, **kwargs) -> dict:
        instructions = {
            "steps": [
                {
                    "tool": "javascript_tool",
                    "params": {"code": JS_INSPECT_ITEMS},
                    "description": "Leer items por ID pattern (inmune a columnas ocultas)"
                }
            ],
            "notes": [
                "Busca span/input con id*='orderedprod', id*='quantity', etc.",
                "No depende de posicion de columna — funciona en view, edit y mixto",
                "Retorna editListButton ID si disponible",
            ]
        }

        return result(
            success=True,
            action=self.action_name,
            data={
                "instructions": instructions,
                "technique": "id_pattern_inspect",
                "method": "javascript_tool",
                "selector": "span[id*='orderedprod'], input[id*='quantity']",
                "code": JS_INSPECT_ITEMS,
                "notes": "ID pattern search — immune to hidden TD columns",
            }
        )


if __name__ == "__main__":
    action = SapInspectItems()
    print_result(action.run())
