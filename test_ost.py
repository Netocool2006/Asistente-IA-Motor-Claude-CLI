import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from ost_search import get_ost_info, search_ost_emails

info = get_ost_info()
print("OST info:", info)

q = sys.argv[1] if len(sys.argv) > 1 else "8030027307"
print(f"\nBuscando: {q}")
import time
t0 = time.time()
results = search_ost_emails(q, max_results=5)
elapsed = round(time.time() - t0, 1)
print(f"Resultados: {len(results)} en {elapsed}s")
for r in results:
    print(f"  Subject: {r['subject']}")
    print(f"  Preview: {r['preview'][:120]}")
    print()
