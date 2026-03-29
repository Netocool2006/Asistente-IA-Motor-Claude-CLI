# Skill: Validar BoM

## Cuándo usar
Cuando el usuario pida revisar, validar, o verificar un BoM (Bill of Materials).

## Pasos obligatorios
1. Consultar la base:
   ```bash
   python knowledge_base.py export bom
   python knowledge_base.py export business_rules --query "bom clasificacion tarifas"
   ```
2. Abrir el archivo Excel del BoM
3. Verificar cada punto del checklist:

### Checklist de validación
- [ ] **Matemática**: subtotales = suma de items, total = subtotales + IVA 12%
- [ ] **Part numbers**: cada código de producto existe y es correcto
- [ ] **Clasificación**: cada item tiene categoría correcta (servicio/licencia/software/hardware/híbrido)
- [ ] **Nomenclatura**: verificar sufijos (_PS para contrato, _RN para renovación)
- [ ] **Tipo de cambio**: verificar TC aplicado, evaluar si conviene ajustar
- [ ] **Periodicidad**: coherente (mensual, anual, one-time) sin mezclas ilógicas
- [ ] **Cantidades**: lógicas y coherentes con el alcance
- [ ] **Descuentos**: dentro del rango permitido
- [ ] **Formato**: Arial 10pt, headers azul #2E75B6, filas alternadas

## Tarifas de referencia
- Soporte 24x7: $80-85 USD/hr
- Asistencia 8x5: $60 USD/hr
- Célula desarrollo: $28.95 USD/hr
- Per Call: $140 USD/hr

## Output esperado
Reporte con:
- Items OK ✅
- Items con error ❌ (detalle del error)
- Sugerencias de corrección
- Total correcto vs total actual
