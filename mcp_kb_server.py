"""
mcp_kb_server.py — MCP Server para Claude Desktop
===================================================
Expone el KB del Asistente IA como herramientas MCP.
Claude Desktop las llama automaticamente segun instrucciones del sistema.

Instalar: pip install mcp
Correr:   python "C:/Chance1/Asistente IA/mcp_kb_server.py"

Configurar en Claude Desktop → Settings → MCP:
{
  "mcpServers": {
    "asistente-ia": {
      "command": "python",
      "args": ["C:/Chance1/Asistente IA/mcp_kb_server.py"]
    }
  }
}
"""

import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server

PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

server = Server("asistente-ia-kb")


def run_kb(args: list, input_text: str = None) -> str:
    """Ejecuta knowledge_base.py con los args dados."""
    cmd = [sys.executable, str(PROJECT_DIR / "knowledge_base.py")] + args
    r = subprocess.run(
        cmd, capture_output=True, text=True, timeout=30,
        encoding="utf-8", cwd=str(PROJECT_DIR),
        input=input_text
    )
    return (r.stdout or "") + (r.stderr or "")


def run_lm(args: list) -> str:
    """Ejecuta learning_memory.py con los args dados."""
    cmd = [sys.executable, str(PROJECT_DIR / "learning_memory.py")] + args
    r = subprocess.run(
        cmd, capture_output=True, text=True, timeout=30,
        encoding="utf-8", cwd=str(PROJECT_DIR)
    )
    return (r.stdout or "") + (r.stderr or "")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="buscar_kb",
            description=(
                "Busca en la base de conocimiento del Asistente IA. "
                "Usar SIEMPRE al inicio de tareas sobre: SOW, BoM, SAP CRM, "
                "Monday.com, propuestas economicas, catalogo GBM. "
                "Devuelve recetas, patrones y reglas de negocio aprendidas."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Tema a buscar (ej: 'SOW estructura', 'SAP login', 'IVA Guatemala')"
                    },
                    "domain": {
                        "type": "string",
                        "description": "Dominio especifico (sow, bom, sap_tierra, monday, business_rules, catalog). Opcional.",
                        "default": ""
                    }
                },
                "required": ["query"]
            }
        ),
        types.Tool(
            name="guardar_aprendizaje",
            description=(
                "Guarda automaticamente un aprendizaje nuevo en el KB. "
                "LLAMAR SIN QUE EL USUARIO LO PIDA cuando: "
                "1) Se resolvio un error o problema, "
                "2) Se descubrio como funciona algo (SAP, Monday, cliente), "
                "3) Se aplico una formula o estructura nueva, "
                "4) El usuario confirmo que algo funciono. "
                "Esto es aprendizaje automatico — hacerlo siempre."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "titulo": {
                        "type": "string",
                        "description": "Nombre corto del patron (ej: 'sap_campo_cantidad_requiere_tab')"
                    },
                    "dominio": {
                        "type": "string",
                        "description": "Dominio: sow, bom, sap_tierra, monday, business_rules, catalog, general"
                    },
                    "contenido": {
                        "type": "string",
                        "description": "Que se aprendio: descripcion, pasos, codigo, error y solucion"
                    },
                    "tags": {
                        "type": "string",
                        "description": "Tags separados por coma (ej: 'sap,campo,validacion')"
                    }
                },
                "required": ["titulo", "dominio", "contenido"]
            }
        ),
        types.Tool(
            name="listar_patrones",
            description="Lista los patrones aprendidos en learning_memory con sus tasas de exito.",
            inputSchema={
                "type": "object",
                "properties": {
                    "dominio": {
                        "type": "string",
                        "description": "Filtrar por dominio. Vacio = todos.",
                        "default": ""
                    }
                }
            }
        ),
        types.Tool(
            name="registrar_error_resuelto",
            description=(
                "Registra un error y su solucion en learning_memory. "
                "LLAMAR AUTOMATICAMENTE cuando se corrigio un error — "
                "sin esperar que el usuario lo pida. "
                "Esto evita repetir el mismo error en sesiones futuras."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "error": {
                        "type": "string",
                        "description": "Descripcion del error que ocurrio"
                    },
                    "solucion": {
                        "type": "string",
                        "description": "Como se resolvio"
                    },
                    "dominio": {
                        "type": "string",
                        "description": "Dominio donde ocurrio: sow, bom, sap_tierra, monday, general"
                    }
                },
                "required": ["error", "solucion", "dominio"]
            }
        ),
        types.Tool(
            name="estadisticas_kb",
            description="Muestra estadisticas del KB: dominios, cantidad de patrones, hits.",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:

    if name == "buscar_kb":
        query = arguments["query"]
        domain = arguments.get("domain", "")
        args = ["export", "--query", query]
        if domain:
            args += ["--domain", domain]
        result = run_kb(args)
        if not result.strip():
            result = f"Sin resultados para '{query}' en el KB."
        return [types.TextContent(type="text", text=result)]

    elif name == "guardar_aprendizaje":
        titulo   = arguments["titulo"]
        dominio  = arguments["dominio"]
        contenido = arguments["contenido"]
        tags     = arguments.get("tags", "general,mcp")

        # Crear entry en formato que knowledge_base.py entiende
        entry = {
            "id": titulo,
            "title": titulo,
            "domain": dominio,
            "content": contenido,
            "tags": [t.strip() for t in tags.split(",")],
            "source": "claude_desktop_mcp",
            "timestamp": datetime.now().isoformat()
        }

        # Guardar via add-fact
        fact_text = f"{titulo}: {contenido}"
        result = run_kb(["add-fact", "--domain", dominio, "--content", fact_text])

        # Tambien registrar en learning_memory como patron exitoso
        lm_result = run_lm([
            "register", titulo,
            "--success", "1.0",
            "--tags", tags,
            "--note", contenido[:200]
        ])

        msg = f"[KB] Guardado en dominio '{dominio}': {titulo}"
        if "error" in (result + lm_result).lower():
            msg += f"\n[WARN] {result[:200]}"
        return [types.TextContent(type="text", text=msg)]

    elif name == "listar_patrones":
        dominio = arguments.get("dominio", "")
        args = ["list"]
        if dominio:
            args += ["--domain", dominio]
        result = run_lm(args)
        return [types.TextContent(type="text", text=result or "Sin patrones registrados.")]

    elif name == "registrar_error_resuelto":
        error    = arguments["error"]
        solucion = arguments["solucion"]
        dominio  = arguments["dominio"]

        patron_id = f"error_resuelto_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        contenido = f"ERROR: {error}\nSOLUCION: {solucion}"

        result = run_kb(["add-fact", "--domain", dominio, "--content", contenido])
        lm_result = run_lm([
            "register", patron_id,
            "--success", "1.0",
            "--tags", f"{dominio},error_fix,auto_captured",
            "--note", contenido[:200]
        ])

        return [types.TextContent(
            type="text",
            text=f"[KB] Error+solucion guardados en '{dominio}': {patron_id}"
        )]

    elif name == "estadisticas_kb":
        result = run_kb(["stats"])
        return [types.TextContent(type="text", text=result)]

    return [types.TextContent(type="text", text=f"Herramienta desconocida: {name}")]


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
