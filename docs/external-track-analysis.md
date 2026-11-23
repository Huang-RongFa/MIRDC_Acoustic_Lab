# 地端外部分析：每聲道 Spectrogram／MFCC，寫回共用資料庫

依據：《CNC Acoustic Lab｜外部音訊分析系統對接規格》（2026-11-17）。本文說明地端程式怎麼對上那份規格，以及目前沒有驗證到的部分。

> **目前的驗證程度（2026-11-23 更新）**：網站的原始碼已經合併到 `main`（`backend/analysis.py`、`backend/analysis_signal.py`、`backend/migrations/004_multi_recorder.sql`、`005_track_analysis.sql`、`frontend/src/RecordingAnalysis.tsx`）。
> 測試資料庫現在用正式的資料表定義建立；數值和 `analysis_signal.py` 逐項比對過；網站查詢 API、PNG API、內建 worker 用的 SQL 也對著地端寫入的資料實際執行過。
> **還沒有做的**：對正式站的資料庫執行、在正式站的分析頁上看結果。正式站實際部署的版本、PyAV 版本、地端以 `track_analysis_writer` 連線寫入，都需要部署管理入口才能驗證。細節見文末「還沒有驗證的」。

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
| 4.1 來源清單 | 照規格的 SQL，LEFT JOIN 保留未封存的裝置；排序和內建分析相同（`source_position`、`participant_id`） | `source.py` `SOURCES_SQL` |
| 4.2 重建原始檔 | 伺服器端游標逐段串流寫到暫存檔；驗證索引從 0 連續、每段 SHA-256、分段數、總位元組數、整檔 SHA-256 | `source.py` `rebuild_asset` |
| 4.2、5.1 以解碼為準 | ffmpeg 解碼成 wav，不改取樣率與聲道數；取樣率、聲道數、frames 都取解碼結果。只接受 1 或 2 聲道。取樣率不限 44100／48000：和內建分析一樣，不是 44100 的重取樣到 44100；重取樣比例超過上限的除外（見下一節「取樣率的上限」） | `source.py` `decode_to_wav` |
| 第 3 節 track_id | `uuid5(NAMESPACE_URL, 'cnc:{session}:{participant}:{channel}')`；資料庫已有同一音軌時沿用既有 ID | `publish.py` `track_uuid`、`existing_track_ids` |
| 6.1 recording_tracks | 只替成功解碼的聲道建列。Mono 一列（index 0）；Stereo 兩列（Left 0、Right 1）。不複製、不平均 | `worker.py` |
| 6.2 track_analysis_runs | `run_id = uuid5('cnc-ext-run:{session}:{fingerprint}')`，同一批輸入重試得到同一個 ID | `publish.py` `run_uuid` |
| 6.2 fingerprint | 來源（裝置＋checksum，含未封存的）、區間、演算法版本與全部參數的 SHA-256 | `publish.py` `make_fingerprint` |
| 6.3 artifacts | spectrogram、mfcc 是 PNG 位元組；matrices 是 `np.savez_compressed`，鍵為 spectrogram、mfcc、times、valid_range | `render.py` |
| 6.4 result JSON | 內建分析寫的每一個欄位名稱都有；整批層級的 `time_range`、`duration_seconds`、`completed_device_count` 算法相同，`mfcc_color_range` 在所有聲道的圖都畫得出來時相同。內容不同的地方（`run_id`、`versions`、錯誤訊息、出圖失敗時的細節等）列在下一節。另外加上 interrupted、matrices_stored、spectrogram_color_range | `worker.py` `analyse_session`、`analyse_devices` |
| 6.4 失敗處理 | 來源未封存、驗證不過、無法解碼、解碼逾時、解碼程式起不來 → 寫進 `source_errors`，其他來源照常處理。取樣率太怪、重取樣代價過高的檔案也列為來源失敗。區間內資料不足 → 音軌 `no_data`、附 error、圖 URL 為 null。某個聲道計算或出圖時出錯 → 只有那個聲道標成 `failed`，它的圖和矩陣不寫入，其他聲道照常。部分成功 → partial；沒有任何成功音軌 → failed。**資料庫連線或查詢本身出錯不算來源失敗**：整個 session 這次不發布任何結果 | `worker.py`、`source.py` |
| 7.4、7.5 交易 | 一個交易，任何一步失敗整筆回復；連線若是 autocommit 模式會直接拒絕。寫入前檢查：result 的 run／session／狀態與要寫的列一致；要寫入的音軌和 result.tracks 必須是同一組；狀態必須和內容相符；每個成功音軌的兩個圖 URL 都有對應的 PNG；沒有成功的音軌不能有任何 artifact。寫入後檢查 artifact 的音軌與工作屬於同一個 session | `publish.py` `publish` |
| 7.6 重試 | 同一批輸入（同一個 fingerprint）已有結果時，**不加 `--force` 一律不重算、不覆寫**，不論既有結果是 completed、partial 還是 failed，也不論新的結果會不會比較好。`--force` 才會重算並取代那一筆（同一個 run_id，鍵相同，不會多出一筆工作）。兩個 worker 同時跑同一個 session 時，只有先提交的那一個會寫入，另一個什麼都不寫 | `worker.py`、`publish.py` `RUN_INSERT`／`RUN_FORCE_UPSERT` |
| 7.7 晚到的裝置 | 來源集合改變 → fingerprint 改變 → `--pending` 會再排一次完整分析，是新的一筆；舊的 partial 保留 | `worker.py` `pending_sessions` |
| 第 8 節參數 | FFT 2048、hop 441、periodic Hann、center=False、只算完整窗；振幅與 dB 定義、Mel 64（HTK、單位峰值）、MFCC C0–C19（DCT-II orthonormal）、polyphase 重取樣（48000→44100 即 147/160）。數值和內建分析逐項比對過 | `signal_contract.py` |
| 第 8 節色階與時間軸 | Spectrogram 固定 −120～0 dBFS；MFCC 用同一 run 所有成功音軌的 min/max；所有圖共用同一個顯示區間（有指定終點就到終點，否則到最長那一軌的結尾） | `worker.py`、`render.py` |
| 第 10 節權限 | 帳號 `track_analysis_writer`：輸入表只開程式實際用到的欄位的 SELECT；三張結果表 SELECT／INSERT／UPDATE；在 `mobile_capture` 沒有 DELETE、不能建表或改表。腳本只處理 `mobile_capture`：這個帳號在其他 schema 原有的權限、以及資料庫預設讓所有帳號建立暫存表的權限，腳本不會收回，只在執行結束時列出來提醒 | `deploy/track_analysis_writer_role.sql` |

## 和網站內建分析對照的結果

對照的版本：`backend/analysis_signal.py`（SHA-256 `9f59fff2…2bf689`，`algorithm_version` v1.4.1）與 `backend/analysis.py`，2026-11-20 取得。

### 已改成和內建分析相同的

先前規格沒寫清楚、我自己決定的幾項，對照原始碼後發現不同，已經改掉（地端的 `algorithm_version` 因此從 `mirdc-onprem-track-1` 換成 `-2`）：

| 項目 | 先前的做法 | 現在（和內建分析相同） |
|---|---|---|
| `times` | 每個窗的起點 | 每個窗的中心：`(first + k×441 + 1024) / 44100` |
| 區間端點 | `round(start×44100)`、`round(end×44100)` | `first = ceil(start×44100)`、`last = min(總長, floor(end×44100))` |
| `valid_range` | 由 `times` 推算 | `[first/44100, (first + (T−1)×441 + 2048)/44100]` |
| 可分析的取樣率 | 只有 44100、48000，其他當成來源失敗 | 其他取樣率也分析：`up/down = 44100/gcd : 取樣率/gcd`，FIR 長度 `128×max(up,down)+1`。地端另外有比例上限，見下面第 3 點 |
| 顯示名稱 `device_name` | 錄音者名稱 | `錄音位置 · 錄音者名稱`，例如 `A · 錄音者 A` |
| `time_range` | 到最後一個完整窗的結尾；沒有音軌時是 null | 有指定終點就到終點，否則到最長那一軌的結尾；沒有音軌時是 `[start, start+1]` |
| `duration_seconds`（整批） | 顯示區間的長度 | 最長那一軌的原始時長 |
| `completed_device_count` | 所有聲道都分析成功的裝置數 | 已完整封存的裝置數 |
| `mfcc_color_range` 沒有成功音軌時 | null | `[-1, 1]` |
| `parameters` | 多層結構 | 單層；內建分析的 16 個鍵同名同型別，後面是地端補充的說明 |
| 資料不足時的錯誤訊息 | 自訂文字 | 和內建分析同一句 |
| 某個聲道計算或出圖時出錯 | 整個 session 這次不發布 | 只有那個聲道標成 `failed`（訊息和內建相同），其他聲道照常發布 |
| 解碼成功的檔案後來讀不回來 | 那台的長度仍算進共用時間軸 | 那台改列來源失敗，共用時間軸只依實際有音軌的裝置決定 |

數值比對（`analysis/tests/test_track_reference.py`）：同一段樣本分別交給兩邊，4 種取樣率 × 5 種訊號 × 8 個區間，120 個有結果、40 個資料不足的案例。

- 重取樣輸出、`times`、`valid_range`：完全相同（差 0）。
- 有沒有結果（資料不足）的判斷：160 個案例全部一致。
- 轉成 float32 之前的頻譜與 MFCC：差距在 1e-9 以下。
- 存進矩陣檔的 float32 數值：頻譜最大差 3.8e-6 dB，MFCC 最大差 3.1e-5。這是 float32 的進位誤差。

### 和內建分析不同、刻意保留的

1. **解碼方式**：內建用 PyAV，地端用 ffmpeg 指令解成 32-bit float。2026-11-20 用 11 個檔案比對過（細節見更新紀錄第八節）：
   - Opus（WebM、Ogg，含兩個 Chrome 實際錄的檔案）與 WAV：長度相同、沒有位移；樣本最大差 9e-8（float32 最後一位），頻譜在 −90 dBFS 以上的頻點最大差 0.0005 dB。
   - 分段的 AAC／MP4：相同。
   - **非分段的 AAC／MP4：地端在結尾多解出 640～684 個樣本（約 14 毫秒，不到一個 AAC 編碼框）**，其餘樣本逐一相同。結果是該音軌的時長多約 0.015 秒、多 1 個分析窗。原因沒有確定：比對用的 PyAV 內含的 FFmpeg 比地端的 ffmpeg 7.1 新，也可能是指令列和函式庫的行為不同。
   - 比對用的 PyAV 是 19.0.2；**網站實際用哪一版不知道**，版本不同結果可能不同。
2. **來源檢查比較嚴**：內建只檢查總位元組數和整檔 SHA-256；地端另外檢查音段索引連續、每段 SHA-256、分段數。所以會有內建能分析、地端卻列為來源失敗的情況：某一段記錄的 SHA-256 和內容不符、或封存紀錄的分段數不對，但整檔的 SHA-256 與位元組數剛好正確。
3. **取樣率的上限**：內建沒有上限。地端在重取樣比例（`44100/gcd : 取樣率/gcd`）任一個數字超過 2048 時，把該來源列為失敗，例如 44099 Hz、1 Hz、2000003 Hz。8000～384000 Hz 的常見取樣率最大只到 1280，不受影響。沒有這個上限時，一個取樣率很怪的檔案會要求幾 GB 記憶體。
4. **`run_id` 與 `track_id`**：內建的 `run_id` 是隨機的；地端是由 session 和 fingerprint 算出來的固定值（重試不會多出一筆）。`track_id` 兩邊都用規格的 uuid5 規則，但資料庫若已有同一音軌、ID 卻不是照這個規則產生的列，地端照規格沿用它，內建則會自己算 uuid5 再寫入而撞到唯一鍵、該次工作失敗。內建和地端都只會產生 uuid5 的 ID，所以這只會發生在有第三個寫入者的時候。
5. **`versions`**：內建列出 numpy、scipy、av、matplotlib 的版本。地端沒有 av，列的是 numpy、scipy、matplotlib、soundfile，加上 `analysis_service`、`producer`。
6. **`mfcc_color_range` 的數值**：地端取的是 float32 矩陣的最小／最大值，內建取 float64，數字在小數第 5 位之後會不同（例如 −287.13785 對 −287.13783）。
7. **錯誤訊息的文字**：`source_errors` 的四個鍵相同，但缺檔、驗證失敗、解碼失敗的訊息文字和內建不同。
8. **session 沒有任何錄音者紀錄**：內建會寫一筆沒有音軌的 failed 結果；地端直接報錯，不寫入任何東西。
9. **矩陣檔的精度**：內建存 float64，地端存 float32（檔案約一半大）。鍵名和形狀相同。目前網站沒有讀取矩陣的 API。
10. **矩陣檔的大小上限**：內建一律寫入。地端預設（`--matrices auto`）有兩道門檻：未壓縮的頻譜矩陣超過 512 MB 就不做；壓縮後超過 64 MB 不寫進資料庫，並在該音軌的結果裡註明。`--matrices always` 一律寫入，`never` 一律不寫。
11. **圖的外觀**：尺寸相同，都是 960×480（分析頁的圖框固定 2:1）。其餘不同：內建是英文軸標、MFCC 用紅藍配色、把資料平均攤在 `valid_range` 上；地端有標題、中文軸標、MFCC 用 viridis、每個窗畫在它的中心位置、沒有資料的時間畫灰色。規格要求的時間軸、頻率／係數軸、共用色階圖例兩邊都有。
12. **`recording_tracks.analysis_status`**：內建每次分析（含區間）都會更新它；地端只有整段分析才更新，區間分析不會把整段的摘要改掉。地端另外會更新顯示名稱。
13. **同一批輸入已有結果時**：內建在主持人再按一次分析時，會把自己失敗的那一筆重新排入。地端不加 `--force` 一律不重算、不覆寫（使用者 2026-11-20 決定）。
14. **`source_position` 是空值時**：地端只顯示錄音者名稱；內建會顯示成 `None · 名稱`。004 已經替舊資料補上這個欄位，正常情況不會遇到。
15. **檔案中途改變取樣率或聲道數**：內建會拒絕；地端交給 ffmpeg 處理，沒有另外檢查。
16. **頻譜圖或矩陣產生失敗的聲道**：兩邊都把那個聲道標成 failed。但內建仍保留它的 `valid_range`，也把它的 MFCC 算進共用色階；地端不寫 `valid_range`，共用色階也不含它。只有 MFCC 圖失敗時兩邊相同。

### 其他自己決定的

1. **`--pending` 處理哪些 session**：狀態是 completed 或 interrupted、至少一個封存音檔、而且目前這批來源還沒有外部整段結果。finalizing 的不處理，等它結束。同一批來源已有外部結果（即使是 partial 或 failed）就不再自動重跑；分析途中程式出錯的 session，在同一次執行裡不再重試。
2. **重試留下的舊圖**：帳號沒有 DELETE 權限。`--force` 重算後若成功音軌變少，舊的 artifact 會留在表裡，但 result 不會再引用它。
3. **不覆寫的代價**：暫時性錯誤造成的 partial 或 failed 不會自動被後來較好的結果取代，要手動加 `--force` 重跑。兩個 worker 同時跑時，留下來的是先成功提交到資料庫的那一筆，不一定是比較好的那一筆。所以建議同一時間只跑一個 worker。

### 畫面會顯示哪一筆（由 `analysis.py` 確認）

查詢 API 取「同一個 session、同一個起訖時間、最晚建立」的那一筆，不分內建或外部。所以：

- 地端先寫入，之後主持人在網站按分析，而且內建對這批來源、這個區間還沒有工作：內建會另外建一筆（fingerprint 不同），比較晚，畫面改顯示內建的。
- 同上，但內建先前已經有同一批來源、同一個區間的工作：內建不會新建，沿用舊的那一筆（失敗的才重新排入），建立時間不變。畫面仍然顯示比較晚建立的地端結果。
- 內建先算完，之後地端第一次寫入（新的一筆）：畫面改顯示地端的。
- 兩筆的建立時間完全相同時，查詢沒有第二個排序條件，顯示哪一筆不確定。
- 地端用 `--force` 重算：更新的是原來那一筆，建立時間不變。如果中間已經有較晚的內建結果，畫面仍然顯示內建的。

內建 worker 只領 `status='queued'` 的列，地端從不寫這個狀態，所以領不到地端的工作；內建重新排入失敗工作時是用它自己的 fingerprint 找，也碰不到地端的列。這兩點有測試（`test_site_queries_read_the_external_result`）。

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
python -X utf8 analysis/tests/test_track_reference.py       # 和儲存庫裡的 backend/analysis_signal.py 比數值
$env:WORKER_TEST_ADMIN_URL = 'postgresql://<測試管理帳號>@127.0.0.1:<port>/postgres'
python -X utf8 analysis/tests/test_track_publish.py         # 每個測試建一個新資料庫，用最小權限帳號跑完整流程
```

- 測試資料庫的建立順序：public V1.2 schema → `backend/migrations` 的 001–005（依檔名順序，含兩個 004）→ 帳號腳本。`006_participant_state_compat.sql` 是需要操作者核准的修補檔，不在一般順序裡，測試不套用。
- 建好的資料庫要通過網站自己的啟動檢查（`backend/schema.py` 的 `check_schema`），地端寫入之後也一樣。
- 測試裡以 `SITE_` 開頭的 SQL 是從 `backend/analysis.py` 照抄的；另有一個測試檢查這些 SQL 還在那個檔案裡，網站那邊改了查詢時測試會失敗。
- 要比對別的版本的 `analysis_signal.py`（例如正式站實際部署的那一份），用環境變數 `SITE_ANALYSIS_SIGNAL_PY` 指過去。

## 對接過程中發現的事

- **`004_multi_recorder.sql` 第 11 行的多餘字元**：2026-11-20 收到的檔案第 11 行開頭多了 `ˊ˙`，PostgreSQL 套用時語法錯誤。網站那邊已在 2026-11-23 修正（commit 2abf2bd），現在 `main` 上的檔案可以套用。
- **004 需要 public V1.2 的資料表**（`public.machines`、`public.recording_sessions`）。只有 `mobile_capture` 的資料庫套不上去。
- **新的錄音必須帶機台**（`take_requires_machine`）：這不影響地端（地端不建立錄音），但測試資料要先建機台。
- **編號衝突還在**：`main` 上同時有 `004_analysis_jobs.sql`（先前離線分析那條線的）和 `004_multi_recorder.sql`。兩個照檔名順序套用沒有問題（測試就是這樣建庫的），但編號重複容易誤會，要不要重新編號由儲存庫的擁有者決定。
- **內建分析會自動跑**：分析頁寫明「完成音檔封存後自動分析」。所以每個 session 都會先有內建結果；地端的結果比它晚建立時，畫面才會改顯示地端的。

## 還沒有驗證的

- **沒有對正式站的資料庫執行過。** 測試用的是儲存庫裡的正式資料表定義，但跑在本機的測試資料庫上，資料是測試產生的。正式站實際部署的是哪個版本也還沒確認。
- **沒有在網站的分析頁上看過結果。** 查詢 API 與 PNG API 用的 SQL 對著地端的資料跑過，回傳的內容包含內建分析會寫的每一個欄位，圖的尺寸也和分析頁的圖框一致；但 API 本身（FastAPI、權限檢查）和前端頁面沒有實際跑。
- **解碼比對的範圍有限**（見上面第 1 點）：只比了 11 個檔案，真實錄音只有 2 個（都是 Chrome 的 WebM／Opus）。iPhone Safari 實際錄出來的 MP4 沒有比過；正式站用的 PyAV 版本不知道。
- **沒有用真實的封存音檔跑過。** 測試的來源是程式產生的 Opus／AAC／WAV。
- 很長的錄音沒有時間或記憶體上限（取樣率的上限只擋掉比例過大的情況，擋不了錄音本身很長）。
- 記憶體：一次只把一台裝置的音訊讀進記憶體，一次只算一個聲道。單一聲道的頻譜矩陣仍然隨錄音長度增加（10 分鐘約 0.5 GB），沒有設上限，也沒有用長錄音實測過。
- 兩個 worker 真的同時執行的情況：自動測試只用模擬；真正的雙執行緒並行是先前用暫時的腳本實跑驗證的，沒有收進自動測試，這次改動後沒有重做。
