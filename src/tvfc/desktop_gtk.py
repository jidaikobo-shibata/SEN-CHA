"""Ubuntu desktop shell. Executed by the OS Python with GTK/WebKit bindings."""
import os
import json
from pathlib import Path
import sys
import tempfile
from urllib.parse import parse_qs, urlparse
from urllib.request import ProxyHandler, Request, build_opener

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import GLib, Gtk, WebKit2  # noqa: E402

APP_NAME = "SEN-CHA"

EXTERNAL_HELP_URLS = {
    "https://www.youtube.com/t/terms",
    "https://waic.jp/translations/WCAG22/Understanding/three-flashes-or-below-threshold",
    "https://waic.jp/translations/WCAG22/Understanding/three-flashes",
}


def create_window(url):
    # GTK otherwise derives the task-list name from desktop_gtk.py.
    GLib.set_prgname("SEN-CHA")
    GLib.set_application_name(APP_NAME)
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not parsed.port:
        raise SystemExit("ローカル画面のURLが不正です。")
    origin = f"http://127.0.0.1:{parsed.port}"
    tokens = parse_qs(parsed.fragment).get("token", [])
    if len(tokens) != 1 or not tokens[0]:
        raise SystemExit("ローカル画面の認証情報がありません。")
    token = tokens[0]
    window = Gtk.Window(title=APP_NAME)
    window.set_default_size(1080, 820)
    window.set_size_request(390, 400)
    manager = WebKit2.UserContentManager()
    manager.register_script_message_handler("tvfc")
    view = WebKit2.WebView.new_with_user_content_manager(manager)
    settings = view.get_settings()
    settings.set_enable_developer_extras(False)

    def decide_policy(_view, decision, kind):
        if kind in (WebKit2.PolicyDecisionType.NAVIGATION_ACTION,
                    WebKit2.PolicyDecisionType.NEW_WINDOW_ACTION):
            target = decision.get_request().get_uri()
            if not target.startswith(origin + "/"):
                decision.ignore()
                if target in EXTERNAL_HELP_URLS:
                    Gtk.show_uri_on_window(window, target, Gtk.get_current_event_time())
                return True
        return False

    view.connect("decide-policy", decide_policy)
    context = view.get_context()

    def save_report(_manager, message):
        try:
            request_data = json.loads(message.get_js_value().to_string())
        except (TypeError, ValueError):
            return
        if not isinstance(request_data, dict):
            return
        format = request_data.get("format")
        if format not in ("html", "json", "csv"):
            return
        suggested = request_data.get("filename")
        if not isinstance(suggested, str):
            return
        safe_name = Path(suggested.replace("\\", "/")).name
        if (safe_name != suggested or len(safe_name) > 255 or
                safe_name != safe_name.strip() or
                any(ord(char) < 32 or ord(char) == 127 for char in safe_name) or
                not safe_name.lower().endswith("." + format)):
            return
        dialog = Gtk.FileChooserDialog(
            title="レポートを保存", transient_for=window,
            action=Gtk.FileChooserAction.SAVE)
        dialog.add_buttons("中止", Gtk.ResponseType.CANCEL,
                           "保存", Gtk.ResponseType.ACCEPT)
        dialog.set_do_overwrite_confirmation(True)
        dialog.set_current_name(safe_name)
        response = dialog.run()
        destination = dialog.get_filename() if response == Gtk.ResponseType.ACCEPT else None
        dialog.destroy()
        if not destination:
            return
        temporary = None
        try:
            request = Request(f"{origin}/api/report/{format}", headers={
                "X-TVFC-Token": token, "Origin": origin})
            with tempfile.NamedTemporaryFile(mode="wb", dir=Path(destination).parent,
                    prefix=".tvfc-report-", suffix=".tmp", delete=False) as output:
                temporary = Path(output.name)
                source = build_opener(ProxyHandler({})).open(request, timeout=30)
                with source:
                    total = 0
                    while data := source.read(1024**2):
                        total += len(data)
                        if total > 512*1024**2:
                            raise ValueError("レポートが512MiBを超えています。")
                        output.write(data)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, destination)
            temporary = None
        except Exception as error:
            if temporary:
                temporary.unlink(missing_ok=True)
            alert = Gtk.MessageDialog(transient_for=window, modal=True,
                message_type=Gtk.MessageType.ERROR, buttons=Gtk.ButtonsType.CLOSE,
                text="レポートを保存できませんでした。")
            alert.format_secondary_text(str(error))
            alert.run()
            alert.destroy()

    manager.connect("script-message-received::tvfc", save_report)

    def download_started(_context, download):
        def choose_destination(_download, suggested_name):
            safe_name = Path(suggested_name.replace("\\", "/")).name or "tvfc-report"
            dialog = Gtk.FileChooserDialog(
                title="レポートを保存", transient_for=window,
                action=Gtk.FileChooserAction.SAVE)
            dialog.add_buttons("中止", Gtk.ResponseType.CANCEL,
                               "保存", Gtk.ResponseType.ACCEPT)
            dialog.set_do_overwrite_confirmation(True)
            dialog.set_current_name(safe_name)
            response = dialog.run()
            destination = dialog.get_filename() if response == Gtk.ResponseType.ACCEPT else None
            dialog.destroy()
            if destination:
                download.set_destination(Path(destination).absolute().as_uri())
                return True
            download.cancel()
            return True
        download.connect("decide-destination", choose_destination)

    context.connect("download-started", download_started)
    window.add(view)
    return window, view


def main():
    url = sys.stdin.readline().strip()
    window, view = create_window(url)
    window.connect("delete-event", lambda *_: (Gtk.main_quit(), False)[1])
    window.connect("destroy", Gtk.main_quit)

    def parent_command(_source, condition):
        if condition & (GLib.IOCondition.HUP | GLib.IOCondition.ERR):
            Gtk.main_quit()
            return False
        if sys.stdin.readline().strip() == "quit":
            Gtk.main_quit()
            return False
        return True

    GLib.io_add_watch(sys.stdin, GLib.IOCondition.IN | GLib.IOCondition.HUP, parent_command)
    view.load_uri(url)
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
