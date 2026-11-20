# 可驗證的多設備同步錄音

保留每台設備獨立收音與原始分段。同步結果是另外下載的 PCM WAV 與 JSON 報告，不覆寫原檔，也不宣稱設備共用取樣時鐘。

## 使用

1. 全員開啟麥克風，保持頁面在前景。主控使用喇叭，不可靜音或戴耳機；所有設備都必須聽得到主控參考音。
2. 主控按「開始統一錄音」，各端於倒數期間預錄。共同零點為伺服器的 `starts_at`，不是收到開始訊息的時間。
3. 主控在倒數中、其後每 10 秒及停止前播放三個掃頻參考音。參考音會污染該小段測量資料；分析時依報告位置排除，不要直接當作 CNC 訊號。
4. 至少錄製 6 秒，建議 15 秒以上以取得分布在中段的驗證點。按停止會先播放尾端參考音，再送停止指令。
5. 全部封存後開啟「錄音結果」→「驗證同步並產生共同時間 WAV」。目前瀏覽器分析支援最多 180 秒、單一壓縮檔 32 MiB、總解碼資料 256 MiB；原始錄音本身不因此限時。
6. 通過時下載各聲源 WAV 與 JSON 報告。未通過或參考音缺失時，保留原檔並依錯誤提示重新錄製，不產生假通過的校正檔。

## 時間與驗證定義

- 後端用開始前後 30 秒內、RTT 小於 2 秒的校時觀測，估測原檔開始的伺服器時間；選最小 RTT 樣本，使用單調時鐘差值。半 RTT 僅是網路估計，不是實際收音誤差上限。
- 參考訊號：版本 `chirp-1`，60 ms、900→4000 Hz 掃頻，Hann 窗；三次位置為 0、230、610 ms。
- 分析第一聲道的正交匹配濾波分數（門檻 0.65），辨識三聲序列。各聲源必須有相同數量、至少六個參考點，首尾跨度至少五秒。
- 以第一位錄音者為參考，第一個和最後一個參考點求時間偏移與線性取樣漂移。其餘參考點不參與擬合，獨立量測最大殘差；門檻 1 ms。漂移超過 2000 ppm、參考點空檔超過 12 秒、缺少頭尾或共同音段覆蓋不足均拒絕。
- 裁切範圍為共同 `starts_at` 到 `stopped_at`，轉換至參考錄音的時間軸後映射至各聲源；全部輸出相同取樣數的 48 kHz / 16-bit PCM WAV，保留全部聲道，用線性插值補償漂移。不補零偽裝完整音訊。
- JSON 包含原檔 SHA-256、參考點時間與分數、偏移、ppm 漂移、獨立點殘差、校時估計、裁切起訖、輸出取樣數及演算法版本；可重新載入原檔再產生結果，報告不寫入資料庫。

## 不能由此證明的精度

「參考點殘差通過」只表示聲學參考音的相對對齊。喇叭到每支麥克風的傳播延遲沒有被扣除；不要用校正檔推論原始聲源的到達時間差。參考點之間的非線性漂移、輸入裝置及編碼器延遲、主控喇叭延遲、絕對倒數起點精度仍未被獨立驗證。網路時鐘估計、WebAudio 排程或上傳完整都不能取代硬體同步證據。

瀏覽器 `MediaRecorder` 的 start 事件不是硬體 ADC 時戳，解碼也會按 AudioContext 取樣率重取樣。參考：[MediaStream Recording](https://www.w3.org/TR/mediastream-recording/)、[Web Audio](https://www.w3.org/TR/webaudio/)。

## 驗證方式

- `npm.cmd --prefix frontend run build`
- 在 Vite 開發伺服器啟動後，設定 `CNC_TEST_URL` 並於 frontend 執行 `playwright test tests/synchronization.spec.ts tests/sync-capture.spec.ts tests/sync-results.spec.ts`。
- 設定已套用現有 migrations 001～004 的隔離 `TEST_DATABASE_URL`，使用專案虛擬環境執行 `pytest backend/tests -q`。
- 實體多手機、Safari、現場噪音、反射及聲學傳播延遲仍需現場驗收。自動化中的已知偏移音訊與 Chrome 模擬音源不等於實體設備精度證明。

### 本次實際驗證（2026-11-12）

- 使用者核准後，對指定測試庫執行現有 004 migration，觀察到 `COMMIT`。沒有新增本功能專用 migration。
- 專案虛擬環境 `pytest backend/tests -q -x --tb=line`：28 passed，1 個既有 Starlette 相依套件棄用警告。包含三組共同 epoch／預錄校時測試。
- 三份新增前端測試檔：9 passed。涵蓋 120 ms 偏移與 300 ppm 漂移、未參與擬合的 8 ms 中段異常、相同 WAV 取樣數、靜音／一般單音拒絕、缺少校時、倒數取消再錄、倒數提早停止、真實 MediaRecorder／Opus 回圈、下載校驗及手機版結果頁。
- 額外 `playwright test tests/sync-live.spec.ts`：1 passed。實際 PostgreSQL／FastAPI 加三個隔離 Chrome context，主控不收音、兩位錄音者連續兩批錄製；確認預錄起點早於共同起點、完整封存、校時欄位及缺少參考音時不產生通過結果。
- `npm.cmd --prefix frontend run build`、`git diff --check` 通過。390px 結果頁無水平溢出，已檢視截圖。
- `graphify update .` 完成 AST 更新；環境仍缺少 SQL extractor，圖譜不構成 SQL 完整性的證據。
