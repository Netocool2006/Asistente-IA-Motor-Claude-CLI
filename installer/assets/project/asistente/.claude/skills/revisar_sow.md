# Skill: Revisar SOW

## Cuándo usar
Cuando el usuario pida revisar, auditar, o verificar un SOW existente.

## Pasos obligatorios
1. Consultar la base:
   ```bash
   python knowledge_base.py export sow --query "revision checklist"
   python knowledge_base.py export business_rules --query "clausulas"
   ```
2. Leer el documento SOW completo
3. Revisar cada punto:

### Checklist de revisión
- [ ] **Fechas**: inicio < fin, vigencia oferta coherente, fechas no vencidas
- [ ] **Montos**: propuesta económica = suma de items, IVA 12% correcto
- [ ] **Contradicciones**: alcance vs propuesta, cláusulas vs condiciones especiales
- [ ] **Ambigüedades**: entregables vagos, responsabilidades no definidas
- [ ] **Lógica**: SLAs con métrica clara, penalidades con base de cálculo
- [ ] **Consistencia nombres**: cliente, proyecto, oportunidad iguales en todo el doc
- [ ] **Cláusulas estándar**: liability cap, vigencia, aceptación tácita, garantía
- [ ] **Numeración**: arábiga con decimales (3.1, 3.1.1), sin saltos
- [ ] **Anexos**: Service Desk, glosario, SLA presentes
- [ ] **Firmantes**: nombres y cargos correctos en ambas partes

## Output esperado
Reporte con:
- Errores críticos 🔴 (bloquean la firma)
- Advertencias 🟡 (deberían corregirse)
- Sugerencias 🟢 (mejoras opcionales)
- Veredicto: LISTO / NECESITA CORRECCIÓN
