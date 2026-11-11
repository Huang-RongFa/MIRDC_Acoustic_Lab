# V1.5 三支實體手機驗收

此文件是實機測試步驟，不是已通過的實機紀錄。自動化使用 Chrome 測試音源；API 測試使用的位元組 fixture 只驗證傳輸，不是正式錄音。

## HTTPS 啟動

使用現有專案 Python 環境、Node 依賴與 PostgreSQL。不要在正式資料庫重跑 V1.2 全量建表。

1. 建立獨立開發資料庫。若需驗證 V1.2 相容性，僅在空白隔離庫套用 `CNC_Acoustic_Lab_DB_v1_2/01_schema_complete.sql`。
2. 停止此資料庫的錄音服務，依序套用 **尚未套用** 的 migration（003 僅執行一次）。既有 001 不需重做，public 舊資料表保留。

```powershell
$db = '<你的 PostgreSQL 開發連線字串>'
psql -X -v ON_ERROR_STOP=1 -d $db -f backend/migrations/001_mobile_capture.sql
psql -X -v ON_ERROR_STOP=1 -d $db -f backend/migrations/002_room_lifecycle.sql
psql -X -v ON_ERROR_STOP=1 -d $db -f backend/migrations/003_recording_metadata.sql
psql -X -v ON_ERROR_STOP=1 -d $db -f backend/migrations/004_analysis_jobs.sql
npm.cmd --prefix frontend run build
./scripts/run-backend.ps1 -DatabaseUrl $db -Port 8015
```

3. 在有 Caddy 的主機，把自己的 DNS 名稱指向該主機，允許 TCP 80／443 入站。PostgreSQL 與 8015 不對公網開放。另開終端，從專案根目錄執行：

```powershell
$env:CNC_SITE_ADDRESS = '你的實際網域名稱'
caddy validate --config deploy/Caddyfile --adapter caddyfile
caddy run --config deploy/Caddyfile --adapter caddyfile
```

4. 三支手機開啟 `https://你的實際網域名稱`。應看到「伺服器已連線」；瀏覽器的麥克風權限與 `wss://同一網域/api/rooms/CODE/ws` 都必須正常。不能用 GitHub Pages 當完整後端，也不能在手機輸入電腦的 localhost。

若沒有公網 DNS，可在同 Wi-Fi 使用 Caddy internal CA：另存本機設定，站點使用 `https://電腦的LAN-IP`，在站點區塊加入 `tls internal`，其餘路由同上。三支手機必須安裝並信任 Caddy 的 **root.crt 公開憑證**（絕不分享私鑰），iOS 另需啟用完整信任；不可略過瀏覽器憑證警告當成驗收。需檢查防火牆與 Wi-Fi client isolation。這個方式只能在可連到電腦的網路使用。

本交付提供部署設定；未替使用者註冊網域、安裝 Caddy、設定路由器或公開現有本機資料庫。沒有可宣稱已驗證的公開 HTTPS 網址。

官方依據：[Caddy 自動 HTTPS](https://caddyserver.com/docs/automatic-https)、[WebSocket 反向代理](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)。

## 正常路徑

1. 三台手機記錄型號、OS、瀏覽器版本、網路；關閉自動鎖定，保持前景。
2. A 建立錄音房間，確認六位 code 不包含 O/0/I/1；記錄 Room ID／Session ID，複製 code 或分享邀請。憑證保存在原瀏覽器，不放進邀請網址。
3. B/C 輸入相同 code，自動分配位置；第四個瀏覽器加入應顯示房間已滿。
4. A 填妥 CNC 與加工參數。各手機授權麥克風，輕拍各自附近或說出 A/B/C；本機及主控對應波形應有變化。不得使用測試音源旗標。
5. 只有 A/B 就緒時，A 不可開始；C 就緒後顯示 3/3，A 開始，等待裝置確認及倒數。
6. 各手機輪流說話並共同聽一次拍手聲，持續 60 秒以上。記錄現場操作時間。另做 30 分鐘長錄音測試（仍需考慮手機儲存空間，不是系統自動停止）。
7. B/C 不可停止整個 Session；由 A 手動停止。等待三份各自封存。
8. 點「錄音測試結果」。核對 Room Code、Session ID、機台、參數、起訖、三個 Recording ID、MIME、大小、取樣率、時長、完整性。
9. 逐檔「載入試聽與波形」，確認能聽見對應手機聲音，下載原始檔在另一播放器重播。不同瀏覽器可產生 WebM／MP4／Ogg，沒有宣稱 WAV；不支援某格式時需在相容播放器驗證。
10. 核對三份錄製時長差異；這不是樣本級同步誤差。以 SQL 核對 UUID、分段數與 SHA256。完成後 A 關閉房間，新的手機不可加入。

## 故障與復原

每一情境使用新房間，保留測試紀錄，不把中斷檔標為成功。

- 拒絕麥克風：顯示原因，不可就緒；允許後重新測試。
- 加入後重新整理：原瀏覽器恢復同一位置，人數不增加，須重新授權／就緒。
- 錄音中 B 切斷網路 10 秒：A 顯示斷線（最遲心跳逾時後）；B 暫存持續。A 停止後讓 B 恢復連線，B 應收到停止狀態並補傳，可能較長，需檢查時長差異。
- 阻擋一個 chunk HTTP 請求：顯示待補傳，解除後重試，不可增加重複索引。缺段尚未補齊時不能宣稱上傳完整。
- B 錄音中刷新：已保存的資料可補傳，但中斷狀態保留，不能三路全部成功。
- A 關閉頁面：其他手機應看到主控斷線，不能冒充完整；其他手機不因斷線自動停止。回原瀏覽器恢復 A，明確停止後檢查中斷狀態。
- A 或 B 鎖定、切換 App、來電：觀察背景／麥克風中斷提示；恢復後檢查對應中斷錄音，不得只看三份檔案存在。手機可能暫停事件與收音，不能保證背景錄音。
- 伺服器重啟：進行中的 Session 標中斷；重連後補傳已保存資料。
- 房間超過建立後 24 小時：不可新加入／開始。已開始的錄音不因 admission expiry 自動停止。

`MediaRecorder` 的 timeslice 不是精準計時器；手機鎖定可能延後分段事件。參考 [MDN dataavailable](https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/dataavailable_event)。

## SQL 查詢

```sql
SET search_path TO mobile_capture;
SELECT r.code,r.id AS room_id,s.id AS session_id,s.status,s.conditions,
       p.source_label,pr.participant_recording_id,pr.status,pr.mime_type,
       pr.sample_rate,pr.channel_count,pr.actual_started_at,pr.stopped_at,
       pr.server_started_at,pr.server_stopped_at,pr.duration_ms,pr.expected_chunks,
       a.chunk_count,a.byte_count,a.checksum
FROM recording_rooms r JOIN recording_sessions s ON s.room_id=r.id
JOIN participant_recordings pr ON pr.session_id=s.id
JOIN room_participants p ON p.id=pr.participant_id
LEFT JOIN audio_assets a ON a.session_id=pr.session_id AND a.participant_id=pr.participant_id
WHERE r.code='替換CODE' ORDER BY p.source_label;

SELECT session_id,participant_recording_id,source_label,chunk_index,
       mime_type,byte_size,checksum,received_at
FROM audio_chunks WHERE session_id='替換為SESSION-UUID'
ORDER BY source_label,chunk_index;

SELECT participant_recording_id,chunk_index,count(*) FROM audio_chunks
GROUP BY participant_recording_id,chunk_index HAVING count(*)>1;
-- 最後一個查詢應無資料；此限制也由主鍵保證。
```

保留每次實機驗收的日期、三台裝置、HTTPS 網址、Session ID、結果、播放結果、異常情境。不要把 token 或原始錄音提交到 Git。
