"""
_paths.py — Resuelve la ruta correcta de datos para Asistente IA
=================================================================
Claude Code CLI setea HOME=AppData/Local/ClaudeCode (para git/bash),
pero Python Path.home() usa USERPROFILE=C:\\Users\\ntoledo.

Los datos (149 patrones, 44 sesiones, 13 dominios) viven en la ruta
que Claude Code creó: $HOME/.adaptive_cli/

Este módulo resuelve eso: busca primero en $HOME env, luego en Path.home().
"""
import os
from pathlib import Path


def get_data_dir() -> Path:
    """Retorna la ruta correcta de ~/.adaptive_cli/ donde están los datos."""
    # Prioridad 1: variable de entorno HOME (Claude Code la setea a AppData)
    env_home = os.environ.get("HOME")
    if env_home:
        candidate = Path(env_home) / ".adaptive_cli"
        if candidate.exists():
            return candidate

    # Prioridad 2: LOCALAPPDATA/ClaudeCode (ruta explícita Windows)
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidate = Path(local_appdata) / "ClaudeCode" / ".adaptive_cli"
        if candidate.exists():
            return candidate

    # Prioridad 3: Path.home() clásico (fallback)
    candidate = Path.home() / ".adaptive_cli"
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


# Ruta resuelta una sola vez al importar
DATA_DIR = get_data_dir()
