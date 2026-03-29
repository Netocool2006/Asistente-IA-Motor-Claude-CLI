"""
sap_click_cycles.py — Accion: Click en tab/menu "Cycles" en SAP CRM
====================================================================
Navega al módulo de Cycles desde el home de SAP CRM.

Uso:
    from sap_actions.sap_click_cycles import SapClickCycles
    res = SapClickCycles().run()
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from base import SapAction, result, print_result


class SapClickCycles(SapAction):
    action_name = "click_cycles"
    screen = "home"
    playbook_key = "sap.navigation.click_cycles"

    def execute(self, **kwargs) -> dict:
        instructions = {
            "steps": [
                {
                    "tool": "find",
                    "params": {"text": "Cycles", "element_type": "link"},
                    "description": "Buscar link/tab Cycles en navegación SAP"
                },
                {
                    "tool": "computer",
                    "params": {"action": "click"},
                    "wait_after": 3000,
                    "description": "Click en Cycles"
                },
            ],
            "fallback_steps": [
                {
                    "tool": "javascript_tool",
                    "params": {
                        "code": """
                        var links = document.querySelectorAll('a, span, td');
                        var target = Array.from(links).find(el => el.textContent.trim() === 'Cycles');
                        if (target) { target.click(); 'clicked'; } else { 'not found'; }
                        """
                    },
                    "description": "Fallback: buscar Cycles por JS en DOM"
                }
            ],
            "validation": {
                "description": "Verificar que se abrió Cycles",
                "success_indicators": ["Cycle", "Sales Cycle", "CycleSearchView"],
            }
        }

        return result(
            success=True,
            action=self.action_name,
            data={
                "instructions": instructions,
                "technique": "find_text_click",
                "method": "claude_chrome",
            }
        )


if __name__ == "__main__":
    action = SapClickCycles()
    print_result(action.run())
