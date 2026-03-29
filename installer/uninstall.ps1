#Requires -Version 5.1
<#
.SYNOPSIS
    Desinstalador de Asistente IA GBM
.PARAMETER InstallPath
    Directorio donde esta instalado. Default: C:\Chance1\Asistente IA
.PARAMETER KeepData
    Conserva KB en ~/.adaptive_cli/
.PARAMETER Silent
    Sin confirmacion interactiva.
#>
param(
    [string]$InstallPath = "C:\Chance1\Asistente IA",
    [switch]$KeepData,
    [switch]$Silent
)

function Log-Ok([string]$msg)   { Write-Host "  [OK]  $msg" -ForegroundColor Green }
function Log-Warn([string]$msg) { Write-Host "  [!]   $msg" -ForegroundColor Yellow }
function Log-Err([string]$msg)  { Write-Host "  [ERR] $msg" -ForegroundColor Red }
function Log-Step([string]$msg) { Write-Host "`n  >>  $msg" -ForegroundColor Magenta }

Write-Host "`n============================================" -ForegroundColor DarkMagenta
Write-Host "  Asistente IA GBM -- Desinstalador" -ForegroundColor Magenta
Write-Host "============================================" -ForegroundColor DarkMagenta
Write-Host "  Directorio: $InstallPath"
if (-not $KeepData) {
    Write-Host "  KB datos:   $env:USERPROFILE\.adaptive_cli\ (se eliminara)"
} else {
    Write-Host "  KB datos:   conservados (-KeepData)" -ForegroundColor Yellow
}
Write-Host ""

if (-not $Silent) {
    $confirm = Read-Host "  Continuar? [s/N]"
    if ($confirm -notmatch "^[sS]") { Write-Host "  Cancelado." -ForegroundColor Yellow; exit 0 }
}

$errors = 0

# ── 1. Limpiar hooks de ~/.claude/settings.json ───────────────────────────────
Log-Step "Limpiando hooks de Claude Code..."
$settingsF = Join-Path ([Environment]::GetFolderPath("UserProfile")) ".claude\settings.json"
if (Test-Path $settingsF) {
    try {
        $hooksDir = Join-Path $InstallPath ".claude\hooks"
        $json = Get-Content $settingsF -Raw | ConvertFrom-Json
        $changed = $false
        $events = @("SessionStart","UserPromptSubmit","PostToolUse","Stop","PreToolUse")
        foreach ($evt in $events) {
            if ($json.hooks.$evt) {
                $before = @($json.hooks.$evt)
                $after  = @($before | ForEach-Object {
                    $entry = $_
                    $filteredHooks = @($entry.hooks | Where-Object { $_.command -notlike "*$hooksDir*" })
                    if ($filteredHooks.Count -gt 0) {
                        $entry.hooks = $filteredHooks
                        $entry
                    }
                })
                if ($after.Count -ne $before.Count) { $changed = $true }
                if ($after.Count -eq 0) {
                    $json.hooks.PSObject.Properties.Remove($evt)
                } else {
                    $json.hooks.$evt = $after
                }
            }
        }
        if ($changed) {
            $json | ConvertTo-Json -Depth 10 | Set-Content $settingsF -Encoding UTF8
            Log-Ok "Hooks limpiados de settings.json"
        } else {
            Log-Warn "No se encontraron hooks de este motor"
        }
    } catch {
        Log-Warn "No se pudo limpiar settings.json: $_"
    }
} else {
    Log-Warn "settings.json no encontrado"
}

$realHome = [Environment]::GetFolderPath("UserProfile")

# ── 2. Eliminar Node.js/Claude Code del PATH de usuario ───────────────────────
Log-Step "Limpiando PATH de usuario..."
try {
    $userPath = [Environment]::GetEnvironmentVariable("PATH","User")
    if ($userPath) {
        $nodeDir   = Join-Path $InstallPath "runtime\node"
        $claudeDir = Join-Path $InstallPath "runtime\claude_code"
        $newPath   = ($userPath.Split(";") | Where-Object { $_ -ne $nodeDir -and $_ -ne $claudeDir }) -join ";"
        if ($newPath -ne $userPath) {
            [Environment]::SetEnvironmentVariable("PATH", $newPath, "User")
            Log-Ok "PATH limpiado"
        } else {
            Log-Warn "Nada que limpiar en PATH"
        }
    }
} catch {
    Log-Warn "No se pudo limpiar PATH: $_"
}

# ── 3. Eliminar directorio de instalacion ─────────────────────────────────────
Log-Step "Eliminando directorio: $InstallPath"
if (Test-Path $InstallPath) {
    try {
        Remove-Item $InstallPath -Recurse -Force
        Log-Ok "Directorio eliminado"
    } catch {
        Log-Err "No se pudo eliminar: $_"
        $errors++
    }
} else {
    Log-Warn "No encontrado: $InstallPath"
}

# ── 4. Eliminar KB (opcional) ──────────────────────────────────────────────────
$dataDir = Join-Path $realHome ".adaptive_cli"
if (-not $KeepData) {
    Log-Step "Eliminando KB: $dataDir"
    if (Test-Path $dataDir) {
        try {
            Remove-Item $dataDir -Recurse -Force -ErrorAction Stop
            Log-Ok "KB eliminada"
        } catch {
            # Algunos archivos pueden estar bloqueados (SQLite WAL, etc.)
            # Intentar eliminar lo que se pueda y reportar lo que quede
            Log-Warn "Algunos archivos estan bloqueados: $($_.Exception.Message)"
            # Segundo intento: eliminar archivos no bloqueados
            Get-ChildItem $dataDir -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
                try { Remove-Item $_.FullName -Force -ErrorAction Stop } catch {}
            }
            # Intentar eliminar el directorio de nuevo
            try {
                Remove-Item $dataDir -Recurse -Force -ErrorAction Stop
                Log-Ok "KB eliminada (segundo intento)"
            } catch {
                Log-Warn "KB parcialmente eliminada. Archivos bloqueados en: $dataDir"
                Log-Warn "Cierra todas las instancias de Claude Code y elimina manualmente: $dataDir"
                $errors++
            }
        }
    } else {
        Log-Warn "KB no encontrada"
    }
} else {
    Log-Ok "KB conservada: $dataDir"
}

Write-Host ""
if ($errors -eq 0) {
    Write-Host "  [OK] Asistente IA GBM desinstalado correctamente." -ForegroundColor Green
    exit 0
} else {
    Write-Host "  [!] Desinstalacion con $errors error(es)." -ForegroundColor Yellow
    exit 1
}
