import requests
import datetime
from pathlib import Path

BASE_URL = "https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2/resolve/main"
MODEL_DIR = Path(r"C:\Chance1\models\multilingual")
LOG_PATH = Path(__file__).parent / "download_model.log"

ARCHIVOS = [
    "config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "sentence_bert_config.json",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "model.safetensors",
    "1_Pooling/config.json",
]

log_lines = []

def log(msg):
    print(msg)
    log_lines.append(msg)

def guardar_log():
    with open(LOG_PATH, 'w', encoding='utf-8') as f:
        f.write(f"=== download_model.py - {datetime.datetime.now()} ===\n\n")
        for l in log_lines:
            f.write(l + "\n")

def descargar(nombre):
    url = f"{BASE_URL}/{nombre}"
    destino = MODEL_DIR / nombre
    destino.parent.mkdir(parents=True, exist_ok=True)

    if destino.exists():
        log(f"  Ya existe: {nombre}")
        return

    log(f"  Descargando: {nombre}")
    try:
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
    except Exception as e:
        log(f"  ERROR al descargar {nombre}: {e}")
        guardar_log()
        raise

    total = int(r.headers.get('content-length', 0))
    descargado = 0

    with open(destino, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024 * 256):
            if chunk:
                f.write(chunk)
                descargado += len(chunk)
                if total:
                    pct = descargado / total * 100
                    mb = descargado / 1024 / 1024
                    print(f"\r    {pct:.1f}% ({mb:.1f} MB)", end='', flush=True)

    msg = f"  Completado: {nombre} ({descargado/1024/1024:.1f} MB)"
    print(f"\r{msg}")
    log_lines.append(msg)

MODEL_DIR.mkdir(parents=True, exist_ok=True)
log(f"Destino: {MODEL_DIR}\n")

for archivo in ARCHIVOS:
    descargar(archivo)
    guardar_log()

log("\nDescarga completa. Probando carga del modelo...")
guardar_log()

from sentence_transformers import SentenceTransformer
import numpy as np
from numpy.linalg import norm

m = SentenceTransformer(str(MODEL_DIR))
log("Modelo cargado OK")

s = m.encode(['pipeline CRM', 'oportunidad SAP', 'error PIL', 'ModuleNotFoundError cv2'])
def sim(a, b): return np.dot(a, b) / (norm(a) * norm(b))

log(f'\nCRM vs SAP:  {sim(s[0], s[1]):.3f}  (esperado > 0.4)')
log(f'PIL vs cv2:  {sim(s[2], s[3]):.3f}  (esperado > 0.5)')
log(f'CRM vs PIL:  {sim(s[0], s[2]):.3f}  (esperado < 0.2)')
log(f'\nLog guardado en: {LOG_PATH}')

guardar_log()
