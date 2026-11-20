# 測試用的資料庫定義

`test_track_publish.py` 用這兩個檔建立測試資料庫，套用順序：

1. `CNC_Acoustic_Lab_DB_v1_2/01_schema_complete.sql`（public V1.2）
2. `backend/migrations/001`–`003`
3. `site_004_multi_recorder.sql`
4. `site_005_track_analysis.sql`
5. `deploy/track_analysis_writer_role.sql`

## 來源

這兩個檔是網站那邊的正式 migration（規格裡的 `backend/migrations/004_multi_recorder.sql`、`005_track_analysis.sql`），2026-11-20 取得。
放在這裡只給測試用，不是這個儲存庫的 migration；`backend/migrations/` 裡的 `004_analysis_jobs.sql` 是另一條線，編號相同但內容無關。

| 檔案 | SHA-256 | 和收到的檔案相比 |
|---|---|---|
| `site_004_multi_recorder.sql` | `65f9a71df28e91395a3eb877e65f7de9a141c93786be79b13be463ac014aae10` | 第 11 行開頭少了兩個字元，其餘逐位元相同 |
| `site_005_track_analysis.sql` | `e6ee63b0af9179811ad17e718b8c42a5fa1847951935a62e3c7b6e6517100a4b` | 逐位元相同 |

收到的 `004_multi_recorder.sql`（SHA-256 `98edb61773e1c6ac71b1dc3122a5d644baa9a4effb3ed370b2e4504b604187cb`）第 11 行開頭多了兩個注音聲調符號
`ˊ˙`（U+02CA、U+02D9），PostgreSQL 18 套用時在這一行報語法錯誤。拿掉這兩個字元之後，004 和 005 都能在 public V1.2 加 001–003 上套用成功。
這兩個字元是原檔就有，還是傳檔過程中混進去的，還沒有確認。

網站的 `backend/analysis.py` 和 `backend/analysis_signal.py` 沒有放進這個儲存庫。`test_track_reference.py` 用環境變數
`SITE_ANALYSIS_SIGNAL_PY` 指到本機的 `analysis_signal.py` 來比對數值；`test_track_publish.py` 裡以 `SITE_` 開頭的 SQL 是從 `analysis.py` 照抄的查詢。
