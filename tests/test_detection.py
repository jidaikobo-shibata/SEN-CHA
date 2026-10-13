import numpy as np
import pytest
from dataclasses import replace

from tvfc.detection import Detector
from tvfc.analysis import analyze
from tvfc.media import MediaError
from tvfc.timeline import Timeline
from tvfc.settings import DEFAULT
from fixtures import make_video


def hits_for(kind, fps=30, sensitivity="standard"):
    detector = Detector(sensitivity)
    hits = []
    for i in range(fps*3):
        t = i/fps
        level = 255 if int(t*8)%2 else 0
        if kind == "static": level = 100
        if kind == "cut": level = 255 if t >= 1 else 0
        if kind == "fade": level = round(t/3*255)
        frame = np.full((60,80,3), level, dtype=np.uint8)
        hits.extend(detector.step(frame,t))
    return hits


@pytest.mark.parametrize("kind", ["static", "cut", "fade"])
def test_nonrepeating(kind):
    assert not hits_for(kind)


def test_four_hz():
    assert hits_for("flash")


def test_high_includes_standard():
    standard = hits_for("flash")
    high = hits_for("flash", sensitivity="high")
    assert [h for h in high if h["profile"] == "standard"] == standard


def test_region_modes_can_suppress_local_flash_but_keep_whole_screen():
    detectors = {name: Detector('standard', settings=replace(DEFAULT, columns=cols, rows=rows))
                 for name, (cols, rows) in {"fine": (8, 6), "broad": (4, 3),
                                           "whole": (0, 0)}.items()}
    local_hits = {name: [] for name in detectors}
    for i in range(90):
        frame = np.zeros((60, 80, 3), dtype=np.uint8)
        if int(i / 30 * 8) % 2:
            frame[2:8, 2:8] = 255
        for name, detector in detectors.items():
            local_hits[name].extend(detector.step(frame, i / 30))
    assert local_hits["fine"]
    assert not local_hits["broad"]
    assert not local_hits["whole"]
    for detector in detectors.values():
        hits = []
        for i in range(90):
            level = 255 if int(i / 30 * 8) % 2 else 0
            hits.extend(detector.step(np.full((60, 80, 3), level, dtype=np.uint8), 3 + i / 30))
        assert any(hit["region"] == 0 for hit in hits)


@pytest.mark.parametrize("kind", ["static","cut","fade","flash","partial","red"])
def test_video(kind, tmp_path):
    report = analyze(make_video(tmp_path / f"{kind}.mp4",kind))
    assert bool(report["candidates"]) == (kind in ("flash","partial","red"))
    assert report["frames"] == 90
    assert report["timeline"]
    assert len(report["timeline"]) <= 1200
    assert report["detail_timeline"]
    assert len(report["detail_timeline"]) <= 60000
    assert all(0 <= point["luminance"] <= 1 and 0 <= point["red"] <= 1
               for point in report["timeline"])
    if report["candidates"]:
        assert .4 <= report["candidates"][0]["start"] < .8
        assert report["candidates"][0]["end"] >= 2.5
    if kind == "red":
        assert any(e["kind"] == "red" for c in report["candidates"] for e in c["evidence"])
    if kind == "partial":
        assert any(e["region"] != 0 for c in report["candidates"] for e in c["evidence"])


def test_timeline_keeps_brief_peak_in_long_video():
    timeline = Timeline(3600, bins=1200)
    timeline.add(120.01, .9, .1)
    timeline.add(120.02, .05, .8)
    timeline.add(120.03, .02, .01)
    points = timeline.export()
    assert len(points) == 1
    assert points[0]["luminance"] == .9
    assert points[0]["red"] == .8


def test_detail_timeline_separates_peaks_hidden_in_overview_bin():
    overview = Timeline(3600, bins=1200)
    detail = Timeline(3600, bins=60000)
    for chart in (overview, detail):
        chart.add(120.01, .9, .1)
        chart.add(120.2, .05, .8)
    assert len(overview.export()) == 1
    assert len(detail.export()) == 2


@pytest.mark.parametrize("fps,vfr,codec", [(30,False,"vp9"),(60,False,"h264"),(60,True,"h264")])
def test_rates_and_codecs(tmp_path, fps, vfr, codec):
    path = tmp_path / ("日本語 空白.webm" if codec == "vp9" else "日本語 空白.mp4")
    report = analyze(make_video(path, fps=fps, vfr=vfr, codec=codec))
    assert report["candidates"]
    assert .4 <= report["candidates"][0]["start"] < .8
    assert 2.5 <= report["candidates"][0]["end"] <= 3
    assert report["frames"] == (fps*3 if not vfr else round(fps*3*.8))


def test_corrupt(tmp_path):
    path = tmp_path / "bad.mp4"
    path.write_bytes(b"not a video")
    with pytest.raises(MediaError):
        analyze(path)


def test_three_hz_no_standard_candidate():
    detector = Detector('standard')
    hits = []
    for i in range(240):
        frame = np.full((12,16,3),255 if (i//10)%2 else 0,dtype=np.uint8)
        hits.extend(detector.step(frame,i/60))
    assert not hits


def test_second_boundary_window():
    detector = Detector('standard')
    hits = []
    # Eight transitions at .55 ... 1.425: four pairs straddling the second boundary.
    times = [.55+.125*i for i in range(8)]
    for i in range(121):
        t = i/60
        level = 255 if sum(t >= change for change in times)%2 else 0
        hits.extend(detector.step(np.full((12,16,3),level,dtype=np.uint8),t))
    assert hits
    assert any(h['start'] < 1 < h['end'] for h in hits)


def test_high_includes_randomized_standard():
    rng = np.random.default_rng(27)
    a,b = Detector('standard'),Detector('high')
    for i in range(120):
        frame = rng.integers(0,256,size=(12,16,3),dtype=np.uint8)
        standard = a.step(frame,i/30)
        high = b.step(frame,i/30)
        assert [h for h in high if h['profile']=='standard'] == standard


def test_hdr_rejected(tmp_path):
    import subprocess
    import imageio_ffmpeg
    from tvfc.media import Unsupported
    source = make_video(tmp_path/'source.mp4')
    target = tmp_path/'hdr.mp4'
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(source),
                    '-c:v','libx264','-preset','ultrafast','-color_trc','smpte2084',str(target)],check=True)
    with pytest.raises(Unsupported,match='伝達特性'):
        analyze(target)


def test_network_playlist_rejected(tmp_path):
    target = tmp_path/'playlist.m3u8'
    target.write_text('#EXTM3U\n#EXTINF:3\nhttp://127.0.0.1:9/secret.ts\n')
    with pytest.raises(MediaError):
        analyze(target)
