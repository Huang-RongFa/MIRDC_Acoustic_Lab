# 地端分析 worker：雲端只寫入，地端計算，資料表溝通

## 為什麼這樣分

- 分析模型每多錄 1 分鐘約多用 2.7 GB 記憶體（2026-11-10 實測），不適合放在雲端後端。
- 後端是單一程序，同時負責三支手機的 WebSocket。在裡面跑幾分鐘的運算，所有錄音中的房間都會斷線。
- 所以雲端只做接收、校驗、存檔；重運算交給地端電腦。兩邊只透過 `mobile_capture` 的資料表溝通。

```
三支手機 ─分段上傳─▶ 雲端後端（只寫入）
                         │ 三聲源封存完成 → recording_sessions.status='completed'
                         │ trigger 在同一個交易裡新增 analysis_jobs（queued）
                         ▼
                   PostgreSQL（mobile_capture）
                         ▲ 地端 worker 主動連出去（不需要開放任何入站連線到地端）
                         │ 認領 → 下載音段並校驗 → ffmpeg 解碼 → analyze_multi_mic
                         │ → 寫 audio_alignment_runs、analysis_results → 工作改為 completed
                         ▼
             網頁「分析結果」頁：GET /api/rooms/{code}/analysis 回傳 results 與 jobs
```

## 資料表（migration 004）

| 表／欄位 | 作用 |
|---|---|
| `analysis_jobs` | 工作佇列：`queued` → `running` → `completed`／`failed` |
| `analysis_jobs.lease_expires_at`、`worker_id` | 租約。worker 每 lease/3 秒延長一次；當機或斷電時租約過期，別台 worker 可接手 |
| `analysis_jobs.attempts`／`max_attempts`（預設 3） | 失敗會回到 `queued` 重試，第 3 次失敗改為 `failed` |
| `analysis_jobs.pipeline_version`、`code_commit` | 每份結果是哪一版程式算的 |
| `analysis_jobs.error` | 給網頁看的失敗原因（≤ 500 字，不含地端路徑或堆疊；完整 log 留地端） |
| 部分唯一索引 `analysis_jobs_one_active` | 同一場錄音同時最多一筆等待或執行中的工作 |
| `analysis_results.job_id`、`audio_alignment_runs.job_id` | 結果對應到哪一筆工作；重跑會新增一筆，不覆蓋舊結果 |
| trigger `session_completed_enqueue` | 錄音完成時自動排入；migration 也會補排「已完成但沒有結果」的舊錄音 |

## 認領與所有權

- 用 `FOR UPDATE SKIP LOCKED` 認領最舊的一筆：兩台 worker 不會拿到同一筆。
- **所有權 = 工作 id ＋ worker_id ＋ 認領時的 attempts ＋ status='running'**。`attempts` 每次認領都加 1，所以舊的嘗試即使 worker_id 相同，延長租約、回報失敗、寫結果都會落空。
- 租約過期只代表「可以被別人認領」。在被別人認領之前，原本的嘗試仍可完成並寫入。
- 心跳發現失去所有權時，立刻終止分析子程序，不寫任何結果。
- 每次嘗試用自己的資料夾 `attempt-<n>`，重疊的嘗試不會互相覆寫檔案。
- 失敗時是否重試，由資料庫當下的 `attempts < max_attempts` 決定。
- 租約過期且已用完重試次數的工作，下一次有 worker 認領時改為 `failed`，不會永遠停在 `running`。
- worker 的每個資料庫連線都設 `statement_timeout=120s`、`lock_timeout=30s`；單筆分析另有 `--timeout-seconds` 上限。

## 對齊判定（不可把未驗證的數字當結果）

模型對齊之後會再量一次殘差。worker 依此給出 `result.alignment`：

- 以實際送進分析的聲源（`channels`）為準：每一支非 A 聲源都必須有 `<聲源>_vs_A`，且殘差欄位是有限數字。
- `verified: true`：每一對的殘餘偏移 ≤ 2 取樣點，且殘餘漂移 ≤ 5 ppm。
- 否則是 `verified: false`，並在 `failed_pairs` 列出原因。網頁顯示「對齊未通過驗證，同步與相位數字不可使用」。
- `audio_alignment_runs.status` 也會寫成 `verified` 或 `unverified`。

## 地端電腦怎麼跑

1. 套用 migration 004（資料庫管理員）。注意事項：
   - 加入佇列的 trigger 函式是 `SECURITY DEFINER`：後端帳號不需要 `analysis_jobs` 的寫入權限，錄音完成不會因權限失敗。
   - 後端帳號需要 `analysis_jobs` 的 SELECT 權限，`GET /analysis` 才讀得到佇列狀態。用同一個帳號套 migration 與跑後端時本來就有；不同帳號時要另外 GRANT。
   - 004 會對 `analysis_results`、`audio_alignment_runs` 加欄位與唯一索引，執行期間短暫鎖住這兩張表。目前兩張表幾乎是空的，影響可忽略；建議仍在沒有人錄音時套用。
2. 執行 `deploy/analysis_worker_role.sql` 建立最小權限帳號 `analysis_worker`，再用 `\password analysis_worker` 設密碼。這個帳號：
   - 能讀：音段、封存紀錄、聲源代號（`room_participants` 只開 id 與聲源，讀不到 token_hash 與姓名）；
   - 能改：工作狀態；
   - 能新增：結果；
   - 不能：新增工作、刪除音段、改動錄音資料。
3. 資料庫只允許地端電腦的對外 IP，並強制 TLS（`sslmode=require`）。
4. 地端電腦（本機用 `audio_preject` 環境，已含 numpy、scipy、soundfile、matplotlib、psycopg；ffmpeg 由 imageio-ffmpeg 提供）：

```powershell
$env:ANALYSIS_DATABASE_URL = 'postgresql://analysis_worker@<資料庫主機>:5432/<資料庫>?sslmode=require&gssencmode=disable'
$env:PGPASSWORD = '<只放在這台電腦>'
python -X utf8 analysis/worker.py --work-dir D:\cnc_analysis
```

- `--once`：處理一筆就結束（排程器用）。
- `--lease-seconds`：預設 300。
- `--timeout-seconds`：單筆分析上限，預設 3600。
- `--poll-seconds`：沒有工作時多久查一次，預設 10。

地端輸出放在 `<work-dir>/<session_id>/<job_id>/attempt-<n>/`：三軌 webm 與 wav、對齊後音檔、圖、`summary.json`、`analyzer.log`。這些大檔**不上傳**；資料庫只存數字。

## 尚未做的

- 圖檔還沒有回傳雲端，網頁目前只顯示 JSON 與判定文字（工作等待或執行中時每 15 秒自動重讀）。下一步可以新增 `analysis_figures`（縮小後的 PNG，存 bytea），並加一個讀圖端點。
- 錄音中的即時輕量特徵（手機端每秒音量與頻帶能量）還沒做。
- 雲端資料庫實際放在哪裡、是否能對地端 IP 開放，需要部署時決定。
