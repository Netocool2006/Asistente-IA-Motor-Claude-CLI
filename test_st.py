import datetime
from pathlib import Path
import numpy as np
from numpy.linalg import norm
from sentence_transformers import SentenceTransformer

print("Cargando modelo multilingue...")
print("(primera vez descarga ~400MB, espera)")
print("-" * 50)

m = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2', show_progress_bar=True)

print("-" * 50)
print("Modelo cargado. Calculando similitudes...\n")

frases = ['pipeline CRM', 'oportunidad SAP', 'error PIL', 'ModuleNotFoundError cv2']
s = m.encode(frases, show_progress_bar=True)

def sim(a, b):
    return np.dot(a, b) / (norm(a) * norm(b))

resultados = [
    f'CRM vs SAP:  {sim(s[0], s[1]):.3f}  (esperado > 0.4)',
    f'PIL vs cv2:  {sim(s[2], s[3]):.3f}  (esperado > 0.5)',
    f'CRM vs PIL:  {sim(s[0], s[2]):.3f}  (esperado < 0.2)',
]

print()
for r in resultados:
    print(r)

log_path = Path(__file__).parent / 'test_st.log'
with open(log_path, 'w', encoding='utf-8') as f:
    f.write(f'=== test_st.py - {datetime.datetime.now()} ===\n')
    f.write(f'Modelo: paraphrase-multilingual-MiniLM-L12-v2\n\n')
    for r in resultados:
        f.write(r + '\n')

print(f'\nLog guardado en: {log_path}')
