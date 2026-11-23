# 網頁錄音擴充：最小侵入式交付

> 後續核心多裝置／Stereo 需求已取代本文件的預設關閉與選用 UI；最新行為見 [stereo-recording-interface.md](stereo-recording-interface.md)。以下保留為前一階段交付紀錄。

本文件描述本次新增內容，不把工作目錄原有未提交修改算成本次成果。

## 架構與範圍

既有路徑是 React `RecorderDevice` → getUserMedia／MediaRecorder → IndexedDB
`cnc-capture-v1` → 帶 SHA-256 的 HTTP 分段上傳 → FastAPI／PostgreSQL
`audio_chunks`、`audio_assets` → 既有結果讀取。房間 WebSocket 已提供
prepare／prepared、共同 starts_at、ping／pong／clock、started、stop；仍沿用它們。

本次在同一麥克風串流旁增加 AudioWorklet PCM 支路，不替換 MediaRecorder。
`multiDeviceSyncEnabled` 預設 false，關閉時沿用原有授權、錄音、參考音及上傳行為。
開啟時，原有壓縮錄音仍保留倒數預錄；附加 PCM 依既有共同時間排程，
使用 AudioContext 真正處理率計數，保存在獨立 IndexedDB `cnc-sync-pcm-v1`。
輸入裝置率、要求率、PCM 處理率各自記錄，不能把 MediaRecorder 的編碼率當作 PCM 率。

控制與音訊排程不代表樣本級同步。時鐘半往返時間僅為估計，不是誤差上限。
PCM 排程若缺少有效校時，仍可保存原始 PCM，但時間對齊不可宣稱成功。
AudioWorklet 在初始化完成後才進入原有麥克風就緒流程；不支援時仍可使用原錄音。

參考 [SyncRecord](https://github.com/PadraicMCE/SyncRecord) 的
[Detection.py](https://github.com/PadraicMCE/SyncRecord/blob/main/Detection.py)
相關偵測與 [SyncAudio.py](https://github.com/PadraicMCE/SyncRecord/blob/main/SyncAudio.py)
獨立音軌對齊概念。本次演算法為獨立實作，沒有複製原始碼或 Android 系統。
參考專案採 [MIT License](https://github.com/PadraicMCE/SyncRecord/blob/main/LICENSE)。

## 檔案

新增：

- `frontend/src/recordingSyncOptions.ts`：預設關閉的開關與每裝置取樣率。
- `frontend/src/pcmCapture.worklet.js`：單聲道 PCM、連續樣本位置、分段序號；不執行網路或儲存。
- `frontend/src/pcmCapture.ts`：排程、AudioWorklet 訊息、非阻塞寫入佇列、失敗狀態。
- `frontend/src/pcmStorage.ts`：獨立暫存、原子寫入與重複拒絕、樣本連續性驗證、原率 WAV 匯出。
- `frontend/src/recordingAssets.d.ts`：Vite worklet URL 型別。
- `frontend/src/RecordingSyncControls.tsx`：錄音區內選用控制與本機附加檔案匯出。
- `backend/audio_sync.py`：獨立 CLI／AudioSyncService；沒有 web API 或資料庫依賴。
- `backend/requirements-sync.txt`：獨立可選依賴，不變更原有 backend requirements。
- `backend/tests/test_audio_sync.py`、`frontend/tests/pcm-recording.spec.ts`：演算法與瀏覽器測試。

既有檔案僅改：

- `frontend/src/capture.ts`：開關啟用時要求取樣率、初始化與啟停附加 PCM。
- `frontend/src/useRoom.ts`：將既有校時估計交給 PCM 模組；不改事件或 payload。
- `frontend/src/syncReference.ts`：新模式停用舊的自動掃頻聲，避免加工量測受干擾；關閉開關時維持舊行為。
- `frontend/src/App.tsx`：新增 import 及錄音台內一個元件呼叫；原有導覽與其他頁面不變。

依 AGENTS.md 執行 `graphify update .`，更新 graphify-out 知識圖。
這是專案索引維護，不是業務功能修改。SQL extractor 缺依賴的警告仍存在，沒有因此安裝無關套件。

**本次是否修改任何非錄音相關功能？否。**
沒有 Migration；沒有 API 路由、請求格式、權限、資料表、實驗關聯、全域 CSS、
結果頁或分析頁變更，也沒有更改舊檔案名稱或下載讀取方式。

## 使用

1. 每台裝置（含主控）在主控錄音台展開「多裝置同步錄音擴充（選用）」。
2. 勾選開關，每個錄音裝置各自選 44100 或 48000 Hz；於未錄音時重新載入，設定才生效。
3. 依原有流程授權麥克風、全員就緒、主控開始／停止。準備訊息列出輸入率、PCM 率與音訊處理設定是否確實關閉。
4. 停止後點「檢查本機 PCM 附加錄音」，分別匯出 WAV 與 metadata。
   每個附加錄音有獨立隨機識別，重試／重錄不覆寫前次資料。
5. 原有壓縮音訊仍會照原有流程補傳與封存。**附加 PCM 目前只在各裝置本機，未自動上傳至伺服器。**
   不清除瀏覽器網站資料，避免尚未匯出的資料消失。重載後不完整的 PCM 可匯出，但不能通過校正。

AudioWorklet 收音與 IndexedDB 寫入分離。超過 128 個待寫區塊、寫入失敗或停止確認逾時時，
附加 PCM 標示失敗並保留已寫區塊，不阻止原有 MediaRecorder 保存。
匯出會檢查順序、樣本數及實際率，缺資料時拒絕產生假完整 WAV。
瀏覽器匯出需載入各區塊，大型或長時間錄音仍需實機記憶體／儲存壓力測試。

## Python 離線入口

已經使用者核准，SciPy 安裝於專案 `.venv`；不更動全域環境。
後端 web app 不 import 此可選模組。需另行安裝時：

```powershell
.venv\Scripts\python.exe -m pip install -r backend/requirements-sync.txt
```

將同房間、同 session 的 WAV 和 metadata 放入一個授權的錄音工作目錄。
建立 manifest（檔名換成真正匯出的檔名；device_id 沿用既有 participant_id）：

```json
{
  "room_code": "ABCDEF",
  "session_id": "實際-session-UUID",
  "mode": "none",
  "tracks": [
    {"wav": "device-A.wav", "metadata": "device-A.json"},
    {"wav": "device-B.wav", "metadata": "device-B.json"}
  ]
}
```

```powershell
.venv\Scripts\python.exe -m backend.audio_sync --root "C:\錄音工作目錄" --manifest manifest.json --enable
```

`--enable` 明確開啟服務的 `multiDeviceSyncEnabled`；未指定時不執行。
輸出在 `derived/<room>/<session>/<新UUID>/`，包含每台裝置的 48000 Hz analysis WAV
及 `sync-report.json`。成功對齊另有獨立 aligned WAV，不合併音軌，不覆寫原始檔。
所有輸入／輸出路徑都限制在指定 root，拒絕跨房間、跨 session、重複裝置及 WAV／metadata 不一致。

模式：

- `none`：只建立真正重取樣的分析副本，狀態 unverified。
- `time`：需 PCM 起始時間及有效校時 metadata；產生估計對齊副本，狀態 time_estimate_unverified，不估造漂移。
- `prbs`：每軌提供明確 `calibration_windows` 秒數範圍，例如 `[[0.1,1.0]]`。
  必須錄到下述版本的真實模板；不是 SyncRecord 原版 PRBS，也不是現有掃頻參考音。

產生模板（檔案已存在時拒絕覆寫）：

```powershell
.venv\Scripts\python.exe -m backend.audio_sync --root "C:\錄音工作目錄" --template --enable
```

僅在**專用校正錄音**或 CNC 加工開始前／結束後，用播放器播放產生的 `cnc-mls10-chip4-v1.wav`，
讓所有麥克風都錄到它。不要在正式加工量測中播放。網頁不自動播放 PRBS。
`calibration_windows` 是各原始 PCM 起點起算的秒數，對應到真正 48 kHz 副本後才偵測。
一次有效標記只估偏移，drift_ppm 為 null。若要估漂移，需同一連續錄音中至少三個
依序對應的標記、首尾至少五秒；中間標記獨立驗證，不能拿不同錄音批次硬套漂移。
漂移以 resample_poly 真正修正，不改 WAV Header。

報告記錄來源率、分析率、原／新樣本數、來源 SHA-256、偏移樣本／毫秒、漂移、信心分數、
校正方法及品質。PRBS 缺失或峰值模糊會回報 failed，仍保留原檔及分析副本可重試。
PRBS 通過僅代表相對聲學對齊，包含物理傳播延遲；絕對精度一律 unverified。
沒有雙向傳播延遲分離，不能把聲學到達差宣稱為裝置時鐘差。

## 相容性與未完成邊界

- 原有多裝置房間、主控開始停止、每軌上傳、斷線重連皆沿用，不建立另一套控制系統。
- 原有單裝置與歷史壓縮音檔仍走原來頁面／API。新增 PCM 不會出現在原結果／分析頁。
- 新開關是每瀏覽器設定；伺服器不協調開關或取樣率，操作時需確認所有裝置（含主控）設定一致。
- 本次未新增自動收集 PCM 到伺服器、線上啟動 Python、網頁 PRBS 播放／輪流發聲協定，
  因這些需要擴充傳輸、控制或儲存契約。使用匯出與離線入口是保留契約的安全替代。
- 不能把獨立校正 take 的偏移直接套到之後重開 AudioContext 的正式 take；目前沒有提供這種假校正。
- 無真實 Android／平板／不同硬體驗證；背景節流、長時間漂移、硬體頻率回退與絕對同步精度仍待實機測試。

## 驗證

基準：前端 build 通過；既有瀏覽器錄音／結果 5 項通過，演算法 4 項通過。
首次後端全套測試因 TEST_DATABASE_URL 未設定得到 19 failed／9 errors，並非成功基準。
隔離測試叢集的登入角色未確認，因此既有資料庫整合測試尚未完成；沒有對實驗資料庫跑寫入測試。

新增測試涵蓋 44100／48000、混合 PCM、共同時間排程、單台停止不牽連其他台、
原音訊補傳、樣本完整性、重複交易原子拒絕、重載保留、開關預設關閉、沒有自動校正音、
PRBS 已知偏移／殘差、合成長時間漂移、原檔不變及校正失敗可重試。
這些是合成訊號和 Chrome 假麥克風結果，不是跨實體裝置精度證明。

最終實際執行：

|命令／檢查|觀察結果|
|---|---|
|`npm --prefix frontend run build`|TypeScript 與 Vite 建置通過，CSS 資產雜湊與基準一致。|
|`.venv\Scripts\python.exe -m pytest backend/tests/test_audio_sync.py -q`|16 passed。|
|`.venv\Scripts\python.exe -m compileall -q backend/audio_sync.py`|通過。|
|在 frontend：`npx playwright test tests/pcm-recording.spec.ts tests/sync-capture.spec.ts tests/sync-results.spec.ts tests/synchronization.spec.ts --reporter=line`|13 passed；使用本機 Vite 與 Chrome 假麥克風，API 上傳由測試攔截模擬，非真實資料庫整合。|
|`git diff --check`|通過；只有既有檔案的 CRLF 提醒。|
|修改前後 SHA-256 比對|僅四個上述既有錄音接入檔案變動，其餘受保護檔案相同；App.tsx 去除兩處新增後可精確還原基準位元組。|
|390px 錄音擴充控制畫面|實際 screenshot 檢視，沒有水平溢出；按鈕與選單可操作。|

測試中曾找到 PCM 重複區塊的 IndexedDB transaction error 為 null；已改為等 transaction abort
再回報，重新執行驗證原子拒絕及重載恢復均通過。
既有後端全套仍受 TEST_DATABASE_URL／隔離測試角色缺失阻擋，不宣稱資料庫回歸通過。
