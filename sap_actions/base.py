"""
base.py — Modulo compartido por todas las acciones SAP
=======================================================
Provee:
  - SapAction: clase base con retry, logging, playbook integration
  - result(): formato estandar de respuesta
  - Constantes comunes (timeouts, delays)
"""

import sys
import json
import time
import traceback
from pathlib import Path
from datetime import datetime

# Agregar proyecto al path
PROJECT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_DIR))

from sap_playbook import lookup, learn, fail as playbook_fail


# ── Constantes ────────────────────────────────────────────────
DEFAULT_TIMEOUT = 15000       # ms para esperar elementos
TYPE_DELAY = 30               # ms entre teclas (campos normales)
PASSWORD_TYPE_DELAY = 50      # ms entre teclas (passwords)
POST_ACTION_WAIT = 2.0        # seg despues de accion SAP (server-side)
POST_TAB_WAIT = 1.0           # seg despues de Tab
MAX_RETRIES = 2               # reintentos por accion


# ── Resultado estandar ────────────────────────────────────────

def result(success: bool, action: str, data: dict = None, error: str = None) -> dict:
    """
    Formato estandar que retorna CADA accion SAP.
    Esto permite que el orquestador sepa exactamente qué paso.
    """
    r = {
        "success": success,
        "action": action,
        "timestamp": datetime.now().isoformat(),
    }
    if data:
        r["data"] = data
    if error:
        r["error"] = error
    return r


# ── Clase base ────────────────────────────────────────────────

class SapAction:
    """
    Clase base para acciones SAP atómicas.

    Cada acción hereda de esta clase e implementa:
      - action_name: str (ej: "login", "search_opportunity")
      - execute(**kwargs) -> dict  (la acción real)

    La clase base maneja:
      - Retry automático
      - Logging al playbook
      - Formato de resultado estandar
      - Lookup de patrones previos
    """

    action_name: str = "unknown"
    screen: str = "any"              # pantalla SAP donde opera
    playbook_key: str = ""           # key semántica para lookup

    def execute(self, **kwargs) -> dict:
        """Override este método con la lógica de la acción."""
        raise NotImplementedError

    def run(self, **kwargs) -> dict:
        """
        Ejecuta la acción con retry y logging.
        Este es el método público que llama el orquestador.
        """
        # 1. Consultar playbook por si hay patrón conocido
        pattern = None
        if self.playbook_key:
            pattern = lookup(self.playbook_key)
            if pattern:
                kwargs["_pattern"] = pattern

        # 2. Intentar con retry
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                res = self.execute(**kwargs)

                # 3. Si tuvo éxito, registrar en playbook
                if res.get("success") and self.playbook_key:
                    d = res.get("data", {})
                    learn(
                        key=self.playbook_key,
                        screen=self.screen,
                        action=self.action_name,
                        technique=d.get("technique", self.action_name),
                        tool=d.get("method", "claude_chrome"),
                        selector=d.get("selector", ""),
                        steps=d.get("steps", ""),
                        notes=d.get("notes", ""),
                        code_snippet=d.get("code", ""),
                    )

                return res

            except Exception as e:
                last_error = str(e)
                tb = traceback.format_exc()

                # Registrar fallo en playbook
                if self.playbook_key:
                    playbook_fail(
                        key=self.playbook_key,
                        screen=self.screen,
                        technique=self.action_name,
                        reason=f"Attempt {attempt}: {last_error}",
                    )

                if attempt < MAX_RETRIES:
                    time.sleep(1)  # pausa breve antes de reintentar
                    continue

        # Todos los intentos fallaron
        return result(
            success=False,
            action=self.action_name,
            error=f"Falló después de {MAX_RETRIES} intentos. Último error: {last_error}",
        )

    def get_pattern(self) -> dict:
        """Consulta el playbook por esta acción."""
        if self.playbook_key:
            return lookup(self.playbook_key)
        return None


# ── Utilidades ────────────────────────────────────────────────

def print_result(res: dict):
    """Imprime resultado como JSON (para uso CLI standalone)."""
    print(json.dumps(res, ensure_ascii=False, indent=2))
