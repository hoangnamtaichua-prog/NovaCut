import os
import sys
import time
import threading
from playwright.sync_api import sync_playwright

ROOT_DIR = os.path.abspath('.')
os.chdir(ROOT_DIR)
sys.path.insert(0, ROOT_DIR)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from web_app import app

def run_server():
    app.run(port=5006, host='127.0.0.1', debug=False, use_reloader=False)

server_thread = threading.Thread(target=run_server, daemon=True)
server_thread.start()
time.sleep(1.5)

print('[Test] Flask started on port 5006', flush=True)

try:
    with sync_playwright() as p:
        print('[Test] Launching Chromium in headed mode...', flush=True)
        browser = p.chromium.launch(headless=False, slow_mo=400)
        page = browser.new_page(viewport={'width': 1440, 'height': 900})

        page.add_init_script("""
            localStorage.setItem('disclaimer_accepted', 'true');
        """)

        print('[Test] Navigating to http://127.0.0.1:5006 ...', flush=True)
        page.goto('http://127.0.0.1:5006')
        page.wait_for_load_state('domcontentloaded')
        time.sleep(2)

        # Dismiss disclaimer if any
        page.evaluate("""() => {
            const d = document.getElementById('modalCopyrightDisclaimer');
            if (d) d.style.display = 'none';
        }""")
        time.sleep(0.5)

        # Click the Batch Editor tab
        print('[Test] Clicking tab viewBatchEditor...', flush=True)
        page.click("button[data-target='viewBatchEditor']")
        time.sleep(1.5)

        # Measure empty state
        info_empty = page.evaluate("""() => {
            const c = document.getElementById('batchEditorTableContainer');
            const view = document.getElementById('viewBatchEditor');
            const table = document.querySelector('.batch-editor-table');
            const emptyZone = document.getElementById('batchEmptyZone');
            return {
                viewDisplay: view ? window.getComputedStyle(view).display : null,
                containerOffsetHeight: c ? c.offsetHeight : null,
                containerClientHeight: c ? c.clientHeight : null,
                containerScrollHeight: c ? c.scrollHeight : null,
                containerComputedHeight: c ? window.getComputedStyle(c).height : null,
                emptyZoneDisplay: emptyZone ? window.getComputedStyle(emptyZone).display : null,
                emptyZoneHeight: emptyZone ? emptyZone.offsetHeight : null,
                tableHeight: table ? table.offsetHeight : null
            };
        }""")
        print('[Test] Info Empty State:', info_empty, flush=True)
        page.screenshot(path='batch_editor_empty_check.png')

        # Add 12 dummy videos
        print('[Test] Adding 12 dummy items to batch...', flush=True)
        page.evaluate("""() => {
            const dummyPaths = [];
            for (let i = 1; i <= 12; i++) {
                dummyPaths.push('D:/Movies/Tap_' + (i < 10 ? '0' + i : i) + '_Tam_Quoc_Dien_Nghia.mp4');
            }
            if (typeof window.addVideosToBatch === 'function') {
                window.addVideosToBatch(dummyPaths);
            }
        }""")
        time.sleep(1.5)

        # Measure populated state
        info_populated = page.evaluate("""() => {
            const c = document.getElementById('batchEditorTableContainer');
            const tbody = document.getElementById('batchTableBody');
            const thead = c ? c.querySelector('thead') : null;
            const th = c ? c.querySelector('th') : null;
            const rows = tbody ? tbody.querySelectorAll('tr').length : 0;
            return {
                rowCount: rows,
                containerOffsetHeight: c ? c.offsetHeight : null,
                containerClientHeight: c ? c.clientHeight : null,
                containerScrollHeight: c ? c.scrollHeight : null,
                hasScrollbar: c ? (c.scrollHeight > c.clientHeight) : false,
                theadPosition: thead ? window.getComputedStyle(thead).position : null,
                thPosition: th ? window.getComputedStyle(th).position : null
            };
        }""")
        print('[Test] Info Populated State:', info_populated, flush=True)
        page.screenshot(path='batch_editor_populated_check.png')

        # Scroll table down by 250px
        print('[Test] Scrolling container by 250px...', flush=True)
        page.evaluate("""() => {
            const c = document.getElementById('batchEditorTableContainer');
            if (c) c.scrollTop = 250;
        }""")
        time.sleep(1)
        page.screenshot(path='batch_editor_scrolled_check.png')

        print('[Test] Keeping browser open for 6 seconds to observe...', flush=True)
        time.sleep(6)
        browser.close()

except Exception as e:
    import traceback
    traceback.print_exc()

print('[Test] Finished script!', flush=True)
