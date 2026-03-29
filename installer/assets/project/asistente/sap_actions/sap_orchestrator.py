"""
sap_orchestrator.py — Orquestador de acciones SAP
===================================================
Encadena microservicios SAP en secuencia. Si una acción falla, se detiene
y reporta exactamente dónde falló.

Uso:
    from sap_actions.sap_orchestrator import SapOrchestrator

    # Definir pipeline
    orch = SapOrchestrator()
    orch.add("login", user="NTOLEDO", password="xxx")
    orch.add("click_opportunities")
    orch.add("search_opportunity", opp_id="241849")
    orch.add("open_opportunity", opp_id="241849")
    orch.add("click_products_tab")
    orch.add("add_product", product_id="LLML245_PS", quantity=1)

    # Obtener instrucciones para Claude Chrome
    pipeline = orch.build()

    # O ejecutar paso a paso
    for step in orch.steps():
        instructions = step.get_instructions()
        # Claude Chrome ejecuta aquí...
        step.mark_done(success=True)

Filosofía:
    El orquestador NO ejecuta nada en el browser.
    Solo genera la SECUENCIA de instrucciones.
    Claude Code es quien las ejecuta via browser tools.
"""

import json
from datetime import datetime
from typing import List, Dict, Any

# Registry de acciones disponibles
ACTION_REGISTRY = {}


def _load_registry():
    """Carga todas las acciones disponibles."""
    global ACTION_REGISTRY
    if ACTION_REGISTRY:
        return

    from sap_actions.sap_login import SapLogin
    from sap_actions.sap_click_cycles import SapClickCycles
    from sap_actions.sap_click_opportunities import SapClickOpportunities
    from sap_actions.sap_search_opportunity import SapSearchOpportunity
    from sap_actions.sap_open_opportunity import SapOpenOpportunity
    from sap_actions.sap_click_products_tab import SapClickProductsTab
    from sap_actions.sap_add_product import SapAddProduct

    ACTION_REGISTRY = {
        "login": SapLogin,
        "click_cycles": SapClickCycles,
        "click_opportunities": SapClickOpportunities,
        "search_opportunity": SapSearchOpportunity,
        "open_opportunity": SapOpenOpportunity,
        "click_products_tab": SapClickProductsTab,
        "add_product": SapAddProduct,
    }


class PipelineStep:
    """Un paso individual en el pipeline."""

    def __init__(self, action_name: str, params: dict, index: int):
        self.action_name = action_name
        self.params = params
        self.index = index
        self.result = None
        self.done = False
        self.success = None

    def get_instructions(self) -> dict:
        """Genera las instrucciones ejecutando la acción."""
        _load_registry()
        action_class = ACTION_REGISTRY.get(self.action_name)
        if not action_class:
            return {"success": False, "error": f"Acción desconocida: {self.action_name}"}

        action = action_class()
        self.result = action.run(**self.params)
        return self.result

    def mark_done(self, success: bool, notes: str = ""):
        """Marca el paso como completado."""
        self.done = True
        self.success = success
        if notes and self.result:
            self.result.setdefault("data", {})["execution_notes"] = notes


class SapOrchestrator:
    """Orquestador de pipeline SAP."""

    def __init__(self):
        self._steps: List[Dict[str, Any]] = []

    def add(self, action_name: str, **params) -> "SapOrchestrator":
        """Agrega una acción al pipeline. Retorna self para chaining."""
        self._steps.append({
            "action": action_name,
            "params": params,
        })
        return self

    def build(self) -> dict:
        """
        Genera el pipeline completo con todas las instrucciones.
        Retorna un dict con la secuencia lista para ejecutar.
        """
        _load_registry()

        pipeline = {
            "created": datetime.now().isoformat(),
            "total_steps": len(self._steps),
            "steps": [],
        }

        for i, step_def in enumerate(self._steps):
            action_name = step_def["action"]
            params = step_def["params"]

            action_class = ACTION_REGISTRY.get(action_name)
            if not action_class:
                pipeline["steps"].append({
                    "index": i,
                    "action": action_name,
                    "error": f"Acción no registrada: {action_name}",
                })
                continue

            action = action_class()
            result = action.run(**params)

            pipeline["steps"].append({
                "index": i,
                "action": action_name,
                "params": params,
                "instructions": result.get("data", {}).get("instructions", {}),
                "warnings": result.get("data", {}).get("instructions", {}).get("warnings", []),
            })

        return pipeline

    def steps(self) -> List[PipelineStep]:
        """Retorna los pasos como objetos PipelineStep para ejecución iterativa."""
        return [
            PipelineStep(s["action"], s["params"], i)
            for i, s in enumerate(self._steps)
        ]

    def summary(self) -> str:
        """Resumen legible del pipeline."""
        lines = [f"SAP Pipeline ({len(self._steps)} pasos):"]
        for i, s in enumerate(self._steps):
            params_str = ", ".join(f"{k}={v}" for k, v in s["params"].items())
            lines.append(f"  {i+1}. {s['action']}({params_str})")
        return "\n".join(lines)

    @staticmethod
    def list_actions() -> list:
        """Lista todas las acciones disponibles."""
        _load_registry()
        actions = []
        for name, cls in sorted(ACTION_REGISTRY.items()):
            actions.append({
                "name": name,
                "screen": cls.screen,
                "playbook_key": cls.playbook_key,
                "description": cls.__doc__.strip().split("\n")[0] if cls.__doc__ else "",
            })
        return actions


# ── Pipelines pre-construidos (recetas comunes) ──────────────

def pipeline_abrir_oportunidad(opp_id: str, user: str = "", password: str = "") -> SapOrchestrator:
    """Pipeline completo: login → navegar → buscar → abrir oportunidad."""
    orch = SapOrchestrator()
    if user and password:
        orch.add("login", user=user, password=password)
    orch.add("click_opportunities")
    orch.add("search_opportunity", opp_id=opp_id)
    orch.add("open_opportunity", opp_id=opp_id)
    return orch


def pipeline_agregar_items(opp_id: str, items: list, user: str = "", password: str = "") -> SapOrchestrator:
    """
    Pipeline completo: login → navegar → abrir opp → tab products → agregar items.

    items: [{"product_id": "LLML245_PS", "quantity": 1}, ...]
    """
    orch = pipeline_abrir_oportunidad(opp_id, user, password)
    orch.add("click_products_tab")
    for item in items:
        orch.add("add_product",
                 product_id=item["product_id"],
                 quantity=item.get("quantity", 1))
    return orch


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "list":
        _load_registry()
        print("Acciones SAP disponibles:")
        print("-" * 40)
        for a in SapOrchestrator.list_actions():
            print(f"  {a['name']:25s} [{a['screen']}]")
        print(f"\nTotal: {len(ACTION_REGISTRY)} acciones")

    elif len(sys.argv) > 1 and sys.argv[1] == "demo":
        orch = pipeline_agregar_items(
            opp_id="241849",
            items=[
                {"product_id": "LLML245_PS", "quantity": 1},
                {"product_id": "SAPLIC200_RN", "quantity": 5},
            ]
        )
        print(orch.summary())
        print()
        pipeline = orch.build()
        print(json.dumps(pipeline, indent=2, ensure_ascii=False, default=str))

    else:
        print("Uso:")
        print("  python sap_orchestrator.py list   — ver acciones disponibles")
        print("  python sap_orchestrator.py demo   — ver pipeline de ejemplo")
