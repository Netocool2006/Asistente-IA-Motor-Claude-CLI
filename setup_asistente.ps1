# setup_asistente.ps1 — Configuración inicial del Asistente IA GBM
# Ejecutar UNA VEZ desde PowerShell:
#   cd "C:\Chance1\Asistente IA"
#   .\setup_asistente.ps1

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Asistente IA GBM — Setup Inicial" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Verificar que estamos en la carpeta correcta ──
$expectedPath = "C:\Chance1\Asistente IA"
if ($PWD.Path -ne $expectedPath) {
    Write-Host "[!] Ejecuta este script desde: $expectedPath" -ForegroundColor Yellow
    Write-Host "    cd '$expectedPath'" -ForegroundColor Yellow
    Write-Host "    .\setup_asistente.ps1" -ForegroundColor Yellow
    exit 1
}

# ── 2. Verificar que los archivos .py existen ──
$requiredFiles = @(
    "knowledge_base.py",
    "learning_memory.py",
    "adaptive_executor.py",
    "domains_config.py",
    "seed_gbm_knowledge.py",
    "CLAUDE.md"
)

$missing = @()
foreach ($f in $requiredFiles) {
    if (-not (Test-Path $f)) {
        $missing += $f
    }
}

if ($missing.Count -gt 0) {
    Write-Host "[ERROR] Faltan archivos:" -ForegroundColor Red
    foreach ($f in $missing) {
        Write-Host "  - $f" -ForegroundColor Red
    }
    Write-Host ""
    Write-Host "Copia todos los archivos descargados a: $expectedPath" -ForegroundColor Yellow
    exit 1
}

Write-Host "[OK] Archivos verificados" -ForegroundColor Green

# ── 3. Verificar Python ──
try {
    $pyVersion = python --version 2>&1
    Write-Host "[OK] Python encontrado: $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Python no encontrado. Instalar Python 3.10+" -ForegroundColor Red
    exit 1
}

# ── 4. Sembrar la base de conocimiento ──
Write-Host ""
Write-Host "Sembrando base de conocimiento..." -ForegroundColor Cyan
python seed_gbm_knowledge.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Fallo al sembrar la base" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "[OK] Base de conocimiento creada" -ForegroundColor Green

# ── 5. Verificar que se creó la carpeta de knowledge ──
$knowledgePath = "$env:USERPROFILE\.adaptive_cli\knowledge"
if (Test-Path $knowledgePath) {
    Write-Host "[OK] Carpeta de conocimiento: $knowledgePath" -ForegroundColor Green
    $jsonFiles = Get-ChildItem -Path $knowledgePath -Recurse -Filter "*.json"
    Write-Host "     $($jsonFiles.Count) archivos JSON creados" -ForegroundColor Gray
} else {
    Write-Host "[WARN] Carpeta knowledge no encontrada en $knowledgePath" -ForegroundColor Yellow
}

# ── 6. Test rápido de búsqueda ──
Write-Host ""
Write-Host "Test de busqueda cross-domain..." -ForegroundColor Cyan
python knowledge_base.py cross-search --query "LLML245 contrato"

# ── 7. Mostrar estadísticas ──
Write-Host ""
Write-Host "Estadisticas:" -ForegroundColor Cyan
python knowledge_base.py stats

# ── 8. Resumen final ──
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  Setup completo!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Archivos del sistema:" -ForegroundColor White
Write-Host '  Proyecto:      C:\Chance1\Asistente IA' -ForegroundColor Gray
Write-Host '  Conocimiento:  %USERPROFILE%\.adaptive_cli\knowledge' -ForegroundColor Gray
Write-Host '  Log:           %USERPROFILE%\.adaptive_cli\execution_log.jsonl' -ForegroundColor Gray
Write-Host ""
Write-Host "Comandos utiles:" -ForegroundColor White
Write-Host '  python knowledge_base.py stats                           # Ver estadisticas' -ForegroundColor Gray
Write-Host '  python knowledge_base.py export --query "algo"           # Buscar conocimiento' -ForegroundColor Gray
Write-Host '  python knowledge_base.py cross-search --query "algo"     # Buscar en todo' -ForegroundColor Gray
Write-Host '  python knowledge_base.py ingest-rules reglas.txt         # Agregar reglas nuevas' -ForegroundColor Gray
Write-Host '  python knowledge_base.py ingest-catalog productos.txt    # Agregar productos' -ForegroundColor Gray
Write-Host ""
Write-Host "Para Claude Code CLI:" -ForegroundColor White
Write-Host "  cd C:\Chance1\Asistente IA" -ForegroundColor Gray
Write-Host '  claude' -ForegroundColor Gray
Write-Host '  (Claude lee CLAUDE.md automaticamente y consulta la base)' -ForegroundColor Gray
Write-Host ""