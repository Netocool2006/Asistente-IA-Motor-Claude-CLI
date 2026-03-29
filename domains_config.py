"""
domains_config.py — Configuración de dominios para Solution Advisor GBM
========================================================================
Define TODOS los dominios de conocimiento del rol, organizados por
las 3 capas de valor: documental, sistemas, conocimiento.
"""

DOMAINS = {
    # ══════════════════════════════════════════════════════════
    #  CAPA 1: INTELIGENCIA DOCUMENTAL
    # ══════════════════════════════════════════════════════════

    "sow": {
        "description": (
            "Todo sobre SOWs: generación desde BoM, revisión (contradicciones, fechas, "
            "montos, ambigüedades, incoherencias), fusión de múltiples SOWs (hasta 6 prácticas), "
            "tipos (Renovación, Proyecto, Bolsa, RFP, Célula), estructura estándar GBM"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "sow_generate",       # Crear SOW desde BoM + plantilla
            "sow_review",         # Detectar errores, contradicciones, incoherencias
            "sow_fusion",         # Mezclar 2-6 SOWs de distintas prácticas
            "sow_economic",       # Propuesta económica (ajuste precio, MEP, pagos)
        ],
    },

    "bom": {
        "description": (
            "Bills of Materials: validación matemática, números de parte, "
            "clasificación (servicio/licencia/software/hardware/híbrido), tipo de cambio, "
            "fusión de múltiples BoMs, formato Excel 8 hojas GBM, estrategia de pricing"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "bom_validate",       # Verificar math, part numbers, clasificación
            "bom_fusion",         # Consolidar N BoMs en uno
            "bom_to_proposal",    # Transformar BoM → propuesta económica
            "bom_fx_strategy",    # Análisis de tipo de cambio, MEP vs lista
            "bom_payment_split",  # Dividir pagos (ej: 12 meses → 5 pagos)
        ],
    },

    "pptx": {
        "description": (
            "Presentaciones PowerPoint: resumen de propuestas para cliente, "
            "ofrecimiento de productos/servicios GBM, decks ejecutivos"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "pptx_proposal_summary",  # Deck resumen de propuesta
            "pptx_product_offering",  # Presentación de producto/servicio
        ],
    },

    # ══════════════════════════════════════════════════════════
    #  CAPA 2: AUTOMATIZACIÓN DE SISTEMAS
    # ══════════════════════════════════════════════════════════

    "sap_tierra": {
        "description": (
            "SAP CRM Web (Tierra): quotes (manual, contrato, estándar), "
            "items en oportunidades, piezas, licencias, costos, servicios de "
            "soporte/asistencia/asesoría. Automatización con Python/Playwright"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "sap_login",              # Login CRM WebUI
            "sap_quote_manual",       # Quote manual
            "sap_quote_contrato",     # Quote de contrato
            "sap_quote_estandar",     # Quote estándar
            "sap_fill_items",         # Llenar items en oportunidad
            "sap_attach_file",        # Adjuntar PDF/correo en SAP
            "sap_navigate_frames",    # Navegación iFrames
        ],
    },

    "sap_nube": {
        "description": (
            "SAP CRM Nube: versión cloud del CRM, formularios, "
            "oportunidades. Diferente interfaz que Tierra"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "sap_nube_quote",
            "sap_nube_items",
            "sap_nube_navigation",
        ],
    },

    "monday": {
        "description": (
            "Monday.com: seguimiento de propuestas, etapas, costos, "
            "valores de venta, criticidad, detalle producto/servicio, "
            "bitácora diaria de actividades"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "monday_update_pipeline",   # Actualizar estado propuesta
            "monday_log_activity",      # Bitácora de actividad
            "monday_import_data",       # Importar datos
        ],
    },

    "bpm_bau": {
        "description": (
            "BPM BAU: disparar procesos, llenar forms y pestañas, "
            "iniciar procesos de autorización"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "bau_start_process",
            "bau_fill_form",
            "bau_approval_flow",
        ],
    },

    "outlook": {
        "description": (
            "Outlook: enviar correos, guardar correos como adjuntos, "
            "attachar correos en SAP, adjuntar PDFs en SAP"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "outlook_send",
            "outlook_save_as_attachment",
            "outlook_to_sap",
        ],
    },

    "files": {
        "description": (
            "Manejo de archivos multi-formato: PDF, Excel, TXT, DOCX, JPG, PPTX. "
            "Conversiones, extracción, OCR, merge"
        ),
        "file": "patterns.json",
        "entry_type": "pattern",
        "tasks": [
            "file_convert",
            "file_extract_text",
            "file_merge_pdfs",
        ],
    },

    # ══════════════════════════════════════════════════════════
    #  CAPA 3: CONOCIMIENTO Y SESIONES
    # ══════════════════════════════════════════════════════════

    "sessions": {
        "description": (
            "Sesiones y reuniones: seguimiento cliente (upsell, extensiones), "
            "alineamiento interno (preventa, AMs, delivery), "
            "aprendizaje de nuevos productos/servicios"
        ),
        "file": "facts.json",
        "entry_type": "fact",
        "tasks": [
            "session_client_followup",     # Captura insights cliente
            "session_internal_alignment",   # Sesiones internas
            "session_product_learning",     # Nuevos productos/servicios
        ],
    },

    # ══════════════════════════════════════════════════════════
    #  TRANSVERSALES (aplican a todo)
    # ══════════════════════════════════════════════════════════

    "business_rules": {
        "description": (
            "Reglas de negocio GBM: nomenclatura códigos (_PS, _RN), "
            "tarifas estándar, cláusulas contractuales, SLAs, procesos internos, "
            "convenciones de pricing, IVA, tipos de quote"
        ),
        "file": "facts.json",
        "entry_type": "fact",
        "tasks": [],  # Se consulta desde cualquier otro dominio
    },

    "catalog": {
        "description": (
            "Catálogo de productos y servicios: IBM (DB2, WAS, MQ, Instana), "
            "SAP licencias, servicios GBM (soporte, asistencia, asesoría, "
            "célula desarrollo), códigos, precios, relaciones entre SKUs"
        ),
        "file": "facts.json",
        "entry_type": "fact",
        "tasks": [],
    },
}


# ── Mapeo de tareas a dominios que se deben consultar ──────────
# Cuando ejecutas una tarea, estos son los dominios ADICIONALES
# que se deben consultar automáticamente (cross-domain)

TASK_DEPENDENCIES = {
    # SOW tasks necesitan reglas de negocio + catálogo
    "sow_generate":     ["business_rules", "catalog", "bom"],
    "sow_review":       ["business_rules", "catalog"],
    "sow_fusion":       ["business_rules", "sow"],
    "sow_economic":     ["business_rules", "catalog", "bom"],

    # BoM tasks necesitan catálogo + reglas
    "bom_validate":     ["business_rules", "catalog"],
    "bom_fusion":       ["business_rules", "catalog"],
    "bom_to_proposal":  ["business_rules", "catalog", "sow"],
    "bom_fx_strategy":  ["business_rules"],
    "bom_payment_split": ["business_rules"],

    # SAP tasks necesitan reglas de negocio (nomenclatura, tipos de quote)
    "sap_fill_items":       ["business_rules", "catalog"],
    "sap_quote_manual":     ["business_rules"],
    "sap_quote_contrato":   ["business_rules", "catalog"],
    "sap_quote_estandar":   ["business_rules"],
    "sap_attach_file":      ["outlook", "files"],

    # Monday necesita contexto de propuestas
    "monday_update_pipeline": ["business_rules"],

    # Sesiones alimentan todo
    "session_client_followup":   ["catalog", "business_rules"],
    "session_product_learning":  ["catalog"],
}


def get_domains_for_task(task: str) -> list[str]:
    """
    Dado un task_id, retorna la lista de dominios que hay que consultar.
    Incluye el dominio propio + dependencias.
    """
    # Encontrar dominio primario de la tarea
    primary = None
    for domain, config in DOMAINS.items():
        if task in config.get("tasks", []):
            primary = domain
            break

    if not primary:
        return list(DOMAINS.keys())  # Si no encuentra, buscar en todo

    # Dominio primario + dependencias
    deps = TASK_DEPENDENCIES.get(task, [])
    all_domains = [primary] + [d for d in deps if d != primary]
    return all_domains


def describe_task(task: str) -> str:
    """Genera descripción legible de una tarea para el prompt."""
    descriptions = {
        "sow_generate": "Generar SOW desde BoM y plantilla GBM",
        "sow_review": "Revisar SOW: contradicciones, fechas, montos, ambigüedades, incoherencias",
        "sow_fusion": "Fusionar múltiples SOWs (hasta 6 prácticas) en uno solo",
        "sow_economic": "Construir propuesta económica desde BoM (ajuste precio, MEP, pagos)",
        "bom_validate": "Validar BoM: matemática, part numbers, clasificación, tipo de cambio",
        "bom_fusion": "Consolidar múltiples BoMs en uno solo",
        "bom_to_proposal": "Transformar BoM → propuesta económica con análisis de pricing",
        "bom_fx_strategy": "Analizar estrategia de tipo de cambio",
        "bom_payment_split": "Reestructurar pagos (ej: mensual → trimestral)",
        "sap_login": "Login en SAP CRM WebUI",
        "sap_fill_items": "Llenar items en oportunidad SAP (piezas, licencias, costos)",
        "sap_quote_manual": "Crear quote manual en SAP CRM",
        "sap_quote_contrato": "Crear quote de contrato en SAP CRM",
        "sap_quote_estandar": "Crear quote estándar en SAP CRM",
        "sap_attach_file": "Adjuntar archivo/correo en SAP CRM",
        "monday_update_pipeline": "Actualizar pipeline de propuestas en Monday.com",
        "monday_log_activity": "Registrar actividad en bitácora Monday.com",
        "session_client_followup": "Capturar insights de sesión con cliente",
        "session_internal_alignment": "Documentar sesión interna de alineamiento",
        "session_product_learning": "Registrar aprendizaje de nuevo producto/servicio",
    }
    return descriptions.get(task, task)
