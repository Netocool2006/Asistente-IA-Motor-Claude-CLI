# Skill: Generar SOW desde BoM

## Cuándo usar
Cuando el usuario pida crear, generar, o redactar un SOW basado en un BoM o propuesta.

## Pasos obligatorios
1. Consultar la base de conocimiento:
   ```bash
   python knowledge_base.py export sow
   python knowledge_base.py export business_rules --query "clausulas tarifas sow"
   ```
2. Identificar el tipo de SOW (Renovación, Proyecto, Bolsa, RFP, Célula)
3. Pedir al usuario: nombre cliente, número oportunidad, tipo SOW, firmantes
4. Seguir estructura estándar GBM:
   - Portada
   - Carta presentación
   - Contenido
   - ¿Por qué GBM?
   - Secciones específicas del tipo
   - Propuesta Económica (IVA 12%)
   - T&C (cláusulas estándar)
   - Aceptación
   - Anexos (Service Desk 7 países ext 3911, glosario, SLA 4 niveles)
   - Contraportada
5. Numeración arábiga con decimales (3.1, 3.1.1)
6. Tono: formal-comercial consultivo, español con términos técnicos en inglés

## Reglas de negocio a verificar SIEMPRE
- Liability cap: 10% del contrato (max $100K USD)
- Vigencia oferta: 30 días
- Aceptación tácita: 3 días hábiles
- Garantía: 30-60 días
- Per Call: $140 USD/hr
- Soporte 24x7: $80-85/hr
- Asistencia 8x5: $60/hr

## Al finalizar
Registrar el aprendizaje con JSON resumen.
