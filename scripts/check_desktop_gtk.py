"""Use Ubuntu's own WebKitGTK to exercise result display and native saving."""
import json
import importlib.util
from pathlib import Path
import sys
import tempfile

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root/'src'))

if len(sys.argv) > 2:
    specification = importlib.util.spec_from_file_location('packaged_desktop_gtk', sys.argv[2])
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    create_window = module.create_window
else:
    from tvfc.desktop_gtk import create_window  # noqa: E402
from gi.repository import GLib, Gtk, WebKit2  # noqa: E402

url = json.loads(Path(sys.argv[1]).read_text())['url']
window, view = create_window(url)
directory = tempfile.TemporaryDirectory(prefix='tvfc-desktop-test-')
saved = Path(directory.name)/'report.html'
state = {'clicked':False, 'dialog':False, 'saved':False, 'chosen':False,
         'analyzed':False, 'playback':False, 'finished':False, 'error':None,
         'expected_name':None}


def fail(message):
    state['error'] = message
    Gtk.main_quit()


def check_ready(_view, result):
    try:
        value = _view.run_javascript_finish(result).get_js_value().to_string()
        data = json.loads(value)
        if not data['ready']:
            GLib.timeout_add(100, check_page)
            return
        if data['candidates'] != 1:
            fail(f'候補表示が不正です: {data}')
            return
        if not data['bridge']:
            fail('専用ウィンドウの保存連携が見つかりません。')
            return
        state['expected_name'] = data['name']
        state['clicked'] = True
        view.run_javascript("document.querySelector('[data-format=html]').click()", None)
    except Exception as error:
        fail(str(error))


def check_page():
    view.run_javascript("JSON.stringify({ready:!document.querySelector('#results-panel').hidden,"
                        "candidates:document.querySelectorAll('.candidate').length,"
                        "bridge:!!window.webkit?.messageHandlers?.tvfc,"
                        "name:reportFilename('html')})",
                        None, check_ready)
    return False


def accept_dialog():
    for top in Gtk.Window.list_toplevels():
        if isinstance(top, Gtk.FileChooserDialog) and top.get_visible():
            state['dialog'] = True
            if top.get_current_name() != state['expected_name']:
                fail(f'保存名が不正です: {top.get_current_name()}')
                return False
            top.set_current_folder(directory.name)
            top.set_current_name(saved.name)
            GLib.timeout_add(500, lambda: (top.response(Gtk.ResponseType.ACCEPT), False)[1])
            return False
    return True


def check_saved():
    if not state['dialog'] or not saved.exists():
        return True
    if '<h1>SEN-CHA 点滅確認候補レポート</h1>' not in saved.read_text():
        fail('保存したHTMLの内容が不正です。')
        return False
    state['saved'] = True
    view.run_javascript("document.querySelector('#open-file').click()", None)
    return False


def begin_analysis():
    def started(_view, result):
        hidden = _view.run_javascript_finish(result).get_js_value().to_boolean()
        if not hidden:
            fail('動画ファイルの解析を開始できませんでした。')
            return
        GLib.timeout_add(100, check_analysis)
    view.run_javascript("document.querySelector('#start').click();"
                        "document.querySelector('#results-panel').hidden", None, started)
    return False


def file_chosen(_view, request):
    state['chosen'] = True
    request.select_files([str(root/'tests/generated/明暗 点滅.mp4')])
    GLib.timeout_add(300, begin_analysis)
    return True


def check_analysis():
    def done(_view, result):
        data = json.loads(_view.run_javascript_finish(result).get_js_value().to_string())
        if data['error']:
            fail(data['error'])
        elif not data['hidden'] and data['count'] == 1:
            state['analyzed'] = True
            GLib.timeout_add(100, check_playback)
        else:
            GLib.timeout_add(100, check_analysis)
    view.run_javascript("JSON.stringify({hidden:document.querySelector('#results-panel').hidden,"
                        "count:document.querySelectorAll('.candidate').length,"
                        "error:document.querySelector('#error').textContent})", None, done)
    return False


def check_playback():
    def checked(_view, result):
        data = json.loads(_view.run_javascript_finish(result).get_js_value().to_string())
        if data['error']:
            fail('動画再生の準備に失敗しました: ' + data['error'])
        elif not data['ready']:
            GLib.timeout_add(100, check_playback)
        elif not data['paused'] or data['time'] <= 0:
            fail(f'候補時刻への一時停止移動が不正です: {data}')
        else:
            state['playback'] = True
            state['finished'] = True
            view.run_javascript("document.querySelector('#quit').click()", None)
            GLib.timeout_add(500, Gtk.main_quit)
    view.run_javascript("(() => { const video=document.querySelector('#playback-video');"
                        "if (!document.querySelector('.seek-button').disabled)"
                        "document.querySelector('.seek-button').click();"
                        "return JSON.stringify({ready:!document.querySelector('.seek-button').disabled,"
                        "paused:video.paused,time:video.currentTime,"
                        "error:video.error ? String(video.error.code) : ''}); })()",
                        None, checked)
    return False


window.connect('destroy', Gtk.main_quit)
view.connect('run-file-chooser', file_chosen)
view.connect('load-changed', lambda _view, event: check_page()
             if event == WebKit2.LoadEvent.FINISHED else None)
GLib.timeout_add(100, accept_dialog)
GLib.timeout_add(100, check_saved)
def timeout():
    names = [type(top).__name__ for top in Gtk.Window.list_toplevels() if top.get_visible()]
    for top in Gtk.Window.list_toplevels():
        if isinstance(top, Gtk.Dialog):
            top.response(Gtk.ResponseType.CANCEL)
    fail('timeout, windows=' + repr(names))
    return False

GLib.timeout_add_seconds(30, timeout)
view.load_uri(url)
window.show_all()
Gtk.main()
assert all(state[key] for key in ('clicked','dialog','saved','chosen','analyzed','playback','finished')), state
assert saved.is_file() and '<h1>SEN-CHA 点滅確認候補レポート</h1>' in saved.read_text(), state
print(json.dumps({'desktop':'GTK/WebKitGTK','result':'passed',
                  'checks':['candidate display','native save dialog filename','HTML download',
                            'video selection','analysis','paused candidate seek','quit']}))
directory.cleanup()
