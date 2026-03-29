"""
sap_open_opportunity.py — Accion: Abrir oportunidad desde resultados
=====================================================================
Después de buscar, hace click en la oportunidad para abrirla.

Uso:
    from sap_actions.sap_open_opportunity import SapOpenOpportunity
    res = SapOpenOpportunity().run(opp_id="241849")

Parámetros:
    opp_id: str — ID de oportunidad visible en resultados (para ubicar el link correcto)
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from base import SapAction, result, print_result


class SapOpenOpportunity(SapAction):
    action_name = "open_opportunity"
    screen = "opportunity_search"
    playbook_key = "sap.opportunity.open"

    def execute(self, opp_id: str = "", **kwargs) -> dict:
        if not opp_id:
            return result(False, self.action_name, error="Falta opp_id")

        instructions = {
            "steps": [
                {
                    "tool": "find",
                    "params": {"text": opp_id, "element_type": "link"},
                    "description": f"Buscar link con ID {opp_id} en resultados"
                },
                {
                    "tool": "computer",
                    "params": {"action": "click"},
                    "wait_after": 5000,
                    "description": "Click para abrir oportunidad (esperar carga completa)"
                },
            ],
            "fallback_steps": [
                {
                    "tool": "javascript_tool",
                    "params": {
                        "code": f"""
                        var frame = window.frames[0];
                        var doc = frame ? (frame.document || frame.contentDocument) : document;
                        var links = doc.querySelectorAll('a, span[onclick]');
                        var target = Array.from(links).find(el => el.textContent.includes('{opp_id}'));
                        if (target) {{ target.click(); 'clicked ' + target.textContent.trim(); }}
                        else {{ 'opp {opp_id} not found in results'; }}
                        """
                    },
                    "description": "Fallback JS: buscar y clickear oportunidad en DOM"
                }
            ],
            "validation": {
                "description": "Verificar que se abrió la oportunidad",
                "success_indicators": ["OpportunityDetail", "Overview", "Products", "Activities"],
            }
        }

        return result(
            success=True,
            action=self.action_name,
            data={
                "instructions": instructions,
                "technique": "find_link_click",
                "method": "claude_chrome",
                "params_used": {"opp_id": opp_id}
            }
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SAP Open Opportunity")
    parser.add_argument("--opp_id", required=True)
    args = parser.parse_args()

    action = SapOpenOpportunity()
    print_result(action.run(opp_id=args.opp_id))
