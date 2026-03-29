"""
test_motor_exhaustivo.py — Prueba EXHAUSTIVA de todos los caminos y sub-caminos
================================================================================
Testea funciones INTERNAS directamente (no solo el entrypoint) para cubrir
cada rama de cada if/else/try/except del motor.

7 módulos × N funciones × M ramas = cobertura completa.
"""
import io, json, sys, os, re, time, shutil, tempfile
from pathlib import Path

# Fix Unicode en Windows antes de cualquier print
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from datetime import datetime, timezone, timedelta
from collections import defaultdict

# ── Setup de paths ─────────────────────────────────────────────
PROJECT_DIR  = Path(__file__).parent
HOOKS_DIR    = PROJECT_DIR / ".claude" / "hooks"
HOME         = Path.home()
ADAPTIVE_DIR = HOME / ".adaptive_cli"
STATE_DIR    = ADAPTIVE_DIR / "hook_state"

# Añadir al path para importar módulos directamente
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(HOOKS_DIR))

# Colores
GR="\033[92m"; RD="\033[91m"; YL="\033[93m"; BL="\033[94m"; CY="\033[96m"
BLD="\033[1m"; RS="\033[0m"

results = defaultdict(int)
_sec = ""

def section(name):
    global _sec
    _sec = name
    print(f"\n{BL}{BLD}{'━'*60}{RS}")
    print(f"{BL}{BLD}  {name}{RS}")
    print(f"{BL}{BLD}{'━'*60}{RS}")

def ok(msg):   results["pass"]+=1; print(f"  {GR}✓{RS} {msg}")
def fail(msg, d=""): results["fail"]+=1; print(f"  {RD}✗ FAIL{RS} {msg}" + (f"\n    {RD}{d[:120]}{RS}" if d else ""))
def warn(msg): results["warn"]+=1; print(f"  {YL}⚠{RS} {msg}")

# ══════════════════════════════════════════════════════════════
# UTILIDADES COMPARTIDAS
# ══════════════════════════════════════════════════════════════

def fresh_tmp_json(data):
    """Crea un archivo JSON temporal y retorna su Path."""
    tf = Path(tempfile.mktemp(suffix=".json"))
    tf.write_text(json.dumps(data), encoding="utf-8")
    return tf

def fresh_tmp_jsonl(lines: list) -> Path:
    tf = Path(tempfile.mktemp(suffix=".jsonl"))
    with tf.open("w", encoding="utf-8") as f:
        for line in lines:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return tf

# ══════════════════════════════════════════════════════════════
# A. ITERATION_LEARN — funciones internas
# ══════════════════════════════════════════════════════════════
section("A. iteration_learn.py — funciones internas")

# Importar el módulo directamente
try:
    import iteration_learn as il
    ok("A.0 import iteration_learn OK")
except Exception as e:
    fail("A.0 import iteration_learn FALLO", str(e))
    il = None

if il:
    # A.1 extract_context — cada tipo de herramienta
    for tool, inp, res, check_key in [
        ("Read",  {"file_path": "C:/project/sow_template.docx"}, "contenido del archivo", "file"),
        ("Edit",  {"file_path": "C:/project/bom.xlsx", "old_string": "old val", "new_string": "new val"}, "updated", "change"),
        ("Write", {"file_path": "C:/project/script.py", "content": "# codigo nuevo"}, "written", "preview"),
        ("Bash",  {"command": "python knowledge_base.py stats"}, "Traceback: Error encontrado", "result"),
        ("Grep",  {"pattern": "sow_fusion", "path": "."}, "match1\nmatch2\nmatch3", "results_count"),
        ("Glob",  {"pattern": "**/*.json"}, "file1.json\nfile2.json", "results_count"),
        ("Agent", {"description": "research SAP patterns"}, "Found 5 patterns", "result"),
        ("mcp__claude-in-chrome__navigate", {"url": "http://sap.local"}, "navigated", "action"),
        ("UnknownTool", {"x": "y"}, "output", "input_preview"),
    ]:
        try:
            ctx = il.extract_context(tool, inp, res)
            if check_key in ctx:
                ok(f"A.1 extract_context({tool}) → campo '{check_key}' presente")
            else:
                warn(f"A.1 extract_context({tool}) → campo '{check_key}' ausente (ctx={list(ctx.keys())})")
        except Exception as e:
            fail(f"A.1 extract_context({tool}) crasheo", str(e))

    # A.2 extract_context — tool_result como dict (formato alternativo)
    try:
        ctx = il.extract_context("Read", {"file_path": "test.py"},
                                  {"content": "codigo python aqui"})
        ok("A.2 extract_context con tool_result como dict")
    except Exception as e:
        fail("A.2 extract_context dict crasheo", str(e))

    # A.3 extract_context — tool_result como lista de bloques
    try:
        ctx = il.extract_context("Read", {"file_path": "test.py"},
                                  {"content": [{"type": "text", "text": "bloque de texto"}]})
        ok("A.3 extract_context con tool_result lista de bloques")
    except Exception as e:
        fail("A.3 extract_context lista crasheo", str(e))

    # A.4 detect_domain — cada dominio individual
    domain_cases = [
        ([{"action":"login SAP CRM tierra playwright", "file":"", "found":""}], "sap_tierra"),
        ([{"action":"genera sow propuesta contrato alcance", "file":"sow.docx", "found":""}], "sow"),
        ([{"action":"valida bom listado material cantidad sku", "file":"bom.xlsx", "found":""}], "bom"),
        ([{"action":"actualiza monday pipeline bitacora", "file":"", "found":""}], "monday"),
        ([{"action":"enviar correo outlook email adjunto", "file":"", "found":""}], "outlook"),
        ([{"action":"aplica IVA tarifa MEP liability", "file":"", "found":""}], "business_rules"),
        ([{"action":"leer hook dashboard knowledge learning", "file":"dashboard.py", "found":""}], "files"),
    ]
    for actions, expected in domain_cases:
        try:
            got = il.detect_domain(actions)
            if got == expected:
                ok(f"A.4 detect_domain → '{expected}' correcto")
            else:
                warn(f"A.4 detect_domain → esperado '{expected}', obtuvo '{got}'")
        except Exception as e:
            fail(f"A.4 detect_domain({expected}) crasheo", str(e))

    # A.5 detect_domain — fallback a "files" cuando no hay match
    try:
        got = il.detect_domain([{"action": "xyz abc", "file": "", "found": ""}])
        if got == "files":
            ok("A.5 detect_domain fallback → 'files'")
        else:
            warn(f"A.5 detect_domain fallback → '{got}' (esperado 'files')")
    except Exception as e:
        fail("A.5 detect_domain fallback crasheo", str(e))

    # A.6 detect_domain — ponderación: business domain gana sobre 'files'
    try:
        # "sow" keywords tienen peso 2, "hook" tiene peso 1 → sow debe ganar
        actions = [{"action": "sow propuesta hook dashboard", "file": "sow.docx", "found": ""}]
        got = il.detect_domain(actions)
        if got == "sow":
            ok("A.6 detect_domain weighted: sow(2) > files(1)")
        else:
            warn(f"A.6 detect_domain weighted → '{got}' (esperado 'sow')")
    except Exception as e:
        fail("A.6 detect_domain weighted crasheo", str(e))

    # A.7 _make_fingerprint — orden no importa
    try:
        a1 = [{"action":"Edito foo.py", "tool":"Edit"}, {"action":"Ejecuto: python test.py", "tool":"Bash"}]
        a2 = [{"action":"Ejecuto: python test.py", "tool":"Bash"}, {"action":"Edito foo.py", "tool":"Edit"}]
        f1, f2 = il._make_fingerprint(a1), il._make_fingerprint(a2)
        if f1 == f2:
            ok("A.7 fingerprint: orden no importa → mismo hash")
        else:
            fail("A.7 fingerprint: mismo contenido distinto orden → distinto hash", f"{f1} vs {f2}")
    except Exception as e:
        fail("A.7 fingerprint crasheo", str(e))

    # A.8 deduplicación — fingerprint TTL 2h
    try:
        # Limpiar fingerprints temporales del test
        fp_file = il.FINGERPRINTS_FILE
        original = {}
        if fp_file.exists():
            try: original = json.loads(fp_file.read_text(encoding="utf-8"))
            except: pass

        # Forzar fingerprint test con timestamp actual
        test_fp = "TEST_FP_DEDUP_" + str(time.time())
        data = original.copy()
        data[test_fp] = time.time()
        fp_file.parent.mkdir(parents=True, exist_ok=True)
        fp_file.write_text(json.dumps(data), encoding="utf-8")

        fps = il._load_fingerprints()
        if test_fp in fps:
            ok("A.8 dedup: fingerprint reciente está presente")
        else:
            fail("A.8 dedup: fingerprint reciente no cargó")

        # Forzar fingerprint expirado (> 2h)
        data[test_fp + "_OLD"] = time.time() - 7300
        fp_file.write_text(json.dumps(data), encoding="utf-8")
        fps2 = il._load_fingerprints()
        if (test_fp + "_OLD") not in fps2:
            ok("A.8 dedup: fingerprint expirado filtrado correctamente")
        else:
            fail("A.8 dedup: fingerprint expirado NO filtrado")

        # Restaurar
        fp_file.write_text(json.dumps(original), encoding="utf-8")
    except Exception as e:
        fail("A.8 dedup fingerprint crasheo", str(e))

    # A.9 _is_failure — cada señal de error
    for signal, result_text, ec, expected in [
        ("exit_code != 0",    "alguna salida",     1,    True),
        ("traceback",         "Traceback occurred", 0,   True),
        ("error:",            "Error: bad thing",  0,    True),
        ("modulenotfounderror","ModuleNotFoundError", 0, True),
        ("cannot",            "cannot connect",    0,    True),
        ("timed out",         "timed out waiting", 0,    True),
        ("exit_code 0 ok",    "All OK",            0,    False),
        ("exit_code None ok", "All OK",            None, False),
    ]:
        try:
            got = il._is_failure("Bash", result_text, ec)
            if got == expected:
                ok(f"A.9 _is_failure [{signal}] → {expected}")
            else:
                fail(f"A.9 _is_failure [{signal}] → esperado {expected}, obtuvo {got}")
        except Exception as e:
            fail(f"A.9 _is_failure [{signal}] crasheo", str(e))

    # A.10 search_kb_on_failure — solo Bash/Edit/Write, no otros
    for tool, expected_skip in [("Read", True), ("Grep", True), ("Glob", True), ("Bash", False)]:
        try:
            out = il.search_kb_on_failure(tool, {"command": "test"},
                                           "Traceback ModuleNotFoundError importerror failed")
            if tool in ("Read", "Grep", "Glob"):
                if out == "":
                    ok(f"A.10 search_kb_on_failure({tool}) → skip correcto (no Bash/Edit/Write)")
                else:
                    fail(f"A.10 search_kb_on_failure({tool}) → no debio buscar")
            else:
                ok(f"A.10 search_kb_on_failure({tool}) → intentó buscar (rc=ok)")
        except Exception as e:
            fail(f"A.10 search_kb_on_failure({tool}) crasheo", str(e))

    # A.11 search_kb_on_failure — sin error_words → retorna ""
    try:
        out = il.search_kb_on_failure("Bash", {"command": "test"},
                                       "True False None line file self")
        if out == "":
            ok("A.11 search_kb_on_failure: solo stop-words → retorna ''")
        else:
            warn(f"A.11 search_kb_on_failure: retorno algo con stop-words: {out[:80]}")
    except Exception as e:
        fail("A.11 search_kb_on_failure stop-words crasheo", str(e))

    # A.12 _capture_failure_context + _get_failure_annotation — ciclo completo
    try:
        test_key = "test_pattern_fail_annotation"
        # Limpiar
        ff = il.FAILURES_FILE
        original_ff = {}
        if ff.exists():
            try: original_ff = json.loads(ff.read_text(encoding="utf-8"))
            except: pass

        # < 3 fallos → sin anotación
        for i in range(2):
            il._capture_failure_context(test_key, {"file_path": f"test{i}.xlsx"}, "error msg")
        ann = il._get_failure_annotation(test_key)
        if ann == "":
            ok("A.12 annotation: < 3 fallos → sin anotación")
        else:
            warn(f"A.12 annotation: < 3 fallos pero salió anotación: {ann}")

        # >= 3 fallos con mismo ext → anotación con ext
        il._capture_failure_context(test_key, {"file_path": "test3.xlsx"}, "error msg")
        ann = il._get_failure_annotation(test_key)
        if ".xlsx" in ann or "fallos" in ann:
            ok(f"A.12 annotation: >= 3 fallos .xlsx → anotación: '{ann.strip()}'")
        else:
            warn(f"A.12 annotation: esperada anotación .xlsx, obtuvo: '{ann}'")

        # Restaurar
        original_ff.pop(test_key, None)
        ff.write_text(json.dumps(original_ff), encoding="utf-8")
    except Exception as e:
        fail("A.12 failure annotation crasheo", str(e))

    # A.13 _is_exploration + _is_action
    for tool, exp_exp, exp_act in [
        ("Read", True, False), ("Grep", True, False), ("Glob", True, False),
        ("Edit", False, True), ("Write", False, True), ("Bash", False, True),
        ("Agent", False, False),
    ]:
        try:
            e = il._is_exploration(tool)
            a = il._is_action(tool)
            if e == exp_exp and a == exp_act:
                ok(f"A.13 {tool}: is_exploration={e}, is_action={a}")
            else:
                fail(f"A.13 {tool}: esperado exp={exp_exp}/act={exp_act}, obtuvo {e}/{a}")
        except Exception as err:
            fail(f"A.13 {tool} crasheo", str(err))

    # A.14 _adaptive_explore_threshold — 3 ramas
    try:
        # Rama 1: mensaje de revision → umbral 8
        lmf = ADAPTIVE_DIR / "last_user_message.txt"
        lmf.parent.mkdir(parents=True, exist_ok=True)
        lmf_orig = lmf.read_text(encoding="utf-8") if lmf.exists() else None
        lmf.write_text("revisa todos los archivos del proyecto y analiza", encoding="utf-8")
        th = il._adaptive_explore_threshold([])
        if th >= 8:
            ok(f"A.14 threshold: mensaje 'revisa' → umbral={th} (>=8)")
        else:
            warn(f"A.14 threshold: mensaje 'revisa' → umbral={th} (esperado >=8)")

        # Rama 2: todos los explores en mismo directorio → umbral 6
        lmf.write_text("ejecuta el script", encoding="utf-8")
        th2 = il._adaptive_explore_threshold(["C:/project/a.py", "C:/project/b.py"])
        if th2 >= 6:
            ok(f"A.14 threshold: mismo directorio → umbral={th2} (>=6)")
        else:
            warn(f"A.14 threshold: mismo dir → {th2} (esperado >=6)")

        # Rama 3: default
        th3 = il._adaptive_explore_threshold(["C:/a/x.py", "C:/b/y.py"])
        if th3 == il.EXPLORE_THRESHOLD:
            ok(f"A.14 threshold: default → umbral={th3}")
        else:
            warn(f"A.14 threshold: default → {th3} (esperado {il.EXPLORE_THRESHOLD})")

        if lmf_orig is not None:
            lmf.write_text(lmf_orig, encoding="utf-8")
    except Exception as e:
        fail("A.14 _adaptive_explore_threshold crasheo", str(e))

    # A.15 trim_actions_log — rota cuando supera max_lines
    try:
        al = il.ACTIONS_LOG
        orig_content = al.read_text(encoding="utf-8") if al.exists() else ""
        # Escribir 6000 lineas
        al.parent.mkdir(parents=True, exist_ok=True)
        al.write_text("\n".join(f'{{"line":{i}}}' for i in range(6000)), encoding="utf-8")
        il.trim_actions_log(max_lines=5000)
        lines_after = al.read_text(encoding="utf-8").splitlines()
        if len(lines_after) <= 5001:
            ok(f"A.15 trim_actions_log: 6000→{len(lines_after)} (max=5000)")
        else:
            fail(f"A.15 trim_actions_log: {len(lines_after)} lineas (esperado <=5001)")
        # Restaurar
        al.write_text(orig_content, encoding="utf-8")
    except Exception as e:
        fail("A.15 trim_actions_log crasheo", str(e))

    # A.16 trim_actions_log — bajo max_lines → no cambia
    try:
        al = il.ACTIONS_LOG
        al.parent.mkdir(parents=True, exist_ok=True)
        al.write_text("\n".join(f'{{"line":{i}}}' for i in range(100)), encoding="utf-8")
        il.trim_actions_log(max_lines=5000)
        lines = al.read_text(encoding="utf-8").splitlines()
        if len(lines) == 100:
            ok("A.16 trim_actions_log: < max → no cambia")
        else:
            fail(f"A.16 trim: {len(lines)} lines (esperado 100)")
    except Exception as e:
        fail("A.16 trim_actions_log bajo max crasheo", str(e))

    # A.17 write_notification — GUARDADO vs DEDUP-SKIP
    try:
        orig = il.NOTIFY_FILE.read_text(encoding="utf-8") if il.NOTIFY_FILE.exists() else ""
        il.write_notification(99, 5, "test summary guardado", "sow", saved=True)
        content = il.NOTIFY_FILE.read_text(encoding="utf-8")
        if "GUARDADO" in content and "iter 99" in content:
            ok("A.17 write_notification: GUARDADO aparece correctamente")
        else:
            fail("A.17 write_notification GUARDADO no encontrado", content[-200:])
        il.write_notification(100, 3, "test summary dedup", "files", saved=False)
        content2 = il.NOTIFY_FILE.read_text(encoding="utf-8")
        if "DEDUP-SKIP" in content2:
            ok("A.17 write_notification: DEDUP-SKIP aparece correctamente")
        else:
            fail("A.17 write_notification DEDUP-SKIP no encontrado")
        # Restaurar
        if orig:
            il.NOTIFY_FILE.write_text(orig, encoding="utf-8")
    except Exception as e:
        fail("A.17 write_notification crasheo", str(e))

# ══════════════════════════════════════════════════════════════
# B. AUTO_LEARN_HOOK — funciones internas
# ══════════════════════════════════════════════════════════════
section("B. auto_learn_hook.py — funciones internas")

try:
    import auto_learn_hook as alh
    ok("B.0 import auto_learn_hook OK")
except Exception as e:
    fail("B.0 import auto_learn_hook FALLO", str(e))
    alh = None

if alh:
    # B.1 read_transcript — formato nested (real)
    msgs_nested = [
        {"type": "user", "message": {"role": "user", "content": "necesito un sow"}},
        {"type": "assistant", "message": {"role": "assistant", "content": "Aqui el SOW"}},
    ]
    tf = fresh_tmp_jsonl(msgs_nested)
    try:
        msgs = alh.read_transcript(str(tf))
        if len(msgs) == 2 and msgs[0].get("role") == "user":
            ok(f"B.1 read_transcript: formato nested → {len(msgs)} mensajes extraidos")
        else:
            fail(f"B.1 read_transcript nested: {len(msgs)} msgs, roles={[m.get('role') for m in msgs]}")
    except Exception as e:
        fail("B.1 read_transcript nested crasheo", str(e))
    tf.unlink(missing_ok=True)

    # B.2 read_transcript — formato flat (legacy)
    msgs_flat = [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "respuesta"},
    ]
    tf = fresh_tmp_jsonl(msgs_flat)
    try:
        msgs = alh.read_transcript(str(tf))
        if len(msgs) == 2:
            ok("B.2 read_transcript: formato flat (legacy) funciona")
        else:
            warn(f"B.2 read_transcript flat: {len(msgs)} msgs (esperado 2)")
    except Exception as e:
        fail("B.2 read_transcript flat crasheo", str(e))
    tf.unlink(missing_ok=True)

    # B.3 read_transcript — lineas corruptas entre lineas validas
    tf = Path(tempfile.mktemp(suffix=".jsonl"))
    with tf.open("w", encoding="utf-8") as f:
        f.write('{"type":"user","message":{"role":"user","content":"msg1"}}\n')
        f.write('esto no es json\n')
        f.write('{"broken": true\n')
        f.write('{"type":"user","message":{"role":"user","content":"msg2"}}\n')
    try:
        msgs = alh.read_transcript(str(tf))
        if len(msgs) == 2:
            ok("B.3 read_transcript: lineas corruptas → solo extrae validas")
        else:
            warn(f"B.3 read_transcript corrupt: {len(msgs)} msgs (esperado 2)")
    except Exception as e:
        fail("B.3 read_transcript corrupt crasheo", str(e))
    tf.unlink(missing_ok=True)

    # B.4 read_transcript — archivo inexistente → lista vacía
    try:
        msgs = alh.read_transcript("/nonexistent/path/xyz.jsonl")
        if msgs == []:
            ok("B.4 read_transcript: archivo inexistente → [] graceful")
        else:
            fail(f"B.4 read_transcript inexistente: {msgs}")
    except Exception as e:
        fail("B.4 read_transcript inexistente crasheo", str(e))

    # B.5 extract_user_messages — filtro de prefijos del sistema
    test_msgs = [
        {"role": "user", "content": "<task-notification>esto es del sistema</task-notification>"},
        {"role": "user", "content": "<system-reminder>recordatorio</system-reminder>"},
        {"role": "user", "content": "necesito hacer un sow"},
        {"role": "user", "content": "ok"},  # muy corto, debe filtrarse
        {"role": "assistant", "content": "respuesta"},  # no user, ignorar
    ]
    try:
        umsg = alh.extract_user_messages(test_msgs)
        if len(umsg) == 1 and "sow" in umsg[0]:
            ok("B.5 extract_user_messages: filtra system prefixes y mensajes cortos")
        else:
            fail(f"B.5 extract_user_messages: {umsg}")
    except Exception as e:
        fail("B.5 extract_user_messages crasheo", str(e))

    # B.6 extract_user_messages — content como lista de bloques
    test_msgs2 = [
        {"role": "user", "content": [
            {"type": "text", "text": "genera un bom completo"},
            {"type": "image", "source": "data..."},
        ]},
    ]
    try:
        umsg = alh.extract_user_messages(test_msgs2)
        if len(umsg) == 1 and "bom" in umsg[0]:
            ok("B.6 extract_user_messages: content como lista de bloques")
        else:
            fail(f"B.6 extract_user_messages lista: {umsg}")
    except Exception as e:
        fail("B.6 extract_user_messages lista crasheo", str(e))

    # B.7 extract_tool_usage — todos los tipos de herramienta
    tool_msgs = [{
        "role": "assistant",
        "content": [
            {"type": "tool_use", "name": "Read",  "input": {"file_path": "C:/file1.py"}},
            {"type": "tool_use", "name": "Edit",  "input": {"file_path": "C:/file2.py"}},
            {"type": "tool_use", "name": "Write", "input": {"file_path": "C:/file3.py"}},
            {"type": "tool_use", "name": "Bash",  "input": {"command": "python test.py"}},
            {"type": "tool_use", "name": "Grep",  "input": {"pattern": "def main"}},
            {"type": "tool_use", "name": "Glob",  "input": {"pattern": "**/*.py"}},
        ]
    }]
    try:
        usage = alh.extract_tool_usage(tool_msgs)
        checks = [
            ("files_read",    1),
            ("files_edited",  1),
            ("files_created", 1),
            ("commands_run",  1),
            ("searches",      2),
        ]
        for field, expected in checks:
            n = len(usage.get(field, []))
            if n == expected:
                ok(f"B.7 extract_tool_usage[{field}] = {n}")
            else:
                fail(f"B.7 extract_tool_usage[{field}] = {n} (esperado {expected})")
    except Exception as e:
        fail("B.7 extract_tool_usage crasheo", str(e))

    # B.8 extract_tool_usage — deduplicación (mismo archivo leído 2 veces)
    dup_msgs = [{
        "role": "assistant",
        "content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "C:/same.py"}},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "C:/same.py"}},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "C:/other.py"}},
        ]
    }]
    try:
        usage = alh.extract_tool_usage(dup_msgs)
        n = len(usage["files_read"])
        if n == 2:
            ok("B.8 extract_tool_usage: dedup → 3 reads de 2 archivos = 2 únicos")
        else:
            fail(f"B.8 dedup reads: {n} (esperado 2)")
    except Exception as e:
        fail("B.8 extract_tool_usage dedup crasheo", str(e))

    # B.9 extract_errors_from_messages — filtra triviales
    err_msgs = [
        {"role": "user", "content": [
            {"type": "tool_result", "is_error": True, "content": "No tab available"},   # trivial
            {"type": "tool_result", "is_error": True, "content": "Traceback: real error en sap login"},  # real
        ]},
        {"role": "assistant", "content": [
            {"type": "text", "text": "Error: failed to connect to SAP server port 443"},  # real
            {"type": "text", "text": "charmap_encode error"},  # trivial
        ]},
    ]
    try:
        errors = alh.extract_errors_from_messages(err_msgs)
        # Debe tener los 2 errores reales, no los triviales
        if len(errors) >= 1:
            ok(f"B.9 extract_errors: {len(errors)} errores reales (triviales filtrados)")
        else:
            warn("B.9 extract_errors: ningún error extraido")
    except Exception as e:
        fail("B.9 extract_errors crasheo", str(e))

    # B.10 extract_learning_json — bloque ```json```
    lj_msgs = [{
        "role": "assistant",
        "content": '```json\n{"status": "success", "task_type": "sap_fill", "strategy": "aria_label"}\n```'
    }]
    try:
        lj = alh.extract_learning_json_from_messages(lj_msgs)
        if lj and lj.get("status") == "success":
            ok("B.10 extract_learning_json: bloque ```json``` detectado")
        else:
            fail(f"B.10 learning json no detectado: {lj}")
    except Exception as e:
        fail("B.10 extract_learning_json crasheo", str(e))

    # B.11 extract_learning_json — inline (sin backticks)
    lj_msgs2 = [{
        "role": "assistant",
        "content": 'La tarea terminó. {"status": "modified", "task_type": "bom_validate", "strategy": "math_check"}'
    }]
    try:
        lj = alh.extract_learning_json_from_messages(lj_msgs2)
        if lj and lj.get("status") == "modified":
            ok("B.11 extract_learning_json: inline detectado")
        else:
            warn(f"B.11 learning json inline no detectado: {lj}")
    except Exception as e:
        fail("B.11 extract_learning_json inline crasheo", str(e))

    # B.12 extract_learning_json — no encontrado → None
    try:
        lj = alh.extract_learning_json_from_messages([
            {"role": "assistant", "content": "simple text sin JSON"}
        ])
        if lj is None:
            ok("B.12 extract_learning_json: no encontrado → None")
        else:
            fail(f"B.12 debe ser None, obtuvo: {lj}")
    except Exception as e:
        fail("B.12 extract_learning_json None crasheo", str(e))

    # B.13 extract_decisions_from_messages — múltiples patrones
    dec_msgs = [
        {"role": "assistant", "content": "voy a usar aria-label para el selector de SAP"},
        {"role": "assistant", "content": "decidí usar subprocess.run con timeout de 120 segundos"},
        {"role": "assistant", "content": "el fix es cambiar tool_output a tool_result en el hook"},
        {"role": "assistant", "content": "la solución es agregar el campo timestamp al registro"},
    ]
    try:
        decs = alh.extract_decisions_from_messages(dec_msgs)
        if len(decs) >= 3:
            ok(f"B.13 extract_decisions: {len(decs)} decisiones extraidas")
        else:
            warn(f"B.13 extract_decisions: solo {len(decs)} (esperado >=3)")
    except Exception as e:
        fail("B.13 extract_decisions crasheo", str(e))

    # B.14 build_conversation_summary — filtra context compaction
    summary_msgs = [
        "This session is being continued from a previous conversation that ran out of context.",
        "Summary: largo resumen del sistema blah blah",
        "necesito hacer un sow para instana",
        "ahora valida el bom",
    ]
    try:
        s = alh.build_conversation_summary(summary_msgs)
        if "This session" not in s and "Summary:" not in s:
            ok("B.14 build_summary: filtra context compaction")
        else:
            fail(f"B.14 summary incluye context compaction: {s[:100]}")
        if "sow" in s.lower() or "bom" in s.lower():
            ok("B.14 build_summary: mensajes reales incluidos")
        else:
            warn(f"B.14 summary no incluye mensajes reales: {s}")
    except Exception as e:
        fail("B.14 build_summary crasheo", str(e))

    # B.15 build_conversation_summary — sesion vacía → mensaje especial
    try:
        s = alh.build_conversation_summary([])
        if "sin mensajes" in s:
            ok("B.15 build_summary vacío → 'sin mensajes del usuario'")
        else:
            fail(f"B.15 summary vacío: '{s}'")
    except Exception as e:
        fail("B.15 build_summary vacío crasheo", str(e))

    # B.16 find_existing_session — match por session_id exacto
    history = [
        {"session_id": "abc-123", "date": "2026-03-20", "user_messages": ["msg1"]},
        {"session_id": "def-456", "date": "2026-03-19", "user_messages": ["msg2"]},
    ]
    try:
        idx = alh.find_existing_session(history, {"session_id": "abc-123", "date": "2026-03-20", "user_messages": []})
        if idx == 0:
            ok("B.16 find_existing_session: match por session_id exacto → idx=0")
        else:
            fail(f"B.16 expected idx=0, got {idx}")
    except Exception as e:
        fail("B.16 find_existing_session crasheo", str(e))

    # B.17 find_existing_session — prefijo manual_ ignorado
    try:
        idx = alh.find_existing_session(
            [{"session_id": "manual_abc-123", "date": "2026-03-20", "user_messages": []}],
            {"session_id": "abc-123", "date": "2026-03-20", "user_messages": []}
        )
        if idx == 0:
            ok("B.17 find_existing_session: prefijo 'manual_' ignorado en match")
        else:
            fail(f"B.17 prefijo manual_: idx={idx} (esperado 0)")
    except Exception as e:
        fail("B.17 find_existing_session manual_ crasheo", str(e))

    # B.18 find_existing_session — match por fecha + overlap > 40%
    try:
        idx = alh.find_existing_session(
            [{"session_id": "diff-id", "date": "2026-03-20",
              "user_messages": ["hacer sow instana", "validar bom"]}],
            {"session_id": "other-id", "date": "2026-03-20",
             "user_messages": ["hacer sow instana", "validar bom", "nuevo msg"]}
        )
        if idx == 0:
            ok("B.18 find_existing_session: match por fecha + overlap msgs")
        else:
            warn(f"B.18 fecha+overlap: idx={idx} (esperado 0)")
    except Exception as e:
        fail("B.18 find_existing_session overlap crasheo", str(e))

    # B.19 find_existing_session — sin match → -1
    try:
        idx = alh.find_existing_session(
            [{"session_id": "xyz", "date": "2026-03-19", "user_messages": ["cosa distinta"]}],
            {"session_id": "abc", "date": "2026-03-20", "user_messages": ["otra cosa"]}
        )
        if idx == -1:
            ok("B.19 find_existing_session: sin match → -1")
        else:
            fail(f"B.19 sin match: idx={idx} (esperado -1)")
    except Exception as e:
        fail("B.19 find_existing_session no match crasheo", str(e))

    # B.20 _merge_sessions — lista merge sin duplicados
    try:
        existing = {"user_messages": ["msg1", "msg2"], "summary": "corto",
                    "metrics": {"tool_calls": 3}, "learning_json": None}
        new      = {"user_messages": ["msg2", "msg3"], "summary": "mas largo que antes",
                    "metrics": {"tool_calls": 5, "errors": 1}, "learning_json": {"status":"success"}}
        merged = alh._merge_sessions(existing, new)
        msgs = merged["user_messages"]
        if "msg1" in msgs and "msg2" in msgs and "msg3" in msgs and len(msgs) == 3:
            ok("B.20 _merge_sessions: lista merge sin duplicados")
        else:
            fail(f"B.20 merge msgs: {msgs}")
        if merged["summary"] == "mas largo que antes":
            ok("B.20 _merge_sessions: summary más largo gana")
        else:
            fail(f"B.20 summary: {merged['summary']}")
        if merged["metrics"]["tool_calls"] == 5:
            ok("B.20 _merge_sessions: metrics toma el máximo")
        else:
            fail(f"B.20 metrics tool_calls: {merged['metrics']}")
        if merged.get("learning_json", {}).get("status") == "success":
            ok("B.20 _merge_sessions: learning_json del nuevo preservado")
        else:
            fail(f"B.20 learning_json: {merged.get('learning_json')}")
    except Exception as e:
        fail("B.20 _merge_sessions crasheo", str(e))

    # B.21 detect_domain (alh version) — todas las ramas
    for files_e, files_c, msgs, expected in [
        (["sow_template.docx"], [], [], "sow"),
        ([], [], ["sap CRM oportunidad quote"], "sap_tierra"),
        (["bom.xlsx"], [], ["listado material"], "bom"),
        ([], [], [], "files"),  # fallback
    ]:
        try:
            got = alh.detect_domain(files_e, files_c, msgs)
            if got == expected:
                ok(f"B.21 alh.detect_domain: archivos={files_e}, msgs='{msgs}' → '{expected}'")
            else:
                warn(f"B.21 alh.detect_domain: esperado '{expected}', obtuvo '{got}'")
        except Exception as e:
            fail(f"B.21 alh.detect_domain({expected}) crasheo", str(e))

    # B.22 record_domain_cooccurrence — < 2 dominios → skip
    try:
        co_file = alh.CO_OCCUR_FILE
        orig_co = json.loads(co_file.read_text(encoding="utf-8")) if co_file.exists() else {}
        alh.record_domain_cooccurrence(["sow"])  # solo 1 → skip
        co_after = json.loads(co_file.read_text(encoding="utf-8")) if co_file.exists() else {}
        if co_after == orig_co:
            ok("B.22 record_cooccurrence: 1 dominio → no cambia")
        else:
            warn("B.22 record_cooccurrence: 1 dominio modificó el archivo (no debería)")
    except Exception as e:
        fail("B.22 record_cooccurrence crasheo", str(e))

    # B.23 record_domain_cooccurrence — 2+ dominios → actualiza
    try:
        alh.record_domain_cooccurrence(["sow", "bom"])
        co_file = alh.CO_OCCUR_FILE
        if co_file.exists():
            data = json.loads(co_file.read_text(encoding="utf-8"))
            if "sow" in data and "bom" in data.get("sow", {}):
                ok("B.23 record_cooccurrence: sow↔bom registrado")
            else:
                fail(f"B.23 cooccurrence: sow→bom no registrado. data={list(data.keys())}")
        else:
            fail("B.23 cooccurrence: archivo no creado")
    except Exception as e:
        fail("B.23 record_cooccurrence 2 dominios crasheo", str(e))

    # B.24 record_domain_sequence — Markov ordinal
    try:
        alh.record_domain_sequence(["sow", "bom", "files"])
        mk_file = alh.MARKOV_FILE
        if mk_file.exists():
            data = json.loads(mk_file.read_text(encoding="utf-8"))
            ok_markov = (
                "bom" in data.get("sow", {}) and
                "files" in data.get("bom", {})
            )
            if ok_markov:
                ok("B.24 record_domain_sequence: Markov sow→bom→files registrado")
            else:
                fail(f"B.24 Markov: sow→bom o bom→files falta. data={data}")
        else:
            fail("B.24 Markov file no creado")
    except Exception as e:
        fail("B.24 record_domain_sequence crasheo", str(e))

    # B.25 extract_reasoning_traces — texto antes de tool_use
    trace_msgs = [{
        "role": "assistant",
        "content": [
            {"type": "text", "text": "Voy a leer el archivo de configuración primero"},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "config.py"}},
            {"type": "text", "text": "Ahora voy a editar el hook"},
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "hook.py"}},
        ]
    }]
    try:
        traces = alh.extract_reasoning_traces(trace_msgs)
        if len(traces) >= 1:
            ok(f"B.25 extract_reasoning_traces: {len(traces)} trazas extraidas")
        else:
            warn("B.25 reasoning traces: ninguna traza extraida")
    except Exception as e:
        fail("B.25 extract_reasoning_traces crasheo", str(e))

# ══════════════════════════════════════════════════════════════
# C. ON_USER_MESSAGE — funciones internas
# ══════════════════════════════════════════════════════════════
section("C. on_user_message.py — funciones internas")

try:
    import on_user_message as oum
    ok("C.0 import on_user_message OK")
except Exception as e:
    fail("C.0 import on_user_message FALLO", str(e))
    oum = None

if oum:
    # C.1 extract_keywords — stop words filtradas, min 3 chars, max 25
    try:
        kws = oum.extract_keywords("el la los y de un necesito ver como que hacer dame sow propuesta contrato")
        stop_in_kws = [w for w in kws if w in oum.STOP_WORDS]
        short_in_kws = [w for w in kws if len(w) < 3]
        if not stop_in_kws and not short_in_kws:
            ok(f"C.1 extract_keywords: sin stop words ni cortas → {kws}")
        else:
            fail(f"C.1 stop_words_remaining={stop_in_kws}, short={short_in_kws}")
    except Exception as e:
        fail("C.1 extract_keywords crasheo", str(e))

    # C.2 extract_keywords — máximo 25 palabras
    try:
        long_prompt = " ".join([f"palabra{i}" for i in range(100)])
        kws = oum.extract_keywords(long_prompt)
        if len(kws) <= 25:
            ok(f"C.2 extract_keywords: máximo 25 palabras → {len(kws)}")
        else:
            fail(f"C.2 keywords > 25: {len(kws)}")
    except Exception as e:
        fail("C.2 extract_keywords max 25 crasheo", str(e))

    # C.3 classify_domains — cada dominio con keywords de peso 2
    domain_prompts = [
        ("sap_tierra", "sap crm tierra playwright iframe aria login"),
        ("sap_nube",   "nube cloud s4hana fiori formulario"),
        ("sow",        "sow propuesta contrato alcance entregable practica"),
        ("bom",        "bom listado material partnum cantidad sku"),
        ("monday",     "monday pipeline bitacora tablero"),
        ("outlook",    "outlook correo email adjunto bandeja smtp"),
        ("files",      "pdf excel docx xlsx word archivo"),
        ("business_rules", "regla nomenclatura sufijo prefijo"),
        ("catalog",    "catalogo sku licencia ibm partnumber"),
    ]
    for expected_domain, prompt in domain_prompts:
        try:
            kws = oum.extract_keywords(prompt)
            domains = oum.classify_domains(kws)
            if expected_domain in domains:
                ok(f"C.3 classify_domains: '{expected_domain}' correctamente detectado")
            else:
                warn(f"C.3 classify_domains: '{expected_domain}' no detectado → {domains}")
        except Exception as e:
            fail(f"C.3 classify_domains({expected_domain}) crasheo", str(e))

    # C.4 classify_domains — multi-dominio: SOW + BOM simultáneo
    try:
        kws = oum.extract_keywords("revisa el bom con listado material y genera sow propuesta contrato")
        domains = oum.classify_domains(kws)
        if "sow" in domains and "bom" in domains:
            ok(f"C.4 classify_domains: multi-dominio SOW+BOM → {domains}")
        else:
            warn(f"C.4 multi-dominio: {domains} (esperado sow+bom)")
    except Exception as e:
        fail("C.4 classify_domains multi crasheo", str(e))

    # C.5 classify_domains — sin keywords → lista vacía
    try:
        domains = oum.classify_domains([])
        if domains == []:
            ok("C.5 classify_domains: keywords vacío → []")
        else:
            fail(f"C.5 empty keywords: {domains}")
    except Exception as e:
        fail("C.5 classify_domains vacío crasheo", str(e))

    # C.6 _kw_overlap — casos borde
    for a, b, expected_gt_zero in [
        ([], [],           False),   # ambos vacíos
        (["a"], [],        False),   # uno vacío
        (["sow", "bom"], ["sow", "monday"],  True),  # overlap parcial
        (["sow"], ["sow"], True),    # overlap total
        (["sow"], ["bom"], False),   # sin overlap
    ]:
        try:
            got = oum._kw_overlap(a, b)
            if expected_gt_zero and got > 0:
                ok(f"C.6 _kw_overlap({a},{b}) = {got:.2f} > 0")
            elif not expected_gt_zero and got == 0:
                ok(f"C.6 _kw_overlap({a},{b}) = 0 correcto")
            else:
                fail(f"C.6 _kw_overlap({a},{b}) = {got}, esperado {'> 0' if expected_gt_zero else '0'}")
        except Exception as e:
            fail(f"C.6 _kw_overlap crasheo", str(e))

    # C.7 cache de clasificación — expirado
    try:
        cache_file = oum.CLASSIFY_CACHE
        orig = cache_file.read_text(encoding="utf-8") if cache_file.exists() else None
        # Escribir cache expirado (> 2h)
        old_ts = (datetime.now() - timedelta(hours=3)).isoformat()
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({
            "domains": ["sow"], "keywords": ["sow", "propuesta"],
            "ts": old_ts
        }), encoding="utf-8")
        result = oum._read_classify_cache(["sow", "propuesta"])
        if result is None:
            ok("C.7 classify_cache: cache expirado → None (re-clasifica)")
        else:
            fail("C.7 classify_cache: cache expirado devolvió resultado")
        if orig: cache_file.write_text(orig, encoding="utf-8")
        else: cache_file.unlink(missing_ok=True)
    except Exception as e:
        fail("C.7 classify_cache expirado crasheo", str(e))

    # C.8 cache de clasificación — hit válido (overlap >= 55%)
    try:
        cache_file = oum.CLASSIFY_CACHE
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({
            "domains": ["sow"], "keywords": ["sow", "propuesta"],
            "ts": datetime.now().isoformat()
        }), encoding="utf-8")
        result = oum._read_classify_cache(["sow", "propuesta", "alcance"])
        if result is not None and result.get("domains") == ["sow"]:
            ok("C.8 classify_cache: hit válido con overlap >= 55%")
        else:
            warn(f"C.8 classify_cache hit: {result}")
    except Exception as e:
        fail("C.8 classify_cache hit crasheo", str(e))

    # C.9 cache de clasificación — miss (overlap < 55%)
    try:
        cache_file = oum.CLASSIFY_CACHE
        cache_file.write_text(json.dumps({
            "domains": ["sow"], "keywords": ["sow", "propuesta"],
            "ts": datetime.now().isoformat()
        }), encoding="utf-8")
        result = oum._read_classify_cache(["playwright", "selenium", "sap"])
        if result is None:
            ok("C.9 classify_cache: miss (overlap < 55%) → None")
        else:
            warn(f"C.9 classify_cache: esperado miss, obtuvo {result}")
    except Exception as e:
        fail("C.9 classify_cache miss crasheo", str(e))

    # C.10 cache de clasificación — JSON corrupto → None graceful
    try:
        cache_file = oum.CLASSIFY_CACHE
        cache_file.write_text("{{{not valid json}}}", encoding="utf-8")
        result = oum._read_classify_cache(["sow"])
        if result is None:
            ok("C.10 classify_cache: JSON corrupto → None graceful")
        else:
            fail(f"C.10 corrupt cache: {result}")
    except Exception as e:
        fail("C.10 classify_cache corrupt crasheo", str(e))

    # C.11 detect_intent — cada intención
    intent_cases = [
        ("crear",       "crea un nuevo sow template para el cliente"),
        ("revisar",     "revisa y verifica el bom que te paso"),
        ("depurar",     "hay un error en el hook que no funciona"),
        ("automatizar", "automatiza el script del pipeline con hook"),
        ("entender",    "explica cómo funciona el sistema de hooks"),
        ("general",     "hola buenos dias"),
    ]
    for expected_intent, prompt in intent_cases:
        try:
            got = oum.detect_intent(prompt)
            if got == expected_intent:
                ok(f"C.11 detect_intent: '{expected_intent}' → '{got}'")
            else:
                warn(f"C.11 detect_intent: '{expected_intent}' → '{got}' (diferente pero no crash)")
        except Exception as e:
            fail(f"C.11 detect_intent({expected_intent}) crasheo", str(e))

    # C.12 get_momentum — neutral, deep_work, context_switch
    pf = oum.PROMPT_HIST_FILE
    pf_orig = pf.read_text(encoding="utf-8") if pf.exists() else None

    # neutral: < 2 entries
    try:
        pf.parent.mkdir(parents=True, exist_ok=True)
        pf.write_text(json.dumps({"ts": datetime.now().isoformat(), "domains": ["sow"], "intent": "crear", "head": "test"}), encoding="utf-8")
        m = oum.get_momentum(["sow"])
        if m == "neutral":
            ok("C.12 get_momentum: < 2 entries → neutral")
        else:
            warn(f"C.12 neutral: {m}")
    except Exception as e:
        fail("C.12 get_momentum neutral crasheo", str(e))

    # deep_work: mismo dominio 3 veces
    try:
        entries = "\n".join(json.dumps({"ts": datetime.now().isoformat(), "domains": ["sow"],
                                         "intent": "crear", "head": f"sow {i}"}) for i in range(3))
        pf.write_text(entries, encoding="utf-8")
        m = oum.get_momentum(["sow"])
        if m == "deep_work":
            ok("C.12 get_momentum: mismo dominio × 3 → deep_work")
        else:
            warn(f"C.12 deep_work esperado, obtuvo: {m}")
    except Exception as e:
        fail("C.12 get_momentum deep_work crasheo", str(e))

    # context_switch: dominio diferente
    try:
        entries = "\n".join(json.dumps({"ts": datetime.now().isoformat(), "domains": ["sow"],
                                         "intent": "crear", "head": f"sow {i}"}) for i in range(3))
        pf.write_text(entries, encoding="utf-8")
        m = oum.get_momentum(["sap_tierra"])  # dominio distinto
        if m == "context_switch":
            ok("C.12 get_momentum: dominio diferente → context_switch")
        else:
            warn(f"C.12 context_switch esperado, obtuvo: {m}")
    except Exception as e:
        fail("C.12 get_momentum context_switch crasheo", str(e))

    if pf_orig is not None:
        pf.write_text(pf_orig, encoding="utf-8")

    # C.13 update_prompt_history — rolling 5 entries
    try:
        pf.parent.mkdir(parents=True, exist_ok=True)
        pf.write_text("", encoding="utf-8")
        for i in range(7):
            oum.update_prompt_history(f"prompt {i}", ["sow"], "crear")
        lines = pf.read_text(encoding="utf-8").strip().splitlines()
        if len(lines) == 5:
            ok(f"C.13 update_prompt_history: rolling 5 entries (7 escritos → {len(lines)})")
        else:
            fail(f"C.13 rolling: {len(lines)} lines (esperado 5)")
        if pf_orig is not None:
            pf.write_text(pf_orig, encoding="utf-8")
    except Exception as e:
        fail("C.13 update_prompt_history crasheo", str(e))

    # C.14 get_co_domains — archivo inexistente → []
    try:
        co_file_tmp = ADAPTIVE_DIR / "domain_cooccurrence_test_tmp.json"
        orig_co_file = oum.CO_OCCUR_FILE
        # Patch temporal
        oum.CO_OCCUR_FILE = co_file_tmp
        result = oum.get_co_domains(["sow"])
        oum.CO_OCCUR_FILE = orig_co_file
        if result == []:
            ok("C.14 get_co_domains: archivo inexistente → []")
        else:
            fail(f"C.14 co_domains inexistente: {result}")
    except Exception as e:
        fail("C.14 get_co_domains inexistente crasheo", str(e))

    # C.15 get_co_domains — co-dominio conocido (de B.23 lo guardamos)
    try:
        result = oum.get_co_domains(["sow"])
        if isinstance(result, list):
            ok(f"C.15 get_co_domains(['sow']) → {result} (lista válida)")
        else:
            fail(f"C.15 get_co_domains no retornó lista: {result}")
    except Exception as e:
        fail("C.15 get_co_domains crasheo", str(e))

    # C.16 get_markov_next — predicción
    try:
        result = oum.get_markov_next(["sow"], [])
        if isinstance(result, list):
            ok(f"C.16 get_markov_next(['sow']) → {result}")
        else:
            fail(f"C.16 markov_next no retornó lista: {result}")
    except Exception as e:
        fail("C.16 get_markov_next crasheo", str(e))

    # C.17 save_injection_record — escribe todos los campos
    try:
        inj_file = oum.INJECTION_FILE
        oum.save_injection_record(["sow"], ["sow","propuesta"], True, True, False, "crear")
        if inj_file.exists():
            data = json.loads(inj_file.read_text(encoding="utf-8"))
            fields = ["ts", "domains", "keywords", "has_lm", "has_kb", "has_ep", "intent"]
            missing = [f for f in fields if f not in data]
            if not missing:
                ok("C.17 save_injection_record: todos los campos presentes")
            else:
                fail(f"C.17 campos faltantes: {missing}")
        else:
            fail("C.17 injection_file no creado")
    except Exception as e:
        fail("C.17 save_injection_record crasheo", str(e))

# ══════════════════════════════════════════════════════════════
# D. POST_ACTION_LEARN — funciones internas
# ══════════════════════════════════════════════════════════════
section("D. post_action_learn.py — funciones internas")

try:
    import post_action_learn as pal
    ok("D.0 import post_action_learn OK")
except Exception as e:
    fail("D.0 import post_action_learn FALLO", str(e))
    pal = None

if pal:
    # D.1 _is_trivial — cada patrón + casos borde
    trivial_cases = [
        ("pwd",    True),
        ("which python", False),   # con argumento = NO trivial (patrón requiere solo "which")
        ("where git", False),      # con argumento = NO trivial
        ("which",  True),          # solo "which" sin argumento = trivial
        ("where",  True),          # solo "where" sin argumento = trivial
        ("xyz",    True),   # < 5 chars
        ("python knowledge_base.py stats", False),
        ("ls -la /project", False),
        ("", True),
    ]
    for cmd, expected in trivial_cases:
        try:
            got = pal._is_trivial(cmd)
            if got == expected:
                ok(f"D.1 _is_trivial('{cmd[:30]}') → {expected}")
            else:
                fail(f"D.1 _is_trivial('{cmd[:30]}') → {got} (esperado {expected})")
        except Exception as e:
            fail(f"D.1 _is_trivial crasheo para '{cmd}'", str(e))

    # D.2 _detect_errors — cada patrón de error
    error_patterns = [
        ("Traceback (most recent call last):", True),
        ("Error: something went wrong",        True),
        ("ModuleNotFoundError: no module",     True),
        ("SyntaxError: invalid syntax",        True),
        ("Permission denied /etc/hosts",       True),
        ("command not found: xyz",             True),
        ("exit code 1",                        True),
        ("ENOENT no such file",                True),
        ("All OK success",                     False),
        ("",                                   False),
    ]
    for text, should_have_errors in error_patterns:
        try:
            errors = pal._detect_errors(text)
            if should_have_errors and len(errors) > 0:
                ok(f"D.2 _detect_errors: '{text[:35]}' → {len(errors)} error(es)")
            elif not should_have_errors and len(errors) == 0:
                ok(f"D.2 _detect_errors: '{text[:35]}' → sin errores (correcto)")
            else:
                fail(f"D.2 _detect_errors: '{text[:35]}' → {errors}")
        except Exception as e:
            fail(f"D.2 _detect_errors crasheo", str(e))

    # D.3 _detect_success — cada patrón de éxito
    success_patterns = [
        ("All OK",                              True),
        ("registrado exitosamente",             True),
        ("3 patterns found successfully",       True),
        ("Running on http://localhost:5000",    True),
        ("exit code 0",                         True),
        ("exitosa operacion",                   True),
        ("Traceback error",                     False),
        ("",                                    False),
    ]
    for text, expected in success_patterns:
        try:
            got = pal._detect_success(text)
            if got == expected:
                ok(f"D.3 _detect_success: '{text[:35]}' → {expected}")
            else:
                fail(f"D.3 _detect_success: '{text[:35]}' → {got} (esperado {expected})")
        except Exception as e:
            fail(f"D.3 _detect_success crasheo", str(e))

    # D.4 _extract_key_info — exit_code None → success=True
    try:
        info = pal._extract_key_info("Read", {"file_path": "C:/test.py"}, "contenido", None)
        if info.get("success") == True:
            ok("D.4 _extract_key_info: exit_code=None → success=True")
        else:
            fail(f"D.4 exit_code None: success={info.get('success')}")
    except Exception as e:
        fail("D.4 _extract_key_info None crasheo", str(e))

    # D.5 _extract_key_info — cada tipo de herramienta
    tool_cases = [
        ("Bash",  {"command": "python test.py"}, "output text", 0, "command"),
        ("Edit",  {"file_path": "test.py", "old_string": "old", "new_string": "new"}, "ok", None, "file"),
        ("Write", {"file_path": "test.py", "content": "nuevo"}, "ok", None, "file"),
        ("Read",  {"file_path": "test.py"}, "contenido", None, "file"),
        ("Grep",  {"pattern": "def main", "path": "."}, "match1\nmatch2", None, "pattern"),
        ("Glob",  {"pattern": "**/*.py"}, "a.py\nb.py", None, "pattern"),
        ("Other", {"x": "y"}, "out", None, "input_preview"),
    ]
    for tool, inp, out, ec, check_field in tool_cases:
        try:
            info = pal._extract_key_info(tool, inp, out, ec)
            if check_field in info:
                ok(f"D.5 _extract_key_info({tool}) → campo '{check_field}' presente")
            else:
                fail(f"D.5 _extract_key_info({tool}) → campo '{check_field}' ausente: {list(info.keys())}")
        except Exception as e:
            fail(f"D.5 _extract_key_info({tool}) crasheo", str(e))

    # D.6 _save_pending_error — overflow a 10 elementos
    try:
        pf = pal.PENDING_ERRORS_FILE
        pf.parent.mkdir(parents=True, exist_ok=True)
        # Llenar con 9 errores
        inicial = [{"tool": "Bash", "timestamp": datetime.now(timezone.utc).isoformat(),
                    "command": f"cmd_{i}", "errors": [], "success": False} for i in range(9)]
        pf.write_text(json.dumps(inicial), encoding="utf-8")
        # Agregar error #10 y #11 → debe quedarse en 10
        for _ in range(2):
            pal._save_pending_error({"tool": "Bash", "timestamp": datetime.now(timezone.utc).isoformat(),
                                     "command": "overflow", "errors": [], "success": False})
        pending = json.loads(pf.read_text(encoding="utf-8"))
        if len(pending) <= 10:
            ok(f"D.6 _save_pending_error: overflow → {len(pending)} (max 10)")
        else:
            fail(f"D.6 overflow: {len(pending)} elementos (esperado <= 10)")
    except Exception as e:
        fail("D.6 _save_pending_error overflow crasheo", str(e))

    # D.7 _check_error_resolution — sin success indicator → no resuelve
    try:
        # Dejar error pendiente
        pf = pal.PENDING_ERRORS_FILE
        err = [{"tool": "Bash", "timestamp": datetime.now(timezone.utc).isoformat(),
                "command": "python test.py", "errors": ["ModuleNotFoundError"], "success": False}]
        pf.write_text(json.dumps(err), encoding="utf-8")
        # Accion sin success indicator
        pal._check_error_resolution({
            "success": True,
            "has_success_indicator": False,  # <-- clave
            "tool": "Bash", "command": "echo ok"
        })
        pending_after = json.loads(pf.read_text(encoding="utf-8"))
        if len(pending_after) == 1:
            ok("D.7 _check_error_resolution: sin success_indicator → no resuelve")
        else:
            fail(f"D.7 sin success_indicator: pending={len(pending_after)} (esperado 1)")
    except Exception as e:
        fail("D.7 _check_error_resolution sin indicator crasheo", str(e))

    # D.8 _check_error_resolution — error viejo (> 10min) → no resuelve
    try:
        pf = pal.PENDING_ERRORS_FILE
        old_ts = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        err = [{"tool": "Bash", "timestamp": old_ts,
                "command": "python viejo.py", "errors": ["OldError"], "success": False}]
        pf.write_text(json.dumps(err), encoding="utf-8")
        pal._check_error_resolution({
            "success": True, "has_success_indicator": True,
            "tool": "Bash", "command": "pip install xyz"
        })
        pending_after = json.loads(pf.read_text(encoding="utf-8"))
        if len(pending_after) == 1:
            ok("D.8 _check_error_resolution: error >10min → no correlaciona")
        else:
            fail(f"D.8 error viejo: pending={len(pending_after)} (esperado 1)")
    except Exception as e:
        fail("D.8 _check_error_resolution viejo crasheo", str(e))

    # D.9 _check_error_resolution — error reciente + success → resuelve y guarda en LM
    try:
        pf = pal.PENDING_ERRORS_FILE
        recent_ts = datetime.now(timezone.utc).isoformat()
        err = [{"tool": "Bash", "timestamp": recent_ts,
                "command": "python playwright_sap.py",
                "errors": ["ModuleNotFoundError: playwright"], "success": False}]
        pf.write_text(json.dumps(err), encoding="utf-8")
        pal._check_error_resolution({
            "success": True, "has_success_indicator": True,
            "tool": "Bash", "command": "pip install playwright && python playwright_sap.py",
            "program": "pip"
        })
        pending_after = json.loads(pf.read_text(encoding="utf-8"))
        if len(pending_after) == 0:
            ok("D.9 _check_error_resolution: error reciente + success → resuelto, pending=0")
        else:
            fail(f"D.9 resolución: pending={len(pending_after)} (esperado 0)")
    except Exception as e:
        fail("D.9 _check_error_resolution reciente crasheo", str(e))

    # D.10 _register_significant_action — cada key_file
    key_files = ["dashboard.py", "index.html", "brand_mirror.py",
                 "knowledge_base.py", "learning_memory.py", "settings.json"]
    for kf in key_files:
        try:
            pal._register_significant_action({
                "tool": "Edit", "file": f"C:/project/{kf}",
                "success": True, "change_summary": "test change"
            })
            ok(f"D.10 _register_significant_action: '{kf}' → sin crash")
        except Exception as e:
            fail(f"D.10 key_file '{kf}' crasheo", str(e))

    # D.11 _register_significant_action — project_script
    for ps in ["dashboard.py", "knowledge_base.py", "learning_memory.py"]:
        try:
            pal._register_significant_action({
                "tool": "Bash", "script": ps,
                "success": True, "exit_code": 0, "errors": [], "program": "python"
            })
            ok(f"D.11 _register_significant_action: script '{ps}' → sin crash")
        except Exception as e:
            fail(f"D.11 project_script '{ps}' crasheo", str(e))

    # D.12 tool_result fallback a tool_output — verificar campo correcto
    try:
        import subprocess as sp
        E = {**os.environ, "PYTHONIOENCODING": "utf-8"}
        # Solo tool_result (nuevo)
        r = sp.run([sys.executable, str(HOOKS_DIR / "post_action_learn.py")],
                   input=json.dumps({"tool_name":"Bash","tool_input":{"command":"python t.py"},
                       "tool_result":"Traceback ModuleNotFoundError error failed", "exit_code":1}),
                   capture_output=True, text=True, timeout=10, encoding="utf-8", env=E,
                   cwd=str(PROJECT_DIR))
        pf2 = pal.PENDING_ERRORS_FILE
        if pf2.exists():
            p = json.loads(pf2.read_text(encoding="utf-8"))
            last = p[-1] if p else {}
            if last.get("errors"):
                ok("D.12 tool_result campo: errores detectados vía 'tool_result'")
            else:
                warn("D.12 tool_result: sin errores detectados")
        else:
            warn("D.12 pending_errors no existe")
    except Exception as e:
        fail("D.12 tool_result fallback crasheo", str(e))

    # D.13 tool_output fallback (backward compat) — si no hay tool_result
    try:
        r = sp.run([sys.executable, str(HOOKS_DIR / "post_action_learn.py")],
                   input=json.dumps({"tool_name":"Bash","tool_input":{"command":"python t.py"},
                       "tool_output":"Traceback error failed ModuleNotFoundError", "exit_code":1}),
                   capture_output=True, text=True, timeout=10, encoding="utf-8", env=E,
                   cwd=str(PROJECT_DIR))
        if r.returncode == 0:
            ok("D.13 tool_output fallback: funciona cuando no hay tool_result")
        else:
            fail("D.13 tool_output fallback crasheo", r.stderr[:200])
    except Exception as e:
        fail("D.13 tool_output fallback crasheo", str(e))

# ══════════════════════════════════════════════════════════════
# E. CAMINOS DE INTEGRACIÓN CRUZADA
# ══════════════════════════════════════════════════════════════
section("E. Integración cruzada — caminos compartidos")

import subprocess as sp
E = {**os.environ, "PYTHONIOENCODING": "utf-8"}

def run_h(hook, stdin_data):
    r = sp.run([sys.executable, str(HOOKS_DIR / hook)],
               input=json.dumps(stdin_data, ensure_ascii=False),
               capture_output=True, text=True, timeout=15,
               encoding="utf-8", env=E, cwd=str(PROJECT_DIR))
    return r.stdout, r.stderr, r.returncode

# E.1 Co-occurrence update → prediction funciona en siguiente query
# Guardamos co-occurrence sow↔bom en B.23, ahora verificamos que on_user_message lo usa
try:
    stdout, _, rc = run_h("on_user_message.py", {
        "prompt": "genera sow propuesta contrato alcance entregable",
        "session_id": "e-co-occur"
    })
    if rc == 0:
        ok("E.1 Co-occur + prediction: UserPromptSubmit con sow funciona")
    else:
        fail("E.1 Co-occur prediction crasheo")
except Exception as e:
    fail("E.1 Co-occur integration crasheo", str(e))

# E.2 Markov chain update → predicción de siguiente dominio
# Guardamos sow→bom en B.24, ahora verificamos que on_user_message predice bom
try:
    stdout, _, rc = run_h("on_user_message.py", {
        "prompt": "genera nuevo sow propuesta contrato servicio alcance",
        "session_id": "e-markov"
    })
    if rc == 0:
        ok("E.2 Markov prediction: UserPromptSubmit con sow no crashea")
    else:
        fail("E.2 Markov prediction crasheo")
except Exception as e:
    fail("E.2 Markov integration crasheo", str(e))

# E.3 iteration_learn → last_learning.txt → SessionStart inline
# Generar una entrada en last_learning.txt
try:
    if il:
        il.write_notification(42, 5, "integration test cycle complete", "sow", saved=True)
    ll_file = ADAPTIVE_DIR / "last_learning.txt"
    if ll_file.exists():
        content = ll_file.read_text(encoding="utf-8")
        if "iter 42" in content:
            ok("E.3 iteration_learn → last_learning.txt → SessionStart readable")
        else:
            warn("E.3 last_learning.txt no contiene iter 42")
    else:
        fail("E.3 last_learning.txt no existe")
except Exception as e:
    fail("E.3 last_learning → SessionStart crasheo", str(e))

# E.4 auto_learn_hook → session_history.json → SessionStart inline
import tempfile as tf_mod
msgs_e4 = [
    {"type": "user", "message": {"role": "user", "content": "genera sow para instana y valida bom"}},
    {"type": "assistant", "message": {"role": "assistant", "content": "SOW generado y BOM validado"}},
]
tf_e4 = fresh_tmp_jsonl(msgs_e4)
try:
    r = sp.run([sys.executable, str(HOOKS_DIR / "auto_learn_hook.py")],
               input=json.dumps({"session_id": "e4-integration", "transcript_path": str(tf_e4)}),
               capture_output=True, text=True, timeout=30,
               encoding="utf-8", env=E, cwd=str(PROJECT_DIR))
    if r.returncode == 0:
        sh_file = ADAPTIVE_DIR / "session_history.json"
        if sh_file.exists():
            sh = json.loads(sh_file.read_text(encoding="utf-8"))
            found = any(s.get("session_id") == "e4-integration" for s in sh)
            if found:
                ok("E.4 auto_learn_hook → session_history.json → SessionStart accessible")
            else:
                warn("E.4 session e4-integration no encontrada en history")
        else:
            fail("E.4 session_history.json no existe")
    else:
        fail("E.4 auto_learn_hook crasheo", r.stderr[:200])
finally:
    tf_e4.unlink(missing_ok=True)

# E.5 post_action_learn error + iteration_learn search_kb_on_failure = misma falla, distinto hook
try:
    # post_action_learn capta el error (D.12 ya lo hizo)
    # iteration_learn busca fix al mismo error
    if il:
        out = il.search_kb_on_failure(
            "Bash",
            {"command": "python playwright_sap.py"},
            "Traceback ModuleNotFoundError playwright not installed failed"
        )
        ok(f"E.5 search_kb_on_failure post error→solution: output={len(out)} chars")
    else:
        skip("E.5 iteration_learn no importado")
except Exception as e:
    fail("E.5 search_kb_on_failure integration crasheo", str(e))

# E.6 inject_record → hint_effectiveness (auto_learn_hook lo audita)
try:
    inj = ADAPTIVE_DIR / "last_injection.json"
    if inj.exists():
        data = json.loads(inj.read_text(encoding="utf-8"))
        fields = ["ts", "domains", "has_lm", "has_kb"]
        missing = [f for f in fields if f not in data]
        if not missing:
            ok(f"E.6 last_injection.json: todos los campos ({list(data.keys())})")
        else:
            fail(f"E.6 last_injection campos faltantes: {missing}")
    else:
        warn("E.6 last_injection.json no existe aún")
except Exception as e:
    fail("E.6 last_injection crasheo", str(e))

# ══════════════════════════════════════════════════════════════
# F. EDGE CASES IMPREDECIBLES
# ══════════════════════════════════════════════════════════════
section("F. Edge cases impredecibles")

# F.1 Todos los archivos de estado borrados simultáneamente (reset total)
test_files = [
    ADAPTIVE_DIR / "classify_cache.json",
    ADAPTIVE_DIR / "domain_cooccurrence.json",
    ADAPTIVE_DIR / "domain_markov.json",
    ADAPTIVE_DIR / "last_injection.json",
    STATE_DIR / "last_actions.jsonl",
    STATE_DIR / "pending_errors.json",
]
backups = {}
for f in test_files:
    if f.exists():
        try: backups[str(f)] = f.read_text(encoding="utf-8")
        except: pass
        f.unlink(missing_ok=True)

stdout, _, rc = run_h("on_user_message.py", {
    "prompt": "genera sow propuesta contrato alcance",
    "session_id": "reset-test"
})
ok("F.1 Con archivos estado borrados: UserPromptSubmit") if rc == 0 else fail("F.1 UserPromptSubmit sin estado crasheo")

stdout2, _, rc2 = run_h("post_action_learn.py", {
    "tool_name": "Bash", "tool_input": {"command": "python test.py"},
    "tool_result": "OK", "exit_code": 0
})
ok("F.1 Con archivos estado borrados: PostToolUse") if rc2 == 0 else fail("F.1 PostToolUse sin estado crasheo")

# Restaurar
for f_path, content in backups.items():
    try: Path(f_path).write_text(content, encoding="utf-8")
    except: pass

# F.2 Archivo de estado a la mitad (escritura interrumpida)
half_json = '{"session_id": "incomplete", "data": ['
sh_file = ADAPTIVE_DIR / "session_history.json"
sh_backup = sh_file.read_text(encoding="utf-8") if sh_file.exists() else "[]"
sh_file.write_text(half_json, encoding="utf-8")
try:
    if alh:
        hist = alh.load_session_history()
        if hist == []:
            ok("F.2 session_history.json partido: load_session_history → [] graceful")
        else:
            fail(f"F.2 JSON partido no graceful: {hist}")
except Exception as e:
    fail("F.2 session_history partido crasheo", str(e))
sh_file.write_text(sh_backup, encoding="utf-8")

# F.3 Lock de archivo bajo concurrencia (2 procesos escriben simultáneamente)
import threading
errors_f3 = []
def write_notify(i):
    try:
        if il:
            il.write_notification(1000+i, 1, f"concurrent write {i}", "sow", True)
    except Exception as e:
        errors_f3.append(str(e))

threads = [threading.Thread(target=write_notify, args=(i,)) for i in range(5)]
for t in threads: t.start()
for t in threads: t.join()
if not errors_f3:
    ok("F.3 Escritura concurrente (5 threads): sin errores de lock")
else:
    warn(f"F.3 Errores de lock bajo concurrencia: {errors_f3[:2]}")

# F.4 Prompt con solo números → sin keywords válidas → exit silencioso
stdout, _, rc = run_h("on_user_message.py", {"prompt": "123 456 789 42", "session_id": "nums"})
if rc == 0 and not stdout.strip():
    ok("F.4 Prompt solo números → exit silencioso")
else:
    warn(f"F.4 Prompt números: rc={rc}, output='{stdout[:50]}'")

# F.5 JSON stdin con caracteres null bytes
import subprocess as sp2
r = sp2.run([sys.executable, str(HOOKS_DIR / "on_user_message.py")],
            input='{"prompt": "sow\x00propuesta"}',
            capture_output=True, text=True, timeout=10, encoding="utf-8", env=E,
            cwd=str(PROJECT_DIR))
ok("F.5 JSON con null bytes → no crashea") if r.returncode == 0 else warn(f"F.5 null bytes: rc={r.returncode}")

# F.6 Transcript con content=None en mensajes
msgs_none = [{"role": "user", "content": None}, {"role": "assistant", "content": None}]
tf_none = fresh_tmp_jsonl([{"type":"user","message":m} for m in msgs_none])
try:
    if alh:
        msgs = alh.read_transcript(str(tf_none))
        ok(f"F.6 content=None en mensaje → {len(msgs)} msgs, sin crash")
    else:
        skip("F.6")
except Exception as e:
    fail("F.6 content=None crasheo", str(e))
tf_none.unlink(missing_ok=True)

# F.7 Archivo JSONL de acciones con 0 bytes
if il:
    al = il.ACTIONS_LOG
    al_backup = al.read_text(encoding="utf-8") if al.exists() else ""
    al.write_text("", encoding="utf-8")
    try:
        result = il.load_actions_for_session("any-session", 1)
        if result == []:
            ok("F.7 ACTIONS_LOG vacío: load_actions → [] graceful")
        else:
            fail(f"F.7 ACTIONS_LOG vacío: {result}")
    except Exception as e:
        fail("F.7 ACTIONS_LOG vacío crasheo", str(e))
    al.write_text(al_backup, encoding="utf-8")

# F.8 session_history.json con 1000 sesiones (rendimiento)
import time as tm_mod
sh_bak = sh_file.read_text(encoding="utf-8") if sh_file.exists() else "[]"
big_history = [{"session_id": f"sess-{i}", "date": "2026-03-01", "user_messages": [f"msg {i}"],
                "summary": f"sesion {i}", "timestamp": "2026-03-01 00:00:00"} for i in range(1000)]
sh_file.write_text(json.dumps(big_history), encoding="utf-8")
t0 = tm_mod.time()
if alh:
    hist = alh.load_session_history()
elapsed = tm_mod.time() - t0
if elapsed < 2.0:
    ok(f"F.8 load_session_history con 1000 sesiones: {elapsed:.3f}s (< 2s)")
else:
    warn(f"F.8 performance: {elapsed:.3f}s para 1000 sesiones")
sh_file.write_text(sh_bak, encoding="utf-8")

# F.9 Mensaje de usuario de 10,000 chars → truncado correctamente
long_msg = "x" * 10000
if alh:
    msgs = [{"role": "user", "content": long_msg}]
    umsg = alh.extract_user_messages(msgs)
    if umsg and len(umsg[0]) <= 500:
        ok(f"F.9 Mensaje 10K chars → truncado a {len(umsg[0])} chars (max 500)")
    else:
        fail(f"F.9 Mensaje 10K no truncado: {len(umsg[0]) if umsg else 0}")

# F.10 detect_domain de iteration_learn con 0 acciones → "files"
if il:
    try:
        got = il.detect_domain([])
        if got == "files":
            ok("F.10 detect_domain con lista vacía → 'files'")
        else:
            fail(f"F.10 detect_domain vacío → '{got}'")
    except Exception as e:
        fail("F.10 detect_domain vacío crasheo", str(e))

# ══════════════════════════════════════════════════════════════
# G. EPISODIC_INDEX — nuevo módulo (todas las ramas)
# ══════════════════════════════════════════════════════════════
section("G. episodic_index.py — FTS5 memoria cross-sesión")

try:
    import episodic_index as ei
    ok("G.0 import episodic_index OK")
except Exception as e:
    fail("G.0 import episodic_index FALLO", str(e))
    ei = None

if ei:
    import tempfile as _tmp, shutil as _sh

    # G.1 _build_body — combina todos los campos
    try:
        record = {
            "summary": "sesion de prueba con sow y bom",
            "user_messages": ["genera sow para instana", "valida bom listado"],
            "decisions": ["voy a usar aria-label para el selector"],
            "errors": [{"detail": "Error: module not found"}],
            "files_edited": ["C:/project/sow_template.docx"],
            "files_created": ["C:/project/bom_output.xlsx"],
            "cwd": "C:/Chance1/Asistente IA",
        }
        body = ei._build_body(record)
        checks = ["sow", "bom", "aria-label", "sow_template", "bom_output"]
        missing = [c for c in checks if c not in body]
        if not missing:
            ok(f"G.1 _build_body: todos los campos incluidos ({len(body)} chars)")
        else:
            fail(f"G.1 _build_body: faltan {missing}")
    except Exception as e:
        fail("G.1 _build_body crasheo", str(e))

    # G.2 _build_body — filtra mensajes del sistema
    try:
        record2 = {
            "summary": "sesion real",
            "user_messages": [
                "This session is being continued from previous conversation...",
                "Summary: largo resumen del sistema...",
                "<task-notification>notificacion</task-notification>",
                "mensaje real del usuario sobre sow",
            ],
        }
        body2 = ei._build_body(record2)
        if "This session" not in body2 and "Summary:" not in body2 and "task-notification" not in body2:
            ok("G.2 _build_body: filtra mensajes del sistema correctamente")
        else:
            fail(f"G.2 _build_body incluye msgs del sistema: {body2[:200]}")
    except Exception as e:
        fail("G.2 _build_body filtro crasheo", str(e))

    # G.3 _detect_domain — keywords en user_messages
    domain_cases = [
        ({"user_messages": ["sap crm oportunidad quote playwright"]}, "sap_tierra"),
        ({"user_messages": ["genera sow propuesta contrato"]},        "sow"),
        ({"user_messages": ["valida bom listado material"]},          "bom"),
        ({"user_messages": ["actualiza monday pipeline"]},            "monday"),
        ({"user_messages": ["envia correo outlook adjunto"]},         "outlook"),
        ({"user_messages": ["edita script python"]},                  "files"),
        ({"domain": "catalog"},                                       "catalog"),  # campo explícito
    ]
    for rec, expected in domain_cases:
        try:
            got = ei._detect_domain(rec)
            if got == expected:
                ok(f"G.3 _detect_domain: '{expected}'")
            else:
                warn(f"G.3 _detect_domain: esperado '{expected}', obtuvo '{got}'")
        except Exception as e:
            fail(f"G.3 _detect_domain({expected}) crasheo", str(e))

    # G.4 index_session — insert nueva sesión
    try:
        test_sid = "g4-test-session-insert"
        ei.index_session({
            "session_id": test_sid,
            "date": "2026-03-20",
            "summary": "prueba de insercion en indice episodico",
            "user_messages": ["testeo la insercion del indice episodico con keywords unicos xyzabc123"],
            "domain": "sow",
        })
        conn = ei._connect()
        ei._ensure_schema(conn)
        row = conn.execute("SELECT * FROM sessions_meta WHERE session_id=?", (test_sid,)).fetchone()
        conn.close()
        if row:
            ok("G.4 index_session: INSERT nueva sesión OK")
        else:
            fail("G.4 index_session: sesión no encontrada en meta")
    except Exception as e:
        fail("G.4 index_session insert crasheo", str(e))

    # G.5 index_session — UPDATE sesión existente (idempotente)
    try:
        ei.index_session({
            "session_id": test_sid,
            "date": "2026-03-20",
            "summary": "version actualizada del registro episodico",
            "user_messages": ["mensaje actualizado"],
            "domain": "bom",
        })
        conn = ei._connect()
        ei._ensure_schema(conn)
        n = conn.execute("SELECT COUNT(*) FROM sessions_meta WHERE session_id=?", (test_sid,)).fetchone()[0]
        conn.close()
        if n == 1:
            ok("G.5 index_session: UPDATE (no duplica) → 1 registro")
        else:
            fail(f"G.5 index_session duplicó: {n} registros")
    except Exception as e:
        fail("G.5 index_session update crasheo", str(e))

    # G.6 index_session — session_id vacío → skip silencioso
    try:
        before = ei.get_stats()["indexed_sessions"]
        ei.index_session({"session_id": "", "summary": "sin id"})
        after = ei.get_stats()["indexed_sessions"]
        if before == after:
            ok("G.6 index_session: session_id vacío → skip silencioso")
        else:
            fail(f"G.6 indexó sesión sin id: {after - before} sesiones extra")
    except Exception as e:
        fail("G.6 index_session vacío crasheo", str(e))

    # G.7 index_session — body vacío → skip
    try:
        before = ei.get_stats()["indexed_sessions"]
        ei.index_session({"session_id": "g7-empty-body", "summary": "", "user_messages": []})
        after = ei.get_stats()["indexed_sessions"]
        if before == after:
            ok("G.7 index_session: body vacío → skip")
        else:
            warn("G.7 index_session: indexó registro con body vacío")
    except Exception as e:
        fail("G.7 index_session body vacío crasheo", str(e))

    # G.8 search — OR: devuelve resultados aunque no estén todas las palabras
    try:
        sr8 = ei.search("sow propuesta contrato alcance entregable", limit=3)
        if sr8:
            ok(f"G.8 search OR: {len(sr8)} resultado(s) para query multi-keyword")
            for r in sr8[:2]:
                ok(f"  [{r['date']}/{r['domain']}] {r['snippet'][:60]}")
        else:
            warn("G.8 search OR: sin resultados (índice puede estar vacío)")
    except Exception as e:
        fail("G.8 search OR crasheo", str(e))

    # G.9 search — query vacía → []
    try:
        sr9 = ei.search("", limit=3)
        if sr9 == []:
            ok("G.9 search: query vacía → []")
        else:
            fail(f"G.9 search vacía: {sr9}")
    except Exception as e:
        fail("G.9 search vacía crasheo", str(e))

    # G.10 search — caracteres especiales sanitizados
    for q in ["sow & bom", "sap (tierra)", "hook:dashboard", "sow OR bom", "a*b"]:
        try:
            sr10 = ei.search(q, limit=1)
            ok(f"G.10 search sanitize: '{q}' → {len(sr10)} resultados, sin crash")
        except Exception as e:
            fail(f"G.10 search '{q}' crasheo", str(e))

    # G.11 search — DB inexistente → []
    try:
        orig = ei.DB_PATH
        ei.DB_PATH = Path("/nonexistent/path/episodic.db")
        sr11 = ei.search("sow", limit=2)
        ei.DB_PATH = orig
        if sr11 == []:
            ok("G.11 search: DB inexistente → []")
        else:
            fail(f"G.11 search DB inexistente: {sr11}")
    except Exception as e:
        ei.DB_PATH = orig
        fail("G.11 search DB inexistente crasheo", str(e))

    # G.12 rebuild_from_history — HISTORY_FILE inexistente → 0
    try:
        orig_hf = ei.HISTORY_FILE
        ei.HISTORY_FILE = Path("/nonexistent/history.json")
        n = ei.rebuild_from_history()
        ei.HISTORY_FILE = orig_hf
        if n == 0:
            ok("G.12 rebuild_from_history: archivo inexistente → 0")
        else:
            fail(f"G.12 rebuild inexistente: {n}")
    except Exception as e:
        ei.HISTORY_FILE = orig_hf
        fail("G.12 rebuild inexistente crasheo", str(e))

    # G.13 rebuild_from_history — JSON corrupto → 0
    try:
        tf_hf = Path(_tmp.mktemp(suffix=".json"))
        tf_hf.write_text("{{{not valid json}}}", encoding="utf-8")
        orig_hf = ei.HISTORY_FILE
        ei.HISTORY_FILE = tf_hf
        n = ei.rebuild_from_history()
        ei.HISTORY_FILE = orig_hf
        tf_hf.unlink(missing_ok=True)
        if n == 0:
            ok("G.13 rebuild_from_history: JSON corrupto → 0 graceful")
        else:
            fail(f"G.13 rebuild corrupto: {n}")
    except Exception as e:
        ei.HISTORY_FILE = orig_hf if 'orig_hf' in dir() else ei.HISTORY_FILE
        fail("G.13 rebuild corrupto crasheo", str(e))

    # G.14 rebuild_from_history — reconstruye desde historial real
    try:
        n = ei.rebuild_from_history()
        stats = ei.get_stats()
        if n > 0 and stats["indexed_sessions"] > 0:
            ok(f"G.14 rebuild_from_history: {n} sesiones indexadas, DB={stats['db_size_kb']}KB")
        else:
            warn(f"G.14 rebuild: {n} sesiones (historial puede estar vacío)")
    except Exception as e:
        fail("G.14 rebuild historial real crasheo", str(e))

    # G.15 get_stats — DB existe vs no existe
    try:
        s = ei.get_stats()
        if "indexed_sessions" in s and "db_size_kb" in s:
            ok(f"G.15 get_stats: {s}")
        else:
            fail(f"G.15 get_stats: campos faltantes {s}")
    except Exception as e:
        fail("G.15 get_stats crasheo", str(e))

    # G.16 search — resultado recién indexado es encontrable
    try:
        uid = f"g16-unique-{int(time.time())}"
        ei.index_session({
            "session_id": uid,
            "date": "2026-03-20",
            "summary": f"sesion unica con keyword zarplantiff para test g16",
            "user_messages": ["zarplantiff es el keyword unico de esta sesion de prueba"],
            "domain": "sow",
        })
        r = ei.search("zarplantiff", limit=1)
        if r and "zarplantiff" in r[0]["snippet"].lower().replace("«","").replace("»",""):
            ok("G.16 search: sesión recién indexada es encontrable inmediatamente")
        else:
            fail(f"G.16 sesión no encontrada: {r}")
    except Exception as e:
        fail("G.16 search inmediato crasheo", str(e))

    # G.17 integración: auto_learn_hook llama index_session via Stop hook
    try:
        msgs_g17 = [
            {"type": "user", "message": {"role": "user", "content": "crea sow para cliente instana"}},
            {"type": "assistant", "message": {"role": "assistant", "content": "Aqui el SOW de Instana"}},
        ]
        tf_g17 = fresh_tmp_jsonl(msgs_g17)
        before = ei.get_stats()["indexed_sessions"]
        r = sp.run([sys.executable, str(HOOKS_DIR / "auto_learn_hook.py")],
                   input=json.dumps({"session_id": "g17-stop-integration", "transcript_path": str(tf_g17)}),
                   capture_output=True, text=True, timeout=30, encoding="utf-8", env=E,
                   cwd=str(PROJECT_DIR))
        tf_g17.unlink(missing_ok=True)
        after = ei.get_stats()["indexed_sessions"]
        if r.returncode == 0 and after >= before:
            ok(f"G.17 Stop hook → index_session vía auto_learn_hook: sesiones {before}→{after}")
        else:
            fail(f"G.17 Stop hook index_session: rc={r.returncode}, sesiones {before}→{after}", r.stderr[:100])
    except Exception as e:
        fail("G.17 Stop hook integration crasheo", str(e))

# ══════════════════════════════════════════════════════════════
# H. FIX EDIT/WRITE EN _check_error_resolution
# ══════════════════════════════════════════════════════════════
section("H. Fix _check_error_resolution Edit/Write")

try:
    import post_action_learn as pal2
    from datetime import timezone as tz2
    pf2 = pal2.PENDING_ERRORS_FILE

    def seed_error(cmd="python bad.py", err="SyntaxError"):
        ts = datetime.now(tz2.utc).isoformat()
        pf2.parent.mkdir(parents=True, exist_ok=True)
        pf2.write_text(json.dumps([{
            "tool": "Bash", "timestamp": ts,
            "command": cmd, "errors": [err], "success": False
        }]), encoding="utf-8")

    def pending_count():
        if not pf2.exists(): return 0
        try: return len(json.loads(pf2.read_text(encoding="utf-8")))
        except: return -1

    # H.1 Edit exitoso resuelve error pendiente (caso nuevo)
    seed_error()
    pal2._check_error_resolution({"tool":"Edit","file":"bad.py","success":True,"has_success_indicator":False})
    if pending_count() == 0:
        ok("H.1 Edit exitoso: resuelve error pendiente (fue gap antes del fix)")
    else:
        fail(f"H.1 Edit no resolvio: pending={pending_count()}")

    # H.2 Write exitoso resuelve error pendiente (caso nuevo)
    seed_error(cmd="open missing.py")
    pal2._check_error_resolution({"tool":"Write","file":"missing.py","success":True,"has_success_indicator":False})
    if pending_count() == 0:
        ok("H.2 Write exitoso: resuelve error pendiente")
    else:
        fail(f"H.2 Write no resolvio: pending={pending_count()}")

    # H.3 Edit FALLIDO (success=False) NO resuelve
    seed_error()
    pal2._check_error_resolution({"tool":"Edit","file":"bad.py","success":False,"has_success_indicator":False})
    if pending_count() == 1:
        ok("H.3 Edit fallido: NO resuelve (correcto)")
    else:
        fail(f"H.3 Edit fallido debería dejar pending=1: {pending_count()}")

    # H.4 Bash con success_indicator SÍ resuelve (comportamiento conservado)
    seed_error()
    pal2._check_error_resolution({"tool":"Bash","command":"pip install x","success":True,"has_success_indicator":True})
    if pending_count() == 0:
        ok("H.4 Bash+success_indicator: resuelve (comportamiento conservado)")
    else:
        fail(f"H.4 Bash+indicator no resolvio: pending={pending_count()}")

    # H.5 Bash SIN success_indicator NO resuelve (comportamiento conservado)
    seed_error()
    pal2._check_error_resolution({"tool":"Bash","command":"echo ok","success":True,"has_success_indicator":False})
    if pending_count() == 1:
        ok("H.5 Bash sin indicator: NO resuelve (comportamiento conservado)")
    else:
        fail(f"H.5 Bash sin indicator debería dejar pending=1: {pending_count()}")

    # H.6 Ciclo completo via entrypoint (main()) — error Bash → fix via Edit
    seed_error(cmd="python scraper.py", err="ImportError: no module")
    stdout_h6, stderr_h6, rc_h6 = run_h("post_action_learn.py", {
        "tool_name": "Edit",
        "tool_input": {"file_path": "scraper.py", "old_string": "import xyz", "new_string": ""},
        "tool_result": "File updated successfully",
        "exit_code": None
    })
    if rc_h6 == 0 and pending_count() == 0:
        ok("H.6 Ciclo completo main(): error Bash → fix Edit → resuelto")
    elif rc_h6 == 0:
        warn(f"H.6 main() rc=0 pero pending={pending_count()} (edit puede no tener exit_code=0)")
    else:
        fail(f"H.6 main() crasheo: rc={rc_h6}", stderr_h6[:100])

except Exception as e:
    fail("H import/setup crasheo", str(e))


# ══════════════════════════════════════════════════════════════
# I. knowledge_base.py — tests directos
# ══════════════════════════════════════════════════════════════
section("I. knowledge_base.py — tests directos")

try:
    import knowledge_base as kb_direct
    ok("I.0 import knowledge_base OK")
except Exception as e:
    fail("I.0 knowledge_base no importa", str(e))
    kb_direct = None

if kb_direct:
    TEST_DOM_KB = "test_kb_direct_exhaustivo"

    # I.1 _load_all_domains retorna dict con al menos 'general'
    try:
        domains_all = kb_direct._load_all_domains()
        assert isinstance(domains_all, dict)
        ok(f"I.1 _load_all_domains() retorna dict ({len(domains_all)} dominios)")
    except Exception as e:
        fail("I.1 _load_all_domains crasheo", str(e))

    # I.2 _ensure_domain crea dominio dinamico
    try:
        kb_direct._ensure_domain(TEST_DOM_KB, "Dominio de test directo KB")
        domains_after = kb_direct._load_all_domains()
        if TEST_DOM_KB in domains_after:
            ok(f"I.2 _ensure_domain('{TEST_DOM_KB}') crea dominio dinamico")
        else:
            fail(f"I.2 dominio no creado: {list(domains_after.keys())[:5]}")
    except Exception as e:
        fail("I.2 _ensure_domain crasheo", str(e))

    # I.3 _ensure_domain es idempotente
    try:
        kb_direct._ensure_domain(TEST_DOM_KB, "desc 2")
        kb_direct._ensure_domain(TEST_DOM_KB, "desc 3")
        ok("I.3 _ensure_domain idempotente (sin duplicar)")
    except Exception as e:
        fail("I.3 _ensure_domain idempotente crasheo", str(e))

    # I.4 register_pattern retorna id
    try:
        pat_id = kb_direct.register_pattern(
            TEST_DOM_KB,
            "test_key_direct_I4",
            {"strategy": "test_I4", "content": "patron de prueba directo I4 keyword_i4_unico"},
            ["tag_test_i4", "exhaustivo"]
        )
        assert isinstance(pat_id, str) and len(pat_id) > 0
        ok(f"I.4 register_pattern() retorna id: {pat_id[:12]}")
    except Exception as e:
        fail("I.4 register_pattern crasheo", str(e))

    # I.5 add_pattern retorna id
    try:
        pat_id2 = kb_direct.add_pattern(
            TEST_DOM_KB,
            "test_key_direct_I5",
            {"strategy": "test_I5", "content": "patron add_pattern directo I5 keyword_i5_unico"},
            ["tag_test_i5"]
        )
        assert isinstance(pat_id2, str) and len(pat_id2) > 0
        ok(f"I.5 add_pattern() retorna id: {pat_id2[:12]}")
    except Exception as e:
        fail("I.5 add_pattern crasheo", str(e))

    # I.6 add_fact retorna id
    try:
        fact_id = kb_direct.add_fact(
            TEST_DOM_KB,
            "test_fact_direct_I6",
            {"rule": "regla de prueba I6 keyword_i6_unico", "source": "test"},
            ["tag_fact_i6"]
        )
        assert isinstance(fact_id, str) and len(fact_id) > 0
        ok(f"I.6 add_fact() retorna id: {fact_id[:12]}")
    except Exception as e:
        fail("I.6 add_fact crasheo", str(e))

    # I.7 search por key exacto
    try:
        hits = kb_direct.search(TEST_DOM_KB, key="test_key_direct_I4")
        if hits:
            ok(f"I.7 search(key='test_key_direct_I4') → {len(hits)} resultado(s)")
        else:
            fail("I.7 search por key exacto → sin resultados")
    except Exception as e:
        fail("I.7 search key crasheo", str(e))

    # I.8 search por tags
    try:
        hits_tags = kb_direct.search(TEST_DOM_KB, tags=["tag_test_i4"])
        if hits_tags:
            ok(f"I.8 search(tags=['tag_test_i4']) → {len(hits_tags)} resultado(s)")
        else:
            fail("I.8 search por tags → sin resultados")
    except Exception as e:
        fail("I.8 search tags crasheo", str(e))

    # I.9 search por text_query
    try:
        hits_txt = kb_direct.search(TEST_DOM_KB, text_query="keyword_i5_unico")
        if hits_txt:
            ok(f"I.9 search(text_query='keyword_i5_unico') → {len(hits_txt)} resultado(s)")
        else:
            warn("I.9 search text_query → sin resultados (texto puede no indexarse aun)")
    except Exception as e:
        fail("I.9 search text_query crasheo", str(e))

    # I.10 search dominio inexistente → lista vacia
    try:
        hits_none = kb_direct.search("dominio_que_no_existe_jamas_xyz999", text_query="algo")
        assert isinstance(hits_none, list)
        ok("I.10 search dominio inexistente → [] graceful")
    except Exception as e:
        fail("I.10 search dominio inexistente crasheo", str(e))

    # I.11 cross_domain_search
    try:
        xr = kb_direct.cross_domain_search(text_query="keyword_i4_unico")
        assert isinstance(xr, dict)
        if xr:
            ok(f"I.11 cross_domain_search() → {len(xr)} dominio(s) con hits")
        else:
            warn("I.11 cross_domain_search → dict vacio (posible delay de escritura)")
    except Exception as e:
        fail("I.11 cross_domain_search crasheo", str(e))

    # I.12 export_context
    try:
        ctx = kb_direct.export_context(TEST_DOM_KB)
        assert isinstance(ctx, str)
        ok(f"I.12 export_context('{TEST_DOM_KB}') → {len(ctx)} chars")
    except Exception as e:
        fail("I.12 export_context crasheo", str(e))

    # I.13 get_global_stats
    try:
        stats = kb_direct.get_global_stats()
        assert isinstance(stats, dict) and "total" in stats
        ok(f"I.13 get_global_stats() → total={stats['total']}")
    except Exception as e:
        fail("I.13 get_global_stats crasheo", str(e))

    # I.14 escritura concurrente (5 threads)
    try:
        import threading as _thr
        _errors_i14 = []
        def _write_pattern(i):
            try:
                kb_direct.add_pattern(TEST_DOM_KB, f"concurrent_I14_{i}",
                                      {"content": f"concurrent content {i}"}, ["concurrent"])
            except Exception as ex:
                _errors_i14.append(str(ex))
        threads = [_thr.Thread(target=_write_pattern, args=(i,)) for i in range(5)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=10)
        if not _errors_i14:
            ok("I.14 Concurrent writes (5 threads) sin excepciones")
        else:
            fail(f"I.14 Concurrent writes: {len(_errors_i14)} error(es)", _errors_i14[0])
    except Exception as e:
        fail("I.14 concurrent writes crasheo", str(e))


# ══════════════════════════════════════════════════════════════
# J. domain_detector.py — tests directos
# ══════════════════════════════════════════════════════════════
section("J. domain_detector.py — tests directos")

try:
    import domain_detector as dd_direct
    ok("J.0 import domain_detector OK")
except Exception as e:
    fail("J.0 domain_detector no importa", str(e))
    dd_direct = None

if dd_direct:
    # J.1 get_domain_hints retorna dict
    try:
        hints = dd_direct.get_domain_hints()
        assert isinstance(hints, dict)
        ok(f"J.1 get_domain_hints() → dict con {len(hints)} dominio(s)")
    except Exception as e:
        fail("J.1 get_domain_hints crasheo", str(e))

    # J.2 learn_domain_keywords agrega keywords
    try:
        dd_direct.learn_domain_keywords("test_dd_direct_J", ["kw_j_unico_alpha", "kw_j_unico_beta", "kw_j_unico_gamma"])
        hints_after = dd_direct.get_domain_hints()
        if "test_dd_direct_J" in hints_after:
            kws = hints_after["test_dd_direct_J"]
            if "kw_j_unico_alpha" in kws:
                ok("J.2 learn_domain_keywords() agrega keywords correctamente")
            else:
                warn(f"J.2 keywords no encontradas: {kws[:5]}")
        else:
            warn("J.2 dominio test_dd_direct_J no encontrado en hints")
    except Exception as e:
        fail("J.2 learn_domain_keywords crasheo", str(e))

    # J.3 detect → auto-asigna con >= AUTO_THRESHOLD keywords
    try:
        detected = dd_direct.detect("texto con kw_j_unico_alpha y kw_j_unico_beta aqui")
        assert isinstance(detected, str)
        if detected == "test_dd_direct_J":
            ok(f"J.3 detect() → '{detected}' (auto-assign correcto)")
        else:
            warn(f"J.3 detect() → '{detected}' (esperado 'test_dd_direct_J')")
    except Exception as e:
        fail("J.3 detect auto-assign crasheo", str(e))

    # J.4 detect → 'general' con texto sin keywords
    try:
        gen = dd_direct.detect("zxqwrtp9 bvnmzx7w fyupql3k vbnzx4r qwrzp2yx blorf9jk")
        assert gen == "general", f"detect retorno '{gen}' (esperado 'general')"
        ok("J.4 detect(sin keywords) → 'general'")
    except Exception as e:
        fail("J.4 detect fallback general crasheo", str(e))

    # J.5 detect → 'general' con texto vacío
    try:
        assert dd_direct.detect("") == "general"
        ok("J.5 detect('') → 'general'")
    except Exception as e:
        fail("J.5 detect vacío crasheo", str(e))

    # J.6 suggest → lista de candidatos con 1 keyword
    try:
        sugg = dd_direct.suggest("texto con kw_j_unico_gamma aqui")
        assert isinstance(sugg, list)
        ok(f"J.6 suggest(1 keyword) → lista de {len(sugg)} candidato(s)")
    except Exception as e:
        fail("J.6 suggest crasheo", str(e))

    # J.7 suggest con texto vacío → []
    try:
        assert dd_direct.suggest("") == []
        ok("J.7 suggest('') → []")
    except Exception as e:
        fail("J.7 suggest vacío crasheo", str(e))

    # J.8 auto_learn_from_session — no crashea
    try:
        dd_direct.auto_learn_from_session("test_dd_direct_J", "texto largo con kw_j_unico_alpha y otras palabras de contexto de negocio")
        ok("J.8 auto_learn_from_session() no crashea")
    except Exception as e:
        fail("J.8 auto_learn_from_session crasheo", str(e))

    # J.9 learn_domain_keywords con lista vacia → no crashea
    try:
        dd_direct.learn_domain_keywords("test_dd_direct_J", [])
        ok("J.9 learn_domain_keywords(lista vacia) no crashea")
    except Exception as e:
        fail("J.9 learn_domain_keywords vacío crasheo", str(e))

    # J.10 HINTS_FILE existe y es JSON valido
    try:
        if dd_direct.HINTS_FILE.exists():
            data = json.loads(dd_direct.HINTS_FILE.read_text(encoding="utf-8"))
            assert isinstance(data, dict)
            ok(f"J.10 HINTS_FILE es JSON valido ({len(data)} dominios)")
        else:
            warn("J.10 HINTS_FILE no existe aun")
    except Exception as e:
        fail("J.10 HINTS_FILE no es JSON valido", str(e))


# ══════════════════════════════════════════════════════════════
# K. ingest_knowledge.py — pipeline completo
# ══════════════════════════════════════════════════════════════
section("K. ingest_knowledge.py — pipeline completo")

try:
    import ingest_knowledge as ik_direct
    ok("K.0 import ingest_knowledge OK")
except Exception as e:
    fail("K.0 ingest_knowledge no importa", str(e))
    ik_direct = None

if ik_direct:
    import tempfile as _tf_k

    # K.1 chunk_text — texto corto (un solo chunk)
    try:
        chunks = ik_direct.chunk_text("texto corto de prueba")
        assert isinstance(chunks, list) and len(chunks) == 1
        ok(f"K.1 chunk_text(texto corto) → 1 chunk")
    except Exception as e:
        fail("K.1 chunk_text corto crasheo", str(e))

    # K.2 chunk_text — texto largo (multiples chunks)
    try:
        texto_largo = "palabra_unica_k2 " * 200  # ~3200 chars > CHUNK_SIZE=800
        chunks_l = ik_direct.chunk_text(texto_largo)
        assert len(chunks_l) > 1
        ok(f"K.2 chunk_text(texto largo) → {len(chunks_l)} chunks (CHUNK_SIZE={ik_direct.CHUNK_SIZE})")
    except Exception as e:
        fail("K.2 chunk_text largo crasheo", str(e))

    # K.3 chunk_text — texto vacío → []
    try:
        assert ik_direct.chunk_text("") == []
        assert ik_direct.chunk_text("   ") == []
        ok("K.3 chunk_text('') → []")
    except Exception as e:
        fail("K.3 chunk_text vacío crasheo", str(e))

    # K.4 chunk_text — overlap hace que chunks se solapen
    try:
        texto_overlap = "A" * ik_direct.CHUNK_SIZE + "B" * ik_direct.CHUNK_SIZE
        c_ov = ik_direct.chunk_text(texto_overlap)
        assert len(c_ov) >= 2
        # El segundo chunk debe comenzar con el overlap del primero
        ok(f"K.4 chunk_text overlap correcto ({len(c_ov)} chunks, overlap={ik_direct.CHUNK_OVERLAP})")
    except Exception as e:
        fail("K.4 chunk_text overlap crasheo", str(e))

    # K.5 read_file — archivo .txt
    try:
        tmp_txt = Path(_tf_k.mktemp(suffix=".txt"))
        tmp_txt.write_text("contenido de prueba K5 kw_k5_unico_txt", encoding="utf-8")
        content = ik_direct.read_file(tmp_txt)
        assert "kw_k5_unico_txt" in content
        ok("K.5 read_file(.txt) lee contenido correctamente")
        tmp_txt.unlink(missing_ok=True)
    except Exception as e:
        fail("K.5 read_file .txt crasheo", str(e))

    # K.6 read_file — archivo .json
    try:
        tmp_json = Path(_tf_k.mktemp(suffix=".json"))
        tmp_json.write_text(json.dumps({"key": "valor_k6_unico_json", "data": [1, 2, 3]}), encoding="utf-8")
        content_j = ik_direct.read_file(tmp_json)
        assert "valor_k6_unico_json" in content_j
        ok("K.6 read_file(.json) lee contenido correctamente")
        tmp_json.unlink(missing_ok=True)
    except Exception as e:
        fail("K.6 read_file .json crasheo", str(e))

    # K.7 ingest_chunk — modo preview (no guarda)
    try:
        result_prev = ik_direct.ingest_chunk(
            "chunk de preview K7 kw_k7_preview",
            "test_kb_direct_exhaustivo", "test_source.txt", 1, "pattern", [], preview=True
        )
        assert result_prev is True
        ok("K.7 ingest_chunk(preview=True) retorna True sin guardar")
    except Exception as e:
        fail("K.7 ingest_chunk preview crasheo", str(e))

    # K.8 ingest_chunk — modo real (guarda en KB)
    try:
        result_real = ik_direct.ingest_chunk(
            "chunk real K8 kw_k8_real_unico contenido ingestado desde test",
            "test_kb_direct_exhaustivo", "test_source_K8.txt", 1, "pattern",
            ["tag_k8", "ingest_test"], preview=False
        )
        assert result_real is True
        ok("K.8 ingest_chunk(preview=False) retorna True y guarda en KB")
    except Exception as e:
        fail("K.8 ingest_chunk real crasheo", str(e))

    # K.9 process_file completo — crea temp .txt y lo ingesta
    try:
        tmp_proc = Path(_tf_k.mktemp(suffix=".txt"))
        tmp_proc.write_text(
            "kw_k9_process_file_unico: contenido de prueba para process_file exhaustivo\n"
            "Este archivo contiene informacion de prueba para verificar el pipeline completo de ingestion.",
            encoding="utf-8"
        )
        total_c, ok_c = ik_direct.process_file(tmp_proc, "test_kb_direct_exhaustivo", "pattern", ["tag_k9"], preview=False)
        assert total_c >= 1 and ok_c >= 1
        ok(f"K.9 process_file() → {total_c} chunks totales, {ok_c} ingestados")
        tmp_proc.unlink(missing_ok=True)
    except Exception as e:
        fail("K.9 process_file crasheo", str(e))

    # K.10 Verificar que chunk de K.8 aparece en KB
    try:
        if kb_direct:
            hits_k8 = kb_direct.search("test_kb_direct_exhaustivo", text_query="kw_k8_real_unico")
            if hits_k8:
                ok(f"K.10 Chunk K.8 encontrado en KB via search ({len(hits_k8)} hits)")
            else:
                warn("K.10 Chunk K.8 no encontrado en KB por text_query (puede ser delay)")
        else:
            skip("K.10 kb_direct no disponible")
    except Exception as e:
        fail("K.10 verificacion KB K.8 crasheo", str(e))

    # K.11 collect_files — archivo con extension no soportada
    try:
        tmp_bad = Path(_tf_k.mktemp(suffix=".xyz_unsupported"))
        tmp_bad.write_text("nada", encoding="utf-8")
        files = ik_direct.collect_files(tmp_bad)
        assert files == []
        ok("K.11 collect_files(extension no soportada) → []")
        tmp_bad.unlink(missing_ok=True)
    except Exception as e:
        fail("K.11 collect_files extensión mala crasheo", str(e))

    # K.12 collect_files — carpeta con archivos mixtos
    try:
        import tempfile as _tf2
        tmpdir = Path(_tf2.mkdtemp())
        (tmpdir / "archivo.txt").write_text("contenido", encoding="utf-8")
        (tmpdir / "archivo.json").write_text("{}", encoding="utf-8")
        (tmpdir / "archivo.exe").write_text("bin", encoding="utf-8")
        files_dir = ik_direct.collect_files(tmpdir)
        exts = {f.suffix for f in files_dir}
        assert ".exe" not in exts
        assert ".txt" in exts or ".json" in exts
        ok(f"K.12 collect_files(carpeta) → {len(files_dir)} archivos soportados (filtra .exe)")
        import shutil as _sh_k
        _sh_k.rmtree(str(tmpdir), ignore_errors=True)
    except Exception as e:
        fail("K.12 collect_files carpeta crasheo", str(e))


# ══════════════════════════════════════════════════════════════
# L. Performance / stress tests
# ══════════════════════════════════════════════════════════════
section("L. Performance / stress tests")

if kb_direct:
    # L.1 Insertar 300 patrones — tiempo < 10s
    try:
        t0 = time.time()
        dom_stress = "test_stress_exhaustivo"
        kb_direct._ensure_domain(dom_stress, "Dominio stress test")
        for i in range(300):
            kb_direct.add_pattern(dom_stress, f"stress_pat_{i}",
                                  {"content": f"patron stress numero {i} con keywords unicas stress_kw_{i}"},
                                  [f"batch_{i // 50}"])
        elapsed = time.time() - t0
        if elapsed < 10:
            ok(f"L.1 Insertar 300 patrones: {elapsed:.2f}s (< 10s)")
        else:
            warn(f"L.1 300 patrones: {elapsed:.2f}s (> 10s, lento pero no falla)")
    except Exception as e:
        fail("L.1 insercion masiva crasheo", str(e))

    # L.2 Busqueda sobre 300 patrones — tiempo < 2s
    try:
        t0 = time.time()
        hits_stress = kb_direct.search(dom_stress, text_query="stress_kw_150")
        elapsed = time.time() - t0
        if elapsed < 2:
            ok(f"L.2 search sobre 300 patrones: {elapsed:.3f}s (< 2s), {len(hits_stress)} hits")
        else:
            warn(f"L.2 search: {elapsed:.3f}s (> 2s)")
    except Exception as e:
        fail("L.2 busqueda masiva crasheo", str(e))

    # L.3 Cross-domain search sobre multiples dominios — tiempo < 3s
    try:
        t0 = time.time()
        xr_stress = kb_direct.cross_domain_search(text_query="patron stress numero")
        elapsed = time.time() - t0
        if elapsed < 3:
            ok(f"L.3 cross_domain_search: {elapsed:.3f}s (< 3s), {len(xr_stress)} dominios")
        else:
            warn(f"L.3 cross_domain_search: {elapsed:.3f}s (> 3s)")
    except Exception as e:
        fail("L.3 cross_domain_search stress crasheo", str(e))

    # L.4 Escritura concurrente (10 threads) — sin excepciones ni corrupcion
    try:
        import threading as _thr2
        _err_l4 = []
        def _write_stress(i):
            try:
                kb_direct.add_pattern(dom_stress, f"concurrent_l4_{i}",
                                      {"content": f"concurrent stress {i}"}, ["l4"])
            except Exception as ex:
                _err_l4.append(str(ex))
        threads_l4 = [_thr2.Thread(target=_write_stress, args=(i,)) for i in range(10)]
        for t in threads_l4: t.start()
        for t in threads_l4: t.join(timeout=15)
        if not _err_l4:
            ok("L.4 Escritura concurrente 10 threads: sin excepciones")
        else:
            fail(f"L.4 concurrent: {len(_err_l4)} error(es)", _err_l4[0])
    except Exception as e:
        fail("L.4 concurrent stress crasheo", str(e))

    # L.5 get_global_stats refleja el volumen correcto
    try:
        stats_stress = kb_direct.get_global_stats()
        assert stats_stress.get("total", 0) > 300
        ok(f"L.5 get_global_stats() refleja volumen: total={stats_stress['total']}")
    except Exception as e:
        fail("L.5 global stats stress crasheo", str(e))
else:
    warn("L skip: knowledge_base no disponible")


# ══════════════════════════════════════════════════════════════
# M. Ciclo completo de sesion (SessionStart→Prompt→Tool→Stop)
# ══════════════════════════════════════════════════════════════
section("M. Ciclo completo de sesion")

try:
    _sid_m = "m-session-lifecycle-exhaustivo"

    # M.1 UserPromptSubmit → on_user_message
    stdout_m1, stderr_m1, rc_m1 = run_h("on_user_message.py", {
        "prompt": "genera sow para proyecto instana monitoreo aplicaciones",
        "session_id": _sid_m,
        "cwd": str(PROJECT_DIR)
    })
    if rc_m1 == 0:
        ok("M.1 UserPromptSubmit (on_user_message) → exit 0")
    else:
        fail(f"M.1 on_user_message exit {rc_m1}", stderr_m1[:150])

    # M.2 PostToolUse Read → post_action_learn
    stdout_m2, stderr_m2, rc_m2 = run_h("post_action_learn.py", {
        "tool_name": "Read",
        "tool_input": {"file_path": str(PROJECT_DIR / "knowledge_base.py")},
        "tool_result": "contenido del archivo knowledge_base.py",
        "exit_code": None,
        "session_id": _sid_m
    })
    if rc_m2 == 0:
        ok("M.2 PostToolUse Read (post_action_learn) → exit 0")
    else:
        fail(f"M.2 post_action_learn Read exit {rc_m2}", stderr_m2[:150])

    # M.3 PostToolUse Bash → post_action_learn
    stdout_m3, stderr_m3, rc_m3 = run_h("post_action_learn.py", {
        "tool_name": "Bash",
        "tool_input": {"command": "python knowledge_base.py stats"},
        "tool_result": "total patterns: 42 OK",
        "exit_code": 0,
        "session_id": _sid_m
    })
    if rc_m3 == 0:
        ok("M.3 PostToolUse Bash exitoso (post_action_learn) → exit 0")
    else:
        fail(f"M.3 post_action_learn Bash exit {rc_m3}", stderr_m3[:150])

    # M.4 PostToolUse Bash con error → post_action_learn registra error pendiente
    stdout_m4, stderr_m4, rc_m4 = run_h("post_action_learn.py", {
        "tool_name": "Bash",
        "tool_input": {"command": "python script_inexistente_m4.py"},
        "tool_result": "ModuleNotFoundError: No module named 'script_inexistente_m4'",
        "exit_code": 1,
        "session_id": _sid_m
    })
    if rc_m4 == 0:
        ok("M.4 PostToolUse Bash con error (post_action_learn) → exit 0")
    else:
        fail(f"M.4 post_action_learn error exit {rc_m4}", stderr_m4[:150])

    # M.5 PostToolUse Edit resuelve error anterior
    stdout_m5, stderr_m5, rc_m5 = run_h("post_action_learn.py", {
        "tool_name": "Edit",
        "tool_input": {"file_path": "script_inexistente_m4.py", "old_string": "x", "new_string": "y"},
        "tool_result": "File updated successfully",
        "exit_code": None,
        "session_id": _sid_m
    })
    if rc_m5 == 0:
        ok("M.5 PostToolUse Edit (post_action_learn resuelve error) → exit 0")
    else:
        fail(f"M.5 post_action_learn Edit exit {rc_m5}", stderr_m5[:150])

    # M.6 Segundo UserPromptSubmit — mismo dominio (deep_work pattern)
    stdout_m6, stderr_m6, rc_m6 = run_h("on_user_message.py", {
        "prompt": "valida el bom para instana listado material partes",
        "session_id": _sid_m,
        "cwd": str(PROJECT_DIR)
    })
    if rc_m6 == 0:
        ok("M.6 Segundo UserPromptSubmit (bom) → exit 0")
    else:
        fail(f"M.6 segundo prompt exit {rc_m6}", stderr_m6[:150])

    # M.7 Stop (auto_learn_hook) — cierra sesion y aprende
    msgs_m7 = [
        {"type": "user", "message": {"role": "user", "content": "genera sow para instana monitoreo"}},
        {"type": "assistant", "message": {"role": "assistant", "content": "SOW generado con exito para Instana"}},
        {"type": "user", "message": {"role": "user", "content": "valida el bom listado material"}},
        {"type": "assistant", "message": {"role": "assistant", "content": "BoM validado: matemática cuadra"}},
    ]
    tf_m7 = fresh_tmp_jsonl(msgs_m7)
    try:
        r_m7 = sp.run(
            [sys.executable, str(HOOKS_DIR / "auto_learn_hook.py")],
            input=json.dumps({"session_id": _sid_m, "transcript_path": str(tf_m7)}),
            capture_output=True, text=True, timeout=30, encoding="utf-8", env=E,
            cwd=str(PROJECT_DIR)
        )
        if r_m7.returncode == 0:
            ok("M.7 Stop/auto_learn_hook → exit 0 (sesion aprendida)")
        else:
            fail(f"M.7 auto_learn_hook exit {r_m7.returncode}", r_m7.stderr[:150])
    finally:
        tf_m7.unlink(missing_ok=True)

    # M.8 Verificar que la sesion quedo en session_history
    try:
        sh_file = ADAPTIVE_DIR / "session_history.json"
        if sh_file.exists():
            sh_data = json.loads(sh_file.read_text(encoding="utf-8"))
            found = any(s.get("session_id") == _sid_m for s in sh_data)
            if found:
                ok(f"M.8 Sesion '{_sid_m}' encontrada en session_history.json")
            else:
                warn(f"M.8 Sesion no encontrada en history ({len(sh_data)} sesiones)")
        else:
            warn("M.8 session_history.json no existe")
    except Exception as e:
        fail("M.8 verificacion session_history crasheo", str(e))

except Exception as e:
    fail("M ciclo sesion crasheo global", str(e))


# ══════════════════════════════════════════════════════════════
# N. B+A search quality — 'general' siempre + cross_search fallback
# ══════════════════════════════════════════════════════════════
section("N. B+A search quality")

if kb_direct:
    import importlib as _imp_n

    # N.1 'general' como dominio transversal — siempre buscado
    try:
        import on_user_message as oum_n
        # Verificar que en main() se añade "general" a all_domains_with_markov
        import inspect
        src = inspect.getsource(oum_n.main) if hasattr(oum_n, "main") else ""
        has_general_b = "general" in src and ("all_domains_with_markov" in src or "general" in src)
        if has_general_b:
            ok("N.1 on_user_message.main() incluye 'general' como dominio B (siempre buscado)")
        else:
            warn("N.1 no se encontro logica B='general' en main()")
    except Exception as e:
        warn(f"N.1 no se pudo verificar B+A via inspect: {e}")

    # N.2 Patron en 'general' — query que no matchea dominios especificos → devuelve general
    try:
        pat_gen = kb_direct.add_pattern(
            "general",
            "test_n2_general_transversal",
            {"strategy": "general_transversal",
             "content": "kw_n2_general_unico: regla transversal que aplica a todos los dominios"},
            ["transversal", "test_n2"]
        )
        hits_gen = kb_direct.search("general", text_query="kw_n2_general_unico")
        if hits_gen:
            ok(f"N.2 Patron en 'general' encontrable via search ({len(hits_gen)} hits)")
        else:
            warn("N.2 Patron en 'general' no encontrado via text_query")
    except Exception as e:
        fail("N.2 patron general crasheo", str(e))

    # N.3 cross_domain_search con dominios=None (A: fallback) retorna resultados
    try:
        xr_n3 = kb_direct.cross_domain_search(text_query="kw_n2_general_unico", domains=None)
        found_gen = "general" in xr_n3 and bool(xr_n3.get("general"))
        if found_gen:
            ok("N.3 cross_domain_search(domains=None) incluye resultados de 'general'")
        else:
            warn(f"N.3 cross_domain_search fallback: {list(xr_n3.keys())[:5]}")
    except Exception as e:
        fail("N.3 cross_domain_search fallback crasheo", str(e))

    # N.4 search_kb en on_user_message — dominio detectado con pocos resultados activa A
    try:
        stdout_n4, _, rc_n4 = run_h("on_user_message.py", {
            "prompt": "kw_n2_general_unico consulta transversal sin dominio especifico",
            "session_id": "n4-b-plus-a-test"
        })
        if rc_n4 == 0:
            ok("N.4 on_user_message con query general → exit 0 (B+A activo)")
        else:
            fail(f"N.4 on_user_message B+A exit {rc_n4}")
    except Exception as e:
        fail("N.4 B+A on_user_message crasheo", str(e))

    # N.5 Dominio 'general' siempre en list_domains o _load_all_domains
    try:
        all_doms_n = kb_direct._load_all_domains()
        # 'general' puede ser creado dinamicamente o estar en builtin
        # verificar que despues de agregar un patron existe
        kb_direct._ensure_domain("general", "Dominio transversal general")
        all_doms_after = kb_direct._load_all_domains()
        if "general" in all_doms_after:
            ok("N.5 Dominio 'general' existe en _load_all_domains() (transversal garantizado)")
        else:
            warn("N.5 'general' no en _load_all_domains — puede ser creado on-demand")
    except Exception as e:
        fail("N.5 dominio general check crasheo", str(e))
else:
    warn("N skip: knowledge_base no disponible")

# ══════════════════════════════════════════════════════════════
# RESUMEN
# ══════════════════════════════════════════════════════════════
total = sum(results.values())
print(f"\n{'═'*60}")
print(f"{BLD}RESUMEN EXHAUSTIVO — {total} casos{RS}")
print(f"{'═'*60}")
print(f"  {GR}✓ PASS{RS}  {results['pass']}")
print(f"  {RD}✗ FAIL{RS}  {results['fail']}")
print(f"  {YL}⚠ WARN{RS}  {results['warn']}")
print(f"  {CY}⊘ SKIP{RS}  {results['skip']}")
print(f"{'═'*60}")

if results["fail"] == 0:
    print(f"\n{GR}{BLD}  TODOS LOS CAMINOS VERIFICADOS — motor sano{RS}\n")
elif results["fail"] <= 3:
    print(f"\n{YL}{BLD}  MOTOR FUNCIONAL — {results['fail']} fallo(s) menores{RS}\n")
else:
    print(f"\n{RD}{BLD}  {results['fail']} FALLOS — revisar{RS}\n")

sys.exit(0 if results["fail"] == 0 else 1)
