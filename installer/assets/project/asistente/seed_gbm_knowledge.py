"""
seed_gbm_knowledge.py — Semilla completa de conocimiento GBM
=============================================================
Corre UNA VEZ para poblar la base con conocimiento inicial.
Después alimentar incrementalmente con:
    python knowledge_base.py ingest-rules nuevas_reglas.txt
    python knowledge_base.py ingest-catalog nuevos_productos.txt
"""

from knowledge_base import add_fact, add_pattern

print("Sembrando base de conocimiento GBM...")

# ══════════════════════════════════════════════════════════════
#  BUSINESS RULES — Reglas transversales
# ══════════════════════════════════════════════════════════════

add_fact("business_rules", "sufijo_PS_contratos", {
    "rule": "Códigos de items de contrato llevan sufijo _PS (post-sale support)",
    "applies_to": "Oportunidades tipo contrato en SAP CRM",
    "examples": [
        {"input": "LLML245", "output": "LLML245_PS", "context": "contrato"},
        {"input": "LLML245", "output": "LLML245", "context": "proyecto"},
        {"input": "DB2ENT100", "output": "DB2ENT100_PS", "context": "contrato IBM"},
    ],
    "exceptions": "Renovaciones usan _RN. Proyectos no llevan sufijo.",
    "source": "Proceso interno GBM", "confidence": "verified",
}, tags=["nomenclatura", "codigos", "contrato", "PS", "items", "oportunidad"])

add_fact("business_rules", "sufijo_RN_renovaciones", {
    "rule": "Códigos de renovación llevan sufijo _RN",
    "applies_to": "Oportunidades tipo renovación de licencia",
    "examples": [{"input": "SAPLIC200", "output": "SAPLIC200_RN", "context": "renovación anual"}],
    "exceptions": "Solo renovaciones, no contratos ni proyectos",
    "source": "Proceso interno GBM", "confidence": "verified",
}, tags=["nomenclatura", "codigos", "renovacion", "RN"])

add_fact("business_rules", "tarifas_soporte", {
    "rule": "Tarifas estándar GBM por tipo de servicio",
    "applies_to": "Propuestas económicas, SOWs, BoMs",
    "examples": [
        {"input": "Soporte 24x7", "output": "$80-85 USD/hr", "context": "crítico"},
        {"input": "Asistencia 8x5", "output": "$60 USD/hr", "context": "estándar"},
        {"input": "Célula desarrollo", "output": "$28.95 USD/hr", "context": "dedicado"},
        {"input": "Per Call", "output": "$140 USD/hr", "context": "por incidente"},
    ],
    "source": "SOW Style Guide GBM", "confidence": "verified",
}, tags=["tarifas", "precios", "soporte", "sow", "propuesta", "bom"])

add_fact("business_rules", "clausulas_estandar", {
    "rule": "Cláusulas estándar para SOWs de GBM",
    "applies_to": "Todos los SOWs",
    "examples": [
        {"input": "Liability cap", "output": "10% contrato (max $100K)", "context": ""},
        {"input": "Vigencia oferta", "output": "30 días", "context": ""},
        {"input": "Aceptación tácita", "output": "3 días hábiles", "context": ""},
        {"input": "Garantía", "output": "30-60 días", "context": ""},
        {"input": "Penalidad cliente", "output": "0.2%/día", "context": ""},
        {"input": "Fee reanudación", "output": "10%", "context": ""},
        {"input": "Mora pago", "output": "3%/mes", "context": ""},
        {"input": "No solicitud", "output": "12-24 meses", "context": ""},
    ],
    "source": "GBM_SOW_Style_Guide.md", "confidence": "verified",
}, tags=["clausulas", "sow", "contrato", "legal"])

add_fact("business_rules", "iva_guatemala", {
    "rule": "IVA Guatemala es 12%, aplica a todas las propuestas económicas",
    "applies_to": "Propuestas económicas Guatemala",
    "source": "Legislación Guatemala", "confidence": "verified",
}, tags=["iva", "impuesto", "guatemala", "propuesta"])

add_fact("business_rules", "tipos_sow", {
    "rule": "5 tipos de SOW con estructura distinta",
    "applies_to": "Generación de SOWs",
    "examples": [
        {"input": "Tipo 1", "output": "Renovación de Licencias", "context": "renewal"},
        {"input": "Tipo 2", "output": "Proyecto de Servicios", "context": "project"},
        {"input": "Tipo 3", "output": "Bolsa de Horas / Soporte", "context": "support"},
        {"input": "Tipo 4", "output": "Respuesta a RFP", "context": "rfp"},
        {"input": "Tipo 5", "output": "Célula de Desarrollo", "context": "dev cell"},
    ],
    "source": "SOW Style Guide", "confidence": "verified",
}, tags=["sow", "tipos", "estructura"])

add_fact("business_rules", "tipos_quote_sap", {
    "rule": "SAP CRM maneja diferentes tipos de quote, cada uno con pantallas distintas",
    "applies_to": "Creación de quotes en SAP CRM",
    "examples": [
        {"input": "Quote manual", "output": "Pantalla libre, campos abiertos", "context": "flexible"},
        {"input": "Quote contrato", "output": "Vinculado a contrato existente, items preconfigurados", "context": "renewal/support"},
        {"input": "Quote estándar", "output": "Template predefinido, flujo guiado", "context": "standard"},
    ],
    "source": "Proceso SAP CRM GBM", "confidence": "verified",
}, tags=["quote", "sap", "tipos", "crm"])

add_fact("business_rules", "bom_clasificaciones", {
    "rule": "Items en BoM se clasifican en categorías que afectan pricing y estructura",
    "applies_to": "Validación y creación de BoMs",
    "examples": [
        {"input": "Servicio", "output": "Horas consultoría, soporte, asistencia", "context": ""},
        {"input": "Licencia", "output": "Software licensing (PVU, VPC, suscripción)", "context": ""},
        {"input": "Software", "output": "Producto software empaquetado", "context": ""},
        {"input": "Hardware", "output": "Equipo físico, servidores, storage", "context": ""},
        {"input": "Híbrido", "output": "Combinación de 2+ categorías", "context": ""},
    ],
    "source": "Proceso interno GBM", "confidence": "verified",
}, tags=["bom", "clasificacion", "items", "producto", "servicio"])

add_fact("business_rules", "propuesta_no_es_copypaste", {
    "rule": "La propuesta económica NO es copy-paste del BoM, requiere análisis",
    "applies_to": "Transformación BoM → propuesta económica",
    "examples": [
        {"input": "Pricing", "output": "Decidir si subir precio o ir a MEP", "context": "estrategia"},
        {"input": "Pagos", "output": "Reestructurar (ej: 12 meses → 5 pagos)", "context": "cliente pidió"},
        {"input": "Tipo cambio", "output": "Evaluar si conviene ajustar TC por estrategia", "context": ""},
    ],
    "source": "Experiencia Néstor / proceso GBM", "confidence": "verified",
}, tags=["propuesta", "economica", "bom", "pricing", "mep", "pagos"])

add_fact("business_rules", "sow_fusion_reglas", {
    "rule": "Al fusionar SOWs: secciones comunes se unifican, específicas se preservan",
    "applies_to": "Fusión de 2-6 SOWs de diferentes prácticas",
    "examples": [
        {"input": "Instana + Fábrica", "output": "1 SOW unificado", "context": "2 prácticas"},
        {"input": "6 prácticas", "output": "1 SOW con 6 secciones técnicas", "context": "máximo"},
    ],
    "exceptions": "Portada, T&C, Aceptación siempre se unifican. Alcance técnico se preserva por práctica.",
    "source": "Proceso GBM", "confidence": "verified",
}, tags=["sow", "fusion", "merge", "practicas"])

add_fact("business_rules", "service_desk", {
    "rule": "GBM Service Desk: 7 países, extensión 3911, SLA 4 niveles",
    "applies_to": "Anexos de SOW", "source": "SOW Style Guide", "confidence": "verified",
}, tags=["service_desk", "soporte", "sla"])

add_fact("business_rules", "bom_formato_excel", {
    "rule": "BoM GBM: Excel 8 hojas, Arial 10pt, headers azul #2E75B6, filas alternadas",
    "applies_to": "Creación de BoMs",
    "source": "Proceso interno GBM", "confidence": "verified",
}, tags=["bom", "excel", "formato"])


# ══════════════════════════════════════════════════════════════
#  CATALOG — Productos
# ══════════════════════════════════════════════════════════════

for code, name, tags in [
    ("DB2ENT", "IBM DB2 Enterprise", ["ibm", "db2", "base_datos"]),
    ("WAS", "IBM WebSphere Application Server", ["ibm", "websphere", "java"]),
    ("IBMMQ", "IBM MQ Messaging", ["ibm", "mq", "mensajeria"]),
    ("INSTANA", "IBM Instana Observability", ["ibm", "instana", "observabilidad", "apm"]),
]:
    add_fact("catalog", code.lower(), {
        "rule": f"{name}",
        "code": code,
        "product_type": "software_license",
        "variants": [f"{code}_PS", f"{code}_RN"],
        "source": "IBM Price List", "confidence": "verified",
    }, tags=tags + ["licencia", "producto"])


# ══════════════════════════════════════════════════════════════
#  SOW — Patrones documentales
# ══════════════════════════════════════════════════════════════

add_pattern("sow", "estructura_general_sow", {
    "strategy": "sow_template_standard",
    "notes": (
        "Estructura: Portada → Carta → Contenido → ¿Por qué GBM? → "
        "[Secciones por tipo] → Propuesta Económica (IVA 12%) → T&C → "
        "Aceptación → Anexos (SD 7 países ext 3911, glosario, SLA 4 niveles) → Contraportada. "
        "Numeración arábiga decimales (3.1, 3.1.1). Tono formal-comercial consultivo."
    ),
}, tags=["sow", "estructura", "template"])

add_pattern("sow", "revision_checklist", {
    "strategy": "sow_review_systematic",
    "notes": (
        "Checklist revisión SOW: 1) Fechas coherentes (inicio < fin, vigencia oferta). "
        "2) Montos: propuesta económica = suma items, IVA 12% correcto. "
        "3) Contradicciones: alcance vs propuesta, cláusulas vs condiciones especiales. "
        "4) Ambigüedades: entregables vagos, responsabilidades no definidas. "
        "5) Lógica: SLA sin métrica, penalidades sin base de cálculo. "
        "6) Nombres: cliente, proyecto, oportunidad consistentes en todo el doc."
    ),
}, tags=["sow", "revision", "review", "checklist", "errores"])

add_pattern("sow", "fusion_proceso", {
    "strategy": "sow_fusion_merge",
    "notes": (
        "Fusión SOWs: 1) Identificar secciones comunes (Portada, ¿Por qué GBM?, T&C, Aceptación). "
        "2) Unificar secciones comunes tomando la versión más completa. "
        "3) Preservar alcance técnico de cada práctica como sub-sección numerada. "
        "4) Consolidar propuesta económica (sumar, verificar math). "
        "5) Unificar anexos sin duplicar. "
        "6) Verificar coherencia global post-fusión."
    ),
}, tags=["sow", "fusion", "merge", "multiples"])


# ══════════════════════════════════════════════════════════════
#  BOM — Patrones
# ══════════════════════════════════════════════════════════════

add_pattern("bom", "validacion_checklist", {
    "strategy": "bom_validate_systematic",
    "notes": (
        "Checklist validación BoM: 1) Matemática cuadre (subtotales, totales, IVA). "
        "2) Part numbers existan y sean correctos. "
        "3) Clasificación correcta (servicio/licencia/software/hardware/híbrido). "
        "4) Tipo de cambio aplicado correctamente. "
        "5) Periodicidad coherente (mensual, anual, one-time). "
        "6) Cantidades lógicas. 7) Descuentos dentro de rango permitido."
    ),
}, tags=["bom", "validacion", "checklist", "math"])

add_pattern("bom", "fusion_multiples", {
    "strategy": "bom_consolidation",
    "notes": (
        "Fusión BoMs: 1) Identificar estructura de cada BoM (hojas, columnas). "
        "2) Normalizar formato (mismo estilo, mismas columnas). "
        "3) Concatenar items por categoría. 4) Recalcular subtotales y totales. "
        "5) Verificar no duplicar items. 6) Tipo de cambio unificado."
    ),
}, tags=["bom", "fusion", "consolidar", "excel"])

add_pattern("bom", "bom_to_propuesta", {
    "strategy": "bom_economic_transform",
    "notes": (
        "BoM → Propuesta: NO es copy-paste. Pasos: "
        "1) Analizar si precio BoM es competitivo o hay que ajustar. "
        "2) Decidir MEP vs precio lista (consultar con AM). "
        "3) Reestructurar pagos según necesidad cliente. "
        "4) Aplicar IVA 12%. 5) Verificar que total propuesta sea coherente con BoM."
    ),
}, tags=["bom", "propuesta", "economica", "pricing"])


# ══════════════════════════════════════════════════════════════
#  SAP TIERRA — Patrones de automatización
# ══════════════════════════════════════════════════════════════

add_pattern("sap_tierra", "login_crm", {
    "strategy": "type_delay_aria_fallback",
    "selector_chain": [
        "input[placeholder*='User']", "input[aria-label*='User']", "#logonuidfield",
    ],
    "code_snippet": "await page.locator(\"input[type='password']\").type(password, delay=50)",
    "notes": "NUNCA .fill() para passwords. IDs dinámicos inútiles. Usar aria-label.",
}, tags=["sap", "login", "playwright"])

add_pattern("sap_tierra", "iframe_navigation", {
    "strategy": "iframe_wait_detect",
    "selector_chain": ["iframe[name*='WorkArea']", "iframe[id*='FRAME']"],
    "code_snippet": "await target.wait_for_load_state('domcontentloaded')",
    "notes": "iFrames anidados. Esperar siempre domcontentloaded.",
}, tags=["sap", "iframe", "navigation"])

add_pattern("sap_tierra", "field_fill_general", {
    "strategy": "click_clear_type_tab",
    "selector_chain": [
        "[aria-label='{field}']", "[placeholder*='{field}']",
        "th:has-text('{field}') + td input",
    ],
    "code_snippet": "await f.click(); await f.fill(''); await f.type(val, delay=30); await page.keyboard.press('Tab')",
    "notes": "Tab CRÍTICO: dispara validación server-side SAP.",
}, tags=["sap", "fields", "input", "validation"])

add_pattern("sap_tierra", "fill_items_oportunidad", {
    "strategy": "items_table_row_by_row",
    "notes": (
        "Llenar items en oportunidad SAP: 1) Navegar a tab de items. "
        "2) Click 'Add' o 'New'. 3) Para cada item: llenar código (verificar sufijo _PS/_RN "
        "según tipo oportunidad), cantidad, precio. 4) Tab entre campos. "
        "5) Guardar después de cada bloque. "
        "IMPORTANTE: consultar business_rules para validar códigos."
    ),
}, tags=["sap", "items", "oportunidad", "codigos", "llenar"])


# ══════════════════════════════════════════════════════════════
#  MONDAY — Patrones
# ══════════════════════════════════════════════════════════════

add_pattern("monday", "update_pipeline", {
    "strategy": "monday_api_or_ui",
    "notes": (
        "Monday.com pipeline: actualizar etapa, costos, valor venta, criticidad. "
        "Bitácora: registrar actividad del día con fecha y detalle. "
        "Detalle producto/servicio por propuesta."
    ),
}, tags=["monday", "pipeline", "propuesta", "seguimiento"])


print("=" * 60)
print("Base de conocimiento GBM sembrada:")
from knowledge_base import get_global_stats
import json
stats = get_global_stats()
for domain, s in stats.items():
    if domain == "total":
        continue
    if s["entries"] > 0:
        print(f"  {domain:16s}: {s['entries']} entradas")
print(f"\n  TOTAL: {stats['total']} entradas")
print("=" * 60)
