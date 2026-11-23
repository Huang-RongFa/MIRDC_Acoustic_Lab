# 2026-11-20 更新：地端外部分析（每聲道 Spectrogram／MFCC），以共用資料庫對接

分支：`claude/external-track-analysis-v1`（從 `claude/analysis-model-sync-v1` 分出）。
狀態：**本機測試通過；跨引擎審查第四輪 PASS；已推送分支、尚未合併。還沒有對真實網站跑過。**

> 這份是第一版的紀錄（當時還沒有網站的正式檔案）。取得正式檔案之後的修正與比對結果在 [`2026-11-20-external-track-analysis-real-schema.md`](2026-11-20-external-track-analysis-real-schema.md)；下面提到「照規格重建」的地方已被那一版取代。

依據：《CNC Acoustic Lab｜外部音訊分析系統對接規格》（2026-11-17）。設計說明見 [`docs/external-track-analysis.md`](../external-track-analysis.md)。

## 一、先講限制

規格引用的網站原始碼不在 GitHub 的任何分支，也不在這台電腦：

- `backend/migrations/004_multi_recorder.sql`、`005_track_analysis.sql`
- `backend/analysis.py`、`backend/analysis_signal.py`
- `frontend/src/RecordingAnalysis.tsx`

所以：

- 測試用的結果表（`recording_tracks`、`track_analysis_runs`、`track_analysis_artifacts`）與規格第 4 節多出來的輸入欄位，是**照規格的文字重建**的，檔名標明 `RECONSTRUCTED`。正式的欄位名稱、NOT NULL、CHECK 若和重建的不同，程式要跟著改。
- 沒有和內建分析的數值比對過。
- 沒有確認網站的查詢 API 與分析頁讀得到寫入的結果。

另外，這個儲存庫的 `004_analysis_jobs.sql`（我先前做的分析佇列）和規格說的 `004_multi_recorder.sql` 編號相同、內容不同。兩條線要合併時，migration 編號需要重新排。

## 二、做了什麼

整合方式：規格第 1 節的「共用 PostgreSQL」。地端程式讀輸入表、寫三張結果表；沒有新增 HTTP API，沒有改網站。

| 檔案 | 內容 |
|---|---|
| `analysis/track_analysis/source.py` | 來源清單（規格 4.1 的 SQL）；從音段重建原始檔並驗證；解碼成各聲道 |
| `analysis/track_analysis/signal_contract.py` | 規格第 8 節的參數：重取樣、STFT 振幅、dB、Mel、MFCC |
| `analysis/track_analysis/render.py` | Spectrogram／MFCC 的 PNG；矩陣 NPZ |
| `analysis/track_analysis/publish.py` | track_id、fingerprint、run_id；一個交易寫入 tracks、run、artifacts |
| `analysis/track_analysis/worker.py` | 整個流程與命令列：`--session`、`--start/--end`、`--dry-run`、`--pending`、`--force`、`--matrices` |
| `deploy/track_analysis_writer_role.sql` | 最小權限帳號 `track_analysis_writer`（規格第 10 節） |
| `analysis/tests/fixtures/track_schema_RECONSTRUCTED_from_spec_20261117.sql` | 照規格重建的測試用 DDL |
| `analysis/tests/test_track_signal.py`（9 項）、`test_track_publish.py`（18 項） | 測試 |
| `docs/external-track-analysis.md` | 設計、規格對照表、自己決定的 12 個細節、怎麼跑 |

### 與內建 worker 的關係（規格 7.1）

規格說內建 worker 會自動領取 queued 工作，網站重啟會把 running 改回 queued，雙方不能無協調地共用工作。這裡的做法：

- 地端**不建立 queued 或 running 的工作**。在地端算完後，用一個交易寫入最終狀態（completed／partial／failed）和全部內容。
- fingerprint 以 `ext:mirdc-onprem:` 開頭，不和內建結果共用，也不覆寫內建的列。

後果：同一個 session 可能同時有內建結果和外部結果，畫面顯示較晚建立的那一筆。要由外部完全接管，仍需要網站停用內建分析，這裡沒有做。

## 三、驗證證據（本機實際執行）

環境：`audio_preject`（Python、numpy、scipy、matplotlib、psycopg）；本機測試用 PostgreSQL 18（127.0.0.1:55433，資料在暫存資料夾）。每個資料庫測試都建一個全新的資料庫、用 `track_analysis_writer` 帳號跑完整流程、測完刪除。

| 檢查 | 結果 |
|---|---|
| `analysis/tests/test_track_signal.py` | **9/9 通過** |
| `analysis/tests/test_track_publish.py` | **18/18 通過** |
| 我另外寫的獨立數值比對（不用被測程式的測試） | STFT 與逐窗手算相差 7e-18；Mel 濾波器與逐點公式相差 3e-15；MFCC 相差 6e-14；重取樣與直接呼叫 scipy 完全相同；48 kHz、振幅 0.5 的單音量到 −6.021 dBFS、落在正確的頻點 |
| 故意改壞程式看測試會不會失敗 | 4 種都被測試抓到：左右聲道取平均、跳過 SHA-256 驗證、fingerprint 不看來源、不沿用既有 track_id |
| 命令列實跑 | `--dry-run` 產生檔案且資料庫 0 列；`--pending --once` 處理剩下的 session；重跑會跳過；區間分析成功；不合法的參數都以代碼 1 結束並說明原因 |
| schema 與帳號腳本 | 001–003＋重建的 DDL＋帳號腳本可套用；帳號腳本可重複執行 |
| 既有測試 | `test_offline.py` 5/5、`test_ears_umik.py` 13/13、`test_background.py` 6/6、`test_synthetic.py` 5/5（沒有改到既有程式） |
| Codex 跨引擎審查 | 見第五節 |

圖的檢查：實際產生的 Spectrogram PNG 有時間軸、頻率軸（0–22050 Hz）、−120～0 dBFS 的色階圖例；顯示區間內沒有資料的部分以灰色表示，不補假資料。

## 四、規格第 11 節驗收清單

| 驗收項目 | 狀態 | 依據 |
|---|---|---|
| 明確選擇資料庫寫回或 HTTP 結果提交 | 已選資料庫寫回 | 本文第二節 |
| 明確決定內建／外部 worker 的工作歸屬、重啟與重試 | **地端單方面的做法已定；需要網站那邊同意** | 只發布最終狀態，見第二節 |
| 使用真正的封存音檔，驗證 byte_count／SHA256 | 程式有做；用合成音檔測過，**沒有用真實封存音檔** | `test_corrupt_source_…`；故意跳過驗證時測試會失敗 |
| 三台 Mono 3＋3；1/2/1 得 4＋4；三台 Stereo 6＋6 | 通過 | `test_three_mono_…`、`test_one_two_one_…` |
| Left／Right 用不同訊號驗證，沒有複製或平均 | 通過 | 左 440 Hz、右 1000 Hz，頻譜峰值各自正確；取平均時測試會失敗 |
| 混合 44100／48000、回報 metadata 不符時以實際解碼為準 | 通過 | 回報 44100 的 Opus 檔解碼為 48000，結果記錄 48000 |
| 同一批次所有圖的時間軸、頻率範圍與各類色階一致 | 通過（數值層） | `time_range` 等於最長音軌的結尾；`mfcc_color_range` 等於所有音軌的 min/max |
| 真正計算 MFCC，不交付 Mel Spectrogram | 通過 | 與獨立重算一致；且不等於 log-Mel 的前 20 列 |
| run.result、tracks、artifacts、URL 全部對應正確 | 通過（對重建的 schema） | 每個 URL 都查得到對應的 PNG |
| 相同 run 重送不重複；不同演算法／參數不誤用同一 fingerprint | 通過 | `test_same_inputs_do_not_duplicate`、`test_published_result_is_never_replaced_without_force`、`test_fingerprint_…` |
| 部分失敗保留其他成功聲道；缺失來源有明確狀態 | 通過 | `test_corrupt_source_…`、`test_missing_asset_…`、`test_all_sources_failing_…` |
| 本站查詢 API 能讀到結果，PNG API 可下載且拒絕無權限使用者 | **未驗證** | 沒有網站的後端程式 |
| 重新整理、Session／區間切換、手機版顯示正常 | **未驗證** | 沒有網站的前端程式 |
| 不修改原始音檔、錄音紀錄與加工條件 | 通過 | 分析前後五張輸入表的內容摘要相同；帳號沒有 UPDATE／DELETE 權限 |

## 五、Codex 跨引擎審查

模型 gpt-6-astra，只驗證、不改檔；它自己重跑了測試，並另外寫腳本重現問題。

**第一輪：FAIL。** 測試它也跑出 9/9、12/12，訊號計算逐項符合規格第 8 節（它獨立算的誤差在 1e-14 以下）。但找到這些問題，全部已修正並各補一個回歸測試：

| 等級 | 問題 | 修正 |
|---|---|---|
| P0 | 兩個 worker 同時跑同一個 session：第二個在第一個提交前就通過「還沒有結果」的檢查，接著遇到暫時的解碼錯誤，會把已發布的 completed 蓋成 failed | 同一批輸入已有結果時，只有不比現有的差才覆寫（completed > partial > failed）；被拒絕時整筆回復、什麼都不寫。`--force` 才無條件覆寫 |
| P1 | 一個來源解碼逾時或解碼程式起不來，例外直接中止整個 session，健康的來源也沒發布 | 轉成來源錯誤寫進 `source_errors`，訊息不含路徑；其他來源照常發布 |
| P1 | 帳號腳本宣稱「沒有 DDL、會收回舊權限」過頭：帳號仍可建暫存表，其他 schema 原有的權限也不會被收回 | 說明改成只保證 `mobile_capture`；腳本結束時列出它管不到的權限；`recording_sessions` 只開程式用到的欄位 |
| P2 | 連線是 autocommit 時，寫到一半失敗會留下已提交的工作列 | `publish()` 拒絕 autocommit 連線 |
| P2 | `publish()` 接受「成功音軌有圖的 URL、卻沒有任何圖」 | 每個成功音軌必須有兩張 PNG 且 URL 相符；沒成功的音軌不能有圖；重複或沒被引用的圖都拒絕 |
| P2 | 所有裝置一次解碼進記憶體 | 改成一次只讀一台裝置、一次只算一個聲道；共用時間軸改由檔案長度算出 |
| P2 | 文件對失敗隔離、交易、權限的說法超過實際 | 已改寫，並把沒做到的列進「還沒有驗證的」 |
| P3 | 區間起點 `-0.0` 和 `0.0` 得到不同的 fingerprint | 正規化 |
| P3 | 音段沒有 SHA-256 紀錄時被當成已驗證 | 改成拒絕 |

**第二輪：FAIL（剩 1 個 P1）。** 第一輪的 9 項它重新驗證，原本的情境都通過；測試它跑出 9/9、17/17。新找到的問題也都修正並補測試：

| 等級 | 問題 | 修正 |
|---|---|---|
| P1 | 「不比現有的差」只比狀態：同樣是 partial，成功音軌較少的結果仍會蓋掉成功音軌較多的，已發布的音軌從結果裡消失 | 改成先比狀態、狀態相同再比成功音軌數，不能變少 |
| P2 | 寫回前的一致性檢查只查單向：要寫入的音軌沒列在 result 裡、沒成功的音軌帶著矩陣檔，都會被接受 | 要寫入的音軌與 result 的音軌必須是同一組；狀態必須和內容相符；沒成功的音軌不能有任何檔案 |
| P2 | 帳號腳本結尾的提醒只算直接授予的權限，漏掉經由 PUBLIC 間接得到的 | 改成算實際有效的權限 |
| P3 | 文件沒寫矩陣檔的未壓縮大小門檻 | 已補上 |

我另外用兩個執行緒對同一個 session 實跑（一個正常、一個中途有來源解碼失敗），三種先後順序的最終結果都是較好的那一筆。這個測試還發現同一個程序內兩個執行緒同時出圖會讓中文字型失效，已在出圖處加鎖。

**第三輪：FAIL（仍有 1 個 P1）。** 下表的「未修」是第三輪結束當時的狀態；後來依使用者的決定改了規則，這兩項都已不存在，見本節後面。 第二輪的 P2、P3 與出圖加鎖都通過；測試它跑出 9/9、17/17。剩下的問題：

| 等級 | 問題 | 狀態 |
|---|---|---|
| P1 | 「不比現有的差」比的是成功音軌的**數量**，不是**哪幾條**。兩次都是 partial、成功音軌數相同但成功的是不同裝置時，第二次會蓋掉第一次，第一次成功的音軌從結果裡消失（它的 PNG 還在表裡，但結果不再引用） | 當時未修；後來規則改掉，已不存在 |
| P2 | 既有結果缺少成功音軌數（或不是數字）時，原本宣稱「只有 `--force` 才能替換」，實際上狀態較高的結果仍然蓋得掉 | 當時未修；後來規則改掉，已不存在 |
| P3 | 設計文件寫「已發布的成功音軌也不會消失」，被上面的反例推翻 | 文件已改成如實描述 |

同一個問題（已發布的結果在什麼條件下可以被覆寫）已經修了三次：第一次只比狀態，第二次加上成功音軌數，第三輪又找到數量相同但組成不同的反例。照專案規則，同一件事三次沒過就停下來，不再自行修第四次。兩個可行的方向：

1. **比成功音軌的集合**：新結果必須包含既有結果的每一條成功音軌才可以覆寫；既有結果格式看不懂時一律不覆寫。保留「重試可以補齊」的能力，規則比較複雜。
2. **不加 `--force` 就一律不覆寫**：同一批輸入已有任何結果就跳過，要重算只能加 `--force`。規則最簡單、沒有比較邏輯；代價是暫時性錯誤造成的 partial 不會自動被後來較好的結果取代。

其餘第三輪確認沒有問題的部分：不會寫入 queued／running；不會改到別人的工作列（即使 `--force`）；寫到一半失敗會完整回復；原始錄音表內容不變；沒有把密碼或本機路徑寫進資料庫。

## 六、怎麼測

```powershell
python -X utf8 analysis/tests/test_track_signal.py
$env:WORKER_TEST_ADMIN_URL = 'postgresql://<測試管理帳號>@127.0.0.1:<port>/postgres'
python -X utf8 analysis/tests/test_track_publish.py
```

對真實資料庫的第一次試跑，建議先用 `--dry-run`，不會寫入任何東西：

```powershell
$env:TRACK_ANALYSIS_DATABASE_URL = '<track_analysis_writer 的連線>'
python -X utf8 analysis/track_analysis/worker.py --session <session_id> --dry-run D:\cnc_track\try1
```

## 七、下一步

1. **取得網站的正式檔案**：`004_multi_recorder.sql`、`005_track_analysis.sql`、`backend/analysis.py`、`backend/analysis_signal.py`。用正式 migration 取代重建的 DDL 重跑測試；用 `analysis_signal.py` 對同一段音檔比對數值。
2. **和網站那邊確認工作歸屬**：同意「外部只發布最終狀態」，或改成停用內建分析。
3. **資料庫連線**：網站的資料庫目前只聽 localhost，地端電腦要連得到，需要部署負責人安排；建立 `track_analysis_writer` 帳號。
4. **對真實 session 試跑**：先 `--dry-run` 看圖，再寫回，確認分析頁顯示正常。
5. 確認 `docs/external-track-analysis.md` 列的 12 個自己決定的細節（`times` 的定義、矩陣存 dB 還是振幅等）。
6. 長錄音的記憶體用量：改成逐裝置解碼。

**使用者的決定（2026-11-20）：不加 `--force` 就一律不覆寫。** 照這個決定改寫：

- 同一批輸入已有結果時，不論狀態，不重算也不覆寫；`--force` 才取代那一筆。沒有任何比較邏輯，所以第三輪的 P1（數量相同、組成不同）和 P2（既有結果缺少成功音軌數）都不再存在。
- 代價：暫時性錯誤造成的 partial 不會自動被後來較好的結果取代。兩個 worker 同時跑時，留下來的是先成功提交的那一筆。
- 我用兩個執行緒實跑 3 種情境各 2 次（兩邊各壞一個不同的來源、一邊正常一邊壞），每次都只有一筆工作、寫入的圖和結果一致、另一個 worker 什麼都沒寫。其中「一邊正常、一邊壞」的情境，留下來的是壞的那一邊（它要算的比較少，先提交），這是這個規則已知的代價。

**第四輪：PASS（沒有 P0、P1）。** 它自己重跑測試（9/9、18/18），並用兩條真實連線重現第三輪的反例：

- 已發布 `{A}` 成功的 partial，再不加 force 發布 `{B}` 成功的 partial：被拒絕，結果、音軌表、圖都沒有變。
- completed→partial、completed→failed、failed→completed 不加 force 全部被拒絕；加 force 都能取代，而且是同一筆（id 與建立時間不變，同一個 fingerprint 始終只有一列）。
- 把第一個交易停在提交前：第二個交易在等鎖，這時外部看到三張表都是 0 列；第一個提交後第二個被拒絕，什麼都沒寫。
- 既有結果是 NULL、`{}`、`[]`、字串、成功音軌數不是數字：不加 force 都拒絕。同一個 fingerprint 但 id 不同的列，加不加 force 都不會被改。
- worker 沒有不加 `--force` 就覆寫的路徑；`--pending` 不會帶 force；提前返回後連線狀態正常。
- 沒有寫入 queued／running、沒有改到別人的工作列、沒有改原始錄音、失敗會完整回復、沒有把密碼或本機路徑寫進資料庫。

它另外提了 2 個 P3，都是文件用詞，已修正：「先算完」改成「先成功提交」；第三輪表格的「未修」註明是當時的狀態。

它的結論附帶一句，這裡照錄：本結論限於指定程式與重建 schema 的本機驗證，不代表正式網站整合已驗收。
