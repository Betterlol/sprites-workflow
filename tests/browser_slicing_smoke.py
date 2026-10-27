import base64
import io
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright, expect

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'tools'))
from sprite_pipeline.projects import ProjectStore

OUTPUT = REPO / '.playwright-mcp' / 'slicing-loop'
OUTPUT.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='sprite-ui-qa-') as temporary:
    root = Path(temporary)
    store = ProjectStore(root)
    store.create('森林信使 · 界面测试', 'test', frame_size=[320, 320])
    project = store.get('test')
    sheet = Image.new('RGBA', (1024, 512))
    draw = ImageDraw.Draw(sheet)
    for i in range(8):
        x, y = (i % 4) * 256, (i // 4) * 256
        dy = [0, 2, 4, 2, 0, -2, -4, -2][i]
        draw.ellipse((x+65,y+100+dy,x+195,y+230+dy), fill='#26776b')
        draw.ellipse((x+55,y+45+dy,x+200,y+165+dy), fill='#e79d57')
        draw.polygon([(x+65,y+80+dy),(x+65,y+15+dy),(x+110,y+60+dy)], fill='#e79d57')
        draw.polygon([(x+150,y+60+dy),(x+195,y+15+dy),(x+195,y+80+dy)], fill='#e79d57')
        draw.ellipse((x+145,y+85+dy,x+155,y+99+dy), fill='#25312b')
        draw.ellipse((x+165,y+115+dy,x+205,y+142+dy), fill='#f8e7c7')
        draw.rectangle((x+88,y+217,x+115,y+240), fill='#5a493a')
        draw.rectangle((x+151,y+217,x+178,y+240), fill='#5a493a')
    buf=io.BytesIO(); sheet.save(buf,format='PNG')
    snap=project.state(); snap=project.upload('source','idle_sheet.png',buf.getvalue(),snap['data'],snap['revision'],snap['asset_revision'])
    ref=sheet.crop((0,0,256,256)); buf=io.BytesIO(); ref.save(buf,format='PNG')
    snap=project.upload('reference','character.png',buf.getvalue(),snap['data'],snap['revision'],snap['asset_revision'])
    data=snap['data']; data['sources']['idle_sheet.png']={'extract':{'method':'grid','cols':4,'rows':2}}
    snap=project.apply(data,snap['revision'],'idle_sheet.png',snap['asset_revision'])
    data=snap['data']; data['actions']['idle']={'fps':12,'loop':True,'sprites':[f'idle_sheet/{i:03d}.png' for i in range(8)]}
    project.save(data,snap['revision'])
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    server=subprocess.Popen([sys.executable,str(REPO/'tools/serve_sprites.py'),'--workspace-root',str(root),'--port',str(port),'--no-browser'],cwd=REPO,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    url=f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(url+'/api/health',timeout=1); break
            except OSError:
                time.sleep(.1)
        with sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1440,'height':960},device_scale_factor=1)
            errors=[]; page.on('pageerror',lambda e:errors.append(e.stack))
            page.goto(url); page.get_by_role('button',name='打开工程').click()
            expect(page.locator('#timeline .timeline-card')).to_have_count(8)
            page.locator('[data-mode="action"]').click()
            page.locator('#action-fps').fill('17'); page.locator('#action-fps').press('Tab')
            page.locator('[data-view="original"]').click()
            expect(page.locator('#timeline .timeline-card')).to_have_count(8)
            page.locator('#slice-width').fill('200'); page.locator('#slice-width').press('Tab')
            page.locator('#slice-height').fill('200'); page.locator('#slice-height').press('Tab')
            expect(page.locator('#timeline .timeline-card')).to_have_count(8)
            def point(x,y):
                bounds=page.locator('#stage').bounding_box()
                return bounds['x']+1+x*(bounds['width']-2)/1024, bounds['y']+1+y*(bounds['height']-2)/512
            def drag(start,end,cancel=False):
                page.mouse.move(*point(*start)); page.mouse.down(); page.mouse.move(*point(*end),steps=6)
                if cancel: page.keyboard.press('Escape')
                page.mouse.up()
            drag((100,100),(120,110))
            expect(page.locator('#slice-x')).to_have_value('20'); expect(page.locator('#slice-y')).to_have_value('10')
            expect(page.locator('#inspector-content')).to_contain_text('ID 000')
            expect(page.locator('#timeline .timeline-card')).to_have_count(8)
            drag((220,210),(250,230))
            expect(page.locator('#slice-width')).to_have_value('230'); expect(page.locator('#slice-height')).to_have_value('220')
            expect(page.locator('#timeline .timeline-card')).to_have_count(8)
            page.locator('#stage').focus(); page.keyboard.press('Control+z')
            expect(page.locator('#slice-width')).to_have_value('200')
            page.keyboard.press('Control+Shift+z'); expect(page.locator('#slice-width')).to_have_value('230')
            expect(page.locator('#timeline .timeline-card')).to_have_count(8)
            drag((120,100),(160,120),cancel=True)
            expect(page.locator('#slice-x')).to_have_value('20')
            page.locator('#remove-box').click()
            expect(page.locator('#toast')).to_contain_text('动作引用')
            page.locator('#slice-create').click(); drag((900,450),(1000,500))
            expect(page.locator('#timeline .timeline-card')).to_have_count(9)
            expect(page.locator('#inspector-content')).to_contain_text('ID 008')
            page.locator('#save-slices').click(); page.wait_for_function("!document.querySelector('.workspace').inert")
            expect(page.locator('#toast')).to_contain_text('其他修改仍保留')
            saved=json.loads(project.path.read_text(encoding='utf-8'))
            assert saved['actions']['idle']['fps']==12
            assert saved['sources']['idle_sheet.png']['extract']['region_ids'][-1]=='008'
            assert (root/'test/source_sprites/idle_sheet/008.png').is_file()
            expect(page.locator('#timeline .timeline-card')).to_have_count(9)
            page.locator('#remove-box').click()
            expect(page.locator('#timeline .timeline-card')).to_have_count(8)
            page.locator('#save-slices').click(); page.wait_for_function("!document.querySelector('.workspace').inert"); expect(page.locator('#toast')).to_contain_text('当前切割已保存')
            expect(page.locator('#timeline .timeline-card')).to_have_count(8)
            drag((900,450),(990,490))
            expect(page.locator('#timeline .timeline-card')).to_have_count(9)
            expect(page.locator('#inspector-content')).to_contain_text('ID 009')
            page.locator('#save-slices').click(); page.wait_for_function("!document.querySelector('.workspace').inert"); expect(page.locator('#toast')).to_contain_text('当前切割已保存')
            expect(page.locator('#timeline .timeline-card')).to_have_count(9)
            page.screenshot(path=str(OUTPUT/'cut-regions-desktop.png'))
            page.locator('[data-view="processed"]').click()
            expect(page.locator('#process-scale')).to_be_visible()
            page.locator('#process-scale').fill('0.8'); page.locator('#process-scale').press('Tab')
            page.locator('[data-view="original"]').click()
            expect(page.locator('#timeline .timeline-card')).to_have_count(9)
            page.locator('#save-slices').click(); page.wait_for_function("!document.querySelector('.workspace').inert"); expect(page.locator('#toast')).to_contain_text('其他修改仍保留')
            saved=json.loads(project.path.read_text(encoding='utf-8'))
            assert saved['sources']['idle_sheet.png'].get('process',{}).get('scale',1)==1
            page.locator('[data-view="processed"]').click()
            expect(page.locator('#process-scale')).to_have_value('0.8')
            page.locator('[data-mode="action"]').click()
            expect(page.locator('#action-fps')).to_have_value('17')
            page.on('dialog',lambda dialog:dialog.accept())
            page.reload(); expect(page.locator('#timeline .timeline-card')).to_have_count(9)
            expect(page.locator('#slice-x')).to_have_value('20')
            expect(page.locator('#inspector-content')).to_contain_text('ID 000')
            page.locator('[data-mode="action"]').click(); expect(page.locator('#action-fps')).to_have_value('12')
            page.locator('[data-view="original"]').click()
            expect(page.locator('#timeline .timeline-card')).to_have_count(9)
            for width,height in [(1920,1080),(1024,768),(390,844)]:
                page.set_viewport_size({'width':width,'height':height})
                if width<=1100:
                    page.locator('#pane-properties').click(); expect(page.locator('#save-slices')).to_be_visible()
                    page.locator('#pane-canvas').click(); expect(page.locator('#slice-select')).to_be_visible()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(OUTPUT/f'layout-{width}.png'))
            page.set_viewport_size({'width':1440,'height':960})
            page.locator('#projects-open').click(); page.locator('#project-new').click()
            page.locator('#new-project-name').fill('新建切割测试'); page.locator('#new-project-id').fill('fresh')
            page.locator('#project-create').click()
            page.locator('[data-view="original"]').click()
            upload=io.BytesIO(); sheet.save(upload,format='PNG')
            page.locator('#source-upload').set_input_files({'name':'fresh.png','mimeType':'image/png','buffer':upload.getvalue()})
            expect(page.locator('#timeline .timeline-card')).to_have_count(8)
            page.locator('#save-slices').click(); page.wait_for_function("!document.querySelector('.workspace').inert")
            expect(page.locator('#toast')).to_contain_text('切割与原始切片已保存')
            fresh_path=root/'fresh/pipeline.json'
            initial=json.loads(fresh_path.read_text(encoding='utf-8'))['sources']['fresh.png']['extract']
            assert [frame['file'] for frame in initial['identities']]==[f'{i:03d}.png' for i in range(8)]
            page.locator('#inspector-content details').first.locator('summary').click()
            page.locator('#extract-major').fill('999999999'); page.locator('#extract-major').press('Tab')
            expect(page.locator('.error-panel').first).to_be_visible()
            page.locator('#extract-method').select_option('boxes')
            expect(page.locator('#slice-create')).to_be_visible()
            page.locator('#slice-create').click(); drag((20,20),(240,245))
            expect(page.locator('#timeline .timeline-card')).to_have_count(1)
            expect(page.locator('#inspector-content')).to_contain_text('ID 008')
            page.locator('#save-slices').click(); page.wait_for_function("!document.querySelector('.workspace').inert")
            final=json.loads(fresh_path.read_text(encoding='utf-8'))['sources']['fresh.png']['extract']
            assert final['region_ids']==['008']
            page.screenshot(path=str(OUTPUT/'manual-fallback.png'))
            assert not errors,errors
            print(json.dumps({'result':'passed','browser_errors':errors,'checks':['move','eight-direction handles','Escape','one-step undo and redo','referenced-region protection','scoped save','monotonic IDs','unrelated draft preservation','reopen','responsive layout'],'screenshots':str(OUTPUT)},ensure_ascii=False))
            browser.close()
    finally:
        server.terminate(); server.wait(timeout=10)
