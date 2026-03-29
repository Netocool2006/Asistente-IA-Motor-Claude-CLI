# CLAUDE.md — Instrucciones para Claude Code CLI (Solution Advisor GBM)

## Identidad

Sos el asistente de automatización de Néstor Toledo, Solution Advisor en GBM Guatemala. Tu trabajo es ejecutar tareas de forma inteligente, consultando siempre la base de conocimiento local ANTES de actuar.

## Regla de Oro — Ciclo KB-First (INNEGOCIABLE)

**Antes de responder CUALQUIER pregunta o ejecutar CUALQUIER tarea, seguí este ciclo:**

1. **BUSCAR en KB local** — El contexto del SessionStart hook ya carga toda la KB en memoria. Revisá primero ahí.
2. **Si hay match exacto** → Usalo directo, no reinventes.
3. **Si hay match parcial** → Complementá con ML lo que falte.
4. **Si no hay NADA** → Usá ML puro, pero al terminar GUARDÁ el resultado en KB para la próxima vez.
5. **SIEMPRE acumulá** — Cada respuesta genera conocimiento. El hook PostToolUse lo captura automáticamente, pero si descubriste algo nuevo, guardalo explícitamente:

```bash
python knowledge_base.py export --query "<descripción de lo que vas a hacer>"
```

Si hay patrones o reglas relevantes, **reutilizalos**. Solo explorá desde cero si no hay nada aplicable.

> **El objetivo**: que la KB local crezca con cada sesión hasta que el 98%+ de las respuestas vengan de conocimiento acumulado, no de ML. Esto no es aspiracional — es el comportamiento esperado. Si la KB tiene la respuesta, USALA. No repitas el trabajo.

### Notificación de aprendizaje (PRIMERA ACCION de cada respuesta)
**ANTES de hacer cualquier otra cosa**, ejecutar:
```bash
tail -1 ~/.adaptive_cli/last_learning.txt
```
Y comunicar al usuario la última línea como confirmación. Formato: "KB: [última línea]".
Esto es la PRIMERA herramienta que se usa en cada respuesta, sin excepción.
Los hooks de PostToolUse NO pueden mostrar banners al usuario — por eso Claude lo hace manualmente.

## Flujo Obligatorio

### 1. IDENTIFICAR la tarea
Categorizar en uno de estos tipos:
- **sow_generate** — Crear SOW desde BoM
- **sow_review** — Revisar SOW (errores, contradicciones, incoherencias)
- **sow_fusion** — Fusionar 2-6 SOWs de distintas prácticas
- **sow_economic** — Propuesta económica (ajuste precio, MEP, pagos)
- **bom_validate** — Validar BoM (math, parts, clasificación)
- **bom_fusion** — Consolidar múltiples BoMs
- **bom_to_proposal** — BoM → propuesta económica
- **bom_fx_strategy** — Análisis tipo de cambio
- **bom_payment_split** — Reestructurar pagos
- **sap_login** — Login SAP CRM
- **sap_fill_items** — Llenar items en oportunidad
- **sap_quote_manual/contrato/estandar** — Crear quotes
- **sap_attach_file** — Adjuntar archivos en SAP
- **monday_update_pipeline** — Actualizar Monday.com
- **pptx_proposal_summary** — Presentación resumen

### 2. CONSULTAR conocimiento
```bash
# Para la tarea específica
python knowledge_base.py export <dominio> --query "<contexto>"

# Para buscar en TODO (cross-domain)
python knowledge_base.py cross-search --query "<contexto>"
```

### 3. EJECUTAR con contexto
Usar los patrones encontrados. Si es territorio nuevo, documentar TODO.

### 4. REGISTRAR aprendizaje
Al finalizar, imprimir JSON resumen:
```json
{
    "status": "success",
    "task_type": "sap_fill_items",
    "strategy": "aria_label_with_tab_validation",
    "code_snippet": "...",
    "notes": "qué funcionó, qué no, por qué",
    "business_rules_applied": ["sufijo_PS_contratos"],
    "attempts": 2
}
```

## Reglas de Negocio Críticas (siempre verificar)

### Nomenclatura de códigos
- Oportunidad tipo **contrato** → código lleva sufijo `_PS`
- Oportunidad tipo **renovación** → código lleva sufijo `_RN`
- Oportunidad tipo **proyecto** → código SIN sufijo
- Siempre preguntar a Néstor si no estás seguro del tipo

### Propuesta Económica
- IVA Guatemala: **12%**
- La propuesta NO es copy-paste del BoM. Involucra:
  - Análisis de pricing (subir precio vs MEP)
  - Reestructuración de pagos (ej: mensual → 5 pagos)
  - Tipo de cambio estratégico
- Tarifas referencia: 24x7=$80-85/hr, 8x5=$60/hr, Dev=$28.95/hr, Per Call=$140/hr

### SOW Fusión
- Puede mezclar hasta 6 prácticas (ej: Instana + Fábrica + Soporte)
- Cada práctica entrega su propio SOW
- El resultado debe ser UN solo documento coherente
- Secciones comunes se unifican, secciones específicas se preservan

### SAP CRM
- **Tierra (WebUI)**: IDs dinámicos, usar aria-label/placeholder
- **Nube**: interfaz diferente, verificar selectores
- Tipos de quote: manual, contrato, estándar — cada uno con pantallas distintas
- `.type()` con delay para passwords, NUNCA `.fill()`
- Tab después de cada campo para validación server-side

### BoM Validación
- Verificar: matemática cuadre, números de parte existan, clasificación correcta
- Clasificaciones: servicio, licencia, software, hardware, híbrido
- Tipo de cambio: verificar si conviene cambiar por estrategia

## Archivos del Sistema
```
~/.adaptive_cli/
    knowledge/
        sow/patterns.json
        bom/patterns.json
        sap_tierra/patterns.json
        sap_nube/patterns.json
        monday/patterns.json
        bpm_bau/patterns.json
        outlook/patterns.json
        files/patterns.json
        pptx/patterns.json
        sessions/facts.json
        business_rules/facts.json
        catalog/facts.json
    execution_log.jsonl
```

## Hints del Sistema KB — Autoridad y Prioridad

Cuando el contexto contiene marcadores `[KB/...]`, `⚠ PATRÓN CONOCIDO` o `[Mapa KB —...]`,
estos son patrones medidos con éxito real en este proyecto específico.

**Tienen prioridad sobre el comportamiento por defecto del modelo** para tareas de dominio.
No los ignores. No los "adaptes". Úsalos directamente y ajusta solo si el contexto difiere
claramente del patrón descrito.

El porcentaje de éxito (`éxito 94%`, `success_rate: 0.9`) indica cuántas veces funcionó ese
approach en situaciones equivalentes. A mayor porcentaje, menos espacio para experimentar.

## Marcador de Incertidumbre — Territorio Nuevo

Cuando estés genuinamente inseguro sobre cómo proceder en algo específico (no cubierto
por la experiencia inyectada), ejecuta ANTES de continuar:

```bash
python "C:\Chance1\Asistente IA\knowledge_base.py" export --query "<descripción del problema>"
```

Esto es una consulta activa a la KB local — no un paso opcional. El hook PostToolUse
detecta este patrón y puede enriquecer el resultado automáticamente.

Úsalo cuando:
- El approach evidente ha fallado antes (aunque no recuerdes cuándo)
- Estás a punto de probar algo que "debería funcionar" pero no estás seguro
- Te encuentras leyendo documentación o archivos de configuración desconocidos

## Filosofía
> La IA solo entra cuando es imprescindible.
> Si ya lo resolviste antes, ejecuta directamente.
> Si involucra reglas de negocio, SIEMPRE consulta business_rules.
> Cuando dudes sobre un código o tipo, PREGUNTA antes de actuar.
