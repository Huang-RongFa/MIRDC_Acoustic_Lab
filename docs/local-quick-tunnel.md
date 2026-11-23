# 地端與 Quick Tunnel 錄音測試

使用完整系統前端、FastAPI、同一個 HTTP/WebSocket 入口；不使用 GitHub Pages 靜態模式。保留既有資料與未提交修改。

## 啟動

本工作區已建立專用測試環境：`tmp/pg-local-20261109`，只監聽 `127.0.0.1:55444`。操作庫為 `cnc_local`，自動測試庫為 `cnc_local_test`，使用者 `cnc_local`，僅回環信任驗證。已套用所需 SQL，請勿重跑。內含明確標示的 `LOCAL-TEST-01 / Local recording test device` 測試機台。

```powershell
# 直接執行：腳本會檢查並啟動尚未執行的本機網站與隔離資料庫
./scripts/run-quick-tunnel.ps1
```

腳本會先確認 `cloudflared` 和本機 API。若 API 尚未啟動，會檢查並啟動上述專用隔離資料庫，再於背景啟動本機網站並等待 API 就緒，之後才建立 Tunnel。網站已在執行時不會重複啟動。看到 HTTPS 網址後保持該視窗開啟。背景網站輸出記錄在 `tmp/run-local.out.log` 和 `tmp/run-local.err.log`。

若網站已在另一個 PowerShell 視窗啟動，但 Tunnel 尚未執行，可在新視窗再次執行同一指令；它會沿用現有網站。若看到「此資料庫已有錄音控制服務」，表示已經有另一個網站服務持有資料庫，請確認 `http://localhost:8015` 可開啟後，不要再啟動 `run-local.ps1`。

自動測試請用獨立資料庫：`./scripts/test-backend.ps1 -TestDatabaseUrl 'postgresql://cnc_local@127.0.0.1:55444/cnc_local_test'`。

需求：專案 `.venv`、`frontend/node_modules`、已套用 V1.2 主表與 migrations 001～004 的隔離 PostgreSQL 資料庫，以及 cloudflared。腳本不安裝依賴、不執行 migration、不覆寫環境設定檔。

```powershell
# 在專案根目錄，替換為已完成升級的隔離資料庫連線
./scripts/run-local.ps1 -DatabaseUrl 'postgresql://使用者@127.0.0.1:連接埠/資料庫'
```

開啟 http://localhost:8015。啟動會先檢查 TypeScript 並建置前端，再啟動單一後端程序；勿在錄音時重啟。已有建置時可加 `-SkipBuild`。資料庫需先啟動，機台需在「設定管理」登錄。

另一個終端執行：

```powershell
./scripts/run-quick-tunnel.ps1
```

將終端印出的 `https://….trycloudflare.com` 網址貼到電腦與手機。所有參與者使用同一網址；手機不要使用 localhost 或一般 LAN HTTP。Quick Tunnel 提供受信任 HTTPS，讓手機可申請麥克風權限，HTTP API 與 WSS 均走同一來源。

測試入口只監聽回環位址，刻意不採信代理 IP 標頭；cloudflared 以本機連線進入。因此此模式允許持有公開網址的人接觸測試應用，不適用於要求內網來源限制的正式部署。正式內網仍依 `v22-local.md` 使用 Caddy 與網段限制。

## 先測一台，再測多台

1. 首頁設定錄音人數為 1，勾選「此裝置也參與錄音」，按「建立新房間」。主控預設只管理，未勾選時需另一裝置加入。
2. 編輯加工條件，選擇已登錄機台並儲存；其他加工條件可選填。
3. 點「測試並授權麥克風」，允許權限，確認說話時波形變化，再按「我已就緒，等待主控」。
4. 按「開始統一錄音」，等待倒數後錄音數秒，再按「由主控者停止錄音」。
5. 等待「錄音儲存完成」，在結果頁試聽及下載原始音檔，再測下一批。
6. 多裝置時建立 2～5 人房間，分享同一 HTTPS 網址與房間碼，各裝置授權、就緒後由主控開始。

## 排查與結束

- Quick Tunnel 說本機 API 尚未就緒：確認 `cloudflared` 已安裝，從專案根目錄執行 `./scripts/run-quick-tunnel.ps1`；新版腳本會嘗試啟動本機服務並印出 HTTPS 網址。
- `此資料庫已有錄音控制服務`：表示服務已啟動或另一個服務程序仍持有資料庫。先開啟 `http://localhost:8015`；若正常，直接執行 Quick Tunnel，不要再執行 `run-local.ps1`。若網頁不可用，確認是否有另一個終端仍執行伺服器，先查看該終端錯誤。
- 網站需要關閉時，在執行網站的 PowerShell 視窗按 Ctrl+C；如視窗已關閉，先用 `Get-NetTCPConnection -State Listen -LocalPort 8015` 找出 PID，確認是本專案的 Python/Uvicorn 後再用 `Stop-Process -Id <PID>`。
- Tunnel 需要關閉時，在執行 `run-quick-tunnel.ps1` 的 PowerShell 視窗按 Ctrl+C。重新啟動後網址可能改變。
- 建房或機台 API 失敗：確認後端終端與資料庫版本；舊 `cnc_lab` 不一定已有 V2.2 結構。不要盲目重跑 migration。
- 麥克風不可用：使用 localhost 或 HTTPS；檢查網站權限與作業系統麥克風權限。
- 換 Tunnel 網址後房間身分不見：瀏覽器儲存依來源區分，請先在原網址完成補傳、下載。不要在錄音中關 Tunnel 或清除網站資料。
- 結束前停止錄音並確認封存，之後在 Tunnel 與伺服器終端各按 Ctrl+C。
- Quick Tunnel 是臨時測試網址，重啟可能換網址。官方說明：https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/

自動化使用 Chrome 模擬麥克風，不能取代真實手機、真實麥克風及背景/鎖屏驗收。

## 本次驗證（2026-11-09）

- `npm.cmd --prefix frontend run build`：TypeScript 與 Vite 建置通過。
- `./scripts/test-backend.ps1 -TestDatabaseUrl 'postgresql://cnc_local@127.0.0.1:55444/cnc_local_test'`：21 passed；有一則 Starlette TestClient 棄用警告。
- 設 `CNC_TEST_URL=http://localhost:8015` 後執行 `npm.cmd --prefix frontend test -- recording.spec.ts recovery.spec.ts`：6 passed，涵蓋三裝置錄音、斷線補傳、連續三批、權限拒絕與中斷恢復。首次因測試機台尚未成功寫入而失敗，補入機台後重跑全部通過。
- 設 `CNC_TEST_URL` 為當次 Quick Tunnel HTTPS 網址後執行 `npm.cmd --prefix frontend test -- recording.spec.ts --grep 'same browser'`：1 passed，實際經過 HTTPS/WSS 建房、錄製三批並解碼音檔；首頁 HTTP 200。
- 新增 PowerShell 腳本語法檢查與 `python -m py_compile backend/local.py` 通過。
- 已執行專案環境的 `python -m graphify update .`；SQL 抽取器未安裝，因此知識圖不涵蓋完整 SQL 結構。
- `git diff --check` 發現原有 `frontend/src/App.tsx:57` 尾端空白，未修改該既有工作區內容。
- 未執行實體手機與真實麥克風驗收，也未執行與此次錄音入口無關的 Pages 測試。
