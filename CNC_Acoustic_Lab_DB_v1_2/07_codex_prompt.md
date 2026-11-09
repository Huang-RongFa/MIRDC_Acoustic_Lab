# 貼給 Codex 的完整指令｜CNC Acoustic Lab 建立全新 SQL 資料庫

請在目前的 CNC Acoustic Lab 專案中完成 **全新 PostgreSQL 資料庫建立、結構驗證及三通道錄音的資料一致性測試**。

我已提供 `CNC_Acoustic_Lab_DB_v1_2.zip`（或同名解壓縮資料夾）。請先讀取其中所有 SQL 和 README，**以其內容為唯一建庫來源**。不要自行沿用先前 V1.0/V1.1 的遷移程式，也不要省略已定義的音訊蒐集欄位。

## 任務一：確認環境與檔案

1. 檢查目前專案路徑、PostgreSQL 版本（建議 14+）、`psql` 是否可用，以及目前連線目標是哪一個資料庫。
2. 確認 `00_create_database.sql`、`01_schema_complete.sql`、`02_column_comments.sql`、`03_data_dictionary.csv`、`04_data_dictionary.md`、`05_validation_queries.sql` 都存在且可讀。
3. 讀取 `06_manifest.json`，確認規格預期為 **28 張資料表、423 個欄位**。
4. 若 `tdd`、`graphify` Skill 已安裝，優先使用；若未安裝，先回報狀況，不要自行建立假的 Skill。

## 任務二：建立資料庫（不可破壞既有資料）

1. 先確認 `cnc_acoustic_lab` 是否已存在：如果已存在且含資料，**不得重建、清空或覆蓋**，改在獨立的測試資料庫上執行驗證，並回報。
2. 若目標確定是全新資料庫且授權帳號具備 CREATEDB 權限，在 PostgreSQL 既有維護資料庫 `postgres` 執行：

   ```bash
   psql -X -v ON_ERROR_STOP=1 -U postgres -d postgres -f 00_create_database.sql
   ```

3. 切換到新建立的 `cnc_acoustic_lab`，依序執行：

   ```bash
   psql -X -v ON_ERROR_STOP=1 -U postgres -d cnc_acoustic_lab -f 01_schema_complete.sql
   psql -X -v ON_ERROR_STOP=1 -U postgres -d cnc_acoustic_lab -f 02_column_comments.sql
   psql -X -v ON_ERROR_STOP=1 -U postgres -d cnc_acoustic_lab -f 05_validation_queries.sql
   ```

4. `CREATE DATABASE` **不可放入 BEGIN/COMMIT**。嚴禁把密碼直接寫到 SQL、程式碼或 Git。若缺少 PostgreSQL，優先在隔離測試容器（例如 Docker Compose）建立暫時資料庫；不要自行更動已有服務設定。
5. 若執行 SQL 出現錯誤，請修正結構上的問題、建立測試驗證後再重試；不可只用靜態文字搜尋就宣稱 SQL 已成功部署。

## 任務三：TDD 驗收案例

使用 TDD 先撰寫測試、再確認實際通過，至少驗證：

1. 28 張表及 423 個欄位全部建立成功，所有主鍵／外鍵／UNIQUE／CHECK／索引可用。
2. 3–5 個研究人員可以各自建立不同 CNC 的實驗與 Session，資料不混淆。
3. 實驗可有多組加工條件及重複試驗，Session 正確綁定 CNC、材料、工件實體、實體刀具、刀具裝夾與工件夾持。
4. 同一錄音 Session 只允許三個獨立聲道，1=A、2=B、3=C，且開錄前必須全部存在；少聲道或重複麥克風不得開錄。
5. 三通道交錯 PCM `BYTEA` 能按 `chunk_index`／`first_frame` 分段寫入；實際內容大小符合 `frame_count * 3 * bytes_per_sample`。
6. 區塊重傳冪等：同一 `chunk_index` + 相同內容可以安全回應成功；資料不一致必須拒絕，不能偷偷覆寫原始音訊。
7. 遺失、重疊、跳號、SHA256 不相符的音訊區塊必須被阻止標記為 completed。
8. 每次完成錄音有原始三通道 WAV/FLAC 的索引、雜湊及音訊品質檢查結果。
9. 一台 capture device 同時只能分配一筆準備／錄音／封存中的 Session，並測試中斷或失敗後釋放設備鎖。
10. 若設備在真正開始採樣前失敗，即使沒有 capture_clock_id，也可合法標記 failed。
11. `machining_presets` 更新不能改寫既有 `recording_sessions` 快照；Session 錄音開始後的加工資訊需保護不可任意覆寫。
12. `channel_features`、`fusion_results`、`model_predictions`、`verified_labels` 分離，正常／異常不可當成錄音前使用者輸入的工況。
13. 所有外鍵對錯誤的機台／刀具裝夾、材料／工件及麥克風校正對應應拒絕。

## 任務四：與手機錄音流程對應

確認資料模型可支援：

手機選擇機台／材料／刀具／加工參數 → 建立 Session（prepared）→ 建立 A/B/C 三個錄音聲道與 XYZ 位置 → 手機按開始 → 錄音主機確認共同採樣時鐘 → 同步錄製三通道 → 約每秒自動上傳三通道 PCM 區塊 → 資料完整性驗證 → 封存原始音檔 → Python 前處理／特徵融合 → 分析結果頁顯示。

請遵守：**手機前端不直接連 PostgreSQL、不提供「手動送 SQL」按鈕，後端才負責錄音儲存和計算。**

## 任務五：Graphify 系統圖譜

若已安裝 Graphify，在 SQL 驗證完成後更新系統知識圖譜，至少包含：

使用者 → 實驗群組 → 加工條件 → CNC／材料／刀具／裝夾 → Session → 三支麥克風／三路聲道 → PCM Chunk／原始音檔 → 品質檢查 → Python 前處理 → 特徵融合 → AI 推論／獨立驗證標籤。

若 Skill 不支援建立圖譜或不存在，請輸出 Mermaid ER Diagram 作為替代，並清楚標示未完成項目。

## 最終請交付

- 建庫執行結果、PostgreSQL 版本、DB 名稱、28 張表和 423 欄是否一致。
- 測試案例、通過／失敗結果與證據，未執行的項目不得標示成功。
- 必須修正的 SQL 或 API 約束問題。
- 重要外鍵路徑與手機錄音資料流程圖。
- 如有修改任何 SQL，提供具體 diff 及原因。

本次優先完成**新資料庫建立與驗證**，先不要擴大開發整個網站或 AI 模型。
