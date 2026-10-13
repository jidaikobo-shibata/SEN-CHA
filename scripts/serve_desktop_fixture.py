"""Local-only server with a precomputed result for the GTK save smoke test."""
import json
import os
from pathlib import Path
import secrets
import sys
import threading

from waitress import create_server

from tvfc.analysis import analyze
from tvfc.jobs import Jobs
from tvfc.web import create_app

def main():
    root = Path(__file__).resolve().parents[1]
    ready = Path(sys.argv[1])
    jobs = Jobs()
    jobs.report = analyze(root/'tests/generated/明暗 点滅.mp4')
    jobs.state = "completed"
    jobs.message = "解析が完了しました。"
    done = threading.Event()
    token = secrets.token_urlsafe(32)
    app = create_app(jobs, token, shutdown=done.set)
    server = create_server(app, host="127.0.0.1", port=0)
    host = f"127.0.0.1:{server.effective_port}"
    app.config['EXPECTED_HOST'] = host
    with os.fdopen(os.open(ready, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600), 'w') as file:
        json.dump({'url':f'http://{host}/#token={token}'}, file)
    threading.Thread(target=server.run, daemon=True).start()
    try:
        done.wait()
    finally:
        jobs.close()
        server.close()


if __name__ == '__main__':
    main()
