# 2026-11-11 更新 v2：雲端只寫入、地端計算（分析工作佇列）

分支：`claude/analysis-model-sync-v1`（延續 v1，新增一個 commit）。
狀態：**已測試、已推送分支、尚未合併**。合併前請審閱。

## 一、為什麼做

v1 的分析模型在雲端跑會有兩個問題（2026-11-10 實測）：
- 每多錄 1 分鐘約多用 2.7 GB 記憶體。
- 後端是單一程序，在裡面跑幾分鐘的運算，所有錄音中的房間都會斷線。

你決定的做法是：雲端只寫入資料表，地端電腦計算，兩邊只靠資料表溝通，先用 `mobile_capture` schema。設計細節見 [`docs/analysis-worker.md`](../analysis-worker.md)。

## 二、改了什麼

| 檔案 | 內容 |
|---|---|
| `backend/migrations/004_analysis_jobs.sql`（新） | `analysis_jobs` 工作佇列（狀態、租約、重試次數、程式版本）。三聲源封存完成時由 trigger 自動排入，並補排已完成但沒有結果的舊錄音。結果表加 `job_id`。 |
| `analysis/worker.py`（新） | 地端 worker：認領工作 → 逐段校驗 SHA256、段數、整檔 SHA256 → ffmpeg 解碼 → 另開程序跑 `analyze_multi_mic.py` → 寫回對齊紀錄與結果 |
| `deploy/analysis_worker_role.sql`（新） | 最小權限帳號 `analysis_worker`：只能讀音段、改工作狀態、新增結果 |
| `backend/catalog.py` | `GET /api/rooms/{code}/analysis` 多回傳 `jobs`（不含 worker 主機資訊） |
| `frontend/src/analysisStatus.ts`（新）、`App.tsx`、`app.css` | 分析頁顯示兩件事：<br>• 地端狀態：等待、分析中、重試中、完成、失敗；<br>• 對齊判定：未通過時明說「同步與相位數字不可使用」。<br>工作進行中每 15 秒自動重讀。 |
| 測試 | `analysis/tests/test_worker.py`（新，12 項）、`frontend/tests-unit/analysisStatus.test.ts`（新）、`frontend/tests/analysis-status.spec.ts`（新）、`recording.spec.ts`（錄完檢查分析頁顯示「等待地端分析」）、`backend/tests/test_catalog.py` |
| 文件 | `docs/analysis-worker.md`（新）；README、`docs/phone-test-v15.md` 的 migration 清單加入 004；`analysis/README.md`、`requirements.txt` |

### 新增：對齊判定

worker 會檢查模型「對齊後重量一次」的殘差：
- 每一對的殘餘偏移 ≤ 2 取樣點，且殘餘漂移 ≤ 5 ppm，才算已驗證。
- 否則結果標成未驗證，並列出原因。

加這個判定的原因：你資料庫裡唯一一場完成的錄音（房號 ZGPPKJ），模型算出 −2000 ppm 與 −3000 ppm 這種不可能的漂移。
- 三軌都是固定 −14.3 dB、峰值 1.46、每 500 ms 重複，判斷是 Chrome 測試音源（Playwright 用的假麥克風），不是真實收音。
- 週期性訊號會讓對齊鎖在週期的倍數上，所以數字沒有意義。
- 現在這筆結果會標成「未驗證：B 殘餘偏移 −71.88 取樣點；C 對齊後無法重新量測」。

## 三、驗證證據（本機實際執行）

測試環境：
- 本機另建 conda 環境 `pg_test`（PostgreSQL 18.6，只監聽 127.0.0.1:55433，資料在暫存資料夾），沒有動到任何既有資料庫。
- `audio_preject` 環境新增 `psycopg` 3.3.2（conda，只新增 2 個套件）。

| 檢查 | 結果 |
|---|---|
| 你的資料庫備份還原到測試庫，套用 004 與帳號腳本 | 成功；ZGPPKJ 自動補排 1 筆工作 |
| 以 `analysis_worker` 帳號跑 worker 處理 ZGPPKJ | 完成。下載 3 軌 25 段、SHA256 全對、解碼、分析、寫回，約 30 秒；判定為未驗證（原因見上）；結果 JSON 不含 worker 主機資訊 |
| 同一場錄音重跑 | 新增一筆結果，舊結果保留 |
| `analysis/tests/test_worker.py` | **12/12 通過**。每項各建新資料庫，以最小權限帳號執行，涵蓋：<br>• 重跑帳號腳本會收回過去給過的敏感欄位權限；<br>• 完成才排入、不重複；<br>• 後端帳號沒有工作表權限時，完成錄音仍能排入；<br>• 合成三軌經 Opus 編碼走完整流程：B 偏移誤差 < 2 取樣點，C 漂移 25 ± 3 ppm，判定已驗證；<br>• worker 帳號不能新增工作、刪音段、讀 token_hash；<br>• 壞段重試 3 次後失敗，且不寫結果；<br>• 兩台 worker 搶同一筆，只有一台拿到；<br>• 租約過期可被接手，舊 worker 寫不進去；<br>• 同一個 worker_id 的舊嘗試改不到新嘗試；<br>• 失去租約時分析子程序在 1 秒內被終止；<br>• 錯誤訊息遮掉路徑；<br>• 判定的各種缺漏情況 |
| `analysis/tests/test_synthetic.py` | 5/5 通過（模型本身未改） |
| 前端 `npm run test:unit` | 12/12 通過 |
| `npm run build`（含 tsc）、`npm run build:pages` | 通過 |
| `tests/analysis-status.spec.ts`（Chrome，390 px 寬） | 2/2 通過：狀態與判定文字正確、不水平捲動、工作完成後自動更新且停止重讀 |
| `tests/audio-contract.spec.ts` | 通過 |
| 後端 `test_api.py`、`test_catalog.py`（套用最終版 004） | 4/4 通過；經真實後端流程完成的錄音恰好排入 1 筆工作 |
| Codex 跨引擎審查（gpt-6-astra，唯讀） | 第一輪 FAIL → 修正 → 第二輪 **PASS**（無 P0/P1），細節見下方「Codex 審查」 |

### 這台電腦上沒有全綠的測試（已比對原始程式，非本次造成）

這台電腦的 PostgreSQL 每次開新連線要 0.5 到 2 秒，後端的連線上限是 5 秒，偶爾會超過：
- **後端 `backend/tests`**：新程式 11/12、原始程式（HEAD 5200735）也是 11/12，每次失敗的是不同的測試，都是連線逾時。失敗的那項單獨重跑會通過，其中包含會觸發新 trigger 的三手機完整流程。
- **`recording.spec.ts`、`recovery.spec.ts`**：新程式與原始程式**失敗在相同的 5 項、相同的步驟**（等「伺服器已連線」或「開始統一錄音」可按）。所以 `recording.spec.ts` 新加的分析頁檢查，在這台電腦上沒能跑到。

請在你的電腦上照第四節跑一次。v15 驗證紀錄顯示，你的環境這些測試是全過的。

### Codex 審查

第一輪指出、已修正的問題：
1. 同一個 worker_id 重用時，舊嘗試可能把新嘗試的工作改回 queued，造成工作永遠卡住。→ 所有寫入都要比對認領時的 attempts。
2. 結果 JSON 帶有 worker 主機名稱；錯誤訊息可能帶地端路徑。→ 移除主機名稱，錯誤訊息遮掉路徑。
3. 對齊判定在欄位缺漏時會丟例外；兩軌也顯示「三軌已驗證」；少一對時不會失敗。→ 依實際聲源檢查，並顯示實際軌數。
4. 重疊的嘗試共用輸出資料夾；失去租約後分析仍繼續跑。→ 每次嘗試各自資料夾，失去租約時立刻終止子程序。
5. trigger 以呼叫者權限執行，後端帳號沒有權限時會讓「錄音完成」整筆失敗。→ 改成 `SECURITY DEFINER`。
6. 其他：
   - worker 帳號權限過寬 → 改成只開必要欄位；
   - 沒有資料庫等待上限 → 加 statement_timeout 與 lock_timeout；
   - 分析頁不會自動更新 → 工作進行中每 15 秒重讀。

第二輪結果：**VERDICT: PASS**，P0、P1 都沒有。另提兩個 P2：
- 含空白的路徑只被遮掉一部分。→ 已修：訊息裡只要有像路徑的內容，就整段不回報，只留例外類型。
- 重跑帳號腳本收不回過去給過的欄位權限。→ 實測不成立：先授予 `SELECT(token_hash)`，重跑腳本後權限是 false。PostgreSQL 收回表權限時會連同欄位權限一起收回。仍補成回歸測試。

## 四、你審閱時可以這樣測

```powershell
# 1. 測試資料庫（不要用正式庫）依序套用 001–004，再建 worker 帳號
psql -X -v ON_ERROR_STOP=1 -d '<測試庫>' -f backend/migrations/004_analysis_jobs.sql
psql -X -v ON_ERROR_STOP=1 -d '<測試庫>' -f deploy/analysis_worker_role.sql

# 2. worker 整合測試（需要能建立資料庫的測試帳號）
$env:WORKER_TEST_ADMIN_URL = 'postgresql://<測試管理帳號>@127.0.0.1:<port>/postgres'
python -X utf8 analysis/tests/test_worker.py

# 3. 後端與前端
./scripts/test-backend.ps1 -TestDatabaseUrl '<測試庫>'
cd frontend; npm run test:unit; npm run build; npx playwright test
```

實機流程：三支手機錄完之後到「分析結果」頁，應該會看到「等待地端分析」。接著在地端電腦執行一次：

```powershell
$env:ANALYSIS_DATABASE_URL = '<worker 帳號連線>'
python -X utf8 analysis/worker.py --work-dir D:\cnc_analysis --once
```

重新整理頁面後，應該看到「地端分析完成」與對齊判定。

## 五、下一步（建議順序）

1. **你決定部署位置**：雲端資料庫放在哪裡，以及能否只對地端電腦的 IP 開放 TLS 連線。worker 只需要對外連線，地端不必開放任何入站連線。
2. **實機錄一次三手機**：真實機台或安靜房間，開頭與結尾各按一次嗶聲，開機前先錄 10 秒空白。用這次的 worker 跑，確認對齊能通過驗證。這也是 v1 的第 1 步，仍未完成。
3. **圖回到網頁**：新增 `analysis_figures`（縮小後的 PNG）與讀圖端點，分析頁直接顯示同步、相位、去背景的圖。
4. **模型分段改寫**：記憶體固定在約 1 GB 以內（估計，改完要實測）。地端電腦 25 GB，目前大約可處理 8 分鐘以內的錄音。
5. v1 仍待辦：
   - 後端保存收音設定（migration 005）；
   - 錄音中標記（正常／異常），需要你決定標記清單；
   - 分析 v2，四種熱力圖改讀房間的加工條件。
