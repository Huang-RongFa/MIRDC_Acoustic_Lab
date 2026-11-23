# 2026-11-23 更新：外部分析接到 main（網站原始碼已合併之後）

分支：`claude/external-track-analysis-v1`（PR #5）。接續 [`2026-11-20-external-track-analysis-real-schema.md`](2026-11-20-external-track-analysis-real-schema.md)。
狀態：**本機測試通過；已推送分支、尚未合併。正式站仍未驗證。**

## 一、背景

2026-11-23，網站那邊的原始碼與 PR #2 的內容經由 `feature/room-code-recording`（PR #6）合併進 `main`。
PR #5 原本疊在 PR #2 的分支上，測試用的是另外收到的網站檔案複本。這次把它改成直接接在 `main` 上。

## 二、對照 main 之後確認的事

| 項目 | 結果 |
|---|---|
| `backend/analysis_signal.py`、`backend/analysis.py`、`005_track_analysis.sql` | 和 2026-11-20 收到的檔案逐位元相同，先前的比對結果仍然有效 |
| `004_multi_recorder.sql` 第 11 行的多餘字元 | 網站那邊已修正（commit 2abf2bd）；現在的內容和先前測試用的版本相同 |
| 分析頁的圖框（`RecordingAnalysis.tsx`、`analysis.css`） | 固定 2:1：`<img width="960" height="480">`，樣式是 `aspect-ratio:2; object-fit:contain` |
| 分析頁用到的欄位 | `device_name`、`channel_label`、`original_sample_rate`、`duration_seconds`、`analysis_status`、`error`、兩個圖的 URL、`source_errors`；地端的結果都有 |
| 內建分析的觸發 | 分析頁寫明封存後自動分析，所以每個 session 都會先有內建結果 |

## 三、改了什麼

| 檔案 | 改動 |
|---|---|
| （合併） | 把 `main` 合併進這個分支，沒有衝突 |
| `analysis/track_analysis/render.py` | 圖從 1200×528 改成 960×480，和內建的圖、分析頁的圖框一致。原本的尺寸放進 2:1 的圖框會上下留白 |
| `analysis/tests/test_track_publish.py` | 建庫改用 `backend/migrations` 的 001–005；新增兩個測試（見下） |
| `analysis/tests/test_track_reference.py` | 預設比對儲存庫裡的 `backend/analysis_signal.py`，不必再設環境變數 |
| `analysis/tests/fixtures/` | 移除。裡面的 004、005 複本現在和 `backend/migrations` 重複 |
| `docs/external-track-analysis.md`、`analysis/README.md` | 同步更新 |

寫回資料庫的程式（`publish.py`）、數值計算（`signal_contract.py`）、帳號腳本都沒有改。

新增的測試：

- `test_database_passes_the_sites_own_startup_check`：測試資料庫在地端寫入之後，要通過網站啟動時的結構檢查（`backend/schema.py` 的 `check_schema`）。
- `test_site_sql_still_matches_the_backend`：測試裡照抄的查詢 API、PNG API、內建 worker 領工作、內建寫音軌的 SQL，以及 track_id 規則與顯示名稱格式，都還在 `backend/analysis.py` 裡。網站那邊改了這些，測試會失敗。

## 四、驗證證據

環境：`audio_preject`（Python 3.10）；本機 PostgreSQL 18 測試庫。

| 檢查 | 結果 |
|---|---|
| `test_track_signal.py` | 9/9 |
| `test_track_reference.py`（對象：儲存庫裡的 `backend/analysis_signal.py`） | 5/5 |
| `test_track_publish.py`（`backend/migrations` 001–005 建庫，最小權限帳號） | 25/25 |
| 既有測試 `test_synthetic`、`test_offline`、`test_ears_umik`、`test_background` | 5/5、5/5、13/13、6/6 |
| 實際產生的圖 | Spectrogram 與 MFCC 都是 960×480 |
| pyflakes | 沒有訊息 |

這次沒有跑跨引擎審查：改動不涉及資料表定義、寫回邏輯或權限，只有圖的尺寸與測試的接線。

沒有跑的：網站自己的測試（`backend/tests/`、前端測試）。那些不是這個 PR 的內容，合併 `main` 時也沒有衝突。

## 五、還沒有驗證的

- **正式站**：實際部署的版本、PyAV 版本、地端以 `track_analysis_writer` 連線寫入資料庫，都需要部署管理入口才能驗證。目前確認的只有 GitHub `main` 與本機隔離的測試環境。
- 網站的 API 本身（FastAPI、權限檢查）與分析頁沒有對著地端寫入的資料實際跑過。→ 同日已在本機做完，見 [`2026-11-23-external-track-analysis-local-site.md`](2026-11-23-external-track-analysis-local-site.md)。
- 其餘同前一份紀錄：iPhone Safari 的錄音沒有比過解碼；很長的錄音沒有時間或記憶體上限。

## 六、下一步

1. 取得部署管理入口後：確認正式站版本與 PyAV 版本；建立 `track_analysis_writer`；用 `--dry-run` 對一個真實 session 跑一次再實際寫回。
2. 在本機把網站的後端跑起來，用它的 API 讀地端寫入的結果（不需要正式站，可以先做）。
3. `004_analysis_jobs.sql` 與 `004_multi_recorder.sql` 編號重複，要不要重新編號由儲存庫的擁有者決定。
