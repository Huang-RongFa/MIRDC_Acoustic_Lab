# HTTP 與 WebSocket 契約

所有 HTTP 端點前綴 `/api`。除建立／加入房間外，使用 `Authorization: Bearer <room participant token>`。建立時回傳一次原始 token；資料庫只保存 SHA256。此 token 是該房間參與者權限，不是跨房間帳號。

## REST

| Method / path | 行為 |
|---|---|
| POST `/rooms` | `{name}`；分配主控 A、Room ID、隨機房間代碼與 Session ID |
| POST `/rooms/{code}/join` | `{name,source_label?:"B"或"C"}`；省略位置自動分配；帶原憑證可恢復身分（200），不重佔名額；錄音開始後不得新加入 |
| POST `/rooms/{code}/close` | 僅主控；錄音及封存期間不可關閉；關閉後保留下載／補傳權限 |
| GET `/rooms/{code}` | 權威 Session、加工條件、三人狀態、個別錄音、server_now |
| PUT `/rooms/{code}/conditions` | 僅主控且 waiting；完整加工快照，額外欄位拒絕 |
| POST `/rooms/{code}/start` | 僅主控；3/3 連線、麥克風、ready、完整加工條件才通過 |
| POST `/rooms/{code}/stop` | 僅主控；發送 stop，進入 finalizing；不設定目標時長 |
| PUT `/rooms/{code}/recordings/{participant_id}/chunks/{index}` | 二進位 body；只能上傳自身聲源 |
| GET `…/chunks` | 已接收 index/checksum 與預期總數，供補傳查詢 |
| POST `…/finish` | `{chunk_count,client_ms,duration_ms?,interrupted}`；主控停止後宣告；缺段 409 |
| GET `…/audio` | 串流輸出按 index 拼接的原始容器；同房間參與者可下載 |
| GET/PUT `/rooms/{code}/catalog` | 房間範圍範本；PUT 僅主控，`{kind,name,values}` |
| GET `/rooms/{code}/analysis` | `{results:[]}` 或真實已保存結果，不回傳模擬資料 |

Chunk headers：`Content-Type` 必須符合 prepared 的 MIME；`X-Checksum` 是音訊 bytes 的 SHA256 小寫 hex；`X-Created-At` 是 client epoch 毫秒。最大 8 MiB／段。session_id 由房間解析，source_label 由具憑證的 participant 解析，不信任呼叫者自行指定的聲源。

唯一鍵 `(session_id,participant_id,chunk_index)`。相同 bytes/checksum/時間/MIME 的重試冪等；內容衝突回 409。完整性要求數量等於宣告、第一段為 0、最後一段為 count−1。每段驗證 SHA256，完整音檔另計總 SHA256 與 byte count。音檔保持 WebM/Opus、MP4 或 Ogg 原格式，沒有宣稱是 PCM WAV。

常見狀態：401 缺憑證；403 非本人／非主控；404 不存在；409 狀態／衝突／不完整；410 房間關閉／到期；413 分段過大；422 欄位／checksum／MIME 不符。完整欄位與型別以 `/docs` 或 `/openapi.json` 為準。

## WebSocket

連線 `/api/rooms/{code}/ws`，第一個訊息 `{type:"auth",token}`，避免把 token 放在 URL 日誌。相同參與者只能一個活動連線；4409 表示已有分頁佔用。4008 是可重連逾時；4400 是認證或訊息無效。

| Client → server | 內容 |
|---|---|
| `mic` | `{mic:true}`，麥克風授權成功；尚未 ready |
| `ready` | `{mic:true}`，使用者確認收音準備 |
| `prepared` | `{mime_type,sample_rate?,channel_count?,processing?}`，MediaRecorder 已建立且可用。`processing`＝`{echo_cancellation,noise_suppression,auto_gain_control,latency}`，取自 `getSettings()`，值為 true／false／null（未回報）；目前後端忽略此欄位，尚未入庫 |
| `started` | `{client_ms,performance_ms}`，MediaRecorder start 事件後回報；停止後允許補送遺失確認 |
| `preview` | `{samples:[-1…1]}`，最多 256 點、伺服器最多約 5 Hz；不存為正式音訊 |
| `ping` | `{client_ms}`，約每 5 秒 |
| `clock` | `{client_sent_ms,server_received_ms,client_received_ms,performance_ms}`；必須對應伺服器剛發送的 pong，單次使用 |
| `error` | `{message}`，授權拒絕、裝置失效、刷新中斷等 |

| Server → client | 行為 |
|---|---|
| `state` | `{state}` 全量快照；重連也取得相同持久化 Session |
| `prepare` | 三個裝置先建立 MediaRecorder；10 秒內未齊備就取消本次準備 |
| `start` | 三個 prepared 之後，後端倒數 3 秒再發出；保存後端 started_at |
| `stop` | 主控停止；裝置停止擷取，最後分段寫入後再 finish |
| `cancel` | `{reason}`，準備逾時或倒數期間有人離線 |
| `preview` | `{source_label,samples,server_ms}`，聲源由伺服器憑證決定 |
| `pong` | `{client_ms,server_ms}`，供時鐘偏移與 RTT 估計 |

倒數／計時都由快照中的 starts_at、started_at、stopped_at 與伺服器時鐘推算；不靠本機累加秒數。每個裝置的 client 時鐘仍是裝置觀測值，不能作樣本同步證明。

## 狀態與恢復

`waiting → preparing → countdown → recording → finalizing → completed`。

只有三個音檔都完整且未中斷才能 completed。三份可用音檔已封存但有中斷時，Session 為 interrupted。缺段／未回報先保持 finalizing，30 秒未完成則 Session 為 interrupted，對應未封存聲源標 failed；仍可補傳。若三份後續均完整且無錄音中斷，可恢復 completed。開始後 10 秒未收到 started 回報則對應聲源標 failed，但不自動停止整體錄音。

音訊分段與 manifest 在 IndexedDB 同一交易寫入，再上傳。控制訊息處理不等待 HTTP 補傳。網路失敗保留分段、每三秒重試；HTTP 呼叫 15 秒逾時。WebSocket 以 1.5 秒間隔重連。

刷新可恢復房間、憑證、已寫入分段和錄音起點，無法恢復瀏覽器已中止的 MediaRecorder。此情況標示 interrupted，保留可用音訊，不能假裝無縫續錄。憑證保存於目前瀏覽器；尚未提供跨裝置帳號恢復。

房間建立後 24 小時停止接受新加入／開始；不停止已開始的錄音。GET／WebSocket 憑證恢復與補傳仍保留。裝置清除網站資料後無法靠名稱或 Room Code 恢復原權限。

GET 快照的 recordings 包含 participant_recording_id、sample_rate、channel_count、duration_ms、server_started_at、server_stopped_at、byte_size、asset_checksum、received_chunks、missing_chunks。未宣告總數時 missing_chunks 為 null，不代表完整。
