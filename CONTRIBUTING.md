# CNC Acoustic Lab 開發與版本管理

Repository: https://github.com/Huang-RongFa/MIRDC_Acoustic_Lab

預設分支：`main`。

## 每個功能階段

1. 從最新的 `main` 建立獨立功能分支（例如 `codex/recording-api`）。
2. 使用 TDD：先建立失敗的行為測試，再實作並確認測試通過。
3. 使用專案設定的執行環境，執行相關測試與必要的建置檢查；記錄實際命令與結果。
4. 程式變更後執行 `graphify update .`，檢查並提交更新的知識圖譜。若工具不可用，明確記錄阻礙，不得宣稱已更新。
5. 同步更新 API、Schema 與相關開發文件。
6. 檢查 staged diff，確認未包含憑證、密碼、原始錄音、資料庫備份或本機環境。
7. 建立清楚的 Git commit，推送功能分支並開 Pull Request；經測試及審查後才合併至 `main`。

不得強制推送或覆蓋既有歷史。遠端有新提交時，先檢查並安全整合。

## 初始內容與驗證界線

目前提供 PostgreSQL Schema、資料字典、API 契約、驗證 SQL 與 Skills；網站前後端尚未包含在此初始結構中。

`CNC_Acoustic_Lab_DB_v1_2/09_static_validate.py` 是靜態一致性檢查，不代表 PostgreSQL 執行測試通過。資料庫行為驗證須使用獨立測試資料庫，不得直接套用到正式資料庫。

`.gitignore` 排除本機設定、密鑰、依賴、錄音與備份；SQL Schema、API 文件、測試及必要 Skills 保留版本管理。忽略規則不能取代提交前的內容檢查。
