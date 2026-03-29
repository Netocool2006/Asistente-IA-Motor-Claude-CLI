#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  Asistente IA GBM — Instalador Linux (offline)
#  GUI: zenity (GNOME) / kdialog (KDE) / terminal (fallback)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

INSTALLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ASSETS_DIR="$INSTALLER_DIR/assets"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "  ${GREEN}[OK]${NC}  $*"; }
err()  { echo -e "  ${RED}[ERROR]${NC} $*" >&2; }
warn() { echo -e "  ${YELLOW}[!]${NC}   $*"; }
step() { echo -e "\n  ${CYAN}${BOLD}→${NC} $*"; }
title(){ echo -e "\n${BOLD}════════════════════════════════════════════${NC}"; echo -e "  $*"; echo -e "${BOLD}════════════════════════════════════════════${NC}"; }

# ── Deteccion de GUI ──────────────────────────────────────────────────────────
GUI_MODE="terminal"
command -v zenity  &>/dev/null && GUI_MODE="zenity"
command -v kdialog &>/dev/null && [ "$GUI_MODE" = "terminal" ] && GUI_MODE="kdialog"

# ── Defaults ──────────────────────────────────────────────────────────────────
INSTALL_PATH="$HOME/Asistente_IA"
USER_NAME=""
USER_POS="Solution Advisor"
DO_SEED=true
DO_HOOKS=true

# ── Verificar bundle ──────────────────────────────────────────────────────────
check_bundle() {
    local fail=0
    [ ! -f "$ASSETS_DIR/python/get-pip.py" ]           && err "get-pip.py no encontrado"           && fail=1
    [ ! -f "$ASSETS_DIR/node/node-linux.tar.xz" ]      && err "Node.js Linux no encontrado"         && fail=1
    [ ! -f "$ASSETS_DIR/claude_code/node_modules.zip" ] && err "Claude Code bundle no encontrado"   && fail=1
    [ ! -d "$ASSETS_DIR/project/asistente" ]            && err "Asistente IA no encontrado en assets" && fail=1
    [ $fail -eq 1 ] && { err "Ejecuta build.py en una maquina con internet."; exit 1; }
}

# ── GUI helpers ───────────────────────────────────────────────────────────────
gui_ask_config() {
    if [ "$GUI_MODE" = "zenity" ]; then
        local res
        res=$(zenity --forms --title="Asistente IA GBM — Configuracion" \
            --text="Configure la instalacion:" \
            --add-entry="Directorio de instalacion: [$INSTALL_PATH]" \
            --add-entry="Tu nombre:" \
            --add-entry="Puesto / rol: [$USER_POS]" \
            --separator="|" 2>/dev/null) || { echo "Cancelado."; exit 0; }
        IFS='|' read -r ip un up <<< "$res"
        [ -n "$ip" ] && INSTALL_PATH="$ip"
        [ -n "$un" ] && USER_NAME="$un"
        [ -n "$up" ] && USER_POS="$up"
        zenity --question --title="Componentes" \
            --text="Sembrar base de conocimiento GBM?\n(SOW, BoM, SAP CRM, reglas de negocio)" 2>/dev/null \
            && DO_SEED=true || DO_SEED=false
    elif [ "$GUI_MODE" = "kdialog" ]; then
        INSTALL_PATH=$(kdialog --inputbox "Directorio de instalacion:" "$INSTALL_PATH" 2>/dev/null) || exit 0
        USER_NAME=$(kdialog --inputbox "Tu nombre:" "" 2>/dev/null) || exit 0
        USER_POS=$(kdialog --inputbox "Puesto / rol:" "$USER_POS" 2>/dev/null) || exit 0
        kdialog --yesno "Sembrar base de conocimiento GBM?" 2>/dev/null && DO_SEED=true || DO_SEED=false
    else
        title "Configuracion"
        read -rp "  Directorio de instalacion [$INSTALL_PATH]: " input; [ -n "$input" ] && INSTALL_PATH="$input"
        read -rp "  Tu nombre: " USER_NAME
        read -rp "  Puesto [$USER_POS]: " input; [ -n "$input" ] && USER_POS="$input"
        read -rp "  Sembrar KB GBM? [S/n]: " input; [[ "$input" =~ ^[Nn] ]] && DO_SEED=false
    fi
}

gui_done() {
    if [ "$GUI_MODE" = "zenity" ]; then
        zenity --info --title="Instalacion completada" --text="$1" 2>/dev/null
    elif [ "$GUI_MODE" = "kdialog" ]; then
        kdialog --msgbox "$1" 2>/dev/null
    else
        ok "$1"
    fi
}

# ── Funciones de instalacion ──────────────────────────────────────────────────

find_or_install_python() {
    for cmd in python3.12 python3.11 python3.10 python3; do
        command -v "$cmd" &>/dev/null && echo "$cmd" && return 0
    done
    # Intentar con Python portable del bundle
    local py_tgz="$ASSETS_DIR/python/Python-linux.tgz"
    if [ -f "$py_tgz" ]; then
        local py_dir="$INSTALL_PATH/runtime/python"
        mkdir -p "$py_dir"
        tar -xzf "$py_tgz" -C "$py_dir" --strip-components=1
        echo "$py_dir/bin/python3"
        return 0
    fi
    err "Python 3.10+ requerido. Instala con: sudo apt install python3"
    return 1
}

install_nodejs() {
    local tar_xz="$ASSETS_DIR/node/node-linux.tar.xz"
    [ ! -f "$tar_xz" ] && { err "Node.js no encontrado: $tar_xz"; return 1; }
    local node_dir="$INSTALL_PATH/runtime/node"
    mkdir -p "$node_dir"
    tar -xJf "$tar_xz" -C "$node_dir" --strip-components=1
    ok "Node.js instalado en $node_dir"
    export PATH="$node_dir/bin:$PATH"
}

install_claude_code() {
    local nm_zip="$ASSETS_DIR/claude_code/node_modules.zip"
    [ ! -f "$nm_zip" ] && { err "Claude Code bundle no encontrado"; return 1; }
    local dst="$INSTALL_PATH/runtime/claude_code"
    mkdir -p "$dst"
    step "Extrayendo node_modules de Claude Code (~200MB)..."
    unzip -q "$nm_zip" -d "$dst"

    # Buscar entry point
    local entry
    entry=$(find "$dst/node_modules/@anthropic-ai/claude-code" -name "cli.js" 2>/dev/null | head -1)
    [ -z "$entry" ] && entry=$(find "$dst/node_modules/@anthropic-ai/claude-code" -name "index.js" 2>/dev/null | head -1)

    local node_bin="$INSTALL_PATH/runtime/node/bin/node"
    if [ -n "$entry" ]; then
        cat > "$INSTALL_PATH/runtime/claude" <<EOF
#!/bin/bash
"$node_bin" "$entry" "\$@"
EOF
        chmod +x "$INSTALL_PATH/runtime/claude"
        ok "Wrapper claude creado: $INSTALL_PATH/runtime/claude"
    else
        warn "Entry point de claude no encontrado. Verifica manualmente."
    fi
}

copy_asistente() {
    local src="$ASSETS_DIR/project/asistente"
    step "Copiando Asistente IA a $INSTALL_PATH..."
    cp -r "$src/." "$INSTALL_PATH/"
    ok "Asistente IA copiado"
}

seed_kb() {
    local python="$1"
    local seed_py="$INSTALL_PATH/seed_gbm_knowledge.py"
    [ ! -f "$seed_py" ] && { warn "seed_gbm_knowledge.py no encontrado"; return; }
    step "Sembrando base de conocimiento GBM..."
    cd "$INSTALL_PATH" && "$python" seed_gbm_knowledge.py
    ok "KB sembrada"
}

configure_hooks() {
    local python="$1"
    local hooks_dir="$INSTALL_PATH/.claude/hooks"
    local settings_dir="$HOME/.claude"
    local settings_f="$settings_dir/settings.json"
    mkdir -p "$settings_dir"

    # Leer o crear settings.json
    if [ ! -f "$settings_f" ]; then
        echo '{"hooks":{}}' > "$settings_f"
    fi

    # Actualizar settings con Python
    "$python" - <<PYEOF
import json, sys
from pathlib import Path

settings_f = Path("$settings_f")
hooks_dir  = Path("$hooks_dir")
python     = "$python"

try:
    data = json.loads(settings_f.read_text())
except:
    data = {}

if "hooks" not in data:
    data["hooks"] = {}

hooks_map = {
    "SessionStart":     "on_session_start.py",
    "UserPromptSubmit": "on_user_message.py",
    "PostToolUse":      "post_action_learn.py",
    "Stop":             "auto_learn_hook.py",
}

for event, script in hooks_map.items():
    entry = [{"matcher": "", "hooks": [{"type": "command", "command": f'"{python}" "{hooks_dir / script}"'}]}]
    if event not in data["hooks"]:
        data["hooks"][event] = entry
    else:
        already = any(
            any(str(hooks_dir) in h.get("command","")
                for h in grp.get("hooks",[]))
            for grp in data["hooks"][event]
        )
        if not already:
            data["hooks"][event].extend(entry)

settings_f.write_text(json.dumps(data, indent=2, ensure_ascii=False))
print("Hooks configurados en:", settings_f)
PYEOF
}

add_to_path_profile() {
    local profile_file="$HOME/.bashrc"
    [ -f "$HOME/.zshrc" ] && profile_file="$HOME/.zshrc"

    local node_bin="$INSTALL_PATH/runtime/node/bin"
    local claude_bin="$INSTALL_PATH/runtime"

    if ! grep -q "Asistente_IA" "$profile_file" 2>/dev/null; then
        cat >> "$profile_file" <<EOF

# Asistente IA GBM
export PATH="$node_bin:$claude_bin:\$PATH"
EOF
        ok "PATH actualizado en $profile_file"
        ok "Ejecuta: source $profile_file  para activar el PATH en esta sesion"
    fi
}

# ── Flujo principal ───────────────────────────────────────────────────────────

main() {
    title "Asistente IA GBM — Instalador Linux"
    check_bundle

    # Bienvenida
    if [ "$GUI_MODE" = "zenity" ]; then
        zenity --question --title="Asistente IA GBM" \
            --text="Instalacion offline del Asistente IA GBM.\n\nInclye:\n  • Python\n  • Node.js + Claude Code CLI\n  • Base de conocimiento GBM\n  • Hooks de aprendizaje automatico\n\nContinuar?" \
            --ok-label="Instalar" --cancel-label="Cancelar" 2>/dev/null \
            || { echo "Cancelado."; exit 0; }
    else
        title "Bienvenida"
        echo "  Asistente IA GBM — Instalacion offline"
        echo "  Incluye: Node.js, Claude Code CLI, KB GBM, hooks"
        read -rp "  Continuar? [S/n]: " yn
        [[ "$yn" =~ ^[Nn] ]] && exit 0
    fi

    gui_ask_config

    mkdir -p "$INSTALL_PATH"

    step "Buscando Python..."
    PYTHON=$(find_or_install_python)
    ok "Python: $PYTHON"

    step "Instalando Node.js portable..."
    install_nodejs

    step "Instalando Claude Code CLI..."
    install_claude_code

    step "Copiando Asistente IA..."
    copy_asistente

    if [ "$DO_SEED" = "true" ]; then
        seed_kb "$PYTHON"
    else
        warn "Seed KB: omitido"
    fi

    if [ "$DO_HOOKS" = "true" ]; then
        step "Configurando hooks Claude Code..."
        configure_hooks "$PYTHON"
    fi

    add_to_path_profile

    local summary="Instalacion completada.

Ruta: $INSTALL_PATH
KB:   $HOME/.adaptive_cli/

Siguiente paso (API Key):
  claude config set apiKey TU_API_KEY

Uso:
  cd \"$INSTALL_PATH\"
  source ~/.bashrc
  claude"

    gui_done "$summary"
    title "Instalacion exitosa"
    echo "$summary"
    ok "Listo."
}

main "$@"
