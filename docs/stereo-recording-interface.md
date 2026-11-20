# 核心多裝置錄音與 Stereo 介面修改

此版本取代前次「選用擴充」介面。修改於目前工作目錄的 React／FastAPI 原始碼，
Git origin 為 Huang-RongFa/MIRDC_Acoustic_Lab；未只改打包 assets，也未提交、推送或部署。

## 行為

- `workspace-nav` 只在 WebSocket 已認證、state 內有目前連線成員且未退出／關房時顯示。
  尚未加入、退出、關閉連線或超過 6 秒未收到伺服器訊息時隱藏；重新取得有效 state 後恢復。
- 多裝置 PCM 為核心路徑。沒有 details 或 multiDeviceSyncEnabled UI 開關。
  舊 localStorage 的 false 不再停用核心 PCM；新設定預設 48000 Hz、Mono。
- 每位錄音者在自己的連線狀態卡設定 44100／48000 Hz 及 Mono／Stereo；他人卡片顯示實際狀態。
  修改即重新準備麥克風，不需重載。準備、倒數、錄音、封存期間不能改設定，服務函式也會檢查。
- 顯示輸入裝置實際率與 AudioContext 的 PCM 實際率。硬體回退／未知會明示，不宣稱要求率等於硬體率。
  壓縮容器（例如 Opus）的編碼率可能固定為 48000，原率 PCM 及 metadata 仍獨立保存。
- Mono 明確選用第一輸入通道建立 1ch MediaRecorder 輸出；不是僅相信 getUserMedia 接受 channelCount。
  Stereo 要求 2ch、檢查 track settings，並等待 AudioWorklet 確認真的收到兩個通道。
  通道不足／不能確認會清理收音資源、拒絕就緒並提示改用 Mono，程式不以複製 Mono 補 R。
- PCM 以 interleaved float32 保存 L/R；sample_count／sample_start 為 frame 數，不是交錯 scalar 數。
  WAV channel count、blockAlign、byteRate 與 data size 隨實際 1／2ch 產生，舊 mono metadata 仍可讀取。
- 主控仍統一開始、停止三位錄音者，亦保留既有 1～5 位設定。錄音時長不受十秒預覽視窗限制。
- 即時波形使用連續 AudioWorklet 預覽點，保留最近十秒，Y 固定 ±1.00，X 固定 -10.00～0.00 秒。
  L/R 各自一路、不同顏色；缺訊號以間斷表示，不偽造資料。只格式化顯示刻度，不四捨五入原 PCM。
- 結果頁可選 L/R 試聽與波形；分析頁可先選裝置、再選 L/R，獨立計算所選窗口的 RMS、peak 與主頻。
  新的瀏覽器聲道檢視不覆寫既有分析 API 結果，不混合不同麥克風音軌。
- 共同控制時間仍只代表排程。未做聲學校正的資料標示未驗證；不在加工過程自動播放參考音。

## 資料庫與 API

**沒有新增 migration，也沒有修改既有資料表。**
網頁錄音實際使用 `mobile_capture`，每個 session／participant 有一筆 `participant_recordings`，
既有 `sample_rate` 與 `channel_count` 可表示每台裝置不同取樣率與 1／2 聲道。
`audio_chunks`／`audio_assets` 保存各裝置的原始容器，不以三位錄音者等同三個音訊通道。
V1.2 `public` 中舊式共用時鐘三通道表不在此網頁資料流內，未修改其歷史語意。

既有建立／加入、start／stop、分段 PUT、finish、audio、analysis 路由不變。

WebSocket 相容擴充：

- 新增 `capture_settings`：只接受房間內錄音者於 waiting 狀態回報。
  欄位：requested_sample_rate（44100／48000）、requested_channel_count（1／2）、
  input_sample_rate、actual_sample_rate、channel_count、support_status（ready／unavailable）。
  房間 snapshot 的 participants 新增 capture_settings；屬連線能力資訊，重連後重報，不變更權限。
- preview 新增 `channels: [[L...], [R...]]`（Mono 只有第一陣列）；保留 samples 作為第一通道供舊客戶端使用。
  驗證有限數值、幅度、通道數、相同長度及頻率限制；舊 samples-only 訊息仍接受。
- prepared 仍使用原格式，sample_rate 為錄音處理率，channel_count 為明確建立的實際錄音輸出通道數。

獨立 Python `AudioSyncService` 支援 mono／stereo 真正 resample_poly 及相同時間變換，
不合併 L/R。PRBS 可透過 manifest 的 calibration_channel 選擇偵測聲道，預設 L；
同一裝置的兩個通道套用相同裝置時鐘變換，保留通道間差異。

## 檔案範圍

|檔案|原因|
|---|---|
|frontend/src/App.tsx|真實連線狀態導航、設定移入錄音者卡、十秒波形及分析入口。|
|frontend/src/useRoom.ts|連線失效判定、收音狀態回報、L/R 預覽緩衝。|
|frontend/src/recordingSyncOptions.ts|核心預設啟用、48000／Mono 預設與聲道設定。|
|frontend/src/RecordingSyncControls.tsx|移除選用 details／開關，顯示率與支援狀態，保留 PCM／metadata 匯出。|
|frontend/src/capture.ts|設定鎖定、Stereo 驗證、明確 1／2ch 錄音輸出。|
|frontend/src/pcmCapture.worklet.js、pcmCapture.ts、pcmStorage.ts|真實雙通道擷取、持續預覽、交錯儲存、frame 計數與 WAV。|
|frontend/src/liveWave.ts（新增）、WavePlot.tsx|十秒連續時間資料、固定座標、兩位小數及 L/R 顏色。|
|frontend/src/ChannelInspector.tsx（新增）、RecordingResults.tsx|每軌獨立聲道試聽／波形／分析。|
|frontend/src/types.ts|連線能力資料型別。|
|backend/app.py、capture_protocol.py（新增）|驗證與廣播收音能力及 L/R 預覽，保留既有路由與權限。|
|backend/audio_sync.py|離線 Stereo 重取樣與對齊，避免單通道限制或誤補零。|
|backend/tests/test_stereo_protocol.py（新增）|能力驗證、Stereo 演算法、三裝置 1／2／1 封存。|
|frontend/tests/stereo-core.spec.ts、stereo-live.spec.ts（新增）|導航、真實 Stereo 訊號、固定波形與三裝置端到端。|
|frontend/tests/pcm-recording.spec.ts、sync-capture.spec.ts|依新版核心模式更新過時的「預設關閉」與自動校正音預期。|

未更動全域 CSS、加工條件、設定管理或登入權限。工作目錄原有未提交變更均保留。
graphify-out 按專案指引更新，不把原有未提交差異全部算成本次修改。

## 測試環境與限制

在 `tmp/pg-stereo-verification` 建立獨立 PostgreSQL 叢集，僅綁定 127.0.0.1:55448，
測試資料庫 cnc_stereo_lab、角色 cnc_stereo_test。只在此新庫套用現有 schema 及 001～004 migration；
不是對使用者 cnc_acoustic_lab 執行 migration。沒有新套件安裝。

測試指令：

```powershell
# 對上述隔離庫設定 TEST_DATABASE_URL，使用現有 PostgreSQL runtime。
.venv\Scripts\python.exe -m pytest backend/tests -q --tb=short
npm --prefix frontend run build
# 在 frontend，CNC_TEST_URL 指向本機 Vite（代理隔離測試後端）
npx playwright test tests/stereo-live.spec.ts tests/stereo-core.spec.ts tests/pcm-recording.spec.ts tests/sync-capture.spec.ts tests/sync-results.spec.ts tests/synchronization.spec.ts --reporter=line
```

Stereo 實驗訊號由真實 Web Audio 左 440 Hz、右 880 Hz 產生，經 AudioWorklet、WAV、
MediaRecorder 編碼／解碼檢查仍有兩個不同聲道。頻率檢查使用穩態零交越週期，
不將編碼器起始靜音誤算成頻率改變。三裝置端到端測試使用真正 HTTP、WebSocket、
PostgreSQL 與三個隔離 Chrome context；其中 Stereo 為上述合成雙通道輸入。

這不是三台實體硬體測試。Android／平板驅動支援、硬體雙麥克風來源獨立性、
背景收音及絕對同步精度仍需實機驗證。瀏覽器通道回報與實際 Worklet 輸入已驗證，
但不以它們保證硬體內部沒有降噪、混音或相同訊號路由。
PCM 仍保存於各裝置 IndexedDB 並可匯出；原有壓縮音軌自動上傳，沒有虛稱 PCM 已自動送到伺服器。

## 實際驗證結果

- 後端全套：**47 passed**（38.48 秒），只有既有 Starlette/httpx 棄用提醒。
- 前端上述六個測試檔：**18 passed**（39.9 秒）。包含真正三裝置連線、主控開始／停止、
  DB 的 1／2／1 聲道、下載解碼的 1／2／1 聲道，以及兩頁的 L/R 操作。
- `npm --prefix frontend run build`：TypeScript 與 Vite 通過。
- 44100／48000 PCM、取樣回退顯示、Mono／Stereo、拒絕不支援 Stereo、
  缺段／重複／重載保留、離線補傳、固定波形與兩位小數均有測試覆蓋。
- 已檢視 390px 寬的實際錄音畫面 screenshot；未增加全域 CSS，既有 CSS 產物 hash 不變。
- 先前測試揭露 getUserMedia 要求 Mono 仍回報 2ch，已以明確單通道輸出修復，
  不修改 metadata 偽稱 Mono。修復後對實際下載音檔再次解碼確認。

未執行部署或 Git push；線上 GitHub Pages／其他服務仍需使用既有發布流程更新。
