"""
sap_login.py — Accion: Login a SAP CRM WebUI
=============================================
Abre SAP CRM, ingresa usuario y password.

Uso CLI:
    python sap_actions/sap_login.py --user NTOLEDO --password xxx --url https://crm.gbm.net

Uso desde orquestador:
    from sap_actions.sap_login import SapLogin
    res = SapLogin().run(user="NTOLEDO", password="xxx", url="https://crm.gbm.net")

Reglas aprendidas:
    - NUNCA usar .fill() para password (SAP no lo registra)
    - Usar type con delay=50ms
    - IDs son dinámicos, usar selectores por type/aria-label
    - Esperar redirección post-login (~3-5 seg)
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from base import SapAction, result, print_result, PASSWORD_TYPE_DELAY


class SapLogin(SapAction):
    action_name = "login"
    screen = "login"
    playbook_key = "sap.login.password"

    def execute(self, user: str = "", password: str = "", url: str = "", **kwargs) -> dict:
        """
        Login a SAP CRM WebUI.

        IMPORTANTE: Este script NO ejecuta browser automation directamente.
        Retorna las INSTRUCCIONES exactas que Claude in Chrome debe seguir.
        Claude Code llama este script → obtiene instrucciones → las ejecuta via browser tools.
        """
        if not user or not password:
            return result(False, self.action_name, error="Faltan user o password")

        # Consultar patrón conocido
        pattern = kwargs.get("_pattern", {})

        instructions = {
            "steps": [
                {
                    "tool": "navigate",
                    "params": {"url": url or "https://crm.gbm.net"},
                    "wait_after": 3000,
                    "description": "Abrir SAP CRM WebUI"
                },
                {
                    "tool": "form_input",
                    "params": {
                        "selector": "input[name='sap-user'], input[id*='USERNAME'], input[aria-label*='User']",
                        "value": user,
                        "method": "type",
                        "delay": 30
                    },
                    "description": "Ingresar usuario"
                },
                {
                    "tool": "form_input",
                    "params": {
                        "selector": "input[type='password']",
                        "value": password,
                        "method": "type",
                        "delay": PASSWORD_TYPE_DELAY
                    },
                    "fallback_selectors": [
                        "input[name='sap-password']",
                        "input[id*='PASSWORD']",
                        "input[aria-label*='Password']"
                    ],
                    "description": "Ingresar password (NUNCA usar fill)"
                },
                {
                    "tool": "keyboard",
                    "params": {"key": "Enter"},
                    "wait_after": 5000,
                    "description": "Submit login y esperar redirección"
                },
            ],
            "validation": {
                "description": "Verificar login exitoso",
                "check": "La URL debe cambiar o debe aparecer el home de SAP CRM",
                "success_indicators": ["WorkCenterView", "home", "opportunity"],
                "failure_indicators": ["error", "invalid", "incorrect password"]
            }
        }

        return result(
            success=True,
            action=self.action_name,
            data={
                "instructions": instructions,
                "technique": "type_with_delay",
                "method": "claude_chrome_type",
                "selector": "input[type='password']",
                "notes": f"Login para user {user}. Password via type delay={PASSWORD_TYPE_DELAY}ms."
            }
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SAP Login")
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--url", default="https://crm.gbm.net")
    args = parser.parse_args()

    action = SapLogin()
    res = action.run(user=args.user, password=args.password, url=args.url)
    print_result(res)
