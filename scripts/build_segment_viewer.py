"""Build the static segment viewer published at <pages>/msm/ (the 錄音分析 tab on GitHub Pages).

Input is an exported viewer bundle plus the viewer server that holds the language engine:
    python -X utf8 scripts/build_segment_viewer.py --bundle <viewer_bundle> --viewer-scripts <ai-builder-cup-2026/proto/scripts> --out msm
Data rules: all session payloads are copied unchanged, and audio is copied for CTWA only.
Every source patch must match exactly once, so an upstream change stops the build instead of silently shipping a broken page.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; connect-src 'self'; media-src 'self'; img-src 'self' data:; object-src 'none'; "
       "base-uri 'none'; form-action 'none'")
NO_AUDIO_ZH = "此場次未附音檔，可檢視波形、頻帶與事件表；"
NO_AUDIO_EN = ("Clip ratio = share of full-scale samples (s0). Audio is not included for this session; the waveform, bands "
               "and event table remain available. The waveform is computed from the raw WAV.")
STYLE = """<style>.msm-bar{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;justify-content:space-between;padding:10px 16px 0;font:13px/1.5 system-ui,sans-serif;color:var(--muted)}
.msm-bar a{color:var(--accent)}.msm-lang{display:inline-flex;flex-shrink:0;border:1px solid var(--line);border-radius:6px;overflow:hidden}
.msm-lang button{font:inherit;min-height:32px;color:var(--ink);background:transparent;border:0;padding:4px 12px;cursor:pointer}.msm-lang button.on{background:var(--accent);color:var(--surface);font-weight:600}
html[lang=en] [data-i18n-zh-only]{display:none}html:not([lang=en]) .msm-en-only{display:none}</style>"""
BAR = """<div class="msm-bar"><span><span data-i18n-zh-only>資料來源：<a href="https://doi.org/10.1038/s41597-026-07255-7" target="_blank" rel="noopener noreferrer">MSM（Purdue，CC BY 4.0）</a>、<a href="https://www.kaggle.com/datasets/nachiketsoni/cutting-tool-wear-audio-dataset" target="_blank" rel="noopener noreferrer">CTWA（N. Soni et al.，Apache 2.0）</a>。公開版只附 CTWA 音檔。</span><span class="msm-en-only">Data: <a href="https://doi.org/10.1038/s41597-026-07255-7" target="_blank" rel="noopener noreferrer">MSM (Purdue, CC BY 4.0)</a> and <a href="https://www.kaggle.com/datasets/nachiketsoni/cutting-tool-wear-audio-dataset" target="_blank" rel="noopener noreferrer">CTWA (N. Soni et al., Apache 2.0)</a>. This public version includes CTWA audio only.</span></span><span class="msm-lang" role="group" aria-label="Language / 語言" data-i18n-skip><button type="button" data-lang="zh" lang="zh-Hant" aria-pressed="false">中文</button><button type="button" data-lang="en" lang="en" aria-pressed="false">EN</button></span></div>"""
PATCHES = [
    ('fetch("api/session?machine=" + encodeURIComponent(m) + "&ds=" + ds)', 'fetch("data/payload/" + encodeURIComponent(m) + "-" + ds + ".json")'),
    ('fetch("api/sessions")', 'fetch("data/sessions.json")'),
    ('"imi_vm20i", ds = h ? +h[2] : 6', '"ctwa_mill", ds = h ? +h[2] : 308'),
    ('chan = c; pending = { t: t, play: play }; audio.src = safeMediaUrl(CH[c].url);',
     'chan = c; pending = { t: t, play: play }; if (hasAudio()) { audio.hidden = false; $("play").disabled = false; audio.src = safeMediaUrl(CH[c].url); } '
     'else { pending = null; audio.pause(); audio.removeAttribute("src"); audio.load(); audio.hidden = true; $("play").disabled = true; audio.currentTime = t || 0; }'),
    ('function setChan(c, t, play) {', 'function hasAudio() { return !!I && I.machine_key === "ctwa_mill"; }\n  function setChan(c, t, play) {'),
    ('if (audio.readyState < 1) { pending = { t: t, play: !!play }; return; }', 'if (audio.readyState < 1 && hasAudio()) { pending = { t: t, play: !!play }; return; }'),
    ('audio.currentTime = t; if (play) audio.play()', 'audio.currentTime = t; if (play && hasAudio()) audio.play()'),
    ('(lossy ? "MP3 約 160 kbps 只供試聽；"', '(!hasAudio() ? "' + NO_AUDIO_ZH + '" : lossy ? "MP3 約 160 kbps 只供試聽；"'),
    ('fillTable(); zoom(60);', 'fillTable(); zoom(60); if (!hasAudio()) { lastCur = undefined; tick(); }'),
    ('。請確認模組仍在執行。"', '。請重新整理頁面。"'),
    ('/^載入失敗：([\\s\\S]*)。請確認模組仍在執行。$/, "Load failed: $1. Check that the module is still running."',
     '/^載入失敗：([\\s\\S]*)。請重新整理頁面。$/, "Load failed: $1. Reload the page."'),
]


def patch(html, old, new):
    if html.count(old) != 1:
        sys.exit(f"source patch matched {html.count(old)} times, expected 1: {old[:70]}")
    return html.replace(old, new)


def build_html(bundle, scripts):
    sys.path.insert(0, str(scripts))
    from viewer_bundle_server import I18N_JS
    html = (bundle / "index.html").read_text(encoding="utf-8")
    for old, new in PATCHES:
        html = patch(html, old, new)
    extra = "<script>Object.assign(window.MSM_I18N_EXTRA.exact," + repr({
        "削波比例＝滿刻度樣本占比（s0）。" + NO_AUDIO_ZH + "波形由原始 WAV 計算。": NO_AUDIO_EN}) + ");</script>"
    html = patch(html, '<meta charset="utf-8">',
                 f'<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="{CSP}">'
                 '<script>document.documentElement.dataset.theme="light";</script>')
    return patch(html, '<div class="wrap">', STYLE + extra + BAR + I18N_JS + '<div class="wrap">')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True, type=Path)
    ap.add_argument("--viewer-scripts", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()
    (a.out / "data" / "payload").mkdir(parents=True, exist_ok=True)
    (a.out / "index.html").write_text(build_html(a.bundle, a.viewer_scripts), encoding="utf-8")
    (a.out / ".gitignore").write_text("# CTWA preview audio is published on purpose; the repository ignores *.mp3 elsewhere.\n!*.mp3\n", encoding="utf-8")
    shutil.copy2(a.bundle / "sessions.json", a.out / "data" / "sessions.json")
    payloads = sorted((a.bundle / "payload").glob("*.json"))
    for p in payloads:
        shutil.copy2(p, a.out / "data" / "payload" / p.name)
    clips = sorted((a.bundle / "audio").glob("ctwamill_*/*.mp3"))
    for p in clips:
        target = a.out / "audio" / p.parent.name / p.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
    size = sum(f.stat().st_size for f in a.out.rglob("*") if f.is_file())
    print(f"payloads={len(payloads)} audio={len(clips)} total_mb={size / 1e6:.1f}")


if __name__ == "__main__":
    main()
