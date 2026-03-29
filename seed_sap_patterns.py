"""
seed_sap_patterns.py — Pre-cargar patrones de SAP CRM conocidos
================================================================
Corre esto UNA VEZ para sembrar la memoria con lo que ya sabés
de tu experiencia automatizando SAP CRM con Playwright.
"""

from learning_memory import register_pattern

# ── 1. Login SAP CRM ──────────────────────────────────────────
register_pattern(
    task_type="sap_login",
    context_key="crm_logon_client500",
    solution={
        "strategy": "type_with_delay_plus_aria_fallback",
        "selector_chain": [
            "input[placeholder*='User']",
            "input[aria-label*='User']",
            "#logonuidfield",  # fallback, a veces funciona
        ],
        "code_snippet": """
# Password: SIEMPRE usar .type() con delay, NUNCA .fill()
await page.locator("input[type='password']").type(password, delay=50)

# Botón login: cascada de fallbacks
for selector in [
    "button[aria-label='Log On']",
    "button:has-text('Log On')",
    "#logonBtn",
    "input[type='submit']",
]:
    btn = page.locator(selector)
    if await btn.count() > 0:
        await btn.click()
        break
""",
        "notes": (
            "SAP CRM WebUI genera IDs dinámicos — NUNCA confiar en ellos. "
            "Usar aria-label o placeholder como selectores primarios. "
            ".fill() NO funciona para password en SAP — usar .type() con delay=50. "
            "El botón de login cambia de ID entre sesiones."
        ),
        "attempts_to_solve": 5,
        "time_to_solve_seconds": 600,
    },
    tags=["sap", "crm", "login", "playwright", "password", "dynamic_ids"],
)

# ── 2. Navegación dentro de SAP CRM ──────────────────────────
register_pattern(
    task_type="sap_navigation",
    context_key="crm_workarea_frames",
    solution={
        "strategy": "iframe_detection_with_wait",
        "selector_chain": [
            "iframe[name*='WorkArea']",
            "iframe[id*='FRAME']",
        ],
        "code_snippet": """
# SAP CRM usa iFrames anidados - hay que esperar y entrar
main_frame = page.frame_locator("iframe[name*='WorkArea']")
# O detectar dinámicamente:
for frame in page.frames:
    if 'CRM' in (frame.name or '') or 'WorkArea' in (frame.url or ''):
        target = frame
        break

# Siempre esperar a que el frame tenga contenido
await target.wait_for_load_state('domcontentloaded')
""",
        "notes": (
            "SAP CRM usa iFrames anidados. El contenido principal suele estar en "
            "un frame llamado 'WorkAreaFrame' o similar. El nombre puede cambiar "
            "entre transacciones. Esperar siempre domcontentloaded antes de interactuar."
        ),
        "attempts_to_solve": 3,
        "time_to_solve_seconds": 300,
    },
    tags=["sap", "crm", "iframe", "navigation", "playwright"],
)

# ── 3. Llenado de campos SAP ─────────────────────────────────
register_pattern(
    task_type="crm_field_fill",
    context_key="sap_input_fields_general",
    solution={
        "strategy": "aria_label_with_click_focus_type",
        "selector_chain": [
            "[aria-label='{field_label}']",
            "[placeholder*='{field_label}']",
            "input[title*='{field_label}']",
            "th:has-text('{field_label}') + td input",
        ],
        "code_snippet": """
# Patrón para llenar campos en SAP CRM:
# 1) Click para dar foco (SAP necesita esto)
# 2) Clear contenido previo
# 3) Type con delay

field = page.locator(f"[aria-label*='{label}']").first
await field.click()
await field.fill('')  # clear
await field.type(value, delay=30)
await page.keyboard.press('Tab')  # trigger SAP validation
""",
        "notes": (
            "Los campos de SAP CRM requieren: click → clear → type → Tab. "
            "El Tab al final es CRÍTICO porque dispara la validación server-side de SAP. "
            "Sin Tab, el valor puede no guardarse. Si el campo tiene autocompletado, "
            "esperar el dropdown y seleccionar con click."
        ),
        "attempts_to_solve": 4,
        "time_to_solve_seconds": 480,
    },
    tags=["sap", "crm", "fields", "input", "playwright", "validation"],
)

# ── 4. Guardar registro SAP ──────────────────────────────────
register_pattern(
    task_type="crm_save",
    context_key="sap_save_record",
    solution={
        "strategy": "save_button_text_locator",
        "selector_chain": [
            "button:has-text('Save')",
            "button:has-text('Guardar')",
            "[aria-label*='Save']",
            "a[title*='Save']",
        ],
        "code_snippet": """
# Guardar en SAP CRM
save_btn = page.locator("button:has-text('Save'), [aria-label*='Save']").first
await save_btn.click()

# Esperar confirmación (SAP tarda)
await page.wait_for_timeout(3000)

# Verificar que no hay error
error = page.locator(".sapMessage, [class*='error'], [class*='Error']")
if await error.count() > 0:
    error_text = await error.first.text_content()
    raise Exception(f"SAP Error: {error_text}")
""",
        "notes": (
            "Después de guardar en SAP, SIEMPRE verificar mensajes de error. "
            "SAP no siempre muestra confirmación visual clara de éxito. "
            "Esperar al menos 3s porque el roundtrip server-side es lento."
        ),
        "attempts_to_solve": 2,
        "time_to_solve_seconds": 120,
    },
    tags=["sap", "crm", "save", "playwright", "validation"],
)

print("✅ 4 patrones SAP CRM sembrados en la memoria local.")
print("   Ejecuta: python learning_memory.py stats")
print("   Para ver el estado de la base de conocimiento.")
