"""
test_hooks.py — Verificación completa del sistema de hooks
===========================================================
Ejecutar: python .claude/hooks/test_hooks.py

Verifica:
1. Que read_transcript() parsea el formato real del JSONL
2. Que extract_user_messages() filtra system messages
3. Que extract_tool_usage() detecta Read, Edit, Write, Bash por separado
4. Que session_start_kb.py genera output sin errores
5. Que la última sesión guardada tiene datos reales (no 0s)
"""

import sys
import json
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(Path(__file__).parent))

PASSED = 0
FAILED = 0


def test(name, condition, detail=""):
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  [PASS] {name}")
    else:
        FAILED += 1
        print(f"  [FAIL] {name} — {detail}")


def main():
    global PASSED, FAILED
    print("=" * 60)
    print("  TEST HOOKS — Verificación completa")
    print("=" * 60)

    # ── Test 1: Encontrar un transcript JSONL real ──
    print("\n1. Buscando transcript JSONL...")
    # Buscar en varias ubicaciones posibles
    possible_dirs = [
        Path.home() / "AppData" / "Local" / "ClaudeCode" / ".claude" / "projects",
        Path(r"C:\Users\ntoledo\AppData\Local\ClaudeCode\.claude\projects"),
    ]
    transcripts = []
    for projects_dir in possible_dirs:
        if projects_dir.exists():
            transcripts = list(projects_dir.rglob("*.jsonl"))
            if transcripts:
                break
    # Tomar el más reciente
    transcripts.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    if not transcripts:
        print("  [SKIP] No se encontró ningún transcript JSONL")
        return

    transcript_path = transcripts[0]
    print(f"  Usando: {transcript_path.name} ({transcript_path.stat().st_size // 1024}KB)")

    # ── Test 2: read_transcript parsea correctamente ──
    print("\n2. Testing read_transcript()...")
    from auto_learn_hook import read_transcript
    messages = read_transcript(str(transcript_path))
    test("Mensajes cargados > 0", len(messages) > 0, f"got {len(messages)}")

    if messages:
        first = messages[0]
        test("Primer mensaje tiene 'role'", "role" in first, f"keys: {list(first.keys())}")
        test("Primer mensaje tiene 'content'", "content" in first, f"keys: {list(first.keys())}")

        roles = set(m.get("role", "") for m in messages)
        test("Hay mensajes role=user", "user" in roles, f"roles encontrados: {roles}")
        test("Hay mensajes role=assistant", "assistant" in roles, f"roles encontrados: {roles}")

    # ── Test 3: extract_user_messages filtra correctamente ──
    print("\n3. Testing extract_user_messages()...")
    from auto_learn_hook import extract_user_messages
    user_msgs = extract_user_messages(messages)
    test("User messages > 0", len(user_msgs) > 0, f"got {len(user_msgs)}")

    # Verificar que no hay system messages
    system_leaked = [m for m in user_msgs if m.startswith("<task-notification")
                     or m.startswith("<system-reminder")]
    test("Sin system messages filtrados", len(system_leaked) == 0,
         f"{len(system_leaked)} system msgs leaked")

    # ── Test 4: extract_tool_usage detecta herramientas ──
    print("\n4. Testing extract_tool_usage()...")
    from auto_learn_hook import extract_tool_usage
    tools = extract_tool_usage(messages)
    total_tools = (len(tools["files_read"]) + len(tools["files_edited"])
                   + len(tools["files_created"]) + len(tools["commands_run"]))
    test("Herramientas detectadas > 0", total_tools > 0, f"got {total_tools}")

    # Verificar que Edit no es bloqueado por Read
    if tools["files_read"] and tools["files_edited"]:
        overlap = set(tools["files_read"]) & set(tools["files_edited"])
        test("Archivos leídos Y editados detectados", len(overlap) > 0,
             f"read={len(tools['files_read'])}, edit={len(tools['files_edited'])}, overlap={len(overlap)}")

    # ── Test 5: session_start_kb genera output ──
    print("\n5. Testing session_start_kb.py output...")
    try:
        from session_start_kb import main as start_main, load_session_history
        # No ejecutar main() porque imprime a stdout, solo verificar componentes
        history = load_session_history()
        test("Session history cargable", isinstance(history, list), f"type: {type(history)}")
        test("Session history no vacía", len(history) > 0, f"got {len(history)} sessions")
    except Exception as e:
        test("session_start_kb importable", False, str(e))

    # ── Test 6: Última sesión tiene datos reales ──
    print("\n6. Verificando última sesión guardada...")
    if history:
        last = history[-1]
        metrics = last.get("metrics", {})
        total_msgs = metrics.get("total_messages", 0)
        user_count = metrics.get("user_messages", 0)
        files_count = metrics.get("files_touched", 0)
        cmds_count = metrics.get("commands_count", 0)
        extracted = user_count + files_count + cmds_count

        test(f"Total messages > 0", total_msgs > 0, f"got {total_msgs}")

        if total_msgs > 10:
            test(f"Datos extraídos > 0 (msgs={user_count}, files={files_count}, cmds={cmds_count})",
                 extracted > 0,
                 "HOOK SILENCIOSAMENTE FALLANDO — parser no entiende el formato")

        summary = last.get("summary", "")
        test("Summary no es genérico", "sin mensajes" not in summary.lower() if summary else False,
             f"summary: {summary[:80]}")

    # ── Resultado ──
    print("\n" + "=" * 60)
    total = PASSED + FAILED
    if FAILED == 0:
        print(f"  RESULTADO: {PASSED}/{total} tests PASSED — Hooks funcionando correctamente")
    else:
        print(f"  RESULTADO: {PASSED}/{total} passed, {FAILED} FAILED — Revisar los fallos arriba")
    print("=" * 60)


if __name__ == "__main__":
    main()
