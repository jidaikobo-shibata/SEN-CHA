import hmac
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import unquote
import webbrowser
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request, send_file
from waitress import create_server

from . import __version__
from .jobs import Jobs
from .media import Cancelled
from .reports import serialize
from .settings import DEFAULT, DEFAULT_SENSITIVITY, REGION_GRIDS


def create_app(jobs=None, token=None, expected_host="127.0.0.1:8765", shutdown=None):
    app = Flask(__name__)
    jobs = jobs or Jobs()
    token = token or secrets.token_urlsafe(32)
    app.config.update(MAX_CONTENT_LENGTH=2*1024**2, TESTING=False)
    app.extensions["jobs"] = jobs
    app.extensions["token"] = token
    app.config["EXPECTED_HOST"] = expected_host

    @app.before_request
    def guard():
        host = app.config["EXPECTED_HOST"]
        if request.host != host:
            abort(403)
        if request.headers.get("Origin") not in (None, f"http://{host}"):
            abort(403)
        if request.path.startswith("/api/"):
            supplied = request.headers.get("X-TVFC-Token", "")
            if not hmac.compare_digest(supplied, token):
                abort(403)
            if request.method != "GET" and request.headers.get("Origin") != f"http://{host}":
                abort(403)

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
            "connect-src 'self'; media-src 'self' blob:; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'")
        return response

    @app.errorhandler(413)
    def too_large(error):
        return jsonify(error="動画は4GiB以内にしてください。"), 413

    @app.get("/")
    def index():
        return render_template("index.html", version=__version__)

    def legal_root():
        packaged = Path(sys.executable).resolve().parent
        if (packaged / "THIRD_PARTY_NOTICES.md").is_file():
            return packaged
        return Path(__file__).resolve().parents[2]

    @app.get("/legal/notices")
    def legal_notices():
        path = legal_root() / "THIRD_PARTY_NOTICES.md"
        if not path.is_file():
            abort(404)
        return Response(path.read_text(encoding="utf-8"), content_type="text/plain; charset=utf-8")

    @app.get("/legal/license")
    def legal_license_text():
        path = legal_root() / "LICENSE"
        if not path.is_file():
            abort(404)
        return Response(path.read_text(encoding="utf-8"), content_type="text/plain; charset=utf-8")

    @app.get("/legal/licenses")
    def legal_licenses():
        root = legal_root()
        directory = root / "licenses"
        if not directory.is_dir():
            directory = root / "dist" / "SEN-CHA" / "licenses"
        files = sorted(path.relative_to(directory).as_posix() for path in directory.rglob("*")
                       if path.is_file() and not path.is_symlink()) if directory.is_dir() else []
        return jsonify(files=files)

    @app.get("/legal/licenses/<path:name>")
    def legal_license(name):
        root = legal_root()
        directory = root / "licenses"
        if not directory.is_dir():
            directory = root / "dist" / "SEN-CHA" / "licenses"
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            abort(404)
        return send_file(path, mimetype="text/plain", as_attachment=False)

    @app.get("/api/status")
    def status():
        return jsonify(jobs.poll())

    @app.post("/api/uploads")
    def begin_upload():
        data = request.get_json(silent=True) or {}
        length = data.get("size")
        sensitivity = data.get("sensitivity", DEFAULT_SENSITIVITY)
        region_mode = data.get("region_mode", "fine")
        if type(length) is not int or not 0 < length <= DEFAULT.max_upload_bytes:
            return jsonify(error="空でない4GiB以内の動画を選択してください。"), 400
        if sensitivity not in ("standard", "high"):
            return jsonify(error="感度が不正です。"), 400
        if not isinstance(region_mode, str) or region_mode not in REGION_GRIDS:
            return jsonify(error="検出領域の設定が不正です。"), 400
        filename = str(data.get("filename", "video"))[:255]
        filename = filename.replace("\\", "/").split("/")[-1]
        filename = "".join(c for c in filename if c >= " " and c != "\x7f") or "video"
        with jobs.lock:
            try:
                path = jobs.begin_upload()
            except ValueError as error:
                return jsonify(error=str(error)), 409
            if shutil.disk_usage(path.parent).free < length + 128*1024**2:
                jobs.upload_failed("一時コピーに必要な空き容量がありません。")
                return jsonify(error=jobs.message), 400
            jobs.upload_expected = length
            jobs.upload_filename = filename
            jobs.upload_sensitivity = sensitivity
            jobs.upload_region_mode = region_mode
            return jsonify(upload_id=jobs.upload_id), 201

    @app.post("/api/youtube")
    def begin_youtube():
        data = request.get_json(silent=True) or {}
        try:
            jobs.begin_youtube(data.get("url"), data.get("sensitivity", DEFAULT_SENSITIVITY),
                               data.get("region_mode", "fine"))
        except ValueError as error:
            return jsonify(error=str(error)), 400
        except OSError:
            return jsonify(error="YouTube動画の取得を開始できませんでした。"), 500
        return jsonify(jobs.poll()), 202

    @app.post("/api/uploads/<upload_id>/chunk")
    def upload_chunk(upload_id):
        with jobs.lock:
            if jobs.state != "uploading" or upload_id != jobs.upload_id:
                return jsonify(error="このコピーは終了または中止されています。"), 409
            try:
                offset = int(request.args.get("offset", "-1"))
            except ValueError:
                return jsonify(error="コピー位置が不正です。"), 400
            length = request.content_length
            if (offset != jobs.upload_written or not length or length > 1024**2
                    or offset+length > jobs.upload_expected):
                return jsonify(error="コピーの長さまたは順序が不正です。"), 400
            from pathlib import Path
            path = Path(jobs.directory)/"input.video"
            try:
                if shutil.disk_usage(path.parent).free < length + 64*1024**2:
                    raise OSError("作業領域の空き容量が不足しています。")
                data = request.get_data()
                if len(data) != length:
                    raise OSError("コピーが途中で途切れました。")
                with path.open("ab") as file:
                    file.write(data)
                jobs.upload_written += length
                jobs.upload_updated = time.monotonic()
                jobs.message = f"端末内へコピー中：{jobs.upload_written*100//jobs.upload_expected}%"
                return jsonify(copied=jobs.upload_written)
            except OSError as error:
                jobs.upload_failed(str(error))
                return jsonify(error=jobs.message), 400

    @app.post("/api/uploads/<upload_id>/finish")
    def finish_upload(upload_id):
        with jobs.lock:
            if jobs.state != "uploading" or upload_id != jobs.upload_id:
                return jsonify(error="このコピーは終了または中止されています。"), 409
            if jobs.upload_written != jobs.upload_expected:
                return jsonify(error="動画のコピーが完了していません。"), 400
            from pathlib import Path
            try:
                jobs.launch(Path(jobs.directory)/"input.video", jobs.upload_filename,
                            jobs.upload_sensitivity, jobs.upload_region_mode)
            except (OSError, ValueError) as error:
                jobs.upload_failed("解析を開始できませんでした。" + str(error))
                return jsonify(error=jobs.message), 400
            return jsonify(jobs.poll()), 202

    @app.post("/api/cancel")
    def cancel():
        jobs.cancel()
        return jsonify(jobs.poll())

    @app.get("/api/result")
    def result():
        jobs.poll()
        if jobs.report is None:
            return jsonify(error="正常完了した結果がありません。"), 409
        return jsonify(jobs.report)

    @app.get("/api/playback")
    def playback():
        jobs.poll()
        with jobs.lock:
            if jobs.state != "completed" or not jobs.playback_path or not jobs.playback_token:
                return jsonify(error="再生用の動画がありません。"), 404
            return jsonify(url=f"/media/{jobs.playback_token}")

    @app.get("/media/<capability>")
    def playback_media(capability):
        jobs.poll()
        with jobs.lock:
            if (jobs.state != "completed" or not jobs.playback_path or
                    not jobs.playback_token or
                    not hmac.compare_digest(capability, jobs.playback_token)):
                abort(404)
            path = jobs.playback_path
            if not path.is_file() or path.is_symlink():
                abort(404)
            return send_file(path, conditional=True)

    @app.get("/api/report/<format>")
    def report(format):
        jobs.poll()
        if format not in ("html", "json", "csv") or jobs.report is None:
            abort(404)
        content = serialize(jobs.report, format)
        return Response(content, content_type="application/octet-stream",
                        headers={"Content-Disposition": f'attachment; filename="sen-cha-{secrets.token_hex(6)}.{format}"'})

    @app.post("/api/shutdown")
    def quit_app():
        if jobs.poll()["state"] in Jobs.ACTIVE:
            return jsonify(error="処理を中止してから終了してください。"), 409
        if shutdown:
            threading.Timer(.5, shutdown).start()
        return jsonify(message="アプリを終了しました。このタブを閉じてください。")
    return app


def _desktop_process(url):
    if sys.platform != "linux":
        raise OSError("この版の専用ウィンドウはUbuntuで検証しています。")
    helper = Path(__file__).with_name("desktop_gtk.py")
    if not helper.exists():
        raise OSError("専用ウィンドウの起動ファイルが見つかりません。")
    process = subprocess.Popen(["/usr/bin/python3", str(helper)], stdin=subprocess.PIPE,
                               text=True, bufsize=1)
    process.stdin.write(url + "\n")
    process.stdin.flush()
    return process


def serve(port=0, open_browser=False, ready_file=None, desktop=True):
    jobs = Jobs()
    token = secrets.token_urlsafe(32)
    done = threading.Event()
    app = create_app(jobs, token, shutdown=done.set)
    server = create_server(app, host="127.0.0.1", port=port, threads=4,
                           max_request_body_size=2*1024**2,
                           channel_timeout=30, clear_untrusted_proxy_headers=True)
    host = f"127.0.0.1:{server.effective_port}"
    app.config["EXPECTED_HOST"] = host
    url = f"http://{host}/#token={token}"
    if ready_file:
        from pathlib import Path
        descriptor = os.open(ready_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump({"url":url}, file)
    print("SEN-CHA:", url, flush=True)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    desktop_process = None
    desktop_started_at = None
    try:
        if open_browser:
            webbrowser.open(url)
        elif desktop:
            desktop_process = _desktop_process(url)
            desktop_started_at = time.monotonic()
        while not done.wait(.5):
            jobs.poll()
            if desktop_process and desktop_process.poll() is not None:
                if desktop_process.returncode and time.monotonic()-desktop_started_at < 2:
                    raise OSError("専用ウィンドウを起動できません。GTK/WebKitGTKを確認するか、--browserを指定してください。")
                if desktop_process.returncode:
                    print("専用ウィンドウが終了したため、アプリを終了します。", file=sys.stderr)
                break
    except KeyboardInterrupt:
        pass
    finally:
        jobs.close()
        server.close()
        if desktop_process and desktop_process.poll() is None:
            try:
                desktop_process.stdin.write("quit\n")
                desktop_process.stdin.flush()
                desktop_process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                if desktop_process.poll() is None:
                    desktop_process.terminate()
                    desktop_process.wait(timeout=3)
