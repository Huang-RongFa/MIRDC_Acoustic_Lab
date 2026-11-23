# V2.2 地端部署與操作

## 部署

1. 在隔離資料庫還原既有資料備份並演練升級。新庫先執行 V1.2 的 `01_schema_complete.sql`，再依序執行 `backend/migrations/001` 至 `004`。已套用 001～003 的資料庫只執行 004 一次。使用 `psql -X -v ON_ERROR_STOP=1 -d <資料庫> -f <檔名>`。004 保留舊房間、錄音、音訊分段和資產，舊批次可保留未知機台。
2. 將已核實的設備登錄在 `public.machines`。主控可從設定管理的「機台」輸入編號及名稱。只有啟用的機台會出現在錄音選單。
3. 設定後端的 `DATABASE_URL`，以逗號分隔 CIDR 設定 `ACOUSTIC_ALLOWED_NETWORKS`。包含主控、手機的指定子網及需要管理的回環位址。執行 `./scripts/run-backend.ps1 -Port 8015`，維持一個 worker。只信任本機 Caddy 傳來的代理標頭，不對外開放 8015 與 PostgreSQL。
4. 執行 `npm --prefix frontend run build`。在專案根目錄執行 `caddy run --config deploy/Caddyfile`。設定 `CNC_SITE_ADDRESS` 為內部 DNS 主機名稱，`ACOUSTIC_PROXY_NETWORKS` 為空格分隔的允許 CIDR。內部 DNS 指向此伺服器。防火牆僅允許指定網段存取 TCP 443。兩層允許清單使用相同的實驗室子網。
5. Caddy 使用內部 CA。由管理員透過可信任管道將根憑證部署到各裝置。iPhone 安裝設定描述檔後，在憑證信任設定開啟完整信任。Android 依裝置管理政策安裝 CA。以同一 HTTPS 網址開啟主控與手機，確認瀏覽器沒有憑證警告。GitHub Pages 提供靜態介面，錄音應使用地端網址。

## 操作與實機驗收表

|步驟|現場應記錄的結果|
|---|---|
|Android Chrome 與 iPhone Safari 開啟內網 HTTPS|記錄裝置、OS、瀏覽器版本、網址、網段與是否信任憑證。|
|主控依序設定 1、2、3、4、5 位|主控預設只管理。勾選「此裝置也參與錄音」才占一個位置。記下各端實際分配與超額加入結果。|
|選擇已登錄的 CNC 及一般設備|分別測試其他條件全空、部分填寫、未選擇及無效機台。開始後比較機台與位置快照。|
|各手機點擊測試並授權麥克風|在同一個內網 HTTPS Origin 確認安全環境、瀏覽器權限及真實波形。拒絕一次，再從網站權限恢復並按重新連接。|
|每支手機依序在不同時間輕敲麥克風附近|主控應在對應位置看到訊號。所有裝置按就緒才可開始。不同手機各用自己的採樣時鐘。|
|在同一房間停止、封存、準備下一次，連續三次|下載每一批的每路原始音檔並試聽。核對批次 ID、位置、採樣率、時長與 SHA-256。|
|錄音時斷網，再停止、恢復網路|保留原瀏覽器頁面與網站資料，讓 IndexedDB 補傳。檢查原始分段及封存狀態。鎖屏、背景及重新整理另行測試。|
|退出、移除、交換與關房|核對主控及全部手機畫面、權杖失效和麥克風指示燈。錄音中關房且某裝置有未封存音訊時，房間應停留在關閉中，待原裝置補傳。|
|從允許與不允許的網段各連線一次|分別記錄防火牆、Caddy、HTTP API、WSS 的結果。|

## API 與即時事件

除建立房間及持房間碼初次加入外，HTTP 使用房間 Bearer 權杖。WSS 連上後首則訊息送 `{"type":"auth","token":"…"}`。房間碼是加入憑據，控制與人員管理另驗證主控身分。以下房間操作都以 `/api/rooms/{code}` 為前綴。

|方法與路徑|請求或回應|
|---|---|
|GET /api/machines|回傳已啟用的通用機台清單。|
|POST /api/rooms|name、required_recorder_count（1～5）、record_as_host（預設 false）。|
|POST /join、POST /leave|以 name 加入空位；退出者撤銷房間權限。需補傳時回傳 pending_upload。|
|GET 房間、GET /state|目前批次、位置、人員、心跳連線、準備及資產狀態。可傳 take_id 查指定批次。|
|PATCH /config|主控在等待時變更 required_recorder_count。|
|PATCH 或 DELETE /participants/{id}|主控使用 name 更名、swap_with 交換位置，或移除人員。|
|PUT /conditions|machine_id 必須為啟用的主檔 UUID，加工數值選填。|
|POST /ready、/start、/stop、/close|各錄音者就緒；其餘由主控執行。|
|POST /next、GET /takes|產生下一個等待批次、列出本房間批次。|
|PUT /recordings/{id}/chunks/{index}|指定 take_id 查詢參數、Content-Type、X-Checksum（SHA-256）、X-Created-At。相同索引與內容可重試。|
|GET /recordings/{id}/chunks、POST /recordings/{id}/finish、GET /recordings/{id}/audio|均指定 take_id。finish 傳 chunk_count、client_ms、duration_ms 及 interrupted，只有分段齊全才封存。|

`/ws/rooms/{code}` 以及相容路徑 `/api/rooms/{code}/ws` 接收 ping、mic、ready、prepared、started、preview、error。伺服器發送 pong、完整 state、prepare、start、stop、stop_personal、cancel、room_closed。state 帶有 event_version 與 assignment_version。手機只發送實際收音預覽，原始錄音分段另以 HTTP 上傳。控制指令與預覽無法提供樣本級同步。
