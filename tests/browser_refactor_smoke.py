"""Optional Chromium check using disposable artwork and an isolated server."""
import io
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.sync_api import expect, sync_playwright

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
from sprite_pipeline.application.projects import ProjectStore


def run():
    with tempfile.TemporaryDirectory(prefix='sprite-refactor-browser-') as temporary:
        root = Path(temporary)
        store = ProjectStore(root)
        store.create('Refactor smoke', 'test', frame_size=[32, 32])
        project = store.get('test')
        sheet = Image.new('RGBA', (16, 8), 'red')
        sheet.paste('green', (8, 0, 16, 8))
        for name, image in [('idle.png', sheet), ('other.png', Image.new('RGBA', (8, 8), 'blue'))]:
            content = io.BytesIO()
            image.save(content, format='PNG')
            state = project.state()
            project.upload('source', name, content.getvalue(), state['data'], state['revision'], state['asset_revision'])
            state = project.state()
            state['data']['sources'][name] = {'extract': {'method': 'grid', 'cols': 2 if name == 'idle.png' else 1, 'rows': 1}}
            project.apply(state['data'], state['revision'], name, state['asset_revision'])
        state = project.state()
        refs = ['idle/001.png', 'other/000.png', 'idle/001.png', 'idle/000.png']
        state['data']['actions']['idle'] = {'fps': 16, 'loop': True, 'sprites': refs,
                                          'animation': {'order': [3, 0], 'durations_ms': [40, 120]}}
        project.save(state['data'], state['revision'])
        files = [root / 'test/processed_sprites' / ref for ref in ['idle/000.png', 'other/000.png']]
        before = [(p.read_bytes(), p.stat().st_mtime_ns) for p in files]
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        server = subprocess.Popen([sys.executable, str(REPO / 'tools/serve_sprites.py'), '--workspace-root', str(root),
                                   '--port', str(port), '--no-browser'], cwd=REPO,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            url = f'http://127.0.0.1:{port}'
            for _ in range(100):
                try:
                    with urllib.request.urlopen(url + '/api/health', timeout=1):
                        break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError(server.stderr.read().decode())
                    time.sleep(.1)
            with sync_playwright() as pw:
                browser = pw.chromium.launch(headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 960})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(url)
                page.get_by_role('button', name='打开工程').click()
                expect(page.locator('#timeline .timeline-card')).to_have_count(2)
                with page.expect_response(lambda response: response.url.endswith('/save-slices')) as saved_slices:
                    page.locator('#save-slices').click()
                assert saved_slices.value.status == 200, saved_slices.value.text()
                page.wait_for_function("!document.querySelector('.workspace').inert")
                assert (root / 'test/source_sprites/idle/001.png').is_file()
                page.locator('[data-view="processed"]').click()
                cards = page.locator('#timeline .timeline-card')
                expect(cards).to_have_count(4)
                assert cards.evaluate_all('(cards) => cards.map(c => c.dataset.ref)') == refs
                assert cards.evaluate_all('(cards) => cards.map(c => Number(c.dataset.duration))') == [62] * 4
                # The first preview must establish known versions before testing
                # a warm incremental edit; persisted thumbnails appear earlier.
                page.wait_for_function("Array.from(document.querySelectorAll('#timeline .timeline-card img')).length === 4 && Array.from(document.querySelectorAll('#timeline .timeline-card img')).every(img => img.src.startsWith('data:'))")
                expect(page.locator('#override-x')).to_be_visible()
                with page.expect_response(lambda response: response.url.endswith('/preview')
                                          and response.request.post_data_json.get('source') == 'idle.png') as response:
                    page.locator('#override-x').fill('1')
                    page.locator('#override-x').press('Tab')
                result = response.value.json()
                assert response.value.status == 200, result
                assert [frame['id'] for frame in result['frames'] if 'url' in frame] == ['001'], result
                expect(cards.nth(0).locator('img')).to_have_attribute('src', cards.nth(2).locator('img').get_attribute('src'))
                page.locator('#play').click()
                expect(page.locator('#play')).not_to_have_text('▶')
                page.locator('#play').click()
                with page.expect_response(lambda response: response.url.endswith('/apply')) as applied:
                    page.locator('#apply-source').click()
                assert applied.value.status == 200, applied.value.text()
                page.wait_for_function("!document.querySelector('.workspace').inert")
                saved = json.loads(project.path.read_text(encoding='utf-8'))
                assert saved['sources']['idle.png']['process']['overrides']['001']['offset'] == [1, 0]
                assert [(p.read_bytes(), p.stat().st_mtime_ns) for p in files] == before
                page.locator('#adjust-playback').select_option('display')
                expect(cards).to_have_count(2)
                assert cards.evaluate_all('(cards) => cards.map(c => Number(c.dataset.duration))') == [40, 120]
                page.reload()
                expect(page.locator('#timeline .timeline-card')).to_have_count(2)
                assert not errors, errors
                browser.close()
                print('Chromium: scoped slicing save, repeated/cross-source action timing, one-frame delta, incremental apply, display timing and reload passed.')
        finally:
            server.terminate()
            server.wait(timeout=15)
            server.stderr.close()


if __name__ == '__main__':
    run()
