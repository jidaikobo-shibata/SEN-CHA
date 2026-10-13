"""Build an offline onedir package for the current OS. Does not publish anything."""
from importlib import metadata
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
NAME = 'SEN-CHA'
RUNTIME_PACKAGES = ['numpy','Flask','waitress','Pillow','blinker','click','itsdangerous',
                    'Jinja2','MarkupSafe','Werkzeug','yt-dlp','yt-dlp-ejs','brotli',
                    'certifi','charset-normalizer','idna','mutagen','pycryptodomex',
                    'requests','urllib3','websockets']


def main():
    numpy_config = np.show_config(mode='dicts')
    if sys.platform == 'linux' and any(
        numpy_config.get('Build Dependencies', {}).get(name, {}).get('name') != 'none'
        for name in ('blas', 'lapack')
    ):
        raise SystemExit('Ubuntu配布版はBLAS/LAPACKなしのNumPyが必要です。docs/distribution.mdを参照してください。')
    suffix = '.exe' if sys.platform == 'win32' else ''
    for binary in ('ffmpeg','ffprobe'):
        if not (ROOT/'vendor/bin'/(binary+suffix)).is_file():
            raise SystemExit(f'vendor/bin/{binary}{suffix}が必要です。')
    if not (ROOT/'vendor/bin'/('qjs'+suffix)).is_file():
        raise SystemExit('vendor/bin/qjsが必要です。docs/distribution.mdを参照してください。')
    args = [sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir',
            '--name',NAME,'--paths',str(ROOT/'src'),
            '--add-data',f'{ROOT / "src/tvfc/templates"}:tvfc/templates',
            '--add-data',f'{ROOT / "src/tvfc/static"}:tvfc/static']
    if sys.platform == 'linux':
        args += ['--add-data',f'{ROOT / "src/tvfc/desktop_gtk.py"}:tvfc']
    args += ['--collect-data', 'yt_dlp_ejs', '--collect-submodules', 'yt_dlp.extractor']
    for binary in (ROOT/'vendor/bin').iterdir():
        if binary.is_file():
            args += ['--add-binary',f'{binary}:vendor/bin']
    args += [str(ROOT/'scripts/launcher.py')]
    subprocess.run(args,cwd=ROOT,check=True)
    output = ROOT/'dist'/NAME
    notices = output/'licenses'
    notices.mkdir(exist_ok=True)
    package_info = []
    for name in RUNTIME_PACKAGES + ['setuptools','packaging','pyinstaller']:
        dist = metadata.distribution(name)
        package_info.append({'name':dist.metadata['Name'],'version':dist.version,
                             'source':f'https://pypi.org/project/{name}/{dist.version}/'})
        for item in dist.files or []:
            if any(word in str(item).lower() for word in ('license','copying','notice','authors')):
                source = Path(dist.locate_file(item))
                if source.is_file():
                    target = notices/name/str(item).replace('..','_')
                    target.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(source,target)
    base = Path(sys.base_prefix)
    python_license = base/'lib'/f'python{sys.version_info.major}.{sys.version_info.minor}'/'LICENSE.txt'
    if not python_license.exists():
        python_license = base/'LICENSE.txt'
    if python_license.exists():
        shutil.copy2(python_license,notices/'Python-LICENSE')
    zlib_license = Path('/usr/share/doc/zlib1g/copyright')
    if zlib_license.exists():
        shutil.copy2(zlib_license,notices/'zlib-copyright')
    for package in ('libgcc-s1','libstdc++6'):
        copyright_file = Path('/usr/share/doc')/package/'copyright'
        if copyright_file.exists():
            shutil.copy2(copyright_file,notices/f'{package}-copyright')
    source_dir = ROOT/'vendor/build/ffmpeg-8.0.3'
    for name in ('COPYING.LGPLv2.1','LICENSE.md'):
        if (source_dir/name).exists():
            shutil.copy2(source_dir/name,notices/f'FFmpeg-{name}')
    supplied_notices = ROOT/'vendor/licenses'
    if supplied_notices.exists():
        shutil.copytree(supplied_notices,notices/'platform',dirs_exist_ok=True)
    shutil.copytree(ROOT/'third_party_licenses',notices/'bundled-js',dirs_exist_ok=True)
    sources = output/'sources'
    sources.mkdir(exist_ok=True)
    for source in (ROOT/'vendor/sources').glob('*'):
        if source.is_file():
            shutil.copy2(source,sources/source.name)
    shutil.copy2(ROOT/'scripts/build_ffmpeg.py',sources/'build_ffmpeg.py')
    if (ROOT/'scripts/build_quickjs.py').exists():
        shutil.copy2(ROOT/'scripts/build_quickjs.py',sources/'build_quickjs.py')
    quickjs_license = ROOT/'vendor/build/quickjs-2026-06-04/LICENSE'
    if quickjs_license.exists():
        shutil.copy2(quickjs_license,notices/'QuickJS-LICENSE')
    for name in ('README.md','LICENSE','THIRD_PARTY_NOTICES.md'):
        if (ROOT/name).exists():
            shutil.copy2(ROOT/name,output/name)
    if (ROOT/'docs').exists():
        shutil.copytree(ROOT/'docs',output/'docs',dirs_exist_ok=True)
    # Include our exact application source for inspection and future modification.
    with tarfile.open(sources/'application-source.tar.gz','w:gz') as archive:
        for relative in ('src','scripts','tests','pyproject.toml','LICENSE','requirements.lock',
                         'requirements-dev.lock','GOAL.md','GOAL-desktop-youtube.md',
                         'third_party_licenses'):
            source = ROOT/relative
            if source.exists():
                archive.add(source,arcname=relative,filter=lambda info: None if any(x in info.name for x in ('__pycache__','tests/generated')) else info)
    info = {'platform':platform.platform(),'machine':platform.machine(),
            'python':platform.python_version(),'runtime_dependencies':package_info,
            'numpy_configuration':numpy_config}
    (output/'build-info.json').write_text(json.dumps(info,indent=2),encoding='utf-8')
    checksums = []
    for source in sorted(output.rglob('*')):
        if source.is_file() and source.name != 'SHA256SUMS':
            checksums.append(f'{hashlib.sha256(source.read_bytes()).hexdigest()}  {source.relative_to(output).as_posix()}')
    (output/'SHA256SUMS').write_text('\n'.join(checksums)+'\n',encoding='utf-8')
    archive_base = ROOT/'dist'/f'{NAME}-{sys.platform}-{platform.machine()}'
    format = 'zip' if sys.platform == 'win32' else 'gztar'
    archive_path = shutil.make_archive(str(archive_base),format,root_dir=ROOT/'dist',base_dir=NAME)
    print('配布物:', archive_path)


if __name__ == '__main__':
    main()
