"""Local Playwright only: no remote connector, no network except loopback."""
import json
from pathlib import Path
import sys
import time

from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'tests'))
from fixtures import make_video  # noqa: E402
ready = Path(sys.argv[1] if len(sys.argv)>1 else '/tmp/tvfc-ready.json')
url = json.loads(ready.read_text())['url']
output = root/'test-results'
output.mkdir(exist_ok=True)
long_video = make_video(output/'long-static.mp4', kind='static', fps=10, duration=65)
errors = []
blocked = []
with sync_playwright() as p:
    browser = p.chromium.launch(executable_path='/usr/bin/google-chrome',headless=True)
    context = browser.new_context(accept_downloads=True)
    def route(request):
        if request.request.url.startswith(('http://127.0.0.1:', 'data:', 'blob:')):
            request.continue_()
        else:
            blocked.append(request.request.url)
            request.abort()
    context.route('**/*', route)
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(url)
    assert page.get_by_text('本文へ移動').count() == 0
    page.keyboard.press('Tab')
    assert page.locator('.app-menu .menu').first.locator('summary').evaluate('(e)=>e===document.activeElement')
    page.keyboard.press('ArrowDown')
    assert page.locator('#menu-file-open').evaluate('(e)=>e===document.activeElement')
    page.keyboard.press('ArrowDown')
    assert page.locator('#menu-url-open').evaluate('(e)=>e===document.activeElement')
    page.keyboard.press('ArrowRight')
    assert page.locator('#menu-show-source').evaluate('(e)=>e===document.activeElement')
    page.keyboard.press('ArrowLeft')
    assert page.locator('#menu-file-open').evaluate('(e)=>e===document.activeElement')
    page.keyboard.press('Escape')
    assert page.locator('.app-menu .menu').first.locator('summary').evaluate('(e)=>e===document.activeElement')
    assert 'SEN-CHA' not in page.locator('.app-menu').inner_text()
    assert page.get_by_role('button',name='動画を開く',exact=True).count() == 1
    page.locator('.app-menu .menu').last.locator('summary').click()
    page.get_by_role('button',name='このアプリについて').click()
    assert page.locator('#about-dialog').is_visible()
    page.locator('#about-dialog button').click()
    page.locator('.app-menu .menu').last.locator('summary').click()
    page.get_by_role('button',name='ライセンス',exact=True).click()
    assert page.locator('#license-dialog').is_visible()
    assert '本体はMITライセンス' in page.locator('#license-dialog').inner_text()
    page.locator('#app-license').filter(has_text='MIT License').wait_for()
    page.locator('#license-notices').filter(has_text='FFmpeg').wait_for()
    page.locator('#license-file').select_option('FFmpeg-COPYING.LGPLv2.1')
    page.locator('#license-content').filter(has_text='GNU LESSER GENERAL PUBLIC LICENSE').wait_for()
    page.locator('#license-dialog button').click()
    page.locator('.app-menu .menu').last.locator('summary').click()
    page.get_by_role('button',name='WCAGと検出条件').click()
    assert page.locator('#detection-dialog').is_visible()
    assert page.locator('#detection-dialog a').count() == 2
    assert '標準：変化量0.10以上' in page.locator('#detection-dialog').inner_text()
    page.locator('#detection-dialog button').click()
    page.keyboard.press('F1')
    assert page.locator('#guide-dialog').is_visible()
    page.locator('#guide-dialog button').click()
    with page.expect_file_chooser() as chooser:
        page.keyboard.press('Control+o')
    chooser.value.set_files(root/'tests/generated/明暗 点滅.mp4')
    assert '明暗 点滅.mp4' in page.locator('#source-name').inner_text()
    page.get_by_label('YouTubeの単一動画URL',exact=True).check()
    page.get_by_label('YouTube動画のURL').fill('https://evil.example/watch?v=YE7VzlLtp-4')
    page.get_by_role('button',name='解析を開始',exact=True).click()
    page.locator('#error').filter(has_text='YouTube').wait_for(timeout=10000)
    page.get_by_label('端末内の動画ファイル',exact=True).check()
    page.locator('.app-menu .menu').nth(1).locator('summary').click()
    page.get_by_role('button',name='検出条件を表示').click()
    assert page.locator('#settings-details').get_attribute('open') is not None
    page.locator('#region-mode').select_option('broad')
    page.locator('#video').set_input_files(root/'tests/generated/明暗 点滅.mp4')
    page.keyboard.press('Control+Enter')
    page.get_by_text('解析が完了しました。',exact=True).wait_for(timeout=60000)
    assert '要確認候補 1件' in page.locator('#summary').inner_text()
    assert '"region_mode": "broad"' in page.locator('#conditions').text_content()
    assert page.locator('#chart svg path.luminance').count() == 1
    assert page.locator('#chart svg .candidate-band').count() == 1
    assert page.locator('#chart svg').get_attribute('role') == 'img'
    page.wait_for_function("document.querySelector('#playback-video').readyState >= 1")
    assert page.locator('video').count() == 1
    assert page.locator('#playback-video').evaluate('(v)=>v.paused')
    page.get_by_role('button',name='候補 1 の開始時刻へ移動').click()
    page.wait_for_function("document.querySelector('#playback-video').currentTime > 0")
    assert page.locator('#playback-video').evaluate('(v)=>v.paused')
    assert float(page.locator('#chart svg .playhead').get_attribute('x1')) > 0
    page.locator('#playback-position').evaluate("e => { e.value = '0.5'; e.dispatchEvent(new Event('change')); }")
    page.wait_for_function("Math.abs(document.querySelector('#playback-video').currentTime - 0.5) < 0.1")
    assert page.locator('#playback-video').evaluate('(v)=>v.paused')
    for format in ('HTML','JSON','CSV'):
        with page.expect_download() as event:
            if format == 'HTML':
                page.get_by_role('button',name='保存',exact=True).click()
            else:
                page.locator('.app-menu .menu').first.locator('summary').click()
                page.locator(f'[data-format={format.lower()}]').click()
        assert event.value.suggested_filename == f'明暗 点滅.{format.lower()}'
        event.value.save_as(output/f'browser-report.{format.lower()}')
    with page.expect_download() as event:
        page.keyboard.press('Control+s')
    assert event.value.suggested_filename == '明暗 点滅.html'
    event.value.save_as(output/'browser-shortcut.html')
    page.evaluate("currentReport.filename = 'YouTubeの動画.webm'")
    with page.expect_download() as event:
        page.get_by_role('button',name='保存',exact=True).click()
    assert event.value.suggested_filename == 'YouTubeの動画.html'
    event.value.save_as(output/'browser-youtube-name.html')
    page.screenshot(path=str(output/'desktop.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path=str(output/'mobile.png'),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.set_viewport_size({'width':1280,'height':900})
    page.locator('#video').set_input_files(long_video)
    page.get_by_role('button',name='解析を開始',exact=True).click()
    page.get_by_text('解析が完了しました。',exact=True).wait_for(timeout=60000)
    assert page.locator('#chart-scroll').evaluate('(e)=>e.scrollWidth > e.clientWidth')
    assert page.locator('#overview-map').get_attribute('aria-valuemax') == '35.000'
    page.locator('#chart-scroll').evaluate('(e)=>e.scrollLeft = e.scrollWidth / 2')
    page.wait_for_function("() => Number(document.querySelector('#overview-map').getAttribute('aria-valuenow')) > 10")
    page.locator('#chart svg').click(position={'x':200,'y':40})
    page.wait_for_function("document.querySelector('#playback-video').currentTime > 10")
    assert page.locator('#playback-video').evaluate('(v)=>v.paused')
    page.locator('#overview-map').focus()
    page.keyboard.press('End')
    assert abs(float(page.locator('#overview-map').get_attribute('aria-valuenow')) - 35) < .1
    page.keyboard.press('Home')
    assert float(page.locator('#overview-map').get_attribute('aria-valuenow')) == 0
    page.locator('#video').set_input_files(root/'tests/generated/静止画.webm')
    page.get_by_role('button',name='解析を開始',exact=True).click()
    page.get_by_text('解析が完了しました。',exact=True).wait_for(timeout=60000)
    assert '今回の検出条件では候補なし' in page.locator('#summary').inner_text()
    assert page.locator('#chart svg .candidate-band').count() == 0
    page.reload()
    page.get_by_text('解析が完了しました。',exact=True).wait_for(timeout=10000)
    assert '今回の検出条件では候補なし' in page.locator('#summary').inner_text()
    # Corrupt input fails explicitly; cancellation permits a subsequent run.
    page.locator('#video').set_input_files(root/'tests/generated/破損.mp4')
    page.get_by_role('button',name='解析を開始',exact=True).click()
    page.locator('#error').filter(has_text='読み取れません').wait_for(timeout=30000)
    page.locator('#video').set_input_files(root/'tests/generated/中止用.mp4')
    page.get_by_role('button',name='解析を開始',exact=True).click()
    page.locator('#status').filter(has_text='解析しています').wait_for(timeout=30000)
    page.get_by_role('button',name='中止',exact=True).click()
    page.locator('#status').filter(has_text='中止しました').wait_for(timeout=30000)
    page.locator('#video').set_input_files(root/'tests/generated/静止画.webm')
    page.get_by_role('button',name='解析を開始',exact=True).click()
    page.get_by_text('解析が完了しました。',exact=True).wait_for(timeout=60000)
    assert '今回の検出条件では候補なし' in page.locator('#summary').inner_text()
    # Toolbar, menus, and visible focus, exercised by keyboard.
    page.locator('#open-file').focus()
    page.keyboard.press('Tab')
    assert page.locator('#open-url').evaluate('(e)=>e===document.activeElement')
    page.keyboard.press('Tab')
    assert page.get_by_role('button',name='解析を開始',exact=True).evaluate('(e)=>e===document.activeElement')
    assert page.locator('#start').evaluate('(e)=>getComputedStyle(e).outlineStyle') != 'none'
    page.locator('.app-menu .menu').first.locator('summary').focus()
    page.keyboard.press('Enter')
    assert page.locator('.app-menu .menu').first.get_attribute('open') is not None
    page.keyboard.press('Escape')
    assert page.locator('.app-menu .menu').first.get_attribute('open') is None
    assert not errors, errors
    assert not blocked, blocked
    if '--gtk-ready' in sys.argv:
        page.locator('#video').set_input_files(root/'tests/generated/明暗 点滅.mp4')
        page.get_by_role('button',name='解析を開始',exact=True).click()
        page.get_by_text('解析が完了しました。',exact=True).wait_for(timeout=60000)
        assert '要確認候補 1件' in page.locator('#summary').inner_text()
    if '--shutdown' in sys.argv:
        page.locator('#video').set_input_files(root/'tests/generated/中止用.mp4')
        page.get_by_role('button',name='解析を開始',exact=True).click()
        page.locator('#status').filter(has_text='解析しています').wait_for(timeout=30000)
        page.keyboard.press('Control+q')
        page.get_by_text('アプリを終了しました。このタブを閉じてください。',exact=True).wait_for()
    browser.close()
print(json.dumps({'browser':'local Google Chrome / Playwright','result':'passed',
                  'checks':['menu arrow keys','first focus','WCAG help links','license help and original','video input','analysis',
                            'overview heatmap','scrollable detail chart','linked paused playback',
                            'candidate result','three named downloads','YouTube title filename',
                            'no autoplay','390px layout',
                            'no-candidate result','reload','keyboard focus','Ctrl+Q while running',
                            'no external requests'],
                  'error_cancel_restart':'passed','page_errors':errors},ensure_ascii=False,indent=2))
