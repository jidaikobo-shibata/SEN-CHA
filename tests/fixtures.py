"""Synthetic fixtures are generated, never automatically played."""
from pathlib import Path
import subprocess
import tempfile

import numpy as np


def make_video(path, kind="flash", fps=30, duration=3, codec="h264", vfr=False):
    import imageio_ffmpeg
    binary = imageio_ffmpeg.get_ffmpeg_exe()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 320, 180
    args = [binary, "-hide_banner", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{width}x{height}", "-r", str(fps), "-i", "pipe:0", "-an"]
    if vfr:
        args += ["-vf", "select='not(eq(mod(n,5),1))'", "-fps_mode", "vfr"]
    args += ["-c:v", "libx264" if codec == "h264" else "libvpx-vp9", "-pix_fmt", "yuv420p",
             "-threads", "2"]
    if codec == "h264":
        args += ["-preset", "ultrafast", "-crf", "0"]
    else:
        args += ["-lossless", "1", "-deadline", "realtime"]
    args += [str(path)]
    with tempfile.TemporaryFile() as error:
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stderr=error)
        try:
            for i in range(round(duration*fps)):
                t = i/fps
                frame = np.zeros((height,width,3),dtype=np.uint8)
                flashing = 0.4 <= t < duration-.25 and int((t-.4)*8)%2 == 1
                if kind == "static":
                    frame[:] = 70
                elif kind == "cut":
                    frame[:] = 200 if t >= 1 else 20
                elif kind == "fade":
                    frame[:] = round(min(1,t/duration)*255)
                elif kind == "partial":
                    frame[:height//3, width*3//4:] = 255 if flashing else 0
                elif kind == "red":
                    frame[:] = [255,0,0] if flashing else [0,0,0]
                else:
                    frame[:] = 255 if flashing else 0
                process.stdin.write(frame.tobytes())
        finally:
            process.stdin.close()
            process.wait()
        if process.returncode:
            error.seek(0)
            raise RuntimeError(error.read().decode())
    return path
