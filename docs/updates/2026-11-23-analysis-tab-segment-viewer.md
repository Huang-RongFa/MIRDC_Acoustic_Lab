# GitHub Pages「錄音分析」改為切段驗證頁（2026-11-23）

## 變更
- Pages 模式的「錄音分析」以 iframe 顯示 `msm/index.html`；一鍵示範與代理人主控台不併入。
- 連後端的完整系統不變，仍顯示真實錄音的 Spectrogram／MFCC 與分析工作狀態。
- `scripts/build_segment_viewer.py` 由比賽 repo 的 viewer bundle 產生靜態頁：API 改讀靜態 JSON，每個原始碼修補都必須剛好命中一次，否則中止建置。

## 公開資料
- 471 場 payload（波形、頻帶、事件、工況）；VF-10 的 10 個封存場次維持不含事件。
- 音檔只有 CTWA 402 段 MP3；MSM 69 場停用播放並顯示說明。總量 138.1 MB，最大單檔 2.03 MB。
- 來源：MSM（Purdue，CC BY 4.0，DOI 10.1038/s41597-026-07255-7）、CTWA（N. Soni et al.，Apache 2.0）。

## 重建
```powershell
python -X utf8 scripts/build_segment_viewer.py --bundle <viewer_bundle> --viewer-scripts <ai-builder-cup-2026/proto/scripts> --out msm
npm.cmd --prefix frontend run build:pages
```
發布時把 `pages-site/index.html` 與它引用的 `assets/` 檔案複製到 repo 根目錄。

## 驗證
- `frontend/tests/pages-segment-viewer.spec.ts` 先紅後綠；`tests/pages.spec.ts` 通過；unit tests 12/12；`npm run build` 通過。
- 切段驗證內容區的 zh 可見文字（CTWA #308，44,759 字）與比賽版 SHA-256 相同。
- 未執行 `graphify update .`：本機 PATH 沒有 graphify。
