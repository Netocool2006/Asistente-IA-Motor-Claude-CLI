# Skill: Automatizar SAP CRM

## Cuándo usar
Cuando el usuario pida interactuar con SAP CRM (login, quotes, items, oportunidades).

## Pasos obligatorios
1. Consultar la base:
   ```bash
   python knowledge_base.py export sap_tierra
   python knowledge_base.py export business_rules --query "quote sap nomenclatura"
   ```
2. Verificar qué tipo de operación es (login, quote, items, adjuntar)

## Reglas SAP CRM Tierra (WebUI)
- IDs dinámicos: NUNCA confiar en ellos
- Selectores estables: aria-label, placeholder, texto visible
- Password: SIEMPRE .type() con delay=50, NUNCA .fill()
- Después de cada campo: presionar Tab (validación server-side)
- iFrames: esperar domcontentloaded antes de interactuar
- Guardar: esperar 3s, verificar mensajes de error

## Prioridad de selectores
1. `[aria-label*='campo']`
2. `[placeholder*='campo']`
3. `input[title*='campo']`
4. `th:has-text('campo') + td input`

## Nomenclatura de códigos (CRÍTICO)
- Oportunidad tipo CONTRATO → código + `_PS`
- Oportunidad tipo RENOVACIÓN → código + `_RN`
- Oportunidad tipo PROYECTO → código SIN sufijo
- SIEMPRE verificar con: `python knowledge_base.py cross-search --query "codigo sufijo"`
- EN CASO DE DUDA → preguntar a Néstor antes de ingresar

## Tipos de quote
- Manual: pantalla libre, campos abiertos
- Contrato: vinculado a contrato existente
- Estándar: template predefinido, flujo guiado

## Herramientas
- Python + Playwright para automatización
- Browser Use como alternativa para navegación visual
- Screenshots en cada paso para diagnóstico
