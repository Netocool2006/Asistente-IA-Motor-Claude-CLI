"""
sap_js_helpers.py — JS helpers reutilizables para SAP CRM WebUI
================================================================
Contiene las 6 mejoras tecnicas identificadas en analisis de mercado:
  1. MutationObserver (reemplaza timeouts fijos)
  2. Frame Discovery dinamico (reemplaza frames[0].frames[1])
  3. SAP Busy Indicator detection
  4. HTMLB Event Bus (sapAwareDispatch)
  5. Error Message Scraping
  6. Element Readiness Check

Uso:
    from sap_js_helpers import JS_HELPERS
    # Prepend to any JS block:
    js_code = JS_HELPERS + your_js_code
"""

# ── Bloque completo de helpers — prepend a cualquier JS ──────
JS_HELPERS = """
// ═══════════════════════════════════════════════════════════
// SAP JS HELPERS v1 — reutilizables en todos los bloques
// ═══════════════════════════════════════════════════════════

// [1] FRAME DISCOVERY — busca el frame con contenido SAP
function findSapFrame(win, depth) {
    depth = depth || 0;
    if (depth > 5) return null;
    try {
        var doc = win.document;
        if (doc.querySelector('[id*="prodtable"]') ||
            doc.querySelector('[id*="btadmini"]') ||
            doc.querySelector('[id*="search_parameters"]') ||
            doc.querySelector('[id*="OG_DESCRIPTION"]') ||
            (doc.title && (doc.title.includes('Opp') || doc.title.includes('Search')))) {
            return win;
        }
    } catch(e) { /* cross-origin */ }
    for (var i = 0; i < win.frames.length; i++) {
        var r = findSapFrame(win.frames[i], depth + 1);
        if (r) return r;
    }
    return null;
}

// [2] SAP BUSY INDICATOR — detecta si SAP esta procesando
function isSapBusy(frame) {
    var doc = (frame && frame.document) || document;
    var selectors = [
        '.sapLpBusyIndicator', '[id*="BusyInd"]',
        '.sapUiLocalBusyIndicator', '.sapCrmOverlay',
        '[id*="overlay"][style*="block"]',
        '[class*="urBusyAnim"]', '[class*="urLoadingInd"]'
    ];
    for (var s of selectors) {
        var el = doc.querySelector(s);
        if (el && el.offsetParent !== null) return true;
    }
    return false;
}

// [3] WAIT FOR SAP IDLE — espera hasta que SAP deje de estar busy
function waitSapIdle(frame, timeout) {
    timeout = timeout || 12000;
    return new Promise(function(resolve, reject) {
        if (!isSapBusy(frame)) { resolve(); return; }
        var start = Date.now();
        var t = setInterval(function() {
            if (!isSapBusy(frame)) { clearInterval(t); resolve(); return; }
            if (Date.now() - start > timeout) { clearInterval(t); reject('SAP busy timeout'); }
        }, 200);
    });
}

// [4] MUTATION OBSERVER — espera cambio real en DOM (reemplaza setTimeout fijo)
function waitForDomChange(frame, targetSelector, timeout) {
    timeout = timeout || 10000;
    var doc = (frame && frame.document) || document;
    return new Promise(function(resolve, reject) {
        // Check if already present
        var existing = targetSelector ? doc.querySelector(targetSelector) : null;
        if (existing && existing.getBoundingClientRect().width > 0) {
            resolve(existing); return;
        }
        var timer = setTimeout(function() {
            obs.disconnect(); reject('MutationObserver timeout: ' + (targetSelector || 'any change'));
        }, timeout);
        var obs = new MutationObserver(function(mutations) {
            if (targetSelector) {
                var el = doc.querySelector(targetSelector);
                if (el && el.getBoundingClientRect().width > 0) {
                    clearTimeout(timer); obs.disconnect(); resolve(el); return;
                }
            } else {
                // Any significant change
                for (var m of mutations) {
                    if (m.addedNodes.length > 0 || m.type === 'attributes') {
                        clearTimeout(timer); obs.disconnect(); resolve(null); return;
                    }
                }
            }
        });
        obs.observe(doc.body || doc.documentElement, {
            childList: true, subtree: true,
            attributes: true, attributeFilter: ['value', 'class', 'style']
        });
    });
}

// [5] SAP-AWARE DISPATCH — usa HTMLB event bus si existe, fallback a DOM events
function sapDispatch(el, value) {
    el.focus();
    el.value = value;
    // Try SAP HTMLB internal handlers first
    if (typeof el.htmlbOnChange === 'function') { try { el.htmlbOnChange(); } catch(e) {} }
    if (typeof el.onsapchange === 'function') { try { el.onsapchange(); } catch(e) {} }
    // Standard DOM events
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    // IE legacy (SAP WebUI can use it)
    if (el.fireEvent) { try { el.fireEvent('onchange'); } catch(e) {} }
}

function sapEnter(el) {
    var opts = {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true};
    el.dispatchEvent(new KeyboardEvent('keydown', opts));
    el.dispatchEvent(new KeyboardEvent('keypress', opts));
    el.dispatchEvent(new KeyboardEvent('keyup', opts));
}

function sapTab(el) {
    var opts = {key: 'Tab', code: 'Tab', keyCode: 9, which: 9, bubbles: true};
    el.dispatchEvent(new KeyboardEvent('keydown', opts));
    el.dispatchEvent(new KeyboardEvent('keyup', opts));
}

// [6] ELEMENT READINESS — espera que elemento sea visible, enabled, no cubierto
function waitForReady(selector, frame, timeout) {
    timeout = timeout || 8000;
    var doc = (frame && frame.document) || document;
    return new Promise(function(resolve, reject) {
        var start = Date.now();
        var check = setInterval(function() {
            var el = doc.querySelector(selector);
            if (el) {
                var rect = el.getBoundingClientRect();
                var style = frame ? frame.getComputedStyle(el) : window.getComputedStyle(el);
                if (rect.width > 0 && rect.height > 0 &&
                    style.visibility !== 'hidden' &&
                    style.display !== 'none' &&
                    !el.disabled) {
                    clearInterval(check); resolve(el); return;
                }
            }
            if (Date.now() - start > timeout) {
                clearInterval(check); reject('Not ready: ' + selector);
            }
        }, 100);
    });
}

// [BONUS] SAP ERROR MESSAGES — lee mensajes de error/warning
function getSapMessages(frame) {
    var doc = (frame && frame.document) || document;
    var messages = [];
    var selectors = [
        '[class*="sapMessage"]', '[id*="msgarea"]', '[id*="MSG_AREA"]',
        '.sapCrmMessageText', '[class*="urMsgBar"]',
        'td[class*="urErrTxt"]', 'span[class*="urErrTxt"]'
    ];
    for (var s of selectors) {
        var els = doc.querySelectorAll(s);
        for (var el of els) {
            var text = (el.innerText || '').trim();
            if (text && text.length > 3) {
                var type = (el.className || '').includes('rr') ? 'error' :
                           (el.className || '').includes('arn') ? 'warning' : 'info';
                messages.push({type: type, text: text.substr(0, 200)});
            }
        }
    }
    return messages;
}

// ═══════════════════════════════════════════════════════════
"""

# ── Helpers individuales para uso selectivo ──────────────────

JS_FIND_SAP_FRAME = """
function findSapFrame(win, depth) {
    depth = depth || 0;
    if (depth > 5) return null;
    try {
        var doc = win.document;
        if (doc.querySelector('[id*="prodtable"]') ||
            doc.querySelector('[id*="btadmini"]') ||
            doc.querySelector('[id*="search_parameters"]') ||
            doc.querySelector('[id*="OG_DESCRIPTION"]') ||
            (doc.title && (doc.title.includes('Opp') || doc.title.includes('Search')))) {
            return win;
        }
    } catch(e) {}
    for (var i = 0; i < win.frames.length; i++) {
        var r = findSapFrame(win.frames[i], depth + 1);
        if (r) return r;
    }
    return null;
}
"""

JS_SAP_DISPATCH = """
function sapDispatch(el, value) {
    el.focus(); el.value = value;
    if (typeof el.htmlbOnChange === 'function') { try { el.htmlbOnChange(); } catch(e) {} }
    if (typeof el.onsapchange === 'function') { try { el.onsapchange(); } catch(e) {} }
    el.dispatchEvent(new Event('input', {bubbles: true}));
    el.dispatchEvent(new Event('change', {bubbles: true}));
    if (el.fireEvent) { try { el.fireEvent('onchange'); } catch(e) {} }
}
"""

JS_WAIT_SAP_IDLE = """
function isSapBusy(frame) {
    var doc = (frame && frame.document) || document;
    var sels = ['.sapLpBusyIndicator','[id*="BusyInd"]','.sapUiLocalBusyIndicator',
                '.sapCrmOverlay','[class*="urBusyAnim"]','[class*="urLoadingInd"]'];
    for (var s of sels) { var el = doc.querySelector(s); if (el && el.offsetParent !== null) return true; }
    return false;
}
function waitSapIdle(frame, timeout) {
    timeout = timeout || 12000;
    return new Promise(function(resolve, reject) {
        if (!isSapBusy(frame)) { resolve(); return; }
        var start = Date.now();
        var t = setInterval(function() {
            if (!isSapBusy(frame)) { clearInterval(t); resolve(); return; }
            if (Date.now()-start > timeout) { clearInterval(t); reject('SAP busy timeout'); }
        }, 200);
    });
}
"""

JS_GET_SAP_MESSAGES = """
function getSapMessages(frame) {
    var doc = (frame && frame.document) || document;
    var msgs = [];
    var sels = ['[class*="sapMessage"]','[id*="msgarea"]','[id*="MSG_AREA"]',
                '.sapCrmMessageText','[class*="urMsgBar"]','td[class*="urErrTxt"]'];
    for (var s of sels) {
        var els = doc.querySelectorAll(s);
        for (var el of els) {
            var t = (el.innerText||'').trim();
            if (t && t.length > 3) msgs.push({type: (el.className||'').includes('rr')?'error':'info', text: t.substr(0,200)});
        }
    }
    return msgs;
}
"""
