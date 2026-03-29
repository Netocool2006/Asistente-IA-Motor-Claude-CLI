"""
sap_search_opportunity.py — Accion: Buscar oportunidad por ID
==============================================================
Estando en la vista de Oportunidades, busca una oportunidad específica.

Uso CLI:
    python sap_actions/sap_search_opportunity.py --opp_id 241849

Uso desde orquestador:
    from sap_actions.sap_search_opportunity import SapSearchOpportunity
    res = SapSearchOpportunity().run(opp_id="241849")

Parámetros:
    opp_id: str — Número de oportunidad a buscar
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from base import SapAction, result, print_result, TYPE_DELAY, POST_ACTION_WAIT


class SapSearchOpportunity(SapAction):
    action_name = "search_opportunity"
    screen = "opportunity_search"
    playbook_key = "sap.opportunity.search"

    def execute(self, opp_id: str = "", **kwargs) -> dict:
        if not opp_id:
            return result(False, self.action_name, error="Falta opp_id (número de oportunidad)")

        instructions = {
            "steps": [
                {
                    "tool": "find",
                    "params": {
                        "text": "Search",
                        "element_type": "input"
                    },
                    "fallback_selector": "input[id*='search'], input[id*='Search'], input[placeholder*='Search']",
                    "description": "Localizar campo de búsqueda"
                },
                {
                    "tool": "computer",
                    "params": {"action": "click"},
                    "description": "Click en campo de búsqueda"
                },
                {
                    "tool": "computer",
                    "params": {
                        "action": "triple_click"
                    },
                    "description": "Seleccionar todo el texto existente"
                },
                {
                    "tool": "computer",
                    "params": {
                        "action": "type",
                        "text": opp_id
                    },
                    "description": f"Escribir ID de oportunidad: {opp_id}"
                },
                {
                    "tool": "keyboard",
                    "params": {"key": "Enter"},
                    "wait_after": 4000,
                    "description": "Ejecutar búsqueda y esperar resultados"
                },
            ],
            "fallback_steps": [
                {
                    "tool": "javascript_tool",
                    "params": {
                        "code": f"""
                        var frame = window.frames[0];
                        var doc = frame ? (frame.document || frame.contentDocument) : document;
                        var inputs = doc.querySelectorAll('input[type="text"]');
                        var searchInput = Array.from(inputs).find(i =>
                            i.id.toLowerCase().includes('search') ||
                            i.getAttribute('placeholder')?.toLowerCase().includes('search')
                        );
                        if (searchInput) {{
                            searchInput.focus();
                            searchInput.value = '{opp_id}';
                            searchInput.dispatchEvent(new Event('input', {{bubbles: true}}));
                            searchInput.dispatchEvent(new Event('change', {{bubbles: true}}));
                            'filled';
                        }} else {{ 'search input not found'; }}
                        """
                    },
                    "description": "Fallback JS: llenar búsqueda por DOM"
                }
            ],
            "validation": {
                "description": f"Verificar que oportunidad {opp_id} aparece en resultados",
                "success_indicators": [opp_id, "result", "1 Entry"],
                "failure_indicators": ["0 Entries", "No data", "not found"]
            }
        }

        return result(
            success=True,
            action=self.action_name,
            data={
                "instructions": instructions,
                "technique": "click_type_enter",
                "method": "claude_chrome",
                "notes": f"Búsqueda de oportunidad {opp_id}. Esperar ~4s para resultados SAP.",
                "params_used": {"opp_id": opp_id}
            }
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SAP Search Opportunity")
    parser.add_argument("--opp_id", required=True, help="Número de oportunidad")
    args = parser.parse_args()

    action = SapSearchOpportunity()
    print_result(action.run(opp_id=args.opp_id))
