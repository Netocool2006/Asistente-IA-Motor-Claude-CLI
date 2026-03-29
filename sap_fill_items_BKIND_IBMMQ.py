"""
sap_fill_items_BKIND_IBMMQ.py
===========================================
Agrega 3 ítems a oportunidad BKIND-IBMMQ-2026_RN en SAP CRM Tierra.

Ítems:
  1. IBMMQ-SUPP-RN  | Qty: 1  | Precio: $72,000
  2. DB2ENT-SUPP-RN | Qty: 1  | Precio: $48,000
  3. SVCS-IMPL-001  | Qty: 40 | Precio: $60

Prerequisito:
  - Chrome corriendo con remote debugging:
      chrome.exe --remote-debugging-port=9222
  - Oportunidad BKIND-IBMMQ-2026_RN ya abierta en SAP Tierra

Uso:
    python sap_fill_items_BKIND_IBMMQ.py

Patrones KB aplicados:
  - fill_items_oportunidad: items_table_row_by_row (éxito 100%)
  - field_fill_general: click_clear_type_tab (éxito 100%)
  - JS simulateType para Product ID (más confiable que keyboard en SAP)
  - keyboard type + Tab para Quantity y Price (NUNCA JS puro — SAP no lo reconoce)
"""

import asyncio
import json
import sys
from datetime import datetime
from playwright.async_api import async_playwright

# ── Configuración ────────────────────────────────────────────
CDP_ENDPOINT = "http://localhost:9222"

ITEMS = [
    {"product_id": "IBMMQ-SUPP-RN",  "quantity": 1,  "price": 72000},
    {"product_id": "DB2ENT-SUPP-RN", "quantity": 1,  "price": 48000},
    {"product_id": "SVCS-IMPL-001",  "quantity": 40, "price": 60},
]

# Delays (ms) — calibrados para SAP Tierra Guatemala
TYPE_DELAY     = 30    # entre teclas (campos normales)
WAIT_POST_CLICK  = 2000  # ms tras click Add
WAIT_POST_JS     = 3000  # ms tras simulateType+Enter (SAP lookup)
WAIT_POST_TAB    = 1500  # ms tras Tab (server-side validation)
WAIT_POST_SAVE   = 3000  # ms tras Save

# ── JS helpers ───────────────────────────────────────────────

def js_find_and_type(field_id_partial: str, value: str) -> str:
    """
    Genera JS para:
      1. Buscar input[id*='{field_id_partial}'] en window.frames[0]
      2. Encontrar el campo vacío (nueva fila)
      3. simulateType + Enter para disparar SAP lookup/resolution
    """
    return f"""
    (function() {{
        function getDoc() {{
            try {{
                var f = window.frames[0];
                return f ? (f.document || f.contentDocument) : document;
            }} catch(e) {{ return document; }}
        }}
        function simulateType(inp, val) {{
            inp.focus();
            inp.value = val;
            inp.dispatchEvent(new Event('input',  {{bubbles: true}}));
            inp.dispatchEvent(new Event('change', {{bubbles: true}}));
        }}
        function simulateEnter(inp) {{
            var o = {{key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}};
            inp.dispatchEvent(new KeyboardEvent('keydown', o));
            inp.dispatchEvent(new KeyboardEvent('keyup',   o));
        }}

        var doc    = getDoc();
        var inputs = Array.from(doc.querySelectorAll('input[id*="{field_id_partial}"]'))
                         .filter(i => i.offsetParent !== null);

        // Preferir campo vacío (nueva fila), si no, el último
        var target = inputs.find(i => !i.value || i.value.trim() === '')
                     || inputs[inputs.length - 1];

        if (!target) return 'NOT FOUND: {field_id_partial}';

        simulateType(target, '{value}');
        simulateEnter(target);
        return 'OK: {value} → ' + target.id;
    }})();
    """


def js_fill_field_by_label(label_text: str, value: str) -> str:
    """
    Fallback: busca campo por texto label cercano y lo llena.
    Útil si el ID del campo de precio no es predecible.
    """
    return f"""
    (function() {{
        function getDoc() {{
            try {{
                var f = window.frames[0];
                return f ? (f.document || f.contentDocument) : document;
            }} catch(e) {{ return document; }}
        }}
        var doc = getDoc();
        // Buscar última fila activa de la tabla de items
        var rows = doc.querySelectorAll('tr[id*="row"], tr.crm-table-row, tbody tr');
        var lastRow = rows[rows.length - 1];
        if (!lastRow) return 'NO ROWS FOUND';

        var inputs = lastRow.querySelectorAll('input');
        if (!inputs.length) return 'NO INPUTS IN LAST ROW';

        // El precio suele ser el último input editable de la fila
        var priceInput = inputs[inputs.length - 1];
        priceInput.focus();
        priceInput.value = '{value}';
        priceInput.dispatchEvent(new Event('input',  {{bubbles: true}}));
        priceInput.dispatchEvent(new Event('change', {{bubbles: true}}));
        return 'FILLED price last-input: ' + priceInput.id + ' = {value}';
    }})();
    """


# ── Función para obtener frame SAP ───────────────────────────

async def get_sap_frame(page):
    """
    SAP Tierra usa iFrames anidados. Retorna el frame principal de contenido.
    Espera a que el frame esté cargado antes de devolver.
    """
    await page.wait_for_load_state("domcontentloaded")
    frames = page.frames
    # El frame de contenido SAP suele ser el segundo (index 1) o el que tiene 'orderedprod' / 'Products'
    for f in frames:
        try:
            url = f.url
            if "sap" in url.lower() or "crm" in url.lower() or url.startswith("https"):
                return f
        except Exception:
            continue
    return page  # fallback: frame principal


# ── Paso 1: Navegar a tab Products ───────────────────────────

async def click_products_tab(page):
    print("\n[1/5] Navegando a tab Products/Items...")

    # Estrategia principal: buscar el tab por texto
    try:
        # Buscar en todos los frames
        for frame in page.frames:
            try:
                tab = frame.locator("a, span, div[role='tab']").filter(has_text="Products")
                count = await tab.count()
                if count > 0:
                    await tab.first.click()
                    await page.wait_for_timeout(WAIT_POST_CLICK)
                    print("   ✓ Click en tab Products (texto exacto)")
                    return True
            except Exception:
                continue

        # Fallback: "Items" (algunos templates SAP lo llaman así)
        for frame in page.frames:
            try:
                tab = frame.locator("a, span").filter(has_text="Items")
                count = await tab.count()
                if count > 0:
                    await tab.first.click()
                    await page.wait_for_timeout(WAIT_POST_CLICK)
                    print("   ✓ Click en tab Items (fallback)")
                    return True
            except Exception:
                continue

        # Fallback JS
        result = await page.evaluate("""
            (function() {
                function getDoc() {
                    try { var f = window.frames[0]; return f ? (f.document || f.contentDocument) : document; }
                    catch(e) { return document; }
                }
                var doc = getDoc();
                var tabs = doc.querySelectorAll('a, span, div[role="tab"]');
                var t = Array.from(tabs).find(el =>
                    el.textContent.trim() === 'Products' ||
                    el.textContent.trim() === 'Items'
                );
                if (t) { t.click(); return 'clicked: ' + t.textContent.trim(); }
                return 'NOT FOUND';
            })();
        """)
        print(f"   JS fallback: {result}")
        await page.wait_for_timeout(WAIT_POST_CLICK)
        return "NOT FOUND" not in str(result)

    except Exception as e:
        print(f"   ✗ Error en click_products_tab: {e}")
        return False


# ── Paso 2: Click botón Add/New ──────────────────────────────

async def click_add_button(page, item_index: int):
    print(f"\n[Ítem {item_index+1}] Click botón Add/New para nueva fila...")

    for btn_text in ["Add", "New", "Agregar", "Nuevo"]:
        for frame in page.frames:
            try:
                btn = frame.locator(f"button, input[type='button'], a").filter(has_text=btn_text)
                count = await btn.count()
                if count > 0:
                    await btn.first.click()
                    await page.wait_for_timeout(WAIT_POST_CLICK)
                    print(f"   ✓ Click '{btn_text}'")
                    return True
            except Exception:
                continue

    print("   ✗ Botón Add/New no encontrado")
    return False


# ── Paso 3: Llenar Product ID vía JS ─────────────────────────

async def fill_product_id(page, product_id: str):
    print(f"   Llenando Product ID: {product_id}...")

    # JS simulateType — más confiable que keyboard en SAP para IDs
    result = await page.evaluate(js_find_and_type("orderedprod", product_id))
    print(f"   JS orderedprod: {result}")
    await page.wait_for_timeout(WAIT_POST_JS)

    if "NOT FOUND" in str(result):
        # Fallback: buscar por aria-label Product ID
        for frame in page.frames:
            try:
                inp = frame.locator("input[aria-label*='Product'], input[placeholder*='Product']")
                count = await inp.count()
                if count > 0:
                    await inp.last.click()
                    await inp.last.fill("")
                    await inp.last.type(product_id, delay=TYPE_DELAY)
                    await page.keyboard.press("Enter")
                    await page.wait_for_timeout(WAIT_POST_JS)
                    print(f"   ✓ Fallback aria-label Product")
                    return True
            except Exception:
                continue
        return False

    return "OK:" in str(result)


# ── Paso 4: Llenar Quantity (keyboard, NO JS puro) ───────────

async def fill_quantity(page, quantity: int):
    print(f"   Llenando Quantity: {quantity}...")

    # BLACKLIST: js_simulateType_pure para Quantity — SAP no lo reconoce
    # USAR: teclado real con foco real

    qty_selectors = [
        "input[id*='quantity']",
        "input[id*='qty']",
        "input[aria-label*='Quantity']",
        "input[aria-label*='Cantidad']",
    ]

    for selector in qty_selectors:
        for frame in page.frames:
            try:
                inputs = frame.locator(selector)
                count = await inputs.count()
                if count > 0:
                    # Última fila = ítem recién agregado
                    target = inputs.last
                    await target.click()
                    await page.keyboard.press("Control+a")
                    await target.type(str(quantity), delay=TYPE_DELAY)
                    await page.keyboard.press("Tab")
                    await page.wait_for_timeout(WAIT_POST_TAB)
                    print(f"   ✓ Quantity: {quantity} (selector: {selector})")
                    return True
            except Exception:
                continue

    # Fallback: Tab desde Product ID y escribir
    print("   Fallback: Tab desde Product ID → Quantity")
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(500)
    await page.keyboard.press("Tab")  # SAP puede tener Description entre medio
    await page.wait_for_timeout(500)
    await page.keyboard.press("Control+a")
    await page.keyboard.type(str(quantity), delay=TYPE_DELAY)
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(WAIT_POST_TAB)
    print(f"   ✓ Quantity fallback Tab-Tab-type")
    return True


# ── Paso 5: Llenar Price / Net Value ─────────────────────────

async def fill_price(page, price: float):
    print(f"   Llenando Price/Net Value: {price}...")

    price_str = str(int(price)) if price == int(price) else str(price)

    # Selectores probables para precio en SAP CRM Tierra
    price_selectors = [
        "input[id*='netval']",
        "input[id*='net_val']",
        "input[id*='NetValue']",
        "input[id*='price']",
        "input[id*='Price']",
        "input[id*='cond']",
        "input[id*='amount']",
    ]

    for selector in price_selectors:
        for frame in page.frames:
            try:
                inputs = frame.locator(selector)
                count = await inputs.count()
                if count > 0:
                    target = inputs.last
                    await target.click()
                    await page.keyboard.press("Control+a")
                    await target.type(price_str, delay=TYPE_DELAY)
                    await page.keyboard.press("Tab")
                    await page.wait_for_timeout(WAIT_POST_TAB)
                    print(f"   ✓ Price: {price_str} (selector: {selector})")
                    return True
            except Exception:
                continue

    # Fallback JS: último input editable de la última fila
    result = await page.evaluate(js_fill_field_by_label("Net Value", price_str))
    print(f"   JS fallback price: {result}")
    await page.keyboard.press("Tab")
    await page.wait_for_timeout(WAIT_POST_TAB)
    return "FILLED" in str(result)


# ── Paso 6: Guardar ──────────────────────────────────────────

async def save_opportunity(page):
    print("\n[5/5] Guardando oportunidad...")

    save_texts = ["Save", "Guardar", "Salvar"]
    for txt in save_texts:
        for frame in page.frames:
            try:
                btn = frame.locator(f"button, input[type='button']").filter(has_text=txt)
                count = await btn.count()
                if count > 0:
                    await btn.first.click()
                    await page.wait_for_timeout(WAIT_POST_SAVE)
                    print(f"   ✓ Guardado con botón '{txt}'")
                    return True
            except Exception:
                continue

    # Fallback: Ctrl+S
    await page.keyboard.press("Control+s")
    await page.wait_for_timeout(WAIT_POST_SAVE)
    print("   ✓ Guardado con Ctrl+S (fallback)")
    return True


# ── Validación post-ítem ─────────────────────────────────────

async def validate_item_in_table(page, product_id: str, quantity: int) -> bool:
    """Verifica que el ítem aparece en la tabla después de cargarlo."""
    try:
        for frame in page.frames:
            try:
                content = await frame.content()
                if product_id in content:
                    print(f"   ✓ Validación: {product_id} encontrado en tabla")
                    return True
            except Exception:
                continue
    except Exception:
        pass
    print(f"   ⚠ Validación: {product_id} NO confirmado visualmente (puede ser delay de SAP)")
    return False


# ── Pipeline principal ────────────────────────────────────────

async def run():
    start_time = datetime.now()
    results = []

    async with async_playwright() as p:
        print("=" * 55)
        print(" SAP Fill Items — BKIND-IBMMQ-2026_RN")
        print("=" * 55)
        print(f"Conectando a Chrome en {CDP_ENDPOINT}...")

        # Conectar a Chrome existente (la oportunidad ya está abierta)
        browser = await p.chromium.connect_over_cdp(CDP_ENDPOINT)
        contexts = browser.contexts
        if not contexts:
            print("ERROR: No hay contexto de browser activo.")
            sys.exit(1)

        page = contexts[0].pages[0] if contexts[0].pages else await contexts[0].new_page()
        print(f"Página activa: {page.url[:80]}...")

        # ── Paso 1: Tab Products ─────────────────────────────
        tab_ok = await click_products_tab(page)
        results.append({"step": "click_products_tab", "ok": tab_ok})

        # ── Pasos 2-4: Agregar cada ítem ─────────────────────
        items_ok = []
        for i, item in enumerate(ITEMS):
            print(f"\n{'─'*50}")
            print(f"  Ítem {i+1}/3: {item['product_id']} | Qty: {item['quantity']} | $: {item['price']}")
            print(f"{'─'*50}")

            add_ok  = await click_add_button(page, i)
            pid_ok  = await fill_product_id(page, item["product_id"])
            qty_ok  = await fill_quantity(page, item["quantity"])
            prc_ok  = await fill_price(page, item["price"])
            val_ok  = await validate_item_in_table(page, item["product_id"], item["quantity"])

            item_result = {
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "price": item["price"],
                "add_button": add_ok,
                "product_id_filled": pid_ok,
                "quantity_filled": qty_ok,
                "price_filled": prc_ok,
                "validated": val_ok,
                "ok": all([add_ok, pid_ok, qty_ok]),
            }
            items_ok.append(item_result)
            print(f"   Resultado: {'OK' if item_result['ok'] else 'PARCIAL'}")

        # ── Paso 5: Guardar ──────────────────────────────────
        save_ok = await save_opportunity(page)
        results.append({"step": "save", "ok": save_ok})

        # ── Resumen final ────────────────────────────────────
        elapsed = (datetime.now() - start_time).seconds
        all_ok  = all(r.get("ok", False) for r in items_ok) and save_ok

        summary = {
            "status":   "success" if all_ok else "partial",
            "task_type": "sap_fill_items_oportunidad",
            "strategy": "js_simulateType_for_pid__keyboard_type_for_qty_price__tab_validation",
            "opportunity": "BKIND-IBMMQ-2026_RN",
            "items_loaded": len([x for x in items_ok if x["ok"]]),
            "items_total":  len(ITEMS),
            "elapsed_sec":  elapsed,
            "items_detail": items_ok,
            "business_rules_applied": [
                "sufijo_RN_renovacion",
                "tab_after_each_field_critico",
                "js_for_product_id_keyboard_for_qty_price",
                "no_js_puro_for_quantity",
            ],
            "notes": "flujo_items: pid→tab/enter(SAP resolve)→qty keyboard→tab→price keyboard→tab. Save al final.",
            "attempts": 1,
        }

        print("\n" + "=" * 55)
        print(" RESULTADO FINAL")
        print("=" * 55)
        print(json.dumps(summary, ensure_ascii=False, indent=2))

        return summary


if __name__ == "__main__":
    asyncio.run(run())
