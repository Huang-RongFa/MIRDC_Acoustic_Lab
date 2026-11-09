# CNC Acoustic Lab｜PostgreSQL 全新資料庫建立規格 V1.2

**用途：** CNC 加工聲學研究系統。手機是操作前端，3 支麥克風透過共用採樣時鐘的多通道錄音介面，同時擷取 A/B/C 三路聲音。後端 API 自動接收三通道 PCM 區塊、寫入 PostgreSQL，再由 Python 做特徵擷取與三聲源融合。

**適用：** 全新 PostgreSQL 14+ 資料庫。**不適用**直接覆蓋已部署的舊資料庫。**SQL 尚未在 PostgreSQL 實際執行驗證**，請由 Codex 在測試 PostgreSQL 執行後再上線。

## 使用方式（依順序）

1. 安裝 PostgreSQL，先連入已有的 `postgres` 維護資料庫，使用有 `CREATEDB` 權限的帳號執行 `00_create_database.sql`。
2. 改連新建的 `cnc_acoustic_lab`，執行 `01_schema_complete.sql`。其內包含全部 28 張表的建立、新增欄位、主鍵／外鍵／CHECK／UNIQUE／索引，並包在一次交易裡；不是舊庫遷移檔。
3. 選擇執行 `02_column_comments.sql`，將全部欄位的繁體中文說明加到資料庫。
4. 執行 `05_validation_queries.sql`，檢查資料表與錄音資料完整性。
5. 依 `07_codex_prompt.md` 讓 Codex 實際執行測試，並用 TDD 驗證錄音流程。

### Windows PowerShell / Linux Terminal

```bash
# 連到既有 maintenance DB 建立新庫：不得包在 BEGIN/COMMIT 中
psql -X -v ON_ERROR_STOP=1 -U postgres -d postgres -f 00_create_database.sql

# 連到新庫建立全部表及欄位
psql -X -v ON_ERROR_STOP=1 -U postgres -d cnc_acoustic_lab -f 01_schema_complete.sql

# 加入繁體中文欄位註解
psql -X -v ON_ERROR_STOP=1 -U postgres -d cnc_acoustic_lab -f 02_column_comments.sql

# 唯讀結構／錄音資料完整性檢查
psql -X -v ON_ERROR_STOP=1 -U postgres -d cnc_acoustic_lab -f 05_validation_queries.sql
```

若在 pgAdmin 執行，**先對 `postgres` 執行第一檔，然後在新的 `cnc_acoustic_lab` Query Tool 執行第二、三檔**。不要一次貼在一個交易裡執行。不要在 SQL 檔中寫入資料庫密碼，登入授權交由 DB 設定與環境變數管理。

## 本次產出

| 檔案 | 內容 |
|---|---|
| `00_create_database.sql` | 建立 UTF-8 的 `cnc_acoustic_lab` 資料庫 |
| `01_schema_complete.sql` | **28 張表、所有 423 個欄位**、索引、主鍵／外鍵／欄位限制；一份可執行的全量建表腳本 |
| `02_column_comments.sql` | 423 個欄位的繁體中文 `COMMENT ON COLUMN` |
| `03_data_dictionary.csv` | 423 個欄位、型別、是否必填、單位與用途，Excel 可讀 |
| `04_data_dictionary.md` | 逐張表完整欄位解釋 |
| `05_validation_queries.sql` | 資料表、A/B/C 聲道、PCM 區塊連續性及內容長度檢查 |
| `06_manifest.json` | 資料表／欄位數摘要 |
| `07_codex_prompt.md` | 可貼給 Codex 的一次建庫與驗證指令 |
| `08_api_contract.md` | 手機、錄音主機、FastAPI、SQL 的最小端點約定 |

## 主要資料流

```text
手機選實驗/條件/機台/材料/刀具/裝夾與錄音設定
  │
  ▼
FastAPI 建立 recording_sessions (prepared) + 3 筆 recording_channels
  │
  ▼
手機下達 start 指令 → recording_control_events
  │
  ▼
錄音主機確認 3 個麥克風共用同一採樣時鐘 → recording (capture_clock_id)
  │
  ├── A/B/C 交錯 PCM、相同 first_frame → audio_chunks.pcm_data (BYTEA)
  │
  └── 可選 CNC 控制器實際 RPM/進給 → machine_telemetry_samples
  │
  ▼
停止時檢查 SHA256、frame 連續性與聲道映射 → audio_quality_checks
  │
  ▼
封存原始三通道 WAV/FLAC → audio_assets
  │
  ▼
Python 前處理與 FFT/MFCC → analysis_runs + channel_features + analysis_artifacts
  │
  ▼
三聲源特徵融合 → fusion_results
  │
  ▼
可選模型推論 → model_predictions（預測）
  │
  └── 其他檢驗證據 → verified_labels（真實標籤）
```

## 加工條件的三層資料

- `machining_presets`：供手機選單的**可編輯**常用範本。
- `experiment_conditions`：研究中的**計畫條件組**（可含重複次數）。
- `recording_sessions`：錄音當下真正使用的加工參數**快照**，包含 `spindle_rpm`、`feed_mm_min`、`axial_depth_mm`、`radial_width_mm`、`feed_per_tooth_mm`、`cutting_speed_m_min`、`cutting_direction`、`toolpath_type`、`coolant_mode`、`nc_program_code`、`pass_no`、材料／刀具／工件實例與裝夾等。錄音開始後不得任意覆寫。

三個音訊來源是 `recording_channels.channel_no` 1=A、2=B、3=C，對應的麥克風位於 `microphones`，座標與方向是每次 Session 獨立的 XYZ/Yaw/Pitch 記錄。

## 資料庫負責什麼，不負責什麼？

- **SQL 負責：** 研究實驗、加工參數、三聲源硬體配置、實際音訊分段 `BYTEA`、音檔路徑、追溯、品質檢查與分析結果的資料保存。
- **FastAPI / 錄音主機負責：** 確認三支麥克風真的同步、回應開始／停止指令、斷線續傳、驗證收到全部 3 個通道、正確處理 Chunk 重試與唯一 Session，以及保證 DB 與音檔封存一致。
- **Python DSP/AI 負責：** 濾波、FFT／STFT、RMS、MFCC、聲學特徵融合與後續推論。不要讓 SQL 當 DSP 計算引擎。

## 尚未由 SQL 自動保證的條件（正式蒐集前必測）

1. 三個實體麥克風均接在同一共用採樣時鐘的裝置；手機直接錄音不一定能做到樣本級同步。
2. 每次開錄之前 A/B/C 三筆 `recording_channels` 已建立，而且指定校正、位置與輸入通道確實有效。
3. 硬體錄音輸出格式必須符合 Session 的採樣率、PCM 位元深度和通道數；不可以只因 `channel_count=3` 就宣稱同步。
4. `audio_chunks` 的 SHA256 要由後端實際計算驗證；SQL 的 CHECK 僅能限制位元組數及雜湊字串格式。
5. 收到網路重試的 Chunk 時，應在 transaction 內比較已存在的 `sha256_hex` 與 `first_frame`，**相同資料才視為冪等成功**，衝突資料必須拒絕。
6. `first_frame` 連續、Chunk index 連續且總 frame 數與封存的音訊一致，才能標示 `completed`。
7. 單台錄音設備的佔用鎖包括 `prepared`、`recording`、`finalizing`。若 Session 逾時，後端清理程序必須先變更狀態才能釋放唯一索引，僅設定 `device_lock_expires_at` 本身**不會自動解除 SQL 唯一鎖**。
8. SQL 的 `condition_snapshot` 是 JSONB，不會自動鎖定禁止 UPDATE；請在 FastAPI 權限規則或額外 immutable trigger 加以保護。
9. 未校正的麥克風資料可用數位 RMS／dBFS，不得直接當作絕對聲壓（Pa／dB SPL）。
10. 3–5 人使用仍必須透過 FastAPI 加登入認證、最小權限、API 防重送、防資料洩漏與備份。

## 資料格式的預設值（尚未實機確認）

| 項目 | 預設 | 備註 |
|---|---|---|
| 收音通道 | 3 | 同一台裝置、同一採樣時鐘 |
| 採樣率 | 48,000 Hz | 可由裝置實際支援值調整 |
| PCM | `pcm_s16le` | 亦允許 `pcm_s24le`，需實機確認硬體輸出 |
| 一次錄音目標 | 30 秒 | 可由手機調整 |
| 寫入 SQL | 約 1 秒一個交錯三聲道 Chunk | 實際分段大小取決於錄音服務 |
| 原始音檔 | 多通道 WAV／FLAC | 不覆寫 |

本版本保留原 V1.1 的全部 288 欄位，擴充後總共 423 欄、28 張表。V1.2 為新的資料庫結構草案，不是已安裝或已測試完成的生產環境。
