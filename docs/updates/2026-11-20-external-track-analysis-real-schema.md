# 2026-11-20 更新（二）：外部分析改用網站的正式資料表定義，並和內建分析對過數值

分支：`claude/external-track-analysis-v1`。接續 [`2026-11-20-external-track-analysis.md`](2026-11-20-external-track-analysis.md)。
狀態：**本機測試通過；已推送分支、尚未合併。還沒有對網站實際的資料庫跑過，也還沒有在網站的分析頁上看過結果。**

設計說明（已同步更新）：[`docs/external-track-analysis.md`](../external-track-analysis.md)。

## 一、這次拿到什麼

2026-11-20 取得網站那邊的四個檔案：

| 檔案 | SHA-256 | 用途 |
|---|---|---|
| `004_multi_recorder.sql` | `98edb617…4187cb`（收到的原檔） | 多錄音者、`source_position`、機台關聯 |
| `005_track_analysis.sql` | `e6ee63b0…100a4b` | 三張結果表 |
| `backend/analysis.py` | 壓縮檔內，未放進儲存庫 | 內建 worker、結果 JSON、查詢與 PNG API |
| `backend/analysis_signal.py` | `9f59fff2…2bf689`，未放進儲存庫 | 內建的數值計算與出圖 |

兩個 SQL 檔放進 `analysis/tests/fixtures/`（只給測試用）。兩個 Python 檔沒有放進儲存庫：數值比對的測試用環境變數指到本機的檔案；`analysis.py` 裡的查詢 SQL 照抄進測試。

## 二、發現的問題

1. **收到的 `004_multi_recorder.sql` 套用會失敗。** 第 11 行開頭多了兩個注音聲調符號 `ˊ˙`（U+02CA、U+02D9）：

   ```
   psql:004_multi_recorder.sql:11: ERROR:  syntax error at or near "ˊ˙ALTER"
   ```

   拿掉這兩個字元之後，004、005 都能在「public V1.2 → 001–003」上套用成功。測試用的是拿掉之後的版本（和原檔只差這 4 個位元組）。這兩個字元是網站的原檔就有，還是傳檔時混進去的，**需要確認**。

2. **先前照規格重建的資料表定義，和正式的有出入：**

   | 項目 | 重建時的假設 | 正式定義 |
   |---|---|---|
   | `participant_recordings.source_position` | 整數 | 文字（`'A'`～`'E'`） |
   | `track_analysis_runs.result` | 可以是空值 | 不可為空，預設 `{}` |
   | `requested_sample_rate`、`requested_channel_count` | 沒有限制 | 只能是 44100／48000、1／2 |
   | 新錄音 | 沒有限制 | 必須帶機台（`take_requires_machine`），`machine_id` 指到 `public.machines` |
   | 004 的前提 | 只需要 `mobile_capture` | 還需要 public V1.2 的 `machines`、`recording_sessions` |

   三張結果表的欄位、主鍵、唯一鍵、外鍵、CHECK 重建得和正式定義相同，只差上表的 `result` 可否為空，以及正式定義多一個 `track_analysis_queue` 索引。寫回的程式（`publish.py`）不需要改。

3. **先前「自己決定」的細節，有 11 項和內建分析不同**，已全部改成相同。清單在設計說明的「已改成和內建分析相同的」（該表共 13 項，另外 2 項是第五輪審查後補上的失敗處理）。最主要的三項：
   - `times` 原本是每個窗的起點，內建是窗的中心（差 1024 個樣本，約 23 毫秒）。
   - 原本只接受 44100／48000 Hz，其他取樣率當成來源失敗；內建任何取樣率都會重取樣後分析。
   - `device_name` 原本只有錄音者名稱；內建是「錄音位置 · 錄音者名稱」。

## 三、改了什麼

| 檔案 | 改動 |
|---|---|
| `analysis/track_analysis/signal_contract.py` | `times` 改成窗的中心；區間端點改用 ceil／floor；`valid_range` 用樣本位置算；重取樣改成任何取樣率通用的公式，並加上比例上限 2048；`PARAMETERS` 改成單層並包含內建的 16 個鍵；版本改為 `mirdc-onprem-track-2` |
| `analysis/track_analysis/source.py` | 不再限制 44100／48000；解碼後就檢查重取樣比例有沒有超過上限、逐塊檢查有沒有無效數值；移除用不到的 `analysis_length` |
| `analysis/track_analysis/worker.py` | 顯示名稱、`time_range`、`duration_seconds`、`completed_device_count`、`mfcc_color_range` 預設值改成內建的算法；`versions` 加上套件版本；單一聲道計算或出圖出錯時只標那個聲道 failed；解碼後讀不回來的裝置改列來源失敗並重算共用時間軸 |
| `analysis/track_analysis/render.py` | 每個窗畫在以它的時間為中心的位置 |
| `analysis/tests/fixtures/` | 移除重建的定義；加入網站的 004（去掉兩個多餘字元）、005 與來源說明 |
| `analysis/tests/test_track_publish.py` | 用正式定義建庫；測試資料補機台、`source_position` 改文字；新增 6 個測試 |
| `analysis/tests/test_track_signal.py` | 配合新的時間定義與取樣率規則 |
| `analysis/tests/test_track_reference.py` | 新增：和 `analysis_signal.py` 比數值 |

`publish.py` 與 `deploy/track_analysis_writer_role.sql` 沒有改。「不加 `--force` 一律不覆寫」的規則沒有動。

## 四、驗證證據

環境：`audio_preject`（Python 3.10、numpy、scipy、soundfile、matplotlib、psycopg）；本機 PostgreSQL 18 測試庫。

| 檢查 | 結果 |
|---|---|
| `test_track_signal.py` | 9/9 通過 |
| `test_track_publish.py`（正式資料表定義，每個測試建新資料庫，最小權限帳號） | 23/23 通過 |
| `test_track_reference.py`（和內建 `analysis_signal.py` 比對） | 5/5 通過 |
| 既有測試 `test_synthetic`、`test_offline`、`test_ears_umik`、`test_background` | 5/5、5/5、13/13、6/6，沒有受影響 |
| pyflakes | 沒有訊息 |

數值比對的範圍：取樣率 44100／48000／16000／96000 × 5 種訊號（白噪音、單音、掃頻、數位靜音、接近 −120 dBFS 的微弱噪音）× 8 個區間，共 160 個案例。

- 120 個兩邊都有結果，40 個兩邊都判定資料不足；沒有任何一個案例兩邊判斷不同。
- 重取樣輸出（7 種取樣率）、`times`、`valid_range`：差 0。
- 轉 float32 之前的頻譜與 MFCC：差距 1e-9 以下。
- 存進矩陣檔的數值：頻譜最大差 3.8e-6 dB、MFCC 最大差 3.1e-5（float32 進位）。

改動之前先跑過一次同樣的比對作為基準：頻譜與 MFCC 當時就一致，`times` 差 0.0232 秒，16000 Hz 被拒絕。

新增的資料庫測試：

- `test_site_queries_read_the_external_result`：用 `analysis.py` 裡查詢 API、PNG API、內建 worker 領工作、內建寫音軌的 SQL 原文，對著地端寫入的資料執行。整段與區間各自查得到；URL 裡的 ID 拿去查拿得到 PNG；換一個 session 拿不到；內建 worker 領不到地端的列；內建之後寫同一批音軌不會多出音軌；result 與 parameters 包含內建會寫的每一個欄位。
- `test_other_sample_rates_are_analysed_like_the_builtin`：16000 Hz 的來源照常分析。
- `test_real_migration_constraints_are_in_force`：確認測試真的跑在正式定義上。
- `test_one_channel_failing_does_not_block_the_others`：某個聲道計算出錯、或圖畫不出來時，只有那個聲道是 failed，其他兩軌照常發布，失敗聲道沒有留下任何圖或矩陣。
- `test_extreme_sample_rate_is_one_source_error`：44099 Hz 的來源列為來源失敗，另一個來源照常發布。
- `test_read_failure_after_decode_recomputes_the_shared_time_axis`：6 秒的那台讀不回來時，共用時間軸是剩下那台的長度，不是 6 秒。

圖的對位另外用一段測試訊號目視確認：1.000 秒的脈衝畫在 1.0，2.000 秒結束的單音畫到 2.0。

## 五、跨引擎審查

Codex（gpt-6-astra，low），只驗證、不改檔；兩輪結束後都確認儲存庫與收到的 SQL 資料夾沒有被更動。

| 輪次 | 判定 | 內容 |
|---|---|---|
| 第五輪 | FAIL | 1 個 P1、5 個 P2、1 個 P3 |
| 第六輪 | PASS | 沒有 P0／P1；剩 1 個 P2、2 個 P3，都是文件用詞，已修正 |

第五輪的 P1：開放其他取樣率之後，一個取樣率極端的來源（它用 2,000,003 Hz 的檔案實測）會要求約 2 GB 的濾波器；而 worker 當時只處理「資料不足」，其他例外會讓同一批的正常來源也發布不了。修法：

- 重取樣比例任一個數字超過 2048 的來源，在解碼後、配置記憶體之前就列為來源失敗。
- 單一聲道計算或出圖出錯時，只把那個聲道標成 failed，其他聲道照常發布。

第五輪它獨立做的確認：

- 收到的 004 在第 11 行失敗；fixture 和原檔只差位移 1270–1274 的 4 個位元組；005 逐位元相同。
- 自己寫的數值比對（沒有用儲存庫裡的測試）：375 個案例，225 個有結果、150 個資料不足，兩邊判斷沒有任何不同；`times`、`valid_range` 逐位元相同；頻譜最大差 3.8e-6 dB，MFCC 最大差 3.0e-5。
- 最小權限帳號在正式定義上跑得完整個流程，對 `public.machines`、`public.recording_sessions` 沒有任何權限。

第六輪它獨立做的確認：

- 2,000,003 Hz、44099 Hz、1 Hz 三種來源：都只是一筆來源失敗，正常來源照常發布，濾波器設計與重取樣一次都沒有被呼叫。
- 上限之內最大的濾波器是 262,145 個係數（約 2 MB）；樣本數最多放大 1764 倍（25 Hz 的來源）。
- 在四個函式各注入三種例外，單一聲道失敗與全部聲道失敗共 24 種情境：其他聲道照常發布、失敗聲道沒有任何圖、資料表與 result 一致、例外訊息裡的路徑沒有寫進資料庫。資料庫錯誤與中斷訊號不會被吞掉。
- 讀不回來的裝置重算時不會無限重試、不會重複記錯、`run_id` 不變、暫存檔都有清掉。
- 三支測試：9/9、5/5、23/23。

第六輪指出、已在文件補上的差異：頻譜圖或矩陣產生失敗的聲道，內建仍保留它的 `valid_range` 並把它的 MFCC 算進共用色階，地端不會（設計說明「刻意保留」第 16 點）。這一項只改了文件，程式和第六輪審查時相同。

它提醒、沒有處理的事：暫存的解碼檔現在保留到整批分析結束（磁碟用量約為所有解碼檔的總和）；錄音很長時仍沒有時間或記憶體上限。

## 六、還沒有驗證的

- **沒有對網站實際的資料庫執行過。** 測試跑在本機測試庫，資料是測試產生的。
- **沒有在網站的分析頁上看過。** 只驗證了 API 用的 SQL 和回傳內容的欄位；FastAPI 本身、權限檢查、前端頁面（`RecordingAnalysis.tsx` 仍未取得）都沒有跑。地端的圖是 1200×528，內建是 960×480，頁面版面會不會受影響不知道。
- **解碼比對的範圍有限**（第八節）：真實錄音只有 2 個 Chrome 的檔案；iPhone Safari 的 MP4 沒有比過；網站用的 PyAV 版本不知道。
- **沒有用真實的封存音檔跑過。**
- 兩個 worker 同時執行的實跑驗證，這次改動後沒有重做（寫回的程式沒有改）。

## 七、下一步

1. 向網站那邊確認 `004_multi_recorder.sql` 第 11 行的兩個多餘字元。
2. 安排地端電腦連到網站的資料庫（規格第 2 節：預設只聽 localhost），建立 `track_analysis_writer` 帳號。
3. 先用 `--dry-run` 對一個真實 session 跑，檢查圖和 result；再實際寫回，在網站的分析頁上看。
4. 和網站那邊談定工作歸屬（同一個 session 內建與外部結果並存時，畫面顯示較晚建立的那一筆）。
5. 兩條線合併時，把這個儲存庫的 `004_analysis_jobs.sql` 重新編號。
6. 向網站那邊問 PyAV 的版本；拿一個 iPhone Safari 實際錄的檔案再比一次解碼。

## 八、解碼比對（同日補做）

使用者同意後，在測試環境 `pg_test` 用 conda 安裝了 `av` 19.0.2 與 `numpy`（`audio_preject` 沒有動）。

做法：同一個檔案分別用兩種方式解碼，存成陣列後比較。

- 網站的方式：取 `analysis_signal.py` 裡的 `decode()` 原文執行（PyAV 19.0.2，內含 libavcodec 63.1）。
- 地端的方式：`track_analysis.source` 的 `decode_to_wav`＋`read_wav`（imageio-ffmpeg 附的 ffmpeg 7.1 指令）。

比對的檔案：9 個程式產生的（5 秒，單音加噪音，1 秒處有脈衝），加上 2 個從網站下載的真實錄音（Chrome 的 WebM／Opus，單聲道 48000 Hz，各約 37 秒）。比對用的腳本和檔案沒有放進儲存庫。

| 檔案 | 取樣率 | 樣本數（網站／地端） | 位移 | 樣本最大差 | 頻譜最大差 (dB) | MFCC 最大差 |
|---|---|---|---|---|---|---|
| 真實錄音 A（Chrome WebM／Opus） | 48000 | 1,782,720／1,782,720 | 0 | 3.7e-8 | 3.2e-3 | 9.2e-5 |
| 真實錄音 B（Chrome WebM／Opus） | 48000 | 1,788,480／1,788,480 | 0 | 4.5e-8 | 3.7e-3 | 1.4e-4 |
| Opus WebM 單聲道 | 48000 | 240,000／240,000 | 0 | 3.0e-8 | 4.4e-3 | 3.1e-5 |
| Opus WebM 立體聲 | 48000 | 240,000／240,000 | 0 | 6.0e-8 | 3.6e-3 | 5.7e-6 |
| Opus WebM（來源 44100） | 48000 | 240,000／240,000 | 0 | 8.9e-8 | 3.1e-3 | 3.1e-5 |
| Opus Ogg 單聲道 | 48000 | 240,000／240,000 | 0 | 4.5e-8 | 2.3e-3 | 3.1e-5 |
| AAC 分段 MP4 | 48000 | 241,664／241,664 | 0 | 2.3e-10 | 0 | 0 |
| **AAC MP4 單聲道** | 44100 | **220,500／221,184** | 0 | 0（共同部分） | 0（共同部分） | 0（共同部分） |
| **AAC MP4 立體聲** | 48000 | **240,000／240,640** | 0 | 0（共同部分） | 0（共同部分） | 0（共同部分） |
| WAV 16-bit 44100 | 44100 | 220,500／220,500 | 0 | 0 | 0 | 0 |
| WAV 16-bit 16000 | 16000 | 80,000／80,000 | 0 | 0 | 0 | 0 |

結論：

1. **Opus 與 WAV 兩邊一致。** Opus 的樣本差在 float32 的最後一位（真實錄音 A 有 0.88% 的樣本不同）。頻譜的最大差出現在接近 −120 dBFS 下限的頻點（真實錄音 A 最差的那一點是 −110 dBFS）；−90 dBFS 以上的頻點最大差 0.0005 dB。差 0.001 dB 以上的頻點，真實錄音 A 的 380 萬個裡有 12 個。
2. **非分段的 AAC／MP4 不一致。** 地端在結尾多解出 684（單聲道）與 640（立體聲）個樣本，約 14 毫秒，不到一個 AAC 編碼框（1024 個樣本）。多出來的部分不是靜音（最大振幅 0.006 與 0.08）。開頭沒有位移，共同部分的樣本逐一相同。對分析的影響：該音軌時長 5.0155 秒對 5.0000 秒、分析窗 497 個對 496 個，前 496 個窗完全相同。
3. 分段的 AAC／MP4 兩邊相同：都是 241,664 個樣本，都比編碼前的 240,000 個多 1,664 個。

沒有確定的事：

- 第 2 點的原因。可能是 FFmpeg 版本不同，也可能是指令列和函式庫的行為不同。沒有另一版 ffmpeg 可以交叉測試。
- 網站實際用的 PyAV 版本。如果它的版本和 19.0.2 的行為不同，上表的「網站」那一欄就不代表網站實際的結果。
- iPhone Safari 實際錄出來的檔案是哪一種 MP4。這裡的 MP4 是 ffmpeg 產生的。

這次沒有改程式。要消除第 2 點的差異，一個做法是地端也改用 PyAV 解碼，但要先知道網站的版本才有意義。
