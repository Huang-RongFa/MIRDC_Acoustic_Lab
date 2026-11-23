# Windows 啟動與 Schema 修復

## 根因與實際連線（2026-11-17）

原 backend.app 預設 localhost:55432/cnc_lab，只有 001 基礎手機表；run-backend.ps1 卻預設 localhost:5432/cnc_acoustic_lab，已具 001～004 欄位。使用者已選擇後者，本次統一 app 預設，DATABASE_URL／明確參數仍優先。localhost 與 127.0.0.1 的 PostgreSQL 驗證規則不同；保留原 localhost，不改 pg_hba 或密碼。

5432 資料庫缺 005：participant_recordings.requested_sample_rate／requested_channel_count，以及 recording_tracks、track_analysis_runs、track_analysis_artifacts。只修 leaving 仍無法啟動目前分析版。Vite 預設代理 127.0.0.1:8000 正確；ECONNREFUSED 是後端啟動失敗的結果。deploy/Caddyfile 的 8015 屬另一部署入口，不改它。

V1.2 public 初始化 SQL 僅用於新資料庫，不定義 mobile_capture.room_participants；不可重新執行完整建表來修復既有庫。001～005 定義現行手機擴充，沒有自動 Migration 或版本登記；原 lifespan 未先確認結構就更新狀態，導致只顯示第一個缺欄位。

leaving 是「正在退出但仍等待最後上傳」，revoked 是「憑證已撤銷」；兩者不同且無舊等效欄位。source_label 必須允許 NULL，供非錄音主控及退出後釋放位置。現有房間與成員主鍵／唯一索引足以支援此路徑，不新增布林索引。

## 修改

- backend/schema.py：列出執行期所有手機表必要欄位，檢查 public 機台／範本欄位及離開狀態型別；只讀 CLI，錯誤指出資料庫、port、缺欄位與修復文件，不顯示憑證。
- backend/app.py：使用選定預設庫；在任何啟動資料更新前檢查 Schema；保留必要中斷／撤權邏輯與單 worker advisory lock；finally 關閉背景工作；新增 `/api/health`。
- frontend/package.json：override 改為 `$rollup` 引用直接依賴規格，保留 WASM 與既有版本；npm install 驗證 lockfile。
- backend/migrations/006_participant_state_compat.sql：可重跑的針對性修復。新增缺少的 boolean flags，既有真值保留，NULL 補 false，設定 NOT NULL/default，允許 source_label NULL；錯誤型別中止，不強制轉型。不能代替漏套的 002～005。
- start-local.ps1：前置檢查 Python/npm/Vite/Schema/ports，兩個獨立 PowerShell 視窗，健康確認後啟動前端；不裝套件、不套 Migration、不殺占用程序。錯誤視窗保留。`-CheckOnly` 僅執行前置檢查。

## 目標資料庫執行計畫與風險

執行前先只讀稽核；使用者其後明確批准「Migration 與啟動，目前無錄音」，才執行以下計畫。日後仍須針對目標確認，不自動套用。

1. 確認 localhost:5432/cnc_acoustic_lab，安排無錄音時段，備份既有資料。
2. 已有 001～004，不重跑。檢查 005 確實未套用，再以 ON_ERROR_STOP 套用 005。
3. 006 可重跑；此目標庫已有 leaving/revoked，通常不改資料。它針對其他部分遷移庫的離開狀態修復，仍須先具備其餘 001～005。
4. 執行只讀 preflight；成功後啟動服務。啟動會將尚在 preparing/countdown/recording 的批次標為 interrupted、結束待退出的參與者，並清除 mic/ready，這是原有重啟恢復行為，故需確認沒有進行中錄音。

005 新增兩欄、三表與索引，不刪錄音、不重置加工參數；DDL 可能暫時鎖表，應於維護時段執行。005 原檔不是可重跑 Migration，僅用在已驗證未套用的庫。006 交易具 5 秒 lock_timeout／30 秒 statement_timeout；執行失敗整筆回滾。若資料型別或約束另有不一致，停止人工檢查，不用 IF NOT EXISTS 掩蓋型別問題。

```powershell
# 僅在核准目標與變更後執行；不要把含密碼 URL 寫入檔案
psql -X -v ON_ERROR_STOP=1 -d 'postgresql://postgres@localhost:5432/cnc_acoustic_lab' -f backend/migrations/005_track_analysis.sql
psql -X -v ON_ERROR_STOP=1 -d 'postgresql://postgres@localhost:5432/cnc_acoustic_lab' -f backend/migrations/006_participant_state_compat.sql
.\start-local.ps1 -CheckOnly
.\start-local.ps1
```

亦可用 `-DatabaseUrl` 或 DATABASE_URL 明確指定其他已準備好的開發庫。後端 http://127.0.0.1:8000、前端 http://localhost:5173。使用 --reload 僅限開發，錄音時不要編輯後端檔案。

## 驗證

已親自執行與觀察：

- 修正前 `npm install --dry-run --ignore-scripts --offline`：重現 EOVERRIDE；修正後在 frontend 執行 `npm install` 成功，23 packages audited、0 vulnerabilities，lockfile 沒有實質變更。npm 提示 esbuild install-script 尚未列入 allowScripts；未繞過核准，既有 esbuild 可正常建置。
- `npm --prefix frontend ls rollup vite`：Rollup WASM 4.68.0 由 Vite 7.3.7 共用；`npm --prefix frontend run build` 通過。
- `.venv/Scripts/python.exe -c "import backend.app"` 通過。
- 設定隔離 TEST_DATABASE_URL 與專案 libpq 路徑後，`pytest backend/tests -q --tb=short`：63 passed。最後新增缺欄位 Migration 測試後，`pytest backend/tests/test_startup.py -q --tb=short`：4 passed（與前述重疊 3 項，不相加宣稱 67）。驗證 missing leaving 精確報錯、Migration 重跑／缺欄修復／原資料保留、連續啟動健康檢查。只有既有 Starlette/httpx 棄用警告。
- `start-local.ps1 -CheckOnly`：Migration 前正確阻擋 5432 缺少 005 的庫，無啟動狀態寫入；隔離庫通過。
- `start-local.ps1 -DatabaseUrl 'postgresql://cnc_test@127.0.0.1:55432/cnc_lab_test'`：實際開兩個獨立視窗，8000 與 5173 代理健康皆 ok。
- `npm test -- stereo-live.spec.ts`：1 passed，經 5173 代理實測三錄音裝置加入、主控開始停止、WebM 上傳與試聽、1/2/1 聲道分析。離開／踢除等由後端回歸覆蓋。未在 5432 庫寫入測試錄音。
- PowerShell parser：start-local.ps1 無語法錯誤；`git diff --check` 通過。
- `graphify update .` 成功；SQL extractor 缺 tree_sitter_sql，SQL 以實際 PostgreSQL 測試為準。

經使用者批准後：先以 pg_dump 備份至 Git 忽略的 `tmp/startup-repair-20261117-0952.dump`，確認 current_database/port 是 cnc_acoustic_lab/5432，套用 005、006。全部 38 張既有資料表筆數前後相同。只結束本次測試服務後，執行預設 start-local.ps1；Schema OK，Backend ready，前後端服務已啟動。既有 VS Code 的失敗 reloader 未終止；若仍開著，請在其原終端按 Ctrl+C，避免日後編輯觸發重複啟動。正式服務保留開啟，無部署／推送。

未驗證：實體三手機、iOS、長時間錄音。現有啟動恢復會更新 mic/ready 與中斷狀態；測試資料保留檢查是在 Migration 後、服務啟動前執行，不宣稱啟動不改任何狀態。
