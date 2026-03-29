"""
sap_click_opportunities.py — Accion: Navegar a la vista de Oportunidades
=========================================================================
Desde el home o cualquier vista, navega al módulo de Oportunidades.

Uso:
    from sap_actions.sap_click_opportunities import SapClickOpportunities
    res = SapClickOpportunities().run()
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from base import SapAction, result, print_result


class SapClickOpportunities(SapAction):
    action_name = "click_opportunities"
    screen = "home"
    playbook_key = "sap.navigation.click_opportunities"

    def execute(self, **kwargs) -> dict:
        instructions = {
            "steps": [
                {
                    "tool": "find",
                    "params": {"text": "Opportunities", "element_type": "link"},
                    "description": "Buscar link Opportunities en navegación"
                },
                {
                    "tool": "computer",
                    "params": {"action": "click"},
                    "wait_after": 3000,
                    "description": "Click en Opportunities"
                },
            ],
            "fallback_steps": [
                {
                    "tool": "javascript_tool",
                    "params": {
                        "code": """
                        var links = document.querySelectorAll('a, span, td');
                        var target = Array.from(links).find(el =>
                            el.textContent.trim() === 'Opportunities' ||
                            el.textContent.trim() === 'Oportunidades'
                        );
                        if (target) { target.click(); 'clicked'; } else { 'not found'; }
                        """
                    },
                    "description": "Fallback JS: buscar Opportunities en DOM"
                }
            ],
            "validation": {
                "description": "Verificar vista de oportunidades abierta",
                "success_indicators": ["OpportunitySearch", "Opportunity Overview", "Search:"],
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
    action = SapClickOpportunities()
    print_result(action.run())
