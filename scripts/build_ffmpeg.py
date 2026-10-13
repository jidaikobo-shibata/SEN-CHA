"""Build the local-only LGPL FFmpeg binaries on Linux/macOS. No sudo or downloads."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '8.0.3'
SOURCE = ROOT/'vendor/sources'/f'ffmpeg-{VERSION}.tar.xz'


def main():
    if sys.platform == 'win32':
        raise SystemExit('Windowsはdocs/distribution.mdのFFmpeg準備手順を参照してください。')
    if not SOURCE.is_file():
        raise SystemExit(f'公式ソースを配置してください: {SOURCE}')
    expected = '6136812ea6d4e68bdba27e33c2a94382711cdf4f8602ffef056ff792bd6f9818'
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != expected:
        raise SystemExit('FFmpegソースのSHA256が確認済みの値と一致しません。')
    build = ROOT/'vendor/build'
    build.mkdir(parents=True,exist_ok=True)
    with tarfile.open(SOURCE) as archive:
        archive.extractall(build,filter='data')
    source_dir = build/f'ffmpeg-{VERSION}'
    args = ['./configure', f'--prefix={ROOT / "vendor"}', '--disable-autodetect',
            '--disable-network','--disable-x86asm','--disable-doc','--disable-debug',
            '--disable-ffplay','--disable-shared','--enable-static','--disable-everything',
            '--enable-ffmpeg','--enable-ffprobe','--enable-protocol=file,pipe',
            '--enable-demuxer=mov,matroska,avi,rawvideo,image2,concat',
            '--enable-decoder=h264,vp9,mpeg4,ffv1,rawvideo,png,mjpeg',
            '--enable-encoder=rawvideo,ffv1,png,mpeg4',
            '--enable-muxer=rawvideo,matroska,avi,image2,mov,mp4',
            '--enable-filter=scale,format,showinfo,null,setsar,setpts','--enable-zlib']
    subprocess.run(args,cwd=source_dir,check=True)
    subprocess.run(['make','-j4'],cwd=source_dir,check=True)
    subprocess.run(['make','install'],cwd=source_dir,check=True)
    print('FFmpeg SHA256:',hashlib.sha256(SOURCE.read_bytes()).hexdigest())


if __name__ == '__main__':
    main()
