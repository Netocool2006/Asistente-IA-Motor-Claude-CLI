# Skill: Buscar información

## Cuándo usar
Cuando el usuario pida buscar un documento, número de oportunidad, código, 
o cualquier información que pueda estar en archivos, correos, o la base de conocimiento.

## Orden de búsqueda
1. **Búsqueda global** (archivos + KB + Outlook):
   ```bash
   python file_search.py "texto a buscar"
   ```

2. **Solo archivos en disco**:
   ```bash
   python file_search.py "texto" --files-only
   python file_search.py "texto" --ext .pdf .docx
   python file_search.py "texto" --open
   ```

3. **Solo base de conocimiento**:
   ```bash
   python knowledge_base.py cross-search --query "texto"
   python knowledge_base.py export --query "texto"
   ```

4. **Solo correos**:
   ```bash
   python outlook_bridge.py search-body "texto" --open
   ```

## Para abrir el documento encontrado
- Archivos: `python file_search.py "texto" --open`
- Correos: `python outlook_bridge.py search-body "texto" --open`
- Ambos buscan y abren el primer resultado

## Rutas que se escanean
- `C:\Chance1\Clientes\` — Proyectos por cliente
- `C:\Chance1\Asistente IA\fuentes\` — Documentos organizados
- Base de conocimiento local (13 dominios)
- Outlook (bandeja de entrada + enviados)
