# 地端外部分析：每聲道 Spectrogram／MFCC，寫回共用資料庫

依據：《CNC Acoustic Lab｜外部音訊分析系統對接規格》（2026-11-17）。本文說明地端程式怎麼對上那份規格，以及目前沒有驗證到的部分。

> **重要**：規格引用的網站原始碼（`backend/migrations/004_multi_recorder.sql`、`005_track_analysis.sql`、`backend/analysis.py`、`backend/analysis_signal.py`、`frontend/src/RecordingAnalysis.tsx`）不在這個儲存庫，也不在開發這支程式的電腦上。測試用的結果表是照規格文字重建的（`analysis/tests/fixtures/track_schema_RECONSTRUCTED_from_spec_20261117.sql`）。**這支程式還沒有對真實網站或真實資料庫跑過。**

## 整合方式

規格第 1 節給了兩種方式，這裡先做「共用 PostgreSQL」：地端程式直接讀輸入表、寫三張結果表。沒有新增任何 HTTP API，也沒有改網站的前後端。

```
網站（錄音、封存）──▶ PostgreSQL mobile_capture
                         ▲  ① 讀來源清單、音段（只 SELECT）
                         │  ② 一個交易寫入 recording_tracks、track_analysis_runs（最終狀態＋result）、
                         │     track_analysis_artifacts（PNG、矩陣）
              地端 worker（analysis/track_analysis/worker.py）
                         ▼
網站既有的 GET /api/v1/sessions/{id}/analysis 與 PNG API 讀到結果
```

## 與內建 worker 的工作歸屬（規格 7.1）

規格指出：內建 worker 會自動領取所有 queued 工作，網站重啟時會把 running 改回 queued，而且沒有 owner／lease 欄位。所以外部系統不能和它共用同一批工作。

這裡採用的做法是規格列的第三種（外部系統使用獨立工作管線，只發布完成品），發布管道暫時用資料庫：

- 地端**不建立 queued 或 running 的工作**。先在地端算完，再用一個交易把最終狀態（completed／partial／failed）、result、tracks、artifacts 一次寫入。內建 worker 從頭到尾看不到可以領取的列，網站重啟也不會把外部工作改回 queued。
- fingerprint 一律以 `ext:mirdc-onprem:` 開頭，不會和內建分析的 fingerprint 相同，也不會覆寫內建的結果。
- 內建的工作列（不論狀態）地端一律不碰。

這個做法的後果要先知道：

- 同一個 session 可能同時有內建結果和外部結果。規格 5.2 說查詢 API 回傳「相同時間條件下最新建立的工作」，所以畫面顯示哪一個，取決於哪一筆比較晚建立。
- 若要由外部系統完全接管，仍需要網站那邊停用內建分析（規格 7.1 第一種），這裡沒有做，也做不了。

## 對應規格的做法

| 規格 | 地端的做法 | 程式 |
|---|---|---|
| 4.1 來源清單 | 照規格的 SQL，LEFT JOIN 保留未封存的裝置 | `source.py` `SOURCES_SQL` |
| 4.2 重建原始檔 | 伺服器端游標逐段串流寫到暫存檔；驗證索引從 0 連續、每段 SHA-256、分段數、總位元組數、整檔 SHA-256 | `source.py` `rebuild_asset` |
| 4.2、5.1 以解碼為準 | ffmpeg 解碼成 wav，不改取樣率與聲道數；取樣率、聲道數、frames 都取解碼結果。只接受 1 或 2 聲道、44100 或 48000 Hz | `source.py` `decode_to_wav` |
| 第 3 節 track_id | `uuid5(NAMESPACE_URL, 'cnc:{session}:{participant}:{channel}')`；資料庫已有同一音軌時沿用既有 ID | `publish.py` `track_uuid`、`existing_track_ids` |
| 6.1 recording_tracks | 只替成功解碼的聲道建列。Mono 一列（index 0）；Stereo 兩列（Left 0、Right 1）。不複製、不平均 | `worker.py` |
| 6.2 track_analysis_runs | `run_id = uuid5('cnc-ext-run:{session}:{fingerprint}')`，同一批輸入重試得到同一個 ID | `publish.py` `run_uuid` |
| 6.2 fingerprint | 來源（裝置＋checksum，含未封存的）、區間、演算法版本與全部參數的 SHA-256 | `publish.py` `make_fingerprint` |
| 6.3 artifacts | spectrogram、mfcc 是 PNG 位元組；matrices 是 `np.savez_compressed`，鍵為 spectrogram、mfcc、times、valid_range | `render.py` |
| 6.4 result JSON | 依範例的欄位，另外加上 valid_range、interrupted、spectrogram_color_range | `worker.py` `analyse_session` |
| 6.4 失敗處理 | 來源未封存、驗證不過、無法解碼、解碼逾時、解碼程式起不來 → 寫進 `source_errors`，其他來源照常處理。區間內資料不足 → 音軌 `no_data`、附 error、圖 URL 為 null。部分成功 → partial；沒有任何成功音軌 → failed。**資料庫連線或查詢本身出錯不算來源失敗**：整個 session 這次不發布任何結果 | `worker.py`、`source.py` |
| 7.4、7.5 交易 | 一個交易，任何一步失敗整筆回復；連線若是 autocommit 模式會直接拒絕。寫入前檢查：result 的 run／session／狀態與要寫的列一致；要寫入的音軌和 result.tracks 必須是同一組；狀態必須和內容相符；每個成功音軌的兩個圖 URL 都有對應的 PNG；沒有成功的音軌不能有任何 artifact。寫入後檢查 artifact 的音軌與工作屬於同一個 session | `publish.py` `publish` |
| 7.6 重試 | 同一批輸入（同一個 fingerprint）已有結果時，**不加 `--force` 一律不重算、不覆寫**，不論既有結果是 completed、partial 還是 failed，也不論新的結果會不會比較好。`--force` 才會重算並取代那一筆（同一個 run_id，鍵相同，不會多出一筆工作）。兩個 worker 同時跑同一個 session 時，只有先提交的那一個會寫入，另一個什麼都不寫 | `worker.py`、`publish.py` `RUN_INSERT`／`RUN_FORCE_UPSERT` |
| 7.7 晚到的裝置 | 來源集合改變 → fingerprint 改變 → `--pending` 會再排一次完整分析，是新的一筆；舊的 partial 保留 | `worker.py` `pending_sessions` |
| 第 8 節參數 | FFT 2048、hop 441、periodic Hann、center=False、只算完整窗；振幅與 dB 定義、Mel 64（HTK、單位峰值）、MFCC C0–C19（DCT-II orthonormal）、48000→44100 polyphase 147/160 | `signal_contract.py` |
| 第 8 節色階與時間軸 | Spectrogram 固定 −120～0 dBFS；MFCC 用同一 run 所有成功音軌的 min/max；所有圖共用同一個顯示區間 | `worker.py`、`render.py` |
| 第 10 節權限 | 帳號 `track_analysis_writer`：輸入表只開程式實際用到的欄位的 SELECT；三張結果表 SELECT／INSERT／UPDATE；在 `mobile_capture` 沒有 DELETE、不能建表或改表。腳本只處理 `mobile_capture`：這個帳號在其他 schema 原有的權限、以及資料庫預設讓所有帳號建立暫存表的權限，腳本不會收回，只在執行結束時列出來提醒 | `deploy/track_analysis_writer_role.sql` |

## 規格沒有講清楚、這裡自己決定的地方

實際對接前要和網站那邊確認，這些都可能和內建實作不同：

1. **`times` 的定義**：每個分析窗的起點時間（`k × hop / 44100`，加上區間起點）。規格只說是「時間秒數」。
2. **`valid_range`**：第一個窗的起點到最後一個窗的終點。
3. **矩陣檔的 `spectrogram`**：存 dBFS 數值（和圖上的顏色同一個量）。規格只說是數值矩陣，沒說是振幅還是 dB。
4. **區間的切法**：先重取樣到 44100，再取 `[round(start×44100), round(end×44100))`。
5. **`recording_tracks.analysis_status`**：只有整段分析（start=0、end 省略）會更新它；區間分析不會把整段的摘要改掉。
6. **矩陣檔的大小**：預設（`--matrices auto`）有兩道門檻：未壓縮的頻譜矩陣超過 512 MB 就直接不做（約 20 分鐘以上的單一聲道）；做出來之後，壓縮後超過 64 MB 也不寫進資料庫。沒寫入時會在該音軌的結果裡註明。10 分鐘的單聲道矩陣未壓縮約 250 MB。`--matrices always` 一律寫入，`never` 一律不寫。
7. **`--pending` 處理哪些 session**：狀態是 completed 或 interrupted、至少一個封存音檔、而且目前這批來源還沒有外部整段結果。finalizing 的不處理，等它結束。
8. **重試留下的舊圖**：帳號沒有 DELETE 權限。`--force` 重算後若成功音軌變少，舊的 artifact 會留在表裡，但 result 不會再引用它。
9. **PNG 的外觀**：規格要求時間軸、頻率／係數軸、共用色階圖例，這裡都有；配色、字型、尺寸和內建的圖不會一樣。
10. **共用的 `recording_tracks`**：這張表不分內建或外部。地端寫入時，已存在的音軌只會更新顯示名稱與整段摘要狀態，track_id 與格式欄位不動。
11. **`--pending` 不重試的情況**：同一批來源已有外部結果（即使是 partial 或 failed）就不再自動重跑；分析途中程式出錯的 session，在同一次執行裡不再重試，重新啟動後會再試。
12. **不覆寫的代價**（使用者 2026-11-20 決定採用這個規則）：暫時性錯誤造成的 partial 或 failed 不會自動被後來較好的結果取代，要手動加 `--force` 重跑。兩個 worker 同時跑時，留下來的是先成功提交到資料庫的那一筆，不一定是比較好的那一筆；實測中有來源失敗的那一個要算的比較少，通常先提交。所以建議同一時間只跑一個 worker。

## 怎麼跑

1. 資料庫管理者執行 `deploy/track_analysis_writer_role.sql`，再用 `\password track_analysis_writer` 設密碼。
2. 地端電腦（`audio_preject` 環境已有 numpy、scipy、soundfile、matplotlib、psycopg；ffmpeg 由 imageio-ffmpeg 提供）：

```powershell
$env:TRACK_ANALYSIS_DATABASE_URL = 'postgresql://track_analysis_writer@<資料庫主機>:5432/cnc_acoustic_lab?sslmode=require'
$env:PGPASSWORD = '<只放在這台電腦>'

# 先不寫資料庫，把結果存到資料夾檢查
python -X utf8 analysis/track_analysis/worker.py --session <session_id> --dry-run D:\cnc_track\try1

# 寫回資料庫
python -X utf8 analysis/track_analysis/worker.py --session <session_id>

# 指定區間
python -X utf8 analysis/track_analysis/worker.py --session <session_id> --start 10 --end 20

# 處理所有還沒有外部結果的 session（--once 處理完目前的清單就結束）
python -X utf8 analysis/track_analysis/worker.py --pending --once
```

規格第 2 節提醒：網站後端與資料庫預設只聽 localhost。地端電腦要連得到資料庫，需要部署負責人另外安排網路路由與允許來源。

## 測試

```powershell
python -X utf8 analysis/tests/test_track_signal.py          # 參數契約，不需要資料庫
$env:WORKER_TEST_ADMIN_URL = 'postgresql://<測試管理帳號>@127.0.0.1:<port>/postgres'
python -X utf8 analysis/tests/test_track_publish.py         # 每個測試建一個新資料庫，用最小權限帳號跑完整流程
```

## 還沒有驗證的

- 沒有對真實網站的資料庫跑過；結果表的欄位、NOT NULL、CHECK 是照規格重建的。拿到正式 migration 後要換掉 fixture 重跑。
- 沒有確認網站的查詢 API 與分析頁真的讀得到這裡寫入的 result 與圖（規格第 11 節最後幾項）。
- 沒有和內建分析的數值逐項比對（沒有 `analysis_signal.py`）。參數是照規格第 8 節實作的，但第 8 節沒有寫到的細節可能不同。
- 記憶體：一次只把一台裝置的音訊讀進記憶體，一次只算一個聲道。單一聲道的頻譜矩陣仍然隨錄音長度增加（10 分鐘約 0.5 GB），沒有設上限，也沒有用長錄音實測過。
- 兩個 worker 真的同時執行的情況：儲存庫裡的自動測試只用模擬（讓第二個 worker 略過「已有結果」的檢查）。真正的雙執行緒並行是用暫時的腳本實跑驗證的（我和 Codex 各做一次），沒有收進自動測試。
