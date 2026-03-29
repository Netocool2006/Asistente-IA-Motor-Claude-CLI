"""
sap_fill_items_BKIND_IBMMQ_2026_RN.py
=======================================
Agrega 3 ítems en la oportunidad BKIND-IBMMQ-2026_RN (ya abierta en el browser).

Prerequisito: La oportunidad está abierta en Chrome con CDP habilitado.
Conectar a Chrome existente:
    chrome.exe --remote-debugging-port=9222

Uso:
    python sap_fill_items_BKIND_IBMMQ_2026_RN.py

Ítems a cargar:
    1. IBMMQ-SUPP-RN  | Qty: 1  | Precio: $72,000
    2. DB2ENT-SUPP-RN | Qty: 1  | Precio: $48,000
    3. SVCS-IMPL-001  | Qty: 40 | Precio: $60

Patrones KB aplicados (éxito 100%):
    - orderedprod: JS simulateType + Enter (NO .fill directo)
    - Quantity: triple_click real + type + Tab (NO JS puro para Qty)
    - Price (netval): JS simulateType + Tab
    - Tab entre campos: CRITICO para validación server-side SAP
    - iFrame: window.frames[0] detectado dinámicamente
"""

import asyncio
import json
from playwright.async_api import async_playwright, Page, Frame

# ─── Configuración ────────────────────────────────────────────────────────────
CDP_URL = "http://localhost:9222"   # Chrome debe tener --remote-debugging-port=9222

ITEMS = [
    {"part_no": "IBMMQ-SUPP-RN",  "qty": 1,  "price": 72000},
    {"part_no": "DB2ENT-SUPP-RN", "qty": 1,  "price": 48000},
    {"part_no": "SVCS-IMPL-001",  "qty": 40, "price": 60},
]

# ─── Helpers JS (patrones del KB) ─────────────────────────────────────────────

JS_FIND_FRAME = """
    (function() {
        // SAP Tierra usa iFrames anidados — detectar dinámicamente
        function getDeepFrame(win) {
            if (win.frames.length > 0) return win.frames[0];
            return win;
        }
        return getDeepFrame(window);
    })();
"""

JS_SIMULATE_TYPE = """
    function simulateType(inp, text) {
        inp.focus();
        inp.value = '';
        inp.value = text;
        inp.dispatchEvent(new Event('input',  {bubbles: true}));
        inp.dispatchEvent(new Event('change', {bubbles: true}));
    }
    function simulateKey(inp, key, keyCode) {
        var opts = {key: key, code: key, keyCode: keyCode, which: keyCode, bubbles: true};
        inp.dispatchEvent(new KeyboardEvent('keydown', opts));
        inp.dispatchEvent(new KeyboardEvent('keypress', opts));
        inp.dispatchEvent(new KeyboardEvent('keyup',   opts));
    }
    function simulateEnter(inp) { simulateKey(inp, 'Enter', 13); }
    function simulateTab(inp)   { simulateKey(inp, 'Tab',   9); }
"""


async def wait_ms(page: Page, ms: int):
    await page.wait_for_timeout(ms)


# ─── PASO 1: Click tab Products ───────────────────────────────────────────────

async def click_products_tab(page: Page):
    """
    Navega al tab Products/Items dentro de la oportunidad.
    Estrategia: find link text → click → fallback JS querySelector en iFrame.
    """
    print("[1/4] Navegando al tab Products...")

    # Intento 1: locator directo (funciona si el tab está en el DOM principal)
    tab = page.get_by_role("link", name="Products").first
    try:
        await tab.click(timeout=5000)
        await wait_ms(page, 3000)
        print("      ✓ Tab Products clickeado (locator directo)")
        return
    except Exception:
        pass

    # Intento 2: texto parcial "Items"
    tab2 = page.get_by_role("link", name="Items").first
    try:
        await tab2.click(timeout=3000)
        await wait_ms(page, 3000)
        print("      ✓ Tab Items clickeado (locator directo)")
        return
    except Exception:
        pass

    # Fallback: JS en el iFrame (patrón del KB sap_click_products_tab)
    result = await page.evaluate("""
        (function() {
            function searchInFrame(win) {
                var d = win.document || win;
                var tabs = d.querySelectorAll('a, span, div[role="tab"], td[role="tab"]');
                var target = Array.from(tabs).find(el =>
                    el.textContent.trim() === 'Products' ||
                    el.textContent.trim() === 'Items'
                );
                if (target) { target.click(); return 'clicked: ' + target.textContent.trim(); }
                return null;
            }
            // Probar frame principal + primer sub-frame
            var res = searchInFrame(window);
            if (res) return res;
            if (window.frames[0]) return searchInFrame(window.frames[0]);
            return 'NOT FOUND';
        })()
    """)
    await wait_ms(page, 3000)
    if result == "NOT FOUND":
        raise RuntimeError("No se encontró el tab Products/Items. Verificar que la oportunidad esté abierta.")
    print(f"      ✓ Tab clickeado via JS fallback: {result}")


# ─── PASO 2: Llenar Product ID (orderedprod) ──────────────────────────────────

async def fill_product_id(page: Page, part_no: str):
    """
    Llena el campo Product ID de la nueva fila.
    Selector: input[id*='orderedprod'] — el que esté vacío.
    Técnica KB: JS simulateType + Enter → esperar 3s resolución SAP.
    """
    js_fill = f"""
        {JS_SIMULATE_TYPE}
        (function() {{
            function findInFrame(d) {{
                var inputs = d.querySelectorAll('input[id*="orderedprod"], input[id*="ORDEREDPROD"]');
                return Array.from(inputs).filter(i => i.offsetParent !== null);
            }}
            var inputs = findInFrame(document);
            if (!inputs.length && window.frames[0]) {{
                inputs = findInFrame(window.frames[0].document);
            }}
            // Preferir el campo vacío (nueva fila)
            var target = inputs.find(i => !i.value || i.value.trim() === '');
            if (!target) target = inputs[inputs.length - 1];  // Fallback: último
            if (!target) return 'NO orderedprod FOUND';
            simulateType(target, '{part_no}');
            simulateEnter(target);
            return 'filled orderedprod: {part_no}';
        }})()
    """
    result = await page.evaluate(js_fill)
    print(f"      orderedprod → {result}")
    # Esperar 3s para resolución SAP (valida el código contra catálogo)
    await wait_ms(page, 3000)


# ─── PASO 3: Llenar Quantity (requiere foco real, NO JS puro) ─────────────────

async def fill_quantity(page: Page, qty: int, part_no: str):
    """
    Llena el campo Quantity.
    BLACKLIST KB: NO usar js_simulateType_pure para Quantity.
    Técnica: triple_click (foco real) + type + Tab para validación server-side.
    """
    # Buscar el campo qty con selector parcial de ID
    qty_selectors = [
        "input[id*='qty']",
        "input[id*='QTY']",
        "input[id*='Qty']",
        "input[id*='quantity']",
        "input[id*='QUANTITY']",
    ]

    qty_input = None
    for sel in qty_selectors:
        candidates = page.locator(sel)
        count = await candidates.count()
        if count > 0:
            # Buscar el visible y vacío/default (nueva fila)
            for i in range(count):
                loc = candidates.nth(i)
                if await loc.is_visible():
                    qty_input = loc
                    break
        if qty_input:
            break

    # Fallback: buscar en frames
    if not qty_input:
        frames = page.frames
        for frame in frames[1:]:  # Saltar frame principal
            for sel in qty_selectors:
                candidates = frame.locator(sel)
                count = await candidates.count()
                if count > 0:
                    for i in range(count):
                        loc = candidates.nth(i)
                        if await loc.is_visible():
                            qty_input = loc
                            break
                if qty_input:
                    break
            if qty_input:
                break

    if not qty_input:
        print(f"      ⚠ Campo Quantity no localizado — usando Tab desde orderedprod")
        # Estrategia alternativa: Tab desde el campo actual hasta Qty
        await page.keyboard.press("Tab")
        await wait_ms(page, 500)
        await page.keyboard.press("Tab")
        await wait_ms(page, 500)
        await page.keyboard.type(str(qty), delay=50)
        await page.keyboard.press("Tab")
        await wait_ms(page, 2000)
        print(f"      qty (Tab nav) → {qty}")
        return

    # Foco real + triple_click + type + Tab
    await qty_input.scroll_into_view_if_needed()
    await qty_input.triple_click()
    await wait_ms(page, 300)
    await qty_input.type(str(qty), delay=30)
    await page.keyboard.press("Tab")           # CRITICO: validación server-side
    await wait_ms(page, 2000)
    print(f"      qty → {qty} (triple_click + type + Tab)")


# ─── PASO 4: Llenar Price / Net Value ─────────────────────────────────────────

async def fill_price(page: Page, price: int, part_no: str):
    """
    Llena el campo Net Value / Price.
    Selector objetivo: input[id*='netval'] o input[id*='NET_VALUE'].
    Técnica: JS simulateType + Tab (igual que orderedprod pero para precio).
    """
    # Intentar locator de Playwright primero
    price_selectors = [
        "input[id*='netval']",
        "input[id*='NET_VALUE']",
        "input[id*='NetVal']",
        "input[id*='price']",
        "input[id*='PRICE']",
        "input[id*='NetPrice']",
    ]

    price_input = None
    for sel in price_selectors:
        candidates = page.locator(sel)
        count = await candidates.count()
        if count > 0:
            for i in range(count):
                loc = candidates.nth(i)
                if await loc.is_visible():
                    price_input = loc
                    break
        if price_input:
            break

    if price_input:
        await price_input.scroll_into_view_if_needed()
        await price_input.triple_click()
        await wait_ms(page, 300)
        await price_input.type(str(price), delay=30)
        await page.keyboard.press("Tab")      # Tab: validación server-side
        await wait_ms(page, 2000)
        print(f"      price → {price} (locator + triple_click + Tab)")
        return

    # Fallback: JS simulateType en netval dentro del iFrame
    js_price = f"""
        {JS_SIMULATE_TYPE}
        (function() {{
            var partials = ['netval', 'NET_VALUE', 'NetVal', 'price', 'PRICE', 'NetPrice'];
            function findPriceInput(d) {{
                for (var p of partials) {{
                    var inputs = d.querySelectorAll('input[id*="' + p + '"]');
                    var visible = Array.from(inputs).filter(i => i.offsetParent !== null);
                    if (visible.length) return visible[visible.length - 1];
                }}
                return null;
            }}
            var inp = findPriceInput(document);
            if (!inp && window.frames[0]) inp = findPriceInput(window.frames[0].document);
            if (!inp) return 'NO price input FOUND';
            simulateType(inp, '{price}');
            simulateTab(inp);
            return 'filled price: {price}';
        }})()
    """
    result = await page.evaluate(js_price)
    await wait_ms(page, 2000)
    print(f"      price → {result}")

    if "NOT FOUND" in result:
        # Último recurso: Tab-navegación desde donde estamos
        print(f"      ⚠ Usando Tab-nav para precio")
        await page.keyboard.press("Tab")
        await wait_ms(page, 500)
        await page.keyboard.type(str(price), delay=50)
        await page.keyboard.press("Tab")
        await wait_ms(page, 2000)


# ─── PASO 5: Click botón Add para nueva fila ─────────────────────────────────

async def click_add_button(page: Page):
    """
    Click en botón Add/New para crear nueva fila en tabla de productos.
    """
    add_btn = page.get_by_role("button", name="Add")
    try:
        await add_btn.click(timeout=5000)
        await wait_ms(page, 2000)
        print("      ✓ Botón Add clickeado")
        return
    except Exception:
        pass

    # Fallback: buscar botón "New"
    new_btn = page.get_by_role("button", name="New")
    try:
        await new_btn.click(timeout=3000)
        await wait_ms(page, 2000)
        print("      ✓ Botón New clickeado")
        return
    except Exception:
        pass

    # Fallback JS
    result = await page.evaluate("""
        (function() {
            function findAdd(d) {
                var btns = d.querySelectorAll('button, input[type="button"], a');
                var target = Array.from(btns).find(b =>
                    b.textContent.trim() === 'Add' ||
                    b.textContent.trim() === 'New' ||
                    b.value === 'Add' || b.value === 'New'
                );
                if (target) { target.click(); return 'clicked: ' + (target.textContent || target.value); }
                return null;
            }
            var r = findAdd(document);
            if (r) return r;
            if (window.frames[0]) return findAdd(window.frames[0].document);
            return 'NOT FOUND';
        })()
    """)
    await wait_ms(page, 2000)
    if result == "NOT FOUND":
        raise RuntimeError("No se encontró el botón Add/New en la tabla de productos.")
    print(f"      ✓ Add via JS: {result}")


# ─── PASO 6: Guardar oportunidad ─────────────────────────────────────────────

async def save_opportunity(page: Page):
    """
    Guarda la oportunidad. Busca botón Save o icono floppy.
    """
    print("[4/4] Guardando oportunidad...")

    # Intento 1: botón Save
    save_btn = page.get_by_role("button", name="Save")
    try:
        await save_btn.click(timeout=5000)
        await wait_ms(page, 4000)
        print("      ✓ Guardado (botón Save)")
        return
    except Exception:
        pass

    # Intento 2: input type=submit
    submit = page.locator("input[type='submit'][value*='Save'], input[type='submit'][value*='Guardar']")
    try:
        await submit.click(timeout=3000)
        await wait_ms(page, 4000)
        print("      ✓ Guardado (submit)")
        return
    except Exception:
        pass

    # Fallback JS
    result = await page.evaluate("""
        (function() {
            function findSave(d) {
                var els = d.querySelectorAll('button, input[type="button"], input[type="submit"], a');
                var target = Array.from(els).find(e =>
                    (e.textContent || e.value || '').includes('Save') ||
                    (e.textContent || e.value || '').includes('Guardar')
                );
                if (target) { target.click(); return 'saved via: ' + (target.textContent || target.value); }
                return null;
            }
            var r = findSave(document);
            if (r) return r;
            if (window.frames[0]) return findSave(window.frames[0].document);
            return 'NOT FOUND';
        })()
    """)
    await wait_ms(page, 4000)
    if result == "NOT FOUND":
        raise RuntimeError("No se encontró el botón Save. Guardar manualmente.")
    print(f"      ✓ {result}")


# ─── VALIDACIÓN FINAL ─────────────────────────────────────────────────────────

async def validate_items(page: Page):
    """
    Verifica que los 3 part numbers aparecen en la tabla de productos.
    """
    print("[✓] Validando ítems en tabla...")
    html = await page.content()
    results = {}
    for item in ITEMS:
        found = item["part_no"] in html
        results[item["part_no"]] = "✓ ENCONTRADO" if found else "✗ NO ENCONTRADO"
        print(f"      {item['part_no']}: {results[item['part_no']]}")

    all_ok = all("✓" in v for v in results.values())
    return all_ok, results


# ─── FLUJO PRINCIPAL ──────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("SAP Fill Items — BKIND-IBMMQ-2026_RN")
    print("Ítems: IBMMQ-SUPP-RN, DB2ENT-SUPP-RN, SVCS-IMPL-001")
    print("=" * 60)

    async with async_playwright() as p:
        # Conectar a Chrome existente (con la oportunidad ya abierta)
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL)
            print(f"✓ Conectado a Chrome via CDP ({CDP_URL})")
        except Exception as e:
            print(f"✗ No se pudo conectar a Chrome en {CDP_URL}")
            print("  Asegúrate de lanzar Chrome con: --remote-debugging-port=9222")
            print(f"  Error: {e}")
            return

        # Tomar el contexto y página activa
        contexts = browser.contexts
        if not contexts:
            print("✗ No hay contextos activos en Chrome")
            return
        context = contexts[0]
        pages = context.pages
        if not pages:
            print("✗ No hay páginas abiertas")
            return

        # Usar la página que tiene SAP (buscar por URL o tomar la activa)
        page = pages[0]
        for p_candidate in pages:
            url = p_candidate.url
            if "sap" in url.lower() or "crm" in url.lower():
                page = p_candidate
                break
        print(f"✓ Página activa: {page.url[:80]}...")

        try:
            # ── PASO 1: Ir al tab Products ─────────────────────────────
            await click_products_tab(page)

            # ── PASO 2-3: Agregar cada ítem ───────────────────────────
            print(f"\n[2/4] Agregando {len(ITEMS)} ítems...")
            for i, item in enumerate(ITEMS, 1):
                print(f"\n  Ítem {i}/{len(ITEMS)}: {item['part_no']} x{item['qty']} @ ${item['price']:,}")

                # 2a. Click Add para nueva fila
                await click_add_button(page)

                # 2b. Llenar Product ID (JS simulateType + Enter)
                await fill_product_id(page, item["part_no"])

                # 2c. Llenar Quantity (triple_click real + Tab — KB blacklist JS puro)
                await fill_quantity(page, item["qty"], item["part_no"])

                # 2d. Llenar Price / Net Value
                await fill_price(page, item["price"], item["part_no"])

                print(f"  → Ítem {i} cargado: {item['part_no']} ✓")
                # Pausa entre ítems para que SAP estabilice
                await wait_ms(page, 1000)

            # ── PASO 4: Guardar ───────────────────────────────────────
            await save_opportunity(page)

            # ── PASO 5: Validar ───────────────────────────────────────
            all_ok, validation = await validate_items(page)

            # ── RESULTADO FINAL ───────────────────────────────────────
            result_json = {
                "status": "success" if all_ok else "partial",
                "task_type": "sap_fill_items",
                "strategy": "sap_fill_items_oportunidad",
                "opportunity": "BKIND-IBMMQ-2026_RN",
                "items_loaded": len(ITEMS),
                "validation": validation,
                "notes": "flujo_items: orderedprod_JS+Enter → qty_triple_click+Tab → netval_JS+Tab → Save",
                "patterns_used": [
                    "orderedprod: js_simulateType + simulateEnter (KB éxito 100%)",
                    "qty: triple_click_real + type + Tab (BLACKLIST: no js puro)",
                    "price: js_simulateType netval + simulateTab",
                    "iframe: window.frames[0] detectado dinámicamente",
                ]
            }

            print("\n" + "=" * 60)
            print(json.dumps(result_json, indent=2, ensure_ascii=False))
            print("=" * 60)

        except Exception as e:
            print(f"\n✗ Error durante ejecución: {e}")
            error_json = {
                "status": "error",
                "task_type": "sap_fill_items",
                "strategy": "sap_fill_items_oportunidad",
                "error": str(e),
                "notes": "Revisar que la oportunidad esté abierta y en el tab correcto"
            }
            print(json.dumps(error_json, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
