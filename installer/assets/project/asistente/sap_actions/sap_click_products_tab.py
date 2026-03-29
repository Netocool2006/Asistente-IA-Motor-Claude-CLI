"""
sap_click_products_tab.py — Accion: Click en tab "Products" dentro de oportunidad
===================================================================================
Estando dentro de una oportunidad abierta, navega al tab de Products/Items.

Uso:
    from sap_actions.sap_click_products_tab import SapClickProductsTab
    res = SapClickProductsTab().run()
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from base import SapAction, result, print_result


class SapClickProductsTab(SapAction):
    action_name = "click_products_tab"
    screen = "opportunity_detail"
    playbook_key = "sap.opportunity.tab.products"

    def execute(self, **kwargs) -> dict:
        instructions = {
            "steps": [
                {
                    "tool": "find",
                    "params": {"text": "Products", "element_type": "link"},
                    "description": "Buscar tab Products en la oportunidad"
                },
                {
                    "tool": "computer",
                    "params": {"action": "click"},
                    "wait_after": 3000,
                    "description": "Click en tab Products"
                },
            ],
            "fallback_steps": [
                {
                    "tool": "javascript_tool",
                    "params": {
                        "code": """
                        var frame = window.frames[0];
                        var doc = frame ? (frame.document || frame.contentDocument) : document;
                        var tabs = doc.querySelectorAll('a, span, div[role="tab"]');
                        var target = Array.from(tabs).find(el =>
                            el.textContent.trim() === 'Products' ||
                            el.textContent.trim() === 'Items'
                        );
                        if (target) { target.click(); 'clicked Products tab'; }
                        else { 'Products tab not found'; }
                        """
                    },
                    "description": "Fallback JS: buscar tab Products"
                }
            ],
            "validation": {
                "description": "Verificar que se ve la tabla de productos",
                "success_indicators": ["Product ID", "Quantity", "Net Value", "orderedprod"],
            }
        }

        return result(
            success=True,
            action=self.action_name,
            data={
                "instructions": instructions,
                "technique": "find_tab_click",
                "method": "claude_chrome",
            }
        )


if __name__ == "__main__":
    action = SapClickProductsTab()
    print_result(action.run())
