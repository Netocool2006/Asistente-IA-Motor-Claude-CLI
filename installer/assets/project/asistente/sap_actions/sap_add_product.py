"""
sap_add_product.py — Accion: Agregar un producto/item a la oportunidad
=======================================================================
Estando en el tab Products, agrega una nueva línea con Product ID.

Uso CLI:
    python sap_actions/sap_add_product.py --product_id LLML245_PS --quantity 1

Uso desde orquestador:
    from sap_actions.sap_add_product import SapAddProduct
    res = SapAddProduct().run(product_id="LLML245_PS", quantity=1)

Reglas de negocio:
    - Contratos llevan sufijo _PS
    - Renovaciones llevan sufijo _RN
    - Proyectos SIN sufijo
    - Tab después de cada campo (dispara validación server-side)
    - Product ID: usar JS simulateType (más rápido)
    - Quantity: REQUIERE foco real (Claude Chrome type, NO JS puro)
"""

import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from base import SapAction, result, print_result, TYPE_DELAY


class SapAddProduct(SapAction):
    action_name = "add_product"
    screen = "opportunity_items"
    playbook_key = "sap.opportunity.items.insert.product_id"

    def execute(self, product_id: str = "", quantity: int = 1, **kwargs) -> dict:
        if not product_id:
            return result(False, self.action_name, error="Falta product_id")

        instructions = {
            "steps": [
                # Paso 1: Click en Add/New para crear fila
                {
                    "tool": "find",
                    "params": {"text": "Add", "element_type": "button"},
                    "fallback_find": {"text": "New", "element_type": "button"},
                    "description": "Buscar botón Add/New para nueva línea"
                },
                {
                    "tool": "computer",
                    "params": {"action": "click"},
                    "wait_after": 2000,
                    "description": "Click Add — esperar nueva fila"
                },

                # Paso 2: Llenar Product ID via JS (más rápido y confiable)
                {
                    "tool": "javascript_tool",
                    "params": {
                        "code": f"""
                        function findSapInput(frame, idPartial) {{
                            var d = frame.document || frame;
                            var inputs = d.querySelectorAll('input[id*="' + idPartial + '"]');
                            return Array.from(inputs).filter(i => i.offsetParent !== null);
                        }}
                        function simulateType(inp, text) {{
                            inp.focus();
                            inp.value = text;
                            inp.dispatchEvent(new Event('input', {{bubbles: true}}));
                            inp.dispatchEvent(new Event('change', {{bubbles: true}}));
                        }}
                        function simulateEnter(inp) {{
                            var opts = {{key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}};
                            inp.dispatchEvent(new KeyboardEvent('keydown', opts));
                            inp.dispatchEvent(new KeyboardEvent('keyup', opts));
                        }}

                        var frame = window.frames[0];
                        var inputs = findSapInput(frame, 'orderedprod');
                        // Buscar el input vacío (la nueva fila)
                        var emptyInput = inputs.find(i => !i.value || i.value.trim() === '');
                        if (emptyInput) {{
                            simulateType(emptyInput, '{product_id}');
                            simulateEnter(emptyInput);
                            'filled: {product_id}';
                        }} else if (inputs.length > 0) {{
                            // Si no hay vacío, usar el último
                            simulateType(inputs[inputs.length-1], '{product_id}');
                            simulateEnter(inputs[inputs.length-1]);
                            'filled last: {product_id}';
                        }} else {{
                            'no orderedprod input found';
                        }}
                        """
                    },
                    "wait_after": 3000,
                    "description": f"Llenar Product ID: {product_id} via JS + Enter para resolución SAP"
                },

                # Paso 3: Llenar Quantity via Claude Chrome (requiere foco real)
                {
                    "tool": "find",
                    "params": {"text": str(quantity), "near": "Quantity"},
                    "fallback_action": "locate quantity field near product just entered",
                    "description": "Localizar campo Quantity de la fila recién creada"
                },
                {
                    "tool": "computer",
                    "params": {"action": "triple_click"},
                    "description": "Seleccionar valor actual de Quantity"
                },
                {
                    "tool": "computer",
                    "params": {
                        "action": "type",
                        "text": str(quantity)
                    },
                    "description": f"Escribir quantity: {quantity}"
                },
                {
                    "tool": "keyboard",
                    "params": {"key": "Tab"},
                    "wait_after": 2000,
                    "description": "Tab para validación server-side de Quantity"
                },
            ],
            "warnings": [
                "BLACKLISTED: No usar js_simulateType_pure para Quantity — SAP no lo reconoce",
                "BLACKLISTED: No usar click_by_coordinates — frágil con resolución/zoom",
                "BLACKLISTED: No usar js_simulateTab — no mueve foco real en SAP",
                "Tab después de Quantity es CRITICO para que SAP procese el valor",
            ],
            "validation": {
                "description": f"Verificar que {product_id} x{quantity} aparece en la tabla",
                "success_indicators": [product_id, str(quantity)],
            }
        }

        return result(
            success=True,
            action=self.action_name,
            data={
                "instructions": instructions,
                "technique": "js_simulateType_then_enter",
                "method": "javascript_tool",
                "selector": "input[id*='orderedprod']",
                "code": f"simulateType(inp, '{product_id}'); simulateEnter(inp);",
                "notes": f"Product: {product_id}, Qty: {quantity}. JS para PID, Claude type para Qty.",
                "params_used": {"product_id": product_id, "quantity": quantity}
            }
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SAP Add Product")
    parser.add_argument("--product_id", required=True, help="Código del producto (con sufijo _PS/_RN si aplica)")
    parser.add_argument("--quantity", type=int, default=1)
    args = parser.parse_args()

    action = SapAddProduct()
    print_result(action.run(product_id=args.product_id, quantity=args.quantity))
