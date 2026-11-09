# V1.5 驗證紀錄

日期：2026-11-09，Asia/Taipei。只列本次親自執行的結果；先前紀錄見 `verification.md`。

## 執行結果

- 隔離 PostgreSQL 18.6：`tmp/pg-v15-run`，僅 `127.0.0.1:55433`。`cnc_lab_api` 用 API／SQL 測試，`cnc_lab_test` 用瀏覽器流程，未更改原有或正式資料庫。
- 新庫依序執行 V1.2 `01_schema_complete.sql`、手機 001/002/003 migrations，均成功；003 trigger 的 schema 解析回歸失敗後，以固定 search_path 修正並驗證。
- `./scripts/test-backend.ps1 -TestDatabaseUrl 'postgresql://cnc_test@127.0.0.1:55433/cnc_lab_api'`：**12 passed**。一項既有 Starlette/httpx 棄用提醒，沒有為此更動依賴。
- `CNC_TEST_URL=http://localhost:5185`、`CNC_PAGES_TEST_URL=http://localhost:4185/MIRDC_Acoustic_Lab/`，`npm.cmd --prefix frontend test`：**6 passed**，48.1 秒。Chrome 測試音源，不是實體手機收音。
- `npm.cmd --prefix frontend run build`、`npm.cmd --prefix frontend run build:pages`：TypeScript／Vite 成功。
- `.venv/Scripts/python.exe -m compileall -q backend`：成功。
- `git diff --check`：工作樹修改沒有 whitespace error；納入既有未追蹤檔後，`git diff --cached --check` 提示原樣保留的 `frontend/src/template.css:24` EOF 空行，未為此改寫使用者模板。
- `.venv/Scripts/graphify.exe update .`：更新 graph.json、graph.html、GRAPH_REPORT.md，AST-only、無 LLM API 費用。最新程式增量更新為 2576 nodes／5108 edges／142 communities；`graphify query RecordingResults` 可查得新結果頁及 App 關係。
- 視覺檢查：實際瀏覽器產生的 `tmp/results-mobile.png`，390px 單欄、三音檔播放器與原始音訊波形；測試亦確認窄螢幕無水平溢出。截圖／錄音／測試資料庫不提交。

## 14 項驗收對照

| # | 驗收 | 本次證據與界線 |
|---|---|---|
| 1 | 唯一 Room Code | 20 房間六位允許字元／唯一性；強制一次碰撞後重試，原房間不變 |
| 2 | 三人同房 | API 自動 A/B/C；三個隔離 Chrome context 同 Session |
| 3 | 第四人拒絕 | join 回 409，不新增位置 |
| 4 | 恢復原位置 | 帶原憑證 join 與 WebSocket 重連，participant ID 不變；頁面刷新恢復 |
| 5 | 未就緒不可開始 | API 409；瀏覽器只有兩人就緒時按鈕禁用 |
| 6 | 3/3 可開始 | 三個 prepared、後端倒數、各自 started、MediaRecorder 分段 |
| 7 | 非主控不可停止 | HTTP 403 |
| 8 | 不自動停止 | ACK 逾時仍維持 recording；主控手動 stop 才停止；瀏覽器持續計時。未做無限時長或 30 分鐘硬體驗收 |
| 9 | 真實音訊資料 | 真正瀏覽器 MediaRecorder 產生容器；輸入是 Chrome 測試音源。三實體手機：待驗收 |
| 10 | 三檔保存／播放 | 三個 API 下載檔均 decodeAudioData 成功、大小 >1000 bytes、時長 >4 秒；結果頁三個 audio readyState、實際 play/currentTime 前進 |
| 11 | SQL 關聯 | 三個獨立 Recording UUID、Session／participant／source 關聯；byte_size 與 trigger；既有 public 28 表及複合 FK 測試 |
| 12 | 重傳去重 | 同 index／SHA／時間／MIME 冪等，衝突 409；缺段補回後封存 |
| 13 | 網路中斷 | WebSocket 斷線 error、ready 清除、原位置重連；瀏覽器 offline／online 後分段補傳與播放 |
| 14 | 關頁／鎖定中斷 | 刷新保留部分音訊且標 interrupted；模擬主控 visibilitychange、真正關閉主控分頁再開啟，均得到 A interrupted、B/C stored；實際 iOS／Android 鎖定待驗收 |

## TDD 證據

本階段先觀察失敗，再修正：六位代碼（1 failed/5 passed）、自動位置／關閉／到期（2 failed/6 passed）、錄音 metadata（1 failed/7 passed）、斷線提示（1 failed/8 passed）、結果頁不存在、主控背景未提示、缺少 ACK／finish 異常回報、直接 SQL trigger 解析錯誤。代碼碰撞是已有實作後的補充回歸測試。沒有把所有既有功能宣稱為本次從零 TDD。

瀏覽器迭代另修正了測試用動態 nth locator（按鈕載入後消失導致索引改變），以及長錯誤訊息在窄螢幕溢出。最終六項全部通過。

## 尚未驗證與限制

- 未建立公開 HTTPS 網址；已提供 `deploy/Caddyfile` 與 `phone-test-v15.md`，仍需要可用網域／主機或本機受信任 CA。本機未安裝 Caddy，因此沒有宣稱執行過 Caddy validate、TLS 發證或 WSS 公網驗收。
- 沒有接觸三支實體手機、Safari、現場 CNC、長時間錄音、儲存耗盡與實體鎖屏。所有硬體成功結論留待實機步驟填寫。
- 每房間一次 Session；完成後建立新房間。憑證依原瀏覽器保存，沒有跨裝置帳號。單 Uvicorn worker。
- 時長是各手機單調時鐘觀測，音檔解碼時長另顯示；沒有做樣本級同步。裝置取樣資訊不等於轉碼後容器的獨立分析結果。
- >32 MiB 的音檔可載入播放器／下載，但略過全檔波形解碼以免耗盡手機記憶體；不支援原始格式的瀏覽器須改用相容播放器。此 MVP 未做伺服器波形縮圖或媒體轉碼。
- Graphify 缺少 `tree_sitter_sql`；105 個檔案格式未分類，不能把圖譜視為完整 SQL 證據。沒有安裝新依賴來掩蓋限制。
- 正式部署前應規劃儲存配額、備份與存取管理；本次沒有加入 FFT、AI 分類或對齊演算法。
