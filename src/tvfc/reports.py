import csv
from datetime import datetime
import html
import io
import json
from pathlib import Path
import uuid

from .settings import SENSITIVITY_LABELS


KINDS = {"luminance": "明暗の反復", "red": "赤色の反復（簡易指標）"}


def csv_safe(value):
    text = str(value)
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def export_csv(report):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["ファイル", "開始秒", "終了秒", "領域", "検出理由", "反復数",
                     "変化量", "検出領域の画面比（閃光面積ではない）", "検出設定", "アプリ版", "処理秒",
                     "動画情報JSON", "全設定JSON", "制約", "作成日時", "取得元URL"])
    extra = [json.dumps(report["metadata"], ensure_ascii=False),
             json.dumps(report["settings"], ensure_ascii=False),
             " / ".join(report["limitations"]), report["created_at"],
             csv_safe(report.get("source_url", ""))]
    for candidate in report["candidates"]:
        for evidence in candidate["evidence"]:
            writer.writerow([csv_safe(report["filename"]), candidate["start"], candidate["end"],
                             evidence["label"], KINDS[evidence["kind"]], evidence["count"],
                             evidence["change"], evidence["area_fraction"],
                             SENSITIVITY_LABELS.get(evidence["profile"], evidence["profile"]),
                             report["app_version"], report["elapsed"]] + extra)
    if not report["candidates"]:
        writer.writerow([csv_safe(report["filename"]), "", "", "", "今回の検出条件では候補なし",
                         "", "", "", SENSITIVITY_LABELS.get(report["settings"]["sensitivity"],
                         report["settings"]["sensitivity"]), report["app_version"], report["elapsed"]] + extra)
    return "\ufeff" + output.getvalue()


def overview_svg(report):
    duration = report["metadata"]["duration"]
    bands = []
    for candidate in report["candidates"]:
        start = max(0, min(1000, candidate["start"] / duration * 1000))
        end = max(start, min(1000, candidate["end"] / duration * 1000))
        bands.append(f'<rect x="{start:.2f}" y="0" width="{max(2, end-start):.2f}" height="150" fill="#ddd2a0"/>')
    paths = []
    for field, color in (("luminance", "#075c69"), ("red", "#a54718")):
        strokes = []
        for point in report.get("timeline", []):
            x = max(0, min(1000, point["time"] / duration * 1000))
            y = 150 - max(0, min(1, point[field])) * 145
            strokes.append(f'M{x:.2f} 150L{x:.2f} {y:.2f}')
        paths.append(f'<path d="{"".join(strokes)}" fill="none" stroke="{color}" stroke-width="1.5"/>')
    return ('<svg viewBox="0 0 1000 160" role="img" '
            'aria-label="動画全体のフレーム間変化と要確認候補の位置。候補の時刻は下の一覧に記載しています。">'
            + ''.join(bands) + '<line x1="0" y1="150" x2="1000" y2="150" stroke="#778b94"/>'
            + ''.join(paths) + '</svg>')


def export_html(report):
    esc = html.escape
    sections = []
    for index, candidate in enumerate(report["candidates"], 1):
        details = []
        overlays = []
        seen = set()
        for evidence in candidate["evidence"]:
            details.append(f'<li>{esc(evidence["label"])}：{KINDS[evidence["kind"]]}、'
                           f'{evidence["count"]}回／移動する1秒窓、変化量 {evidence["change"]:.3f}'
                           f'（{esc(SENSITIVITY_LABELS.get(evidence["profile"], evidence["profile"]))}）</li>')
            if evidence["region"] not in seen:
                seen.add(evidence["region"])
                x0,y0,x1,y1 = evidence["box"]
                overlays.append(f'<rect x="{x0*100}" y="{y0*100}" width="{(x1-x0)*100}" '
                                f'height="{(y1-y0)*100}"/>')
        sections.append(f'<section><h2>候補 {index}：{candidate["start"]:.3f}〜{candidate["end"]:.3f}秒</h2>'
                        f'<div class="image"><img alt="候補区間の静止画" src="data:image/png;base64,{candidate["thumbnail"]}">'
                        f'<svg aria-hidden="true" viewBox="0 0 100 100" preserveAspectRatio="none">{"".join(overlays)}</svg></div>'
                        f'<p>静止画の時刻：{candidate["thumbnail_time"]:.3f}秒。枠は区間内で検出した領域です。</p>'
                        f'<ul>{"".join(details)}</ul></section>')
    summary = f'要確認候補 {len(report["candidates"])}件' if report["candidates"] else "今回の検出条件では候補なし"
    metadata = {key: report[key] for key in ("metadata", "settings", "app_version", "frames", "elapsed", "created_at")}
    if report.get("source_url"):
        metadata["source_url"] = report["source_url"]
    return f'''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>SEN-CHA — 点滅確認候補 — {esc(report['filename'])}</title>
<style>body{{font:1rem/1.7 sans-serif;max-width:64rem;margin:auto;padding:2rem;color:#182d39;background:#fff}}section{{border-top:2px solid #607482;padding:1rem 0}}.image{{position:relative;max-width:640px}}img{{width:100%;display:block}}.image svg{{position:absolute;inset:0;width:100%;height:100%}}.image rect{{fill:none;stroke:#ffcf00;stroke-width:.5;stroke-dasharray:2 1}}.overview svg{{display:block;width:100%;height:auto;max-height:16rem;background:#f6f9fa;border:1px solid #b8cad4}}pre{{white-space:pre-wrap;overflow-wrap:anywhere}}</style>
<main><h1>SEN-CHA 点滅確認候補レポート</h1><p>{esc(report['filename'])}</p><p><strong>{summary}</strong></p>
<p>WCAG適合判定ではありません。静止画は再生されません。</p>
<p>検出感度：{esc(SENSITIVITY_LABELS.get(report['settings']['sensitivity'], report['settings']['sensitivity']))}</p>
<section class="overview"><h2>動画全体の変化</h2><p>各時点で最も大きかったフレーム間変化です。色の帯は要確認候補の区間です。グラフの高さは危険度やWCAGの閾値ではありません。</p>
<p>明暗の変化：青緑 ／ 赤色指標の変化：茶色 ／ 要確認候補：淡い黄色</p>{overview_svg(report)}
<p>開始 0秒 — 終了 {report['metadata']['duration']:.2f}秒。候補の正確な時刻は下の一覧に記載しています。</p></section>
{''.join(sections)}<h2>検査条件と測定結果</h2><pre>{esc(json.dumps(metadata, ensure_ascii=False, indent=2))}</pre>
<h2>制約</h2><ul>{''.join('<li>'+esc(item)+'</li>' for item in report['limitations'])}</ul></main></html>'''


def serialize(report, format):
    if format == "json":
        return json.dumps(report, ensure_ascii=False, indent=2)
    if format == "csv":
        return export_csv(report)
    if format == "html":
        return export_html(report)
    raise ValueError("出力形式が不正です")


def save_reports(report, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stem = "sen-cha-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    paths = []
    for format in ("html", "json", "csv"):
        path = directory / f"{stem}.{format}"
        with path.open("x", encoding="utf-8", newline="") as file:
            file.write(serialize(report, format))
        paths.append(path)
    return paths
