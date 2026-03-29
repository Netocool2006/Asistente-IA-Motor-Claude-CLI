# 🧠 Adaptive CLI — Sistema de Aprendizaje Incremental para Claude Code

## La Idea

```
Día 1: "Login SAP CRM" → Claude piensa 10 min, prueba 5 selectores, lo logra
Día 2: "Login SAP CRM" → Consulta memoria → Lo resuelve en 5 segundos
```

La IA **solo se invoca cuando no hay patrón local**. Todo lo aprendido persiste
en un JSON local. Es un ciclo de: **detectar → corregir → registrar → reutilizar**.

## Arquitectura

```
┌─────────────────────────────────────────────────────┐
│                    TÚ (Néstor)                      │
│  "Hacé login en SAP CRM y creá una oportunidad"     │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│             adaptive_executor.py                     │
│                                                      │
│  1. search_pattern("sap_login", "crm_logon")        │
│     ├─ HIT  → Genera prompt con solución inyectada  │
│     └─ MISS → Genera prompt de exploración          │
│                                                      │
│  2. claude -p "<prompt>" --output-format json        │
│                                                      │
│  3. Parsea resultado → Registra/actualiza patrón    │
└────────────────────┬────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│           ~/.adaptive_cli/                           │
│                                                      │
│   learned_patterns.json    ← Base de conocimiento   │
│   execution_log.jsonl      ← Log append-only        │
└─────────────────────────────────────────────────────┘
```

## Setup

### 1. Copiar archivos al proyecto

```powershell
# En tu máquina Windows (C:\Chance1\SAP_Tierra_IA)
mkdir adaptive_cli
# Copiar estos archivos ahí:
#   learning_memory.py
#   adaptive_executor.py
#   seed_sap_patterns.py
#   CLAUDE.md
```

### 2. Sembrar patrones iniciales

```bash
cd C:\Chance1\SAP_Tierra_IA\adaptive_cli
python seed_sap_patterns.py
python learning_memory.py stats
```

### 3. Copiar CLAUDE.md a la raíz del proyecto

```powershell
copy adaptive_cli\CLAUDE.md C:\Chance1\SAP_Tierra_IA\CLAUDE.md
```

> **Esto es clave**: Claude Code CLI lee `CLAUDE.md` automáticamente
> al iniciar. Ahí le decimos que consulte la memoria antes de actuar.

## Uso Diario

### Opción A: Ejecución automática completa

```bash
python adaptive_executor.py run sap_login crm_logon "Haz login en SAP CRM WebUI client 500"  --tags sap,login,playwright
```

### Opción B: Solo generar el prompt (para copiar/pegar a Claude CLI)

```bash
python adaptive_executor.py prepare sap_login crm_logon "Haz login en SAP CRM"
```

### Opción C: Dentro de Claude Code CLI (interactivo)

Cuando estés en una sesión de `claude` CLI, simplemente pedile:
```
Antes de escribir código, ejecutá `python adaptive_executor.py export sap_login`
y usá los patrones que encuentres.
```

El `CLAUDE.md` ya le dice que haga esto, pero podés reforzarlo.

### Inspeccionar la memoria

```bash
# Estadísticas globales
python learning_memory.py stats

# Listar todos los patrones
python learning_memory.py list

# Buscar un patrón específico
python learning_memory.py search sap_login crm_logon

# Exportar como texto (para review humano)
python learning_memory.py export sap_login
```

## Cómo se "Pule" el Sistema

### Escenario: Patrón funciona → se refuerza
```
search_pattern() → HIT (95% éxito)
→ Claude usa la solución directamente
→ record_reuse(success=True)
→ success_rate sube a 96.5%
```

### Escenario: Patrón falla → se corrige
```
search_pattern() → HIT (80% éxito)
→ Claude intenta la solución, falla
→ Claude explora, encuentra fix
→ update_pattern() con la corrección
→ record_reuse(success=True) con el fix
→ Próxima vez ya incluye el fix
```

### Escenario: Patrón degradado → se re-evalúa
```
search_pattern() → HIT (45% éxito) < THRESHOLD
→ Claude ignora solución vieja
→ Explora desde cero con contexto previo
→ register_pattern() nuevo o update
```

## Estructura del JSON de Patrones

```json
{
  "id": "a1b2c3d4e5f6",
  "task_type": "sap_login",
  "context_key": "crm_logon_client500",
  "solution": {
    "strategy": "type_with_delay_plus_aria_fallback",
    "selector_chain": ["[aria-label*='User']", "input[type='password']"],
    "code_snippet": "await page.locator(...).type(pwd, delay=50)",
    "notes": "NUNCA usar .fill() para passwords en SAP",
    "attempts_to_solve": 5,
    "time_to_solve_seconds": 600
  },
  "tags": ["sap", "login", "playwright"],
  "stats": {
    "success_rate": 0.95,
    "reuses": 12,
    "lookups": 18
  },
  "history": [
    {
      "previous_solution": { "...": "versión anterior" },
      "changed_at": "2026-03-15T...",
      "reason": "SAP actualizó el botón de login"
    }
  ]
}
```

## Extensión Futura

- **Browser Use integration**: Cuando Browser Use capture pantallas,
  alimentar automáticamente los patrones con selectores visuales
- **Categorías nuevas**: No solo SAP — usar para cualquier automatización
  (Monday.com, APIs, generación de docs, etc.)
- **Dashboard**: Un script que genere un HTML con el "mapa de conocimiento"
  del sistema (qué sabe, qué está débil, qué es nuevo)
