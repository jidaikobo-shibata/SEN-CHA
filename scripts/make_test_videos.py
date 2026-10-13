"""Create local test inputs without displaying or playing them."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests'))
from fixtures import make_video

output = ROOT/'tests/generated'
output.mkdir(parents=True,exist_ok=True)
make_video(output/'明暗 点滅.mp4')
make_video(output/'静止画.webm',kind='static',codec='vp9')
make_video(output/'中止用.mp4',duration=30)
(output/'破損.mp4').write_bytes(b'not a video')
if '--benchmark' in sys.argv:
    import imageio_ffmpeg
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-f','lavfi','-i',
                    'testsrc2=duration=60:size=1920x1080:rate=30',
                    '-c:v','libx264','-preset','ultrafast','-crf','28','-threads','2',
                    '-y',str(output/'benchmark-1080p.mp4')],check=True)
print('作成しました。点滅を含むため、自動再生はしません:',output)
