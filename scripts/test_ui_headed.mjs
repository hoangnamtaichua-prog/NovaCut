import { chromium } from 'playwright';
import { spawn } from 'child_process';

async function main() {
    console.log('[Test] Starting Flask server on port 5005...');
    const server = spawn('python', ['-c', `
import os, sys
ROOT_DIR = os.path.abspath('.')
os.chdir(ROOT_DIR)
sys.path.insert(0, ROOT_DIR)
from flask import Flask, send_from_directory
from routes.core import core_bp

app = Flask(__name__, static_folder='web', static_url_path='/static')
app.register_blueprint(core_bp)
app.run(port=5005, host='127.0.0.1', debug=False)
`], { stdio: 'pipe' });

    server.stderr.on('data', d => console.error('[Server Err]:', d.toString()));
    server.stdout.on('data', d => console.log('[Server Out]:', d.toString()));

    await new Promise(r => setTimeout(r, 2000));

    console.log('[Test] Launching Chromium in HEADED mode...');
    const browser = await chromium.launch({ headless: false, slowMo: 400 });
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

    page.on('console', msg => console.log(`[Browser Console ${msg.type()}]:`, msg.text()));
    page.on('pageerror', err => console.error('[Browser Error]:', err));

    console.log('[Test] Navigating to http://127.0.0.1:5005 ...');
    await page.goto('http://127.0.0.1:5005');
    await page.waitForLoadState('domcontentloaded');
    await page.waitForTimeout(1000);

    console.log('[Test] Clicking tab viewBatchEditor...');
    const batchTab = await page.$('#tabBatchEditor, [data-target="viewBatchEditor"]');
    if (batchTab) {
        await batchTab.click();
        console.log('[Test] Clicked batch tab successfully');
    } else {
        console.log('[Test] Could not find batch tab by selector, trying to show viewBatchEditor directly');
        await page.evaluate(() => {
            const v = document.getElementById('viewBatchEditor');
            if (v) v.style.display = 'block';
        });
    }

    await page.waitForTimeout(1500);

    const info = await page.evaluate(() => {
        const c = document.getElementById('batchEditorTableContainer');
        const empty = document.getElementById('batchEmptyZone');
        const table = document.querySelector('.batch-editor-table');
        const view = document.getElementById('viewBatchEditor');
        const card = document.querySelector('.batch-table-card');

        return {
            viewFound: !!view,
            viewDisplay: view ? window.getComputedStyle(view).display : null,
            viewHeight: view ? view.offsetHeight : null,
            cardFound: !!card,
            cardHeight: card ? card.offsetHeight : null,
            containerFound: !!c,
            containerOffsetHeight: c ? c.offsetHeight : null,
            containerOffsetWidth: c ? c.offsetWidth : null,
            containerDisplay: c ? window.getComputedStyle(c).display : null,
            containerVisibility: c ? window.getComputedStyle(c).visibility : null,
            containerHeightStyle: c ? window.getComputedStyle(c).height : null,
            emptyFound: !!empty,
            emptyDisplay: empty ? window.getComputedStyle(empty).display : null,
            tableFound: !!table,
            tableOffsetHeight: table ? table.offsetHeight : null
        };
    });

    console.log('[Test Result Info]:', JSON.stringify(info, null, 2));

    await page.screenshot({ path: 'batch_editor_ui_check.png', fullPage: false });
    console.log('[Test] Saved screenshot to batch_editor_ui_check.png');

    await page.waitForTimeout(3000);
    await browser.close();
    server.kill();
    process.exit(0);
}

main().catch(err => {
    console.error(err);
    process.exit(1);
});
