import shutil
import threading

import pytest

from fixtures import make_video
from tvfc.media import Cancelled, Unsupported
from tvfc.web import create_app
from tvfc.youtube import canonical_url, download_video


@pytest.mark.parametrize('url', [
    'https://youtu.be/YE7VzlLtp-4',
    'https://youtube.com/watch?v=YE7VzlLtp-4&t=10',
    'https://m.youtube.com/shorts/YE7VzlLtp-4',
])
def test_single_video_url(url):
    assert canonical_url(url) == 'https://www.youtube.com/watch?v=YE7VzlLtp-4'


@pytest.mark.parametrize('url', [
    'https://youtube.com.evil.example/watch?v=YE7VzlLtp-4',
    'https://youtube.com@evil.example/watch?v=YE7VzlLtp-4',
    'http://youtube.com/watch?v=YE7VzlLtp-4',
    'https://youtube.com:444/watch?v=YE7VzlLtp-4',
    'https://youtube.com/playlist?list=abc',
    'https://youtube.com/watch?v=YE7VzlLtp-4&list=abc',
    'https://youtube.com/watch?v=YE7VzlLtp-4&v=YE7VzlLtp-4',
    'https://youtu.be/YE7VzlLtp-4?list=abc',
    'https://youtube.com/watch?v=YE7VzlLtp-4#fragment',
    'https://youtu.be/YE7VzlLtp-4/other',
    'file:///etc/passwd',
])
def test_reject_other_urls(url):
    with pytest.raises(ValueError):
        canonical_url(url)


def test_download_hooks_and_offline_analysis(tmp_path, monkeypatch):
    source = make_video(tmp_path/'fixture.mp4')
    directory = tmp_path/'acquired'
    directory.mkdir()
    records = []
    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options
            assert options['noplaylist'] and options['ignoreconfig']
            assert options['remote_components'] == []
            assert options['js_runtimes']['quickjs']['path'].endswith('/qjs')
            assert 'cookiefile' not in options and 'cookiesfrombrowser' not in options
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def extract_info(self, url, download):
            assert url == 'https://www.youtube.com/watch?v=YE7VzlLtp-4'
            assert download is True
            assert self.options['match_filter']({'duration': 3, 'live_status':'not_live'}) is None
            shutil.copyfile(source, directory/'input.mp4')
            self.options['progress_hooks'][0]({'status':'downloading', 'downloaded_bytes':100,
                                               'total_bytes':200})
            return {'title':'テスト動画', 'id':'YE7VzlLtp-4'}
    import yt_dlp
    monkeypatch.setattr(yt_dlp, 'YoutubeDL', FakeYoutubeDL)
    path, filename = download_video('https://youtu.be/YE7VzlLtp-4', directory, records.append)
    assert path.read_bytes() == source.read_bytes()
    assert filename == 'テスト動画.mp4'
    assert records[0]['percent'] == 50


def test_cancel_during_acquisition(tmp_path, monkeypatch):
    import yt_dlp
    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def extract_info(self, url, download):
            self.options['progress_hooks'][0]({'status':'downloading', 'downloaded_bytes':5,
                                               'total_bytes':10})
    monkeypatch.setattr(yt_dlp, 'YoutubeDL', FakeYoutubeDL)
    event = threading.Event()
    event.set()
    with pytest.raises(Cancelled):
        download_video('https://youtu.be/YE7VzlLtp-4', tmp_path, cancel=event)


def test_reject_oversized_download_before_file_is_kept(tmp_path, monkeypatch):
    import yt_dlp
    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def extract_info(self, url, download):
            self.options['progress_hooks'][0]({'status':'downloading',
                'downloaded_bytes':5,'total_bytes':5*1024**3})
    monkeypatch.setattr(yt_dlp, 'YoutubeDL', FakeYoutubeDL)
    with pytest.raises(Unsupported, match='4GiB'):
        download_video('https://youtu.be/YE7VzlLtp-4', tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_url_endpoint_rejects_untrusted_input():
    app = create_app(token='secret')
    client = app.test_client()
    host = 'http://127.0.0.1:8765'
    data = {'url':'https://evil.example/watch?v=YE7VzlLtp-4'}
    assert client.post('/api/youtube',base_url=host,json=data).status_code == 403
    headers = {'X-TVFC-Token':'secret','Origin':host}
    assert client.post('/api/youtube',base_url=host,headers=headers,json=data).status_code == 400
    assert app.extensions['jobs'].directory is None
