# V2.2 驗證紀錄

本機分支為 `feature/room-code-recording`。以 Git 查得遠端 main 為 `81f0396cd32567095186f1c11ef8d91ae2887035`，其根目錄包含靜態網頁與 V1.2 SQL，缺少本機功能分支的 frontend、backend 和 deploy。改動位於功能分支的原始碼。

## 自動化

- 在獨立 PostgreSQL 叢集建立全新資料庫，順序執行 V1.2 建庫 SQL 及 migrations 001～004，psql 啟用 ON_ERROR_STOP，全部成功。
- 透過專案虛擬環境執行 `python -m pytest backend/tests -q -x --tb=short`，20 passed。唯一警告為 Starlette 的 TestClient 相依套件棄用提醒。
- `npm --prefix frontend run build` 通過 TypeScript 檢查及 Vite 正式建置。
- Playwright 的 recording 與 recovery 測試以桌面 Chrome 和測試麥克風運行，原有五項通過。另行執行同瀏覽器三批次錄音測試，一項通過。首輪曾有一項在開始按鈕等待逾時，重跑完整五項通過。
- 未在實體手機執行任何上述測試。PostgreSQL 的五路測試使用可辨識的測試位元組，三路 Chrome 測試使用真正的 MediaRecorder 和解碼播放。

|驗收|本次觀察|
|---|---|
|T01～T05、T18、T28|測試拒絕未選與不存在機台、一般設備只選機台、CNC 部分參數、開始後拒絕變更及主檔改名後快照保存。|
|T06～T13|五組參數化測試確認 A 至 E、自動分配上限、退出後可替補、交換 API 成功；各端交換後的畫面仍待實機比對。|
|T14、T15|資料表保存每個批次的參與者與位置；自行退出的舊憑證經驗證失效。主控移除錄音中人員及待補傳的完整時序尚待專項驗證。|
|T16、T17、T24、T25|五路連線在錄音中重複關房，先停止、補傳、各自封存，再收到 room_closed。已關閉房間拒絕加入、舊權杖拒絕查詢、非主控拒絕管理。離線實機重新整理仍待驗證。|
|T19|同一 Chrome 頁面連續錄製三次，下載並成功解碼三個獨立 take_id 的音檔。|
|T20～T22|Chrome 驗證拒絕授權、斷線補傳、重新整理與背景造成中斷的標記。未拔除實體麥克風測試音軌失效。|
|T23、T26、T27|重複開始及關房、後端拒絕外網測試位址、五路獨立 SHA-256 封存通過。防火牆、Caddy 與五支實體手機仍待驗證。|

實機驗收欄位、步驟與地端部署方式見 `docs/v22-local.md`。未在已部署的研究資料庫執行 migration，也未將服務部署到實驗室內網。
