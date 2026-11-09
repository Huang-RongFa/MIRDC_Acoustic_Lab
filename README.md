# CNC Acoustic Lab V1.5

保留 V1.4 HTML 視覺的 React + TypeScript、FastAPI/WebSocket、PostgreSQL 三手機加工聲學蒐集專案。

- [公開設計成果](https://huang-rongfa.github.io/MIRDC_Acoustic_Lab/)：GitHub Pages 靜態前端，沒有「介面預覽」標籤；顯示真實的未連線狀態，不冒充錄音成功。
- `frontend/`：五頁前端、真實麥克風波形、MediaRecorder 分段、IndexedDB 保存與補傳。
- `backend/`：具房間憑證、主控權限、三人準備 barrier、後端倒數、音訊完整性檢查的可執行程式。
- `backend/migrations/001_mobile_capture.sql`：新增 `mobile_capture` schema；不刪除或重寫 V1.2 的 28 張資料表。
- [三手機 HTTPS／SQL 完整驗收步驟](docs/phone-test-v15.md)、[本次 V1.5 驗證](docs/verification-v15.md)。
- [API 與 WebSocket](docs/api.md)、[SQL 與模組設計](docs/architecture.md)、[驗證紀錄](docs/verification.md)。

## 本機執行

需求：Node.js 22.12+、Python 3.12、PostgreSQL 14+。本工作區已建立 `.venv` 與 `frontend/node_modules`。不要將錄音、憑證、資料庫目錄或環境設定提交 Git。

新電腦先選定 Python 執行檔，再建立專案環境：

```powershell
& '你的 Python 3.12 執行檔完整路徑' -m venv .venv
& ./.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
npm.cmd --prefix frontend ci
```

僅依序執行尚未套用的 migration；003 不可重複執行。在**新建的開發資料庫**套用 migration；既有 V1.2 資料庫只套用手機 migration，不重跑全量 V1.2 建表：

```powershell
psql -X -v ON_ERROR_STOP=1 -d '<你的 PostgreSQL 開發連線>' -f backend/migrations/001_mobile_capture.sql
psql -X -v ON_ERROR_STOP=1 -d '<你的 PostgreSQL 開發連線>' -f backend/migrations/002_room_lifecycle.sql
psql -X -v ON_ERROR_STOP=1 -d '<你的 PostgreSQL 開發連線>' -f backend/migrations/003_recording_metadata.sql
./scripts/run-backend.ps1 -DatabaseUrl '<你的 PostgreSQL 開發連線>'
# 第二個終端
npm.cmd --prefix frontend run dev
```

開啟 `http://localhost:5173`。FastAPI OpenAPI 文件在 `http://127.0.0.1:8000/docs`。Vite 代理 `/api` 與 WebSocket 至後端；開發時維持兩個終端執行。

此工作區建立的隔離測試叢集位於 `tmp/pg-test`，僅監聽 `127.0.0.1:55432`：`cnc_lab` 用於本機展示；`cnc_lab_test` 用於自動測試。它使用本機信任驗證，不適合網路或正式環境。測試不連接原有資料庫。

```powershell
./scripts/run-backend.ps1 -DatabaseUrl 'postgresql://cnc_test@127.0.0.1:55432/cnc_lab'
./scripts/test-backend.ps1 -TestDatabaseUrl 'postgresql://cnc_test@127.0.0.1:55432/cnc_lab_test'
```

## 三支手機操作

1. 以受信任 HTTPS 開啟網站。主控建立房間，該手機就是聲源 A。
2. 主控填寫加工條件，分享房間連結；另外兩支手機分別加入 B、C。
3. 三支手機各自授權麥克風，確認實際波形，按「我已就緒」。
4. 主控在 3/3 就緒後開始，裝置準備回覆後統一倒數；開始後不限時。
5. 主控停止，各裝置停止、補傳、封存。任何缺段或中斷都不會變成「全部成功」。
6. 「錄音測試結果」顯示三檔完整性、時長、試聽、原始波形與下載；「實驗紀錄」可重新選取舊房間。請保存原瀏覽器資料，清除網站資料會失去房間憑證與尚未補傳的本機音訊。

## HTTPS 與部署

GitHub Pages 不執行 Python、WebSocket 或 PostgreSQL。公開 Pages 現在只發布設計成果。正式三手機使用必須把完整前端與後端部署到同一個 HTTPS 網域，或設定受控反向代理；`/api/*` 與 WebSocket 均轉發至單一 Uvicorn worker，PostgreSQL 只提供給後端。手機以一般 LAN HTTP 位址開啟時通常不能授權麥克風。

後端以 PostgreSQL advisory lock 防止兩個控制程序同時持有相同資料庫。不要用多 worker，也不要在錄音中使用程式自動重載。服務重啟會把進行中的工作階段標為中斷，保存音訊分段供補傳。

```powershell
npm.cmd --prefix frontend run build        # 完整系統前端，需連接後端
npm.cmd --prefix frontend run build:pages  # GitHub Pages 靜態成果，輸出 pages-site/
```

瀏覽器測試使用已安裝的 Google Chrome 與瀏覽器測試音源，不會操作真實麥克風。先啟動後端與前端，再於另一終端提供靜態測試服務：

```powershell
cd frontend
npm.cmd exec vite preview -- --outDir ../pages-site --base /MIRDC_Acoustic_Lab/ --host 127.0.0.1 --port 4173
# 另一個終端，在 frontend 目錄
npm.cmd test
```

Pages 的 `/MIRDC_Acoustic_Lab/` base 已設定。發布時使用 `pages-site/index.html` 與 `pages-site/assets/`；不能誤發布完整系統模式後假裝已連接服務。Windows 原生 Rollup 被應用程式控制阻止，因此專案使用使用者核准的官方 Rollup WASM 版本；沒有停用系統安全設定。

## 尚待正式部署／硬體驗收

- 真實三手機、iOS Safari、手機鎖定／背景、長時間收音、儲存空間耗盡及不穩定行動網路尚需實測。
- 指令同步不等於樣本同步。已保存各機實際起點與時鐘觀測；跨手機樣本對齊演算法尚未實作。
- 分段與重建驗證保證位元組完整性；正式伺服器尚未內建音訊解碼器逐檔檢查。瀏覽器整合測試已對產生的三個 WebM 音檔實際解碼。
- 分析頁讀取真實後端結果；FFT/RMS/濾波、融合與模型工作程序尚未接上，沒有假分析數值。
- 設定目前為房間範圍的加工快照範本；跨房間的組織帳號、共用主檔管理與既有 V1.2 分析管線整合未完成。
- 網域、TLS 憑證、正式 PostgreSQL、備份及外部登入服務尚未部署。沒有對既有正式資料庫做 migration。
