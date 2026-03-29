#Requires -Version 5.1
<#
.SYNOPSIS
    Instalador grafico offline de Asistente IA (GBM -- Claude Code)
.PARAMETER Headless
    Instala sin GUI (para testing/CI).
.PARAMETER InstallPath
    Directorio destino en modo headless.
.PARAMETER SkipNode
    No instalar Node.js / Claude Code (headless).
#>
param(
    [switch]$Headless,
    [string]$InstallPath = "C:\Chance1\Asistente IA",
    [switch]$SkipNode
)

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$INSTALLER_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$ASSETS_DIR    = Join-Path $INSTALLER_DIR "assets"

# ── Colores ───────────────────────────────────────────────────────────────────
$C_BG      = [System.Drawing.Color]::FromArgb(15, 12, 25)
$C_PANEL   = [System.Drawing.Color]::FromArgb(25, 20, 42)
$C_ACCENT  = [System.Drawing.Color]::FromArgb(180, 120, 255)
$C_SUCCESS = [System.Drawing.Color]::FromArgb(72, 200, 140)
$C_ERROR   = [System.Drawing.Color]::FromArgb(255, 90, 95)
$C_TEXT    = [System.Drawing.Color]::FromArgb(225, 220, 240)
$C_MUTED   = [System.Drawing.Color]::FromArgb(130, 120, 155)
$C_LOG_BG  = [System.Drawing.Color]::FromArgb(8, 5, 16)
$C_LOG_FG  = [System.Drawing.Color]::FromArgb(200, 180, 240)

$F_TITLE = New-Object System.Drawing.Font("Segoe UI", 17, [System.Drawing.FontStyle]::Bold)
$F_STEP  = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
$F_BODY  = New-Object System.Drawing.Font("Segoe UI", 9)
$F_MONO  = New-Object System.Drawing.Font("Consolas", 8)
$F_BTN   = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$F_SMALL = New-Object System.Drawing.Font("Segoe UI", 8)

# ── Estado ───────────────────────────────────────────────────────────────────
$script:State = @{
    Step        = 0
    InstallPath = "C:\Chance1\Asistente IA"
    UserName    = ""
    NodeDir     = ""
    PythonExe   = ""
    ClaudeExe   = ""
    Success     = $false
}

# ── Log ───────────────────────────────────────────────────────────────────────
$script:logBox = $null

function Write-Log([string]$msg, [string]$level="info") {
    $ts     = Get-Date -Format "HH:mm:ss"
    $prefix = switch ($level) {
        "ok"    {"[OK]   "}; "err" {"[ERR]  "}
        "warn"  {"[WARN] "}; "step"{"[>>]   "}; default{"       "}
    }
    $line = "$ts $prefix $msg"
    if ($script:logBox) {
        $script:logBox.AppendText("$line`r`n")
        $script:logBox.ScrollToCaret()
        [System.Windows.Forms.Application]::DoEvents()
    }
}

function Invoke-Step([string]$msg, [scriptblock]$fn) {
    Write-Log $msg "step"
    try { & $fn; Write-Log "OK" "ok" }
    catch { Write-Log "FALLO: $($_.Exception.Message)" "err"; throw }
    [System.Windows.Forms.Application]::DoEvents()
}

# ── Funciones de instalacion ──────────────────────────────────────────────────

function Install-PythonPortable {
    $zip   = Join-Path $ASSETS_DIR "python\python-embed-win.zip"
    $pip   = Join-Path $ASSETS_DIR "python\get-pip.py"
    $pyDir = Join-Path $script:State.InstallPath "runtime\python"

    if (-not (Test-Path $zip)) { throw "No encontrado: $zip" }
    if (Test-Path $pyDir) { Remove-Item $pyDir -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $pyDir | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $pyDir)

    # Habilitar site-packages
    $pthF = Get-ChildItem $pyDir -Filter "python3*._pth" | Select-Object -First 1
    if ($pthF) {
        $content = Get-Content $pthF.FullName
        $content -replace "^#\s*import site","import site" | Set-Content $pthF.FullName -Encoding UTF8
    }

    $pyExe = Join-Path $pyDir "python.exe"
    $script:State.PythonExe = $pyExe

    if (Test-Path $pip) {
        Write-Log "Bootstrapping pip..." "step"
        & $pyExe $pip --no-index 2>&1 | Out-Null
    }
}

function Install-NodeJS {
    $zip     = Join-Path $ASSETS_DIR "node\node-win.zip"
    $nodeDir = Join-Path $script:State.InstallPath "runtime\node"

    if (-not (Test-Path $zip)) { throw "No encontrado: $zip" }
    New-Item -ItemType Directory -Force -Path $nodeDir | Out-Null
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $nodeDir)

    # Node se extrae en un subdirectorio con version (node-v20.x.x-win-x64/)
    $subdir = Get-ChildItem $nodeDir -Directory | Select-Object -First 1
    if ($subdir) {
        # Mover contenido al nivel raiz
        Get-ChildItem $subdir.FullName | Move-Item -Destination $nodeDir -Force
        Remove-Item $subdir.FullName -ErrorAction SilentlyContinue
    }

    $script:State.NodeDir = $nodeDir
}

function Install-ClaudeCode {
    $nmTar   = Join-Path $ASSETS_DIR "claude_code\node_modules.tar"
    $nmZip   = Join-Path $ASSETS_DIR "claude_code\node_modules.zip"
    $nodeDir = $script:State.NodeDir
    $dstDir  = Join-Path $script:State.InstallPath "runtime\claude_code"

    if (-not (Test-Path $nodeDir)) { throw "Node.js no instalado aun" }

    New-Item -ItemType Directory -Force -Path $dstDir | Out-Null

    Write-Log "Extrayendo node_modules de Claude Code..." "step"
    if (Test-Path $nmTar) {
        # Extraer .tar con Windows tar.exe
        & "$env:SystemRoot\System32\tar.exe" -xf $nmTar -C $dstDir 2>&1 | Out-Null
    } elseif (Test-Path $nmZip) {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory($nmZip, $dstDir)
    } else {
        throw "No encontrado: ni $nmTar ni $nmZip"
    }

    # Crear wrapper claude.cmd que usa nuestro Node portable
    $nodeExe  = Join-Path $nodeDir "node.exe"
    $claudeJs = Join-Path $dstDir "node_modules\.bin\claude"

    # Buscar el entry point de claude
    $claudeMain = Get-ChildItem "$dstDir\node_modules\@anthropic-ai\claude-code" -Filter "cli.js" -Recurse `
                  | Select-Object -First 1

    if (-not $claudeMain) {
        # Buscar index.js como fallback
        $claudeMain = Get-ChildItem "$dstDir\node_modules\@anthropic-ai\claude-code" -Filter "index.js" `
                      | Select-Object -First 1
    }

    if ($claudeMain) {
        $claudeCmd = @"
@echo off
"$nodeExe" "$($claudeMain.FullName)" %*
"@
        $script:State.ClaudeExe = Join-Path $dstDir "claude.cmd"
        Set-Content $script:State.ClaudeExe $claudeCmd -Encoding UTF8
        Write-Log "claude.cmd creado: $($script:State.ClaudeExe)" "ok"
    } else {
        Write-Log "Entry point de claude no encontrado, verificar manualmente." "warn"
    }
}

function Copy-AsistenteFiles {
    $src = Join-Path $ASSETS_DIR "project\asistente"
    $dst = $script:State.InstallPath
    if (-not (Test-Path $src)) { throw "No encontrado: $src" }
    Get-ChildItem $src -Recurse | ForEach-Object {
        $rel  = $_.FullName.Substring($src.Length + 1)
        $dest = Join-Path $dst $rel
        if ($_.PSIsContainer) {
            New-Item -ItemType Directory -Force -Path $dest | Out-Null
        } else {
            New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
            Copy-Item $_.FullName -Destination $dest -Force
        }
    }
}

function Seed-GBMKnowledge {
    $pyExe  = $script:State.PythonExe
    $seedPy = Join-Path $script:State.InstallPath "seed_gbm_knowledge.py"
    if (Test-Path $seedPy) {
        Write-Log "Ejecutando seed_gbm_knowledge.py..." "step"
        $out = & $pyExe $seedPy 2>&1
        Write-Log ($out -join " ") "ok"
    }
}

function ConvertTo-Hashtable($obj) {
    if ($obj -is [System.Management.Automation.PSCustomObject]) {
        $ht = @{}
        $obj.PSObject.Properties | ForEach-Object { $ht[$_.Name] = ConvertTo-Hashtable $_.Value }
        return $ht
    } elseif ($obj -is [Array]) {
        return @($obj | ForEach-Object { ConvertTo-Hashtable $_ })
    } else { return $obj }
}

function Configure-ClaudeHooks {
    $hooksDir  = Join-Path $script:State.InstallPath ".claude\hooks"
    $claudeDir = Join-Path ([Environment]::GetFolderPath("UserProfile")) ".claude"
    $settingsF = Join-Path $claudeDir "settings.json"
    New-Item -ItemType Directory -Force -Path $claudeDir | Out-Null

    $settings = @{}
    if (Test-Path $settingsF) {
        try { $settings = ConvertTo-Hashtable (Get-Content $settingsF -Raw | ConvertFrom-Json) }
        catch { $settings = @{} }
    }

    $pyExe = $script:State.PythonExe
    $hooksMap = @{
        SessionStart     = "on_session_start.py"
        UserPromptSubmit = "on_user_message.py"
        PostToolUse      = "post_action_learn.py"
        Stop             = "auto_learn_hook.py"
    }

    if (-not $settings.ContainsKey("hooks")) { $settings.hooks = @{} }
    foreach ($event in $hooksMap.Keys) {
        $hookFile = Join-Path $hooksDir $hooksMap[$event]
        $hookEntry = @(@{ matcher=""; hooks=@(@{ type="command"; command="`"$pyExe`" `"$hookFile`"" }) })
        if (-not $settings.hooks.ContainsKey($event)) {
            $settings.hooks[$event] = $hookEntry
        } else {
            $alreadyIn = $settings.hooks[$event] | Where-Object {
                ($_.hooks | Where-Object { $_.command -like "*$hooksDir*" }).Count -gt 0
            }
            if (-not $alreadyIn) { $settings.hooks[$event] = @($settings.hooks[$event]) + @($hookEntry) }
        }
    }

    # CLAUDE.md path para Claude Code
    if (-not $settings.ContainsKey("env")) { $settings.env = @{} }

    $settings | ConvertTo-Json -Depth 10 | Set-Content $settingsF -Encoding UTF8
    Write-Log "Hooks configurados en: $settingsF" "ok"
}

function Add-ToPATH {
    # Agregar Node y claude.cmd al PATH de usuario para esta sesion
    $nodeDir   = $script:State.NodeDir
    $claudeDir = Split-Path $script:State.ClaudeExe

    $userPath = [Environment]::GetEnvironmentVariable("PATH","User")
    $newPaths = @($nodeDir, $claudeDir) | Where-Object {
        $_ -and ($userPath -notlike "*$_*")
    }
    if ($newPaths) {
        $updated = ($newPaths + $userPath) -join ";"
        [Environment]::SetEnvironmentVariable("PATH", $updated, "User")
        Write-Log "PATH actualizado con Node.js y claude.cmd" "ok"
    }
}

# ── Modo headless (DESPUES de funciones definidas) ───────────────────────────
if ($Headless) {
    $script:State.InstallPath = $InstallPath

    function HL-Step([string]$msg, [scriptblock]$fn) {
        Write-Host "$(Get-Date -Format 'HH:mm:ss') [>>]  $msg" -ForegroundColor Magenta
        try { & $fn; Write-Host "$(Get-Date -Format 'HH:mm:ss') [OK]  OK" -ForegroundColor Green }
        catch { Write-Host "$(Get-Date -Format 'HH:mm:ss') [ERR] FALLO: $($_.Exception.Message)" -ForegroundColor Red; throw }
    }

    Write-Host "`n==== Asistente IA GBM -- Headless Install ====" -ForegroundColor Magenta
    Write-Host "  Destino: $InstallPath`n" -ForegroundColor Gray

    try {
        HL-Step "Creando directorio"  { New-Item -ItemType Directory -Force -Path $script:State.InstallPath | Out-Null }
        HL-Step "Python portable"     { Install-PythonPortable }
        if (-not $SkipNode) {
            HL-Step "Node.js"         { Install-NodeJS }
            HL-Step "Claude Code CLI" { Install-ClaudeCode }
        } else {
            Write-Host "  [!]  Node.js/Claude: omitido (-SkipNode)" -ForegroundColor Yellow
        }
        HL-Step "Copiar Asistente IA" { Copy-AsistenteFiles }
        HL-Step "Seed KB GBM"         { Seed-GBMKnowledge }
        HL-Step "Configurar hooks"    { Configure-ClaudeHooks }
        if (-not $SkipNode) { HL-Step "PATH" { Add-ToPATH } }
        Write-Host "`n[OK] Instalacion completada: $InstallPath" -ForegroundColor Green
        exit 0
    } catch {
        Write-Host "`n[ERROR] $_" -ForegroundColor Red
        exit 1
    }
}

# ── Ventana ───────────────────────────────────────────────────────────────────
$form = New-Object System.Windows.Forms.Form
$form.Text = "Asistente IA GBM -- Instalador"; $form.Size = New-Object System.Drawing.Size(680,560)
$form.StartPosition = "CenterScreen"; $form.FormBorderStyle = "FixedSingle"
$form.MaximizeBox = $false; $form.BackColor = $C_BG

# Header
$pHdr = New-Object System.Windows.Forms.Panel
$pHdr.Dock="Top"; $pHdr.Height=72; $pHdr.BackColor=$C_PANEL
$form.Controls.Add($pHdr)

$lT = New-Object System.Windows.Forms.Label
$lT.Text="Asistente IA GBM"; $lT.Font=$F_TITLE; $lT.ForeColor=$C_ACCENT
$lT.Location=New-Object System.Drawing.Point(20,10); $lT.AutoSize=$true
$pHdr.Controls.Add($lT)

$lS = New-Object System.Windows.Forms.Label
$lS.Text="Instalador offline -- Claude Code CLI + Base de Conocimiento GBM"
$lS.Font=$F_SMALL; $lS.ForeColor=$C_MUTED
$lS.Location=New-Object System.Drawing.Point(22,46); $lS.AutoSize=$true
$pHdr.Controls.Add($lS)

$stepN = @("Bienvenida","Configuracion","Instalando","Listo")
for ($i=0;$i-lt 4;$i++){
    $sl=New-Object System.Windows.Forms.Label
    $sl.Name="si_$i"; $sl.Text="$($i+1). $($stepN[$i])"
    $sl.Font=$F_SMALL; $sl.ForeColor=$C_MUTED
    $sl.Location=New-Object System.Drawing.Point((445+$i*0),(10+$i*15)); $sl.AutoSize=$true
    $pHdr.Controls.Add($sl)
}

# Content
$pCon = New-Object System.Windows.Forms.Panel
$pCon.Location=New-Object System.Drawing.Point(0,72)
$pCon.Size=New-Object System.Drawing.Size(680,420); $pCon.BackColor=$C_BG
$form.Controls.Add($pCon)

# Footer
$pFtr = New-Object System.Windows.Forms.Panel
$pFtr.Dock="Bottom"; $pFtr.Height=58; $pFtr.BackColor=$C_PANEL
$form.Controls.Add($pFtr)

$btnB = New-Object System.Windows.Forms.Button
$btnB.Text="< Atras"; $btnB.Font=$F_BTN; $btnB.Size=New-Object System.Drawing.Size(100,34)
$btnB.Location=New-Object System.Drawing.Point(430,12); $btnB.BackColor=$C_MUTED
$btnB.ForeColor=$C_BG; $btnB.FlatStyle="Flat"; $btnB.FlatAppearance.BorderSize=0
$btnB.Visible=$false; $pFtr.Controls.Add($btnB)

$btnN = New-Object System.Windows.Forms.Button
$btnN.Text="Siguiente >"; $btnN.Font=$F_BTN; $btnN.Size=New-Object System.Drawing.Size(130,34)
$btnN.Location=New-Object System.Drawing.Point(540,12); $btnN.BackColor=$C_ACCENT
$btnN.ForeColor=$C_BG; $btnN.FlatStyle="Flat"; $btnN.FlatAppearance.BorderSize=0
$pFtr.Controls.Add($btnN)

# ── Panel 0: Bienvenida ───────────────────────────────────────────────────────
$p0=New-Object System.Windows.Forms.Panel; $p0.Dock="Fill"; $p0.BackColor=$C_BG
$pCon.Controls.Add($p0)

$rb_w=New-Object System.Windows.Forms.RichTextBox
$rb_w.Text=@"
Bienvenido al instalador del Asistente IA GBM

Este instalador configurara el entorno completo para usar Claude Code CLI
con la base de conocimiento especializada de GBM Guatemala.

Que se instalara:

  Python 3.12 portable   Entorno Python independiente del sistema

  Node.js portable       Runtime para Claude Code CLI

  Claude Code CLI        @anthropic-ai/claude-code (pre-bundleado offline)
                         Incluye todas las dependencias npm

  Asistente IA GBM       Base de conocimiento: SOW, BoM, SAP, Monday
                         Hooks de aprendizaje automatico por sesion
                         Patrones GBM pre-sembrados (reglas de negocio,
                         tarifas, clasificaciones, flujos SAP CRM)

Notas importantes:
  - Claude Code CLI requiere API Key de Anthropic para funcionar.
  - La instalacion NO requiere internet.
  - La API Key se configura despues (claude config set apiKey <key>).

Haga clic en "Siguiente" para configurar la instalacion.
"@
$rb_w.Font=$F_BODY; $rb_w.BackColor=$C_BG; $rb_w.ForeColor=$C_TEXT
$rb_w.ReadOnly=$true; $rb_w.BorderStyle="None"
$rb_w.Location=New-Object System.Drawing.Point(30,20); $rb_w.Size=New-Object System.Drawing.Size(620,380)
$p0.Controls.Add($rb_w)

# ── Panel 1: Configuracion ────────────────────────────────────────────────────
$p1=New-Object System.Windows.Forms.Panel; $p1.Dock="Fill"; $p1.BackColor=$C_BG; $p1.Visible=$false
$pCon.Controls.Add($p1)

$l1h=New-Object System.Windows.Forms.Label; $l1h.Text="Configuracion"; $l1h.Font=$F_STEP
$l1h.ForeColor=$C_TEXT; $l1h.Location=New-Object System.Drawing.Point(30,15); $l1h.AutoSize=$true
$p1.Controls.Add($l1h)

function New-Field([System.Windows.Forms.Panel]$par,[int]$y,[string]$lbl,[string]$val,[bool]$pwd=$false){
    $l=New-Object System.Windows.Forms.Label; $l.Text=$lbl; $l.Font=$F_SMALL; $l.ForeColor=$C_MUTED
    $l.Location=New-Object System.Drawing.Point(30,$y); $l.AutoSize=$true; $par.Controls.Add($l)
    $t=New-Object System.Windows.Forms.TextBox; $t.Text=$val; $t.Font=$F_BODY
    $t.BackColor=$C_PANEL; $t.ForeColor=$C_TEXT; $t.BorderStyle="FixedSingle"
    $t.Location=New-Object System.Drawing.Point(30,($y+18)); $t.Size=New-Object System.Drawing.Size(610,24)
    if($pwd){$t.PasswordChar='*'}; $par.Controls.Add($t); return $t
}

$tf_inst = New-Field $p1  55 "Directorio de instalacion:"                              $script:State.InstallPath
$tf_name = New-Field $p1 115 "Tu nombre (para personalizar CLAUDE.md):"                "Nestor Toledo"
$tf_pos  = New-Field $p1 165 "Puesto / rol (para contexto en respuestas):"             "Solution Advisor GBM Guatemala"

# Info nota API
$lApiNote=New-Object System.Windows.Forms.Label
$lApiNote.Text="Nota: La API Key de Anthropic se configura DESPUES de instalar con: claude config set apiKey <TU_KEY>"
$lApiNote.Font=$F_SMALL; $lApiNote.ForeColor=$C_MUTED
$lApiNote.Location=New-Object System.Drawing.Point(30,260); $lApiNote.Size=New-Object System.Drawing.Size(610,18)
$p1.Controls.Add($lApiNote)

$ck_seed=New-Object System.Windows.Forms.CheckBox
$ck_seed.Text="Sembrar base de conocimiento GBM (recomendado -- incluye SOW, SAP, BoM, reglas)"
$ck_seed.Font=$F_BODY; $ck_seed.ForeColor=$C_TEXT; $ck_seed.Checked=$true
$ck_seed.Location=New-Object System.Drawing.Point(30,290); $ck_seed.AutoSize=$true
$p1.Controls.Add($ck_seed)

$ck_hooks=New-Object System.Windows.Forms.CheckBox
$ck_hooks.Text="Configurar hooks en ~/.claude/settings.json (aprendizaje automatico por sesion)"
$ck_hooks.Font=$F_BODY; $ck_hooks.ForeColor=$C_TEXT; $ck_hooks.Checked=$true
$ck_hooks.Location=New-Object System.Drawing.Point(30,320); $ck_hooks.AutoSize=$true
$p1.Controls.Add($ck_hooks)

# ── Panel 2: Instalando ───────────────────────────────────────────────────────
$p2=New-Object System.Windows.Forms.Panel; $p2.Dock="Fill"; $p2.BackColor=$C_BG; $p2.Visible=$false
$pCon.Controls.Add($p2)

$l2h=New-Object System.Windows.Forms.Label; $l2h.Name="l2h"; $l2h.Text="Instalando..."
$l2h.Font=$F_STEP; $l2h.ForeColor=$C_TEXT
$l2h.Location=New-Object System.Drawing.Point(30,15); $l2h.AutoSize=$true
$p2.Controls.Add($l2h)

$pg=New-Object System.Windows.Forms.ProgressBar; $pg.Minimum=0; $pg.Maximum=100; $pg.Value=0
$pg.Location=New-Object System.Drawing.Point(30,50); $pg.Size=New-Object System.Drawing.Size(610,20)
$pg.Style="Continuous"; $p2.Controls.Add($pg)

$l2s=New-Object System.Windows.Forms.Label; $l2s.Text="Preparando..."; $l2s.Font=$F_BODY
$l2s.ForeColor=$C_ACCENT; $l2s.Location=New-Object System.Drawing.Point(30,76)
$l2s.Size=New-Object System.Drawing.Size(610,18); $p2.Controls.Add($l2s)

$script:logBox=New-Object System.Windows.Forms.RichTextBox
$logBox.Font=$F_MONO; $logBox.BackColor=$C_LOG_BG; $logBox.ForeColor=$C_LOG_FG
$logBox.ReadOnly=$true; $logBox.ScrollBars="Vertical"
$logBox.Location=New-Object System.Drawing.Point(30,100); $logBox.Size=New-Object System.Drawing.Size(610,298)
$p2.Controls.Add($logBox)

# ── Panel 3: Listo ────────────────────────────────────────────────────────────
$p3=New-Object System.Windows.Forms.Panel; $p3.Dock="Fill"; $p3.BackColor=$C_BG; $p3.Visible=$false
$pCon.Controls.Add($p3)

$l3i=New-Object System.Windows.Forms.Label; $l3i.Name="l3i"; $l3i.Text="OK"
$l3i.Font=New-Object System.Drawing.Font("Segoe UI",34,[System.Drawing.FontStyle]::Bold)
$l3i.ForeColor=$C_SUCCESS; $l3i.Location=New-Object System.Drawing.Point(295,30); $l3i.AutoSize=$true
$p3.Controls.Add($l3i)

$l3t=New-Object System.Windows.Forms.Label; $l3t.Name="l3t"; $l3t.Text="Instalacion completada"
$l3t.Font=$F_STEP; $l3t.ForeColor=$C_TEXT
$l3t.Location=New-Object System.Drawing.Point(30,110); $l3t.AutoSize=$true
$p3.Controls.Add($l3t)

$tb3=New-Object System.Windows.Forms.RichTextBox; $tb3.Name="tb3"
$tb3.Font=$F_BODY; $tb3.BackColor=$C_BG; $tb3.ForeColor=$C_TEXT
$tb3.ReadOnly=$true; $tb3.BorderStyle="None"
$tb3.Location=New-Object System.Drawing.Point(30,145); $tb3.Size=New-Object System.Drawing.Size(610,230)
$p3.Controls.Add($tb3)

# ── Navegacion ────────────────────────────────────────────────────────────────
$allP=@($p0,$p1,$p2,$p3)

function Update-Ind {
    for($i=0;$i-lt 4;$i++){
        $sl=$pHdr.Controls["si_$i"]; if(-not $sl){continue}
        if($i-eq $script:State.Step){$sl.ForeColor=$C_ACCENT;$sl.Font=$F_BTN}
        elseif($i-lt $script:State.Step){$sl.ForeColor=$C_SUCCESS;$sl.Font=$F_SMALL}
        else{$sl.ForeColor=$C_MUTED;$sl.Font=$F_SMALL}
    }
}

function Show-Step([int]$n){
    $script:State.Step=$n
    for($i=0;$i-lt $allP.Count;$i++){$allP[$i].Visible=($i-eq $n)}
    Update-Ind
    switch($n){
        0{$btnB.Visible=$false;$btnN.Text="Siguiente >";$btnN.Visible=$true;$btnN.BackColor=$C_ACCENT}
        1{$btnB.Visible=$true;$btnN.Text="Instalar";$btnN.BackColor=$C_ACCENT}
        2{$btnB.Visible=$false;$btnN.Visible=$false}
        3{$btnB.Visible=$false;$btnN.Text="Cerrar";$btnN.Visible=$true
          $btnN.BackColor=if($script:State.Success){$C_SUCCESS}else{$C_ERROR}}
    }
}

function Start-Installation {
    Show-Step 2

    $script:State.InstallPath = $tf_inst.Text.Trim()
    $doSeed  = $ck_seed.Checked
    $doHooks = $ck_hooks.Checked

    $steps = @(
        @{pct=8;  msg="Creando directorio";         fn={New-Item -ItemType Directory -Force -Path $script:State.InstallPath|Out-Null}}
        @{pct=22; msg="Extrayendo Python 3.12";     fn={Install-PythonPortable}}
        @{pct=38; msg="Extrayendo Node.js";         fn={Install-NodeJS}}
        @{pct=58; msg="Instalando Claude Code CLI"; fn={Install-ClaudeCode}}
        @{pct=70; msg="Copiando Asistente IA";      fn={Copy-AsistenteFiles}}
        @{pct=80; msg="Sembrando KB GBM";           fn={if($doSeed){Seed-GBMKnowledge}else{Write-Log "Seed: omitido" "warn"}}}
        @{pct=90; msg="Configurando hooks Claude";  fn={if($doHooks){Configure-ClaudeHooks}else{Write-Log "Hooks: omitido" "warn"}}}
        @{pct=96; msg="Agregando Claude al PATH";   fn={Add-ToPATH}}
        @{pct=100;msg="Finalizando";                fn={Write-Log "Asistente IA instalado." "ok"}}
    )

    $script:State.Success=$true
    foreach($s in $steps){
        $l2s.Text=$s.msg; $pg.Value=$s.pct
        [System.Windows.Forms.Application]::DoEvents()
        try{ Invoke-Step $s.msg $s.fn }
        catch{
            $script:State.Success=$false
            $p2.Controls["l2h"].ForeColor=$C_ERROR; $p2.Controls["l2h"].Text="Error"
            $btnN.Text="Cerrar"; $btnN.Visible=$true; $btnN.BackColor=$C_ERROR
            return
        }
    }

    $p2.Controls["l2h"].Text="Instalacion exitosa"; $p2.Controls["l2h"].ForeColor=$C_SUCCESS

    $claudeNote = if($script:State.ClaudeExe){"claude.cmd listo en: $($script:State.ClaudeExe)"}
                  else{"Verifica manualmente el entry point de Claude Code"}

    $p3.Controls["tb3"].Text=@"
Instalacion completada correctamente.

Rutas:
  Asistente IA: $($script:State.InstallPath)
  Python:       $($script:State.InstallPath)\runtime\python\python.exe
  Node.js:      $($script:State.InstallPath)\runtime\node\node.exe
  Claude Code:  $claudeNote
  KB datos:     $env:USERPROFILE\.adaptive_cli\

Configuracion de Claude Code:
  Hooks activos en: $env:USERPROFILE\.claude\settings.json

Siguiente paso obligatorio -- API Key:
  Abre una terminal y ejecuta:
  claude config set apiKey TU_API_KEY_ANTHROPIC

Uso:
  cd "$($script:State.InstallPath)"
  claude

La base de conocimiento GBM cargara automaticamente al iniciar.
"@
    Show-Step 3
}

$btnN.Add_Click({ switch($script:State.Step){0{Show-Step 1};1{Start-Installation};3{$form.Close()}} })
$btnB.Add_Click({ if($script:State.Step-eq 1){Show-Step 0} })

Show-Step 0
[System.Windows.Forms.Application]::Run($form)
