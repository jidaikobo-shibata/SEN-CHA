import json
import threading
import time
from pathlib import Path

import pytest

from tvfc.analysis import analyze
from tvfc.jobs import Jobs
from tvfc.jobs import worker
from tvfc.media import Cancelled, Unsupported
from tvfc.reports import serialize, save_reports
from tvfc.web import create_app
from fixtures import make_video


@pytest.fixture
def report(tmp_path):
    return analyze(make_video(tmp_path/'sample.mp4'))


def test_reports(report, tmp_path):
    assert report['settings']['sensitivity'] == 'high'
    report['filename'] = '=1+1<img src=x onerror=alert(1)>.mp4'
    html = serialize(report,'html')
    assert '<h1>SEN-CHA 点滅確認候補レポート</h1>' in html
    assert '検出感度：標準設定' in html
    assert '標準設定' in serialize(report,'csv')
    assert '動画全体の変化' in html
    assert '危険度やWCAGの閾値ではありません' in html
    assert '<svg viewBox="0 0 1000 160"' in html
    assert '<img src=x' not in html
    assert '&lt;img src=x' in html
    assert "'=1+1" in serialize(report,'csv')
    assert '閃光面積ではない' in serialize(report,'csv')
    assert json.loads(serialize(report,'json'))['filename'] == report['filename']
    first = save_reports(report,tmp_path)
    second = save_reports(report,tmp_path)
    assert len(set(first+second)) == 6
    assert all(p.exists() for p in first+second)


def test_guards(report):
    jobs = Jobs()
    jobs.report = report
    jobs.state = 'completed'
    app = create_app(jobs, 'test-secret')
    client = app.test_client()
    host = 'http://127.0.0.1:8765'
    assert client.get('/api/result',base_url=host).status_code == 403
    good = {'X-TVFC-Token':'test-secret', 'Origin':host}
    assert client.get('/api/result',base_url=host,headers=good).status_code == 200
    assert client.get('/api/result',base_url='http://evil.example',headers=good).status_code == 403
    assert client.get('/api/result',base_url=host,headers={**good,'Origin':'http://evil.example'}).status_code == 403
    assert client.post('/api/cancel',base_url=host,headers={'X-TVFC-Token':'test-secret'}).status_code == 403
    assert client.get('/api/report/../../etc/passwd',base_url=host,headers=good).status_code != 200
    assert client.get('/',base_url=host).headers['Content-Security-Policy']
    assert client.post('/api/uploads',base_url=host,headers=good,
                       json={'filename':'v.mp4','size':10,'region_mode':[]}).status_code == 400


def test_license_help(tmp_path, monkeypatch):
    import tvfc.web
    (tmp_path/'LICENSE').write_text('MIT License\nCopyright (c) 2026 TVFC contributors',encoding='utf-8')
    (tmp_path/'THIRD_PARTY_NOTICES.md').write_text('FFmpeg: LGPL',encoding='utf-8')
    (tmp_path/'licenses').mkdir()
    (tmp_path/'licenses/FFmpeg-COPYING.LGPLv2.1').write_text(
        'GNU LESSER GENERAL PUBLIC LICENSE',encoding='utf-8')
    monkeypatch.setattr(tvfc.web.sys,'executable',str(tmp_path/'SEN-CHA'))
    app = create_app(token='test-secret')
    client = app.test_client()
    host = 'http://127.0.0.1:8765'
    page = client.get('/',base_url=host).text
    assert '<option value="high" selected>標準設定</option>' in page
    assert '<option value="standard">低感度（候補を絞る）</option>' in page
    assert '本体はMITライセンス' in page
    assert 'menu-help-license' in page
    own_license = client.get('/legal/license',base_url=host)
    assert own_license.status_code == 200
    assert 'MIT License' in own_license.text
    notices = client.get('/legal/notices',base_url=host)
    assert notices.status_code == 200
    assert 'FFmpeg' in notices.text
    names = client.get('/legal/licenses',base_url=host).json['files']
    assert 'FFmpeg-COPYING.LGPLv2.1' in names
    original = client.get('/legal/licenses/FFmpeg-COPYING.LGPLv2.1',base_url=host)
    assert original.status_code == 200
    assert 'GNU LESSER GENERAL PUBLIC LICENSE' in original.text
    assert client.get('/legal/licenses/../../etc/passwd',base_url=host).status_code != 200


def test_playback_is_scoped_and_seekable(report, tmp_path):
    source = make_video(tmp_path/'playback.mp4')
    jobs = Jobs()
    jobs.report = report
    jobs.state = 'completed'
    jobs.playback_path = source
    jobs.playback_token = 'private-capability'
    app = create_app(jobs, 'test-secret')
    client = app.test_client()
    host = 'http://127.0.0.1:8765'
    headers = {'X-TVFC-Token':'test-secret'}
    assert client.get('/api/playback', base_url=host).status_code == 403
    assert client.get('/api/playback', base_url=host, headers=headers).json == {
        'url':'/media/private-capability'}
    assert client.get('/media/wrong', base_url=host).status_code == 404
    assert client.get('/media/private-capability', base_url='http://evil.example').status_code == 403
    partial = client.get('/media/private-capability', base_url=host,
                         headers={'Range':'bytes=0-9'})
    assert partial.status_code == 206
    assert len(partial.data) == 10
    assert partial.headers['Content-Type'].startswith('video/')
    assert partial.headers['Cache-Control'] == 'no-store'
    assert partial.headers['Cross-Origin-Resource-Policy'] == 'same-origin'
    jobs.playback_token = None
    assert client.get('/media/private-capability', base_url=host).status_code == 404


def test_youtube_playback_copy_lives_until_next_job(tmp_path):
    class Events:
        def put_nowait(self, _value): pass
        def cancel_join_thread(self): pass
    directory = tmp_path/'job'
    directory.mkdir()
    source = make_video(directory/'input.mp4')
    worker(source, '動画.mp4', 'standard', 'fine', directory,
           Events(), threading.Event(), source_url='https://www.youtube.com/watch?v=example1234',
           retain_input=True)
    outcome = json.loads((directory/'outcome.json').read_text())
    assert outcome['state'] == 'completed'
    assert outcome['playback_file'] == 'input.mp4'
    assert source.exists()
    jobs = Jobs()
    jobs.directory = str(directory)
    jobs.playback_path = source
    jobs.playback_token = 'old-token'
    jobs.state = 'completed'
    try:
        jobs.begin_upload()
        assert not directory.exists()
        assert jobs.playback_path is None
        assert jobs.playback_token is None
    finally:
        jobs.close()


def test_cancel_before_decode(tmp_path):
    path = make_video(tmp_path/'video.mp4')
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        analyze(path,cancel=cancel)


def wait_job(jobs):
    for _ in range(200):
        state = jobs.poll()
        if state['state'] not in Jobs.ACTIVE:
            return state
        time.sleep(.05)
    raise AssertionError('job timeout')


def test_job_cancel_restart_cleanup(tmp_path):
    jobs = Jobs()
    source = make_video(tmp_path/'long.mp4',duration=15)
    try:
        path = jobs.begin_upload()
        directory = path.parent
        path.write_bytes(source.read_bytes())
        jobs.launch(path,'long.mp4','standard')
        jobs.cancel()
        assert wait_job(jobs)['state'] == 'cancelled'
        assert not directory.exists()
        path = jobs.begin_upload()
        directory = path.parent
        path.write_bytes(make_video(tmp_path/'short.mp4').read_bytes())
        jobs.launch(path,'short.mp4','standard')
        assert wait_job(jobs)['state'] == 'completed'
        assert jobs.report['candidates']
        assert not directory.exists()
    finally:
        jobs.close()


def test_upload_chunks_cancel_stale_and_restart(tmp_path):
    jobs = Jobs()
    app = create_app(jobs,'test-secret')
    client = app.test_client()
    host = 'http://127.0.0.1:8765'
    headers = {'X-TVFC-Token':'test-secret','Origin':host}
    def post(url, **kwargs):
        return client.post(url,base_url=host,headers=headers,**kwargs)
    try:
        first = post('/api/uploads',json={'filename':'video.mp4','size':10}).json['upload_id']
        directory = Path(jobs.directory)
        assert post(f'/api/uploads/{first}/chunk?offset=0',data=b'12345').status_code == 200
        assert post(f'/api/uploads/{first}/chunk?offset=0',data=b'12345').status_code == 400
        assert post(f'/api/uploads/{first}/finish').status_code == 400
        assert post('/api/cancel').json['state'] == 'cancelled'
        assert not directory.exists()
        source = make_video(tmp_path/'test.mp4').read_bytes()
        second = post('/api/uploads',json={'filename':'test.mp4','size':len(source),
                                          'region_mode':'broad'}).json['upload_id']
        assert post(f'/api/uploads/{first}/chunk?offset=5',data=b'67890').status_code == 409
        assert post(f'/api/uploads/{second}/chunk?offset=0',data=source).status_code == 200
        assert post(f'/api/uploads/{second}/finish').status_code == 202
        assert wait_job(jobs)['state'] == 'completed'
        assert jobs.report['candidates']
        assert jobs.report['settings']['region_mode'] == 'broad'
        assert (jobs.report['settings']['columns'],jobs.report['settings']['rows']) == (4,3)
    finally:
        jobs.close()


def test_disk_shortage_and_expired_upload(monkeypatch):
    import tvfc.web
    from collections import namedtuple
    jobs = Jobs()
    app = create_app(jobs,'secret')
    client = app.test_client()
    host = 'http://127.0.0.1:8765'
    headers = {'X-TVFC-Token':'secret','Origin':host}
    usage = namedtuple('usage','total used free')
    with monkeypatch.context() as patch:
        patch.setattr(tvfc.web.shutil,'disk_usage',lambda path:usage(100,100,0))
        response = client.post('/api/uploads',base_url=host,headers=headers,
                               json={'filename':'x.mp4','size':100})
        assert response.status_code == 400
        assert jobs.directory is None
    path = jobs.begin_upload()
    directory = path.parent
    path.write_bytes(b'partial')
    jobs.upload_updated -= 121
    assert jobs.poll()['state'] == 'failed'
    assert not directory.exists()


def test_cancel_during_decoding(tmp_path):
    path = make_video(tmp_path/'long.mp4',duration=10)
    event = threading.Event()
    calls = []
    def progress(state):
        calls.append(state)
        event.set()
    with pytest.raises(Cancelled):
        analyze(path,progress=progress,cancel=event)
    assert calls


def test_default_window_is_launched(monkeypatch):
    import tvfc.web
    opened = []
    class FakeServer:
        effective_port = 8765
        def run(self):
            pass
        def close(self):
            pass
    class FakeWindow:
        returncode = 0
        def poll(self):
            return 0
    monkeypatch.setattr(tvfc.web, 'create_server', lambda *args, **kwargs: FakeServer())
    monkeypatch.setattr(tvfc.web, '_desktop_process', lambda url: (opened.append(url), FakeWindow())[1])
    tvfc.web.serve(desktop=True)
    assert len(opened) == 1 and opened[0].startswith('http://127.0.0.1:8765/#token=')
