# Skill: Gestionar correos Outlook

## Cuándo usar
Cuando el usuario pida buscar, enviar, reenviar correos o trabajar con adjuntos.

## Herramienta
Usar `outlook_bridge.py` para TODAS las operaciones de correo.

## Comandos disponibles
```bash
# Buscar en asunto/remitente
python outlook_bridge.py search "texto"
python outlook_bridge.py search "texto" --from
python outlook_bridge.py search "texto" --open

# Buscar DENTRO del cuerpo (números de oportunidad, códigos, etc.)
python outlook_bridge.py search-body "273847" --open

# Ver últimos correos
python outlook_bridge.py recent 10

# Leer correo completo
python outlook_bridge.py read <EntryID>

# Descargar adjuntos
python outlook_bridge.py download <EntryID>

# Abrir correo en Outlook
python outlook_bridge.py open <EntryID>

# Enviar correo
python outlook_bridge.py send "to@mail.com" "Asunto" "Cuerpo"
python outlook_bridge.py send "to@mail.com" "Asunto" "Cuerpo" --attach archivo.pdf
python outlook_bridge.py send "to@mail.com" "Asunto" "Cuerpo" --draft

# Responder / Reenviar
python outlook_bridge.py reply <EntryID> "texto respuesta"
python outlook_bridge.py forward <EntryID> "destino@mail.com"
```

## Reglas de seguridad
- Antes de ENVIAR un correo, SIEMPRE mostrar preview a Néstor y pedir confirmación
- Usar --draft primero si hay duda
- Nunca enviar información confidencial sin confirmación explícita

## Buscar archivos en disco + correos a la vez
```bash
python file_search.py "273847"
```
Esto busca en archivos PDF/DOCX/XLSX + knowledge base + Outlook simultáneamente.
