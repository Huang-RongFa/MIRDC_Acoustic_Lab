# 既有 V1.4 驗證紀錄

這是先前工作階段留下的紀錄；本次 V1.5 親自執行的證據請見 [verification-v15.md](verification-v15.md)。

日期：2026-11-09（Asia/Taipei）。下列是本次實際執行結果，不把靜態審查或瀏覽器測試音源當作三實體手機驗收。

## 已觀察結果

| 檢查 | 結果 |
|---|---|
| 在隔離 `cnc_lab_test` 套用 V1.2 全量 SQL，再套用 mobile migration | PostgreSQL 18 兩次交易均 COMMIT，V1.2 28 表仍存在 |
| `./scripts/test-backend.ps1 -TestDatabaseUrl <隔離測試庫>` | 5 passed；一項 Starlette/httpx 棄用提醒 |
| `npm.cmd --prefix frontend run build` | TypeScript 無錯誤；Vite production build 成功 |
| `npm.cmd test`（frontend） | 4 passed，包含三個隔離瀏覽器的真實 MediaRecorder／Web Audio／IndexedDB 流程 |
| `node scripts/verify-pages.mjs`（frontend） | 公開 GitHub Pages HTTP 200，標題正常，JavaScript errors=[] |
| GitHub Pages build | commit `81f0396cd32567095186f1c11ef8d91ae2887035`，status built，error null |
| `.venv/Scripts/graphify.exe update .` | 成功產生 graph.json、graph.html、GRAPH_REPORT.md；完整涵蓋程度見下方限制 |

## 測試涵蓋

- 主控分配 A、B/C 唯一聲源，同一位置重複加入被拒絕。
- 無憑證不得讀取、一般錄音者不得停止整個 Session。
- 一人未就緒時禁止開始；三個 WebSocket prepared 後才開始。
- 主控開始／停止，開始後加工條件不可修改，計時持續至主控停止。
- 波形預覽由 B 的訊息送到 A，標記由伺服器憑證決定。
- 三聲源分別上傳，SHA256 校驗、相同內容冪等、衝突拒絕、缺段補傳。
- 後送 start ACK 可在 finalizing 補回；已封存 finish 不可改寫為中斷。
- 三個 MediaRecorder 產生的 WebM 音檔按序重建，瀏覽器實際 decodeAudioData 成功且長度 >4 秒。
- 離線暫存與回線補傳；完成後刷新恢復同一 Session／歷史下載。
- 麥克風拒絕時仍未就緒；錄音中刷新標示 interrupted，不能假報全部完成。
- PostgreSQL 複合 FK 拒絕跨房間錄音；A/B/C 唯一限制由 DB 強制。
- 0.5mm 刀具 API 可接受，超上限與負 RPM 拒絕。
- 設定 upsert、無分析結果時回空陣列。
- Pages 五頁導覽、375px 無水平溢出、不發送後端 API 請求、不使用「介面預覽」標籤。

## TDD 與審查

房間、同步控制、分段補傳、設定讀取、延遲 ACK 與封存重放均先觀察失敗，再實作修正。部分瀏覽器端是既有功能的整合驗證，未把它們宣稱為逐功能 test-first。

依 code-review skill 分別執行 Standards／Spec 靜態審查。已修正：數值上下限不一致、完成宣告重放、舊準備 timeout 干擾新嘗試、HTTP 上傳阻塞 WS 控制、遺失 start ACK 無法補傳、逾時連線不重連、interrupted session 無法離開。也修正正常停止時把仍在落盤的最後分段誤判成刷新中斷。

## 未驗證／未完成

真實手機／Safari／長錄音／儲存耗盡／實際 CNC 現場、正式 HTTPS 後端與 SQL 部署、音檔伺服器解碼、樣本級對齊、FFT／RMS／濾波／融合／模型工作程序、跨房間帳號與主檔管理均未完成驗收。這些不列為 PASS。

Graphify AST 更新成功，但 SQL extractor 缺少 `tree_sitter_sql`，部分字型／資料格式也不受支援；因此不能把圖譜視為完整 SQL 關聯證據。SQL 關聯證據來自 PostgreSQL migration 與實際約束測試。未設定 LLM 金鑰、未使用付費語義解析。
