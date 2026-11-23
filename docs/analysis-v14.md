# 錄音分析 V1.4 開發與驗收

驗證日期：2026-11-17（Asia/Taipei）。本次修改原始碼，保留工作區原有多裝置、PCM 與同步擴充；未提交、推送或部署。

## 1. 現有架構檢查

- 前端已有 React 19、TypeScript、Vite；不是只有 minified bundle。原分析頁呈現既有 `analysis_results` JSON 與瀏覽器聲道檢查。
- 後端已有 FastAPI、WebSocket 與 PostgreSQL。房間 Bearer 憑證驗證成員權限，主控有開始／停止、加工條件及房間管理權限。
- 手機分段位元組在 `mobile_capture.audio_chunks`，封存索引在 `audio_assets`；共同鍵為 `(session_id, participant_id)`。chunk 索引還包含裝置，不會因不同裝置的 chunk_index 相同而衝突。
- V1.2 的 `public` schema 為既有共享時鐘三聲道模型；現行手機流程使用獨立 `mobile_capture` schema。沒有把 public 的三聲道限制直接套到手機錄音。
- 尚無既有 STFT／MFCC 後端工作程序。本次新增持久化分析佇列，沿用單一服務 worker 的既有架構。

## 2. 修改／新增檔案

新增：

- `backend/analysis_signal.py`：解碼、重取樣、STFT、Mel filter bank、DCT、PNG、數值矩陣。
- `backend/analysis.py`：分析排程、持久化、狀態、受保護 API。
- `backend/migrations/005_track_analysis.sql`：只新增分析表與要求取樣率／聲道數欄位。
- `backend/requirements-analysis.txt`：沿用 NumPy／SciPy，加上 PyAV／Matplotlib。
- `frontend/src/RecordingAnalysis.tsx`、`frontend/src/analysis.css`：分析頁。
- `backend/tests/test_analysis_signal.py`、`backend/tests/test_analysis_api.py`、`backend/tests/prepare_analysis_ui.py`、`frontend/tests/analysis.spec.ts`：計算、API 與真實 PNG 瀏覽器驗證。

局部修改：`backend/app.py`（啟動分析 worker、保存要求格式）、`backend/audio.py`（封存交易中排程）、`backend/requirements.txt`（引用分析依賴）、`frontend/src/App.tsx`（接入分析頁）、`frontend/tests/stereo-live.spec.ts`（分析頁新驗收條件）、`README.md`。graphify 產物依規範更新。其他既有未提交修改保留。

## 3. 前端

Session 下拉選單列出目前授權房間的批次；批次卡顯示名稱（Session ID 前八碼）、日期、最大實際時長、封存裝置數、成功可分析音軌數。每張卡另列裝置／聲道、實際解碼原始取樣率及自身時長。

Spectrogram 與 MFCC 各有獨立區塊，共用相同來源排序及區間。桌機兩欄，760px 以下單欄；沒有額外 PCM、權限診斷或模型圖表。支援全部／個別音軌、共同時間區間、原生 dialog 放大（Escape／鍵盤焦點）、PNG 下載。非主控可讀取結果；啟動新分析沿用主控權限。

圖片需以 Bearer 憑證取得後轉為短期 Blob URL，卸載時釋放；不把憑證放入 URL，也不下載矩陣到手機。每兩秒取得狀態；切換 Session 取消舊請求與清除舊圖。尚未分析、排隊、執行、部分完成、失敗均有真實狀態。

## 4. 44100／48000 Hz

PyAV 以實際解碼 frame 的 rate／layout 為準。`requested_sample_rate` 為瀏覽器要求值，`reported_sample_rate` 為錄音準備時回報值，`original_sample_rate` 和 `actual_sample_rate` 為解碼值，`analysis_sample_rate=44100`。歷史錄音沒有要求值時保留 null，不猜測。

44100 Hz 複製分析資料；48000 Hz 使用 147/160 polyphase resampling。FIR 為 `128*max(up,down)+1` taps，Kaiser beta 8.6，歸一化截止頻率 `1/max(up,down)`。此低通濾波先於降採樣；不是修改標頭。原始位元組、SHA256 與下載端點均維持原狀。

時間範圍以各錄音起點為 0，沒有宣稱跨裝置樣本同步。圖表最高頻率 22050 Hz；不宣稱保留原始 48 kHz 中 22050 Hz 以上資訊。圖表統一 X 軸，較短來源超出有效範圍處留白；完整窗不足 2048 samples 時回報 no_data，不補造訊號。

## 5. 聲道拆分與儲存

每個 `participant_recordings` 是一個 Session 中的錄音裝置，連到該裝置原始 `audio_assets`。解碼得到 1 聲道建立 Mono；2 聲道建立 Left／Right，各自計算，無平均或複製。要求 Stereo 但實際 Mono 只建立一條 Mono。超過兩聲道的歷史檔會回報不支援，不擅自丟棄聲道。

`recording_tracks` 以 `(session_id, device_id, channel_index)` 唯一識別，保存實際 frames、duration、rate 與 label。`audio_asset_id` 在 API 中為既有複合鍵的 `session/device` 字串；資料表以複合外鍵連到原始資產，不另造一份原始音檔。

每次執行保存 parameters、algorithm_version、套件版本、SHA256、有效時間範圍與結果；`track_analysis_artifacts` 保存每聲道兩張 PNG 與 float64 NPZ 矩陣。原始音檔與數值矩陣不因軸標籤的兩位小數而降低精度。PNG 顯示最多 1200 時間欄，僅繪圖做分箱平均；保存的矩陣仍為每個 hop。

## 6. 實際計算

實作在 `backend/analysis_signal.py`：

1. `decode`：解碼並保持每個實際聲道及解碼取樣率。
2. `resample`：各聲道獨立建立 44100 Hz 分析拷貝。
3. `calculate`：2048 FFT、441 hop、periodic Hann、不置中、不填補結尾。FFT 分批計算。
4. Spectrogram：FFT 振幅除以 Hann 窗總和，單邊內部頻率乘二（DC／Nyquist 不乘），`20 log10(max(amplitude, 1e-6))`；全批固定 -120～0 dBFS，以 peak amplitude 1 為完整刻度，不是校正聲壓，也沒有每檔最大值歸零。
5. MFCC：單邊振幅平方 → 64 個 HTK Mel 三角濾波器（unit peak）→ 固定參考 `10 log10(max(mel_power,1e-12))` → Type-II orthonormal DCT → C0～C19。沒有把 Mel Spectrogram 當 MFCC。
6. MFCC 色階取同一分析工作所有成功聲道的共同 min/max，不做每張圖 Min-Max 正規化。

採用的函式定義可參照 [SciPy resample_poly](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html)。實際運算版本保存於每筆結果；本次驗證為 NumPy 2.5.4、SciPy 1.18.1、PyAV 19.0.2、Matplotlib 3.11.2。

## 7. API 與 Migration

API 沿用房間 Bearer：

| 方法 | 路徑 | 行為 |
|---|---|---|
| GET | `/api/v1/sessions/{session_id}/analysis` | 取得指定 start_seconds／end_seconds 的最新狀態與動態音軌 |
| POST | 同上 | 主控提交 `{start_seconds:0,end_seconds:null}`；202 回傳 run_id |
| GET | `/api/v1/sessions/{sid}/analysis/{run}/tracks/{track}/{kind}.png` | 受房間權限保護的 spectrogram／mfcc 圖片 |

原 `/api/rooms/{code}/analysis` 相容保留，不改寫舊 JSON 結果。新的分析結果放在新表，避免污染舊格式。

封存成功的同一交易建立 queued 工作，無完整音檔不排程。新資產集合或新區間有新工作；相同輸入與參數去重。單一背景執行緒避免圖表繪製競爭；來源或單聲道失敗不會抹除成功兄弟聲道。服務重啟將 running 恢復 queued，artifact 寫入可重跑。失敗工作可由主控用相同參數重試。

005 為新增式 Migration；不刪表、不改寫 public V1.2 舊資料、不變更原音檔或 chunk 索引、不變更舊 `channel_features`／`analysis_runs`。V1.2 的 public 三聲道資料仍可用原 SQL／原系統讀取；本次沒有把未提供資產存取／授權映射的 public 歷史檔自動匯入新手機分析頁。既有 mobile_capture 批次可由主控按分析載入。

## 8. 驗證與限制

已親自執行：

- `npm.cmd --prefix frontend run build`：TypeScript＋Vite 通過（52 modules）。
- `git diff --check`：通過，僅有工作區既有 CRLF 提示。
- 專案 `.venv` 的 `pytest backend/tests -q --tb=short`，設定隔離 `TEST_DATABASE_URL` 與專案既有 psycopg libpq 路徑：**60 passed**，含新增 13 項分析測試。Starlette/httpx 有既有棄用警告，未為消除警告另裝依賴。
- `npm.cmd test -- analysis.spec.ts stereo-live.spec.ts`（CNC_TEST_URL 指向 5176）：**2 passed**。
- `.venv/Scripts/python.exe -m graphify update .`：成功；SQL extractor 的 tree_sitter_sql 未安裝，因此 SQL 以真實 PostgreSQL Migration 驗證為準。

後端測試覆蓋三台 Mono、混合 rate、1/2/1、全部 Stereo（3/3/4/6 音軌）、每軌兩張真實 PNG、固定 dB 參考、解析 DCT 係數、抗混疊、metadata 不符以實際 rate 為準、Stereo 要求但實際 Mono、缺失裝置、解碼失敗、未完成錄音、共用區間、無足夠樣本、跨房間與非主控權限、重啟讀取與重跑。

瀏覽器用已安裝 Chrome：一組測試使用真實 API 中的 WAV 訊號驗證桌機／手機與下載；另一組由三個獨立瀏覽器裝置實際 MediaRecorder 編碼、分段上傳、試聽，再自動產生 4＋4 張圖。測試使用可辨識的測試音源，沒有在產品中使用測試矩陣或模擬圖表。桌機與手機截圖在 `tmp/analysis-desktop.png`、`tmp/analysis-mobile.png`，已目視檢查。

尚未驗證／未包含：真實三支手機、iOS Safari、長時間／多小時資源壓力、正式 HTTPS 部署。手機只載入 PNG，但目前後端仍保留單工作完整解碼 PCM 與結果矩陣於記憶體；FFT 中間運算分批，尚非全串流分析。高併發／大量長錄音需後續容量規劃。未新增模型辨識、特徵融合、物理音壓校正或跨裝置精確同步。

## 9. 建置與啟動

現有專案 `.venv` 已獲准安裝分析依賴。新環境使用 README 的已確認 Python 建立專案環境，然後安裝 `backend/requirements.txt`（現在會引用分析依賴）。

停止目標服務並確認資料庫版本後，**只套用尚未執行的 Migration**，順序為 001、002、003、004、005；003～005 不可重複執行。不要重建既有 public V1.2 schema。

```powershell
# 已完成 001～004 的目標開發資料庫
psql -X -v ON_ERROR_STOP=1 -d '<開發資料庫連線>' -f backend/migrations/005_track_analysis.sql
npm.cmd --prefix frontend run build
./scripts/run-backend.ps1 -DatabaseUrl '<開發資料庫連線>'
# 另一終端
npm.cmd --prefix frontend run dev
```

或用現有 `scripts/run-local.ps1 -DatabaseUrl '<開發資料庫連線>'` 提供單一來源前後端。

本次僅啟動 `tmp/pg-test` 本機 55432 測試叢集，補齊 `cnc_lab_test` 缺少的 002～005；首次 004 因缺 003 失敗，該次交易回滾後依版本補齊。沒有套用至 `cnc_lab` 或正式資料庫。

重現 UI 驗證時，先停掉佔用該隔離資料庫 advisory lock 的後端，再設定 TEST_DATABASE_URL 執行 `.venv/Scripts/python.exe -m backend.tests.prepare_analysis_ui`；測試憑證只寫入被 Git 忽略的 tmp。接著啟動該資料庫的後端與 Vite，執行上述 Playwright 指令。
