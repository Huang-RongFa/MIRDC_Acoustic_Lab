# analysis/ — 多手機錄音分析模型（v1）

把網站錄下的 A／B／C 三個音檔對齊，算出聲道間相位，做背景雜音移除。
錄音與分析結果都**不進 Git**（`.gitignore` 已排除 wav 等音訊）；這裡只放程式與合成資料測試。

## 檔案

| 檔案 | 作用 |
|---|---|
| `analyze_multi_mic.py` | 主程式：2 或 3 軌的同步、相位、背景移除，輸出圖與 `summary.json` |
| `sync_chirp.py` | 同步嗶聲規格與偵測；常數必須與 `frontend/src/syncChirp.ts` 相同 |
| `tests/test_synthetic.py` | 合成三麥克風資料（已知偏移、25 ppm 時脈漂移、嗶聲）驗證整條流程 |
| `worker.py` | 地端分析 worker：從 `mobile_capture.analysis_jobs` 認領工作、校驗並解碼音段、跑本模型、結果寫回資料表（見 [`docs/analysis-worker.md`](../docs/analysis-worker.md)） |
| `offline.py` | 不經過網站資料庫的離線分析：`chirp` 產生同步嗶聲 wav；`run` 把 2–3 個任意格式的錄音檔（webm、m4a、wav）解碼成 48 kHz 單聲道後跑本模型，印出對齊判定（與 worker 同一套標準）並寫 `offline_report.json` |
| `tests/test_offline.py` | 離線分析測試：嗶聲檔可被偵測、混合格式（webm／m4a／44.1 kHz wav）對齊通過、無嗶聲時改用包絡仍通過、拒絕把輸出寫進儲存庫 |
| `record_usb.py` | 同時錄一台雙聲道 USB 裝置（例如 miniDSP EARS）與一支單聲道 USB 麥克風（例如 UMIK-2）；錄完檢查聲道數、長度、破音、沒聲音、左右是否相同。只支援 Windows，用內附的 ffmpeg，不需要另外安裝套件 |
| `background_check.py` | 雙聲道同一時鐘的錄音能把背景音消掉多少：各頻段的相干度上限，以及「前半段估計轉移函數、後半段驗收」實際做到的消除量 |
| `tests/test_background.py` | 背景檢查的測試（6 項，合成資料、答案已知） |
| `tests/test_ears_umik.py` | 雙聲道同一時鐘＋獨立時鐘麥克風的測試（11 項，不需要接上裝置） |
| `tests/test_worker.py` | worker 的資料庫整合測試（每個測試建新資料庫，用最小權限帳號跑） |
| `track_analysis/` | 地端外部分析：照《外部音訊分析系統對接規格》（2026-11-17）讀取各裝置封存音檔，逐聲道算 Spectrogram／MFCC，寫回共用資料庫的 `recording_tracks`、`track_analysis_runs`、`track_analysis_artifacts`。說明見 [`docs/external-track-analysis.md`](../docs/external-track-analysis.md)。測試用網站的正式資料表定義，數值和網站內建分析比對過；**還沒有對網站實際的資料庫跑過** |
| `tests/test_track_signal.py`、`tests/test_track_publish.py`、`tests/test_track_reference.py` | 外部分析的參數契約測試（9 項）、資料庫整合測試（23 項）、和網站內建分析的數值比對（5 項，需要網站的 `analysis_signal.py`，沒有就跳過） |
| `requirements.txt` | numpy、scipy、soundfile、matplotlib、psycopg（worker 用）、imageio-ffmpeg（沒有系統 ffmpeg 時） |

## 用法

先把網站下載的 webm 解碼成單聲道 wav（取樣率三檔一致）：

```powershell
ffmpeg -i <session>_A.webm -ac 1 -ar 48000 A.wav
ffmpeg -i <session>_B.webm -ac 1 -ar 48000 B.wav
ffmpeg -i <session>_C.webm -ac 1 -ar 48000 C.wav
python -X utf8 analysis/analyze_multi_mic.py --a A.wav --b B.wav --c C.wav --out results/<session>
python -X utf8 analysis/tests/test_synthetic.py
```

`--c` 可省略（兩支手機時）。A 一律是主控手機。

或用離線工具一次完成解碼與分析（輸出資料夾必須在儲存庫外）：

```powershell
python -X utf8 analysis/offline.py chirp --out D:\cnc_offline\sync_chirp.wav
python -X utf8 analysis/offline.py run --a A.webm --b B.webm --c C.webm --out D:\cnc_offline\run1 --note "機台、轉速、麥克風位置"
python -X utf8 analysis/tests/test_offline.py
```

## 雙聲道裝置（EARS）＋獨立麥克風（UMIK-2）

EARS 的左右兩支麥克風在同一台 USB 裝置上，共用一個時鐘：沒有起點差，也沒有漂移。
UMIK-2 是另一台裝置，有自己的時鐘，和手機一樣要對齊。

```powershell
python -X utf8 analysis/record_usb.py list
python -X utf8 analysis/record_usb.py record --stereo EARS --mono UMIK --seconds 60 --out D:\cnc_offline\run2
python -X utf8 analysis/offline.py run --stereo-ab D:\cnc_offline\run2\stereo.wav --c D:\cnc_offline\run2\mono.wav --ab-spacing-m 0.15 --out D:\cnc_offline\run2\analysis
python -X utf8 analysis/tests/test_ears_umik.py
```

- **錄音前必須關閉 Windows 的「音訊增強」**（設定 → 系統 → 音效 → 輸入 → 該裝置）。Windows 11 預設會替 USB 麥克風掛上「語音清晰度」（降噪＋回音消除），它會把穩定的噪音壓到完全無聲，機台運轉聲正是這種聲音。`record_usb.py` 錄音前會檢查並警告。
- A＝左聲道、B＝右聲道、C＝獨立麥克風。
- **A–B 不對齊**：量到的時間差就是聲學到達時間差（B 比 A 晚到為正），只記錄、不補償。相位用原始兩軌計算，所以 A–B 的相位斜率不是 0，而是到達時間差。注意兩個數字的正負號相反：B 晚到時，到達時間差為正、相位斜率換算的時間差為負。
- **C 對齊到 A**：做法和手機相同（嗶聲或包絡粗對齊、機台聲精對齊、補償漂移）。因此 A–C、B–C 的相位仍是相對相位，主聲源的到達時間差已被對齊抵消。
- `--ab-spacing-m`：兩支麥克風開孔的間距。給了就會算直線上限 d/c 與相位不混疊的頻率上限 c/(2d)。時間差超過直線上限會提醒；超過 1.5 倍（留給治具繞射的餘裕）就判定不通過，代表間距填錯，或這兩軌不是同一個時鐘。
- 背景移除的「各軌平均」會先把 B 朝主聲源對正再平均，只影響第 4 步；相位與輸出的 `B_aligned.wav` 都是原始的 B。
- 直接呼叫模型時用 `--same-clock B --spacing B=0.15`。

### 背景音能消掉多少（到機台旁先做這個）

```powershell
python -X utf8 analysis/record_usb.py record --stereo E.A.R.S --seconds 60 --out D:\cnc_offline\bg1
python -X utf8 analysis/background_check.py --stereo D:\cnc_offline\bg1\stereo.wav --out D:\cnc_offline\bg1\background --note "機台停機，只有廠房背景音"
python -X utf8 analysis/tests/test_background.py
```

- 錄一段只有背景音的錄音（機台不加工），至少 20 秒，建議 60 秒以上。
- 每個頻段給兩個數字（負值＝變小）：
  - **上限**：由兩軌的相干度 γ² 決定，殘餘比例是 1 − γ²。γ² = 0.5 最多消 3 dB，0.9 最多 10 dB，0.99 最多 20 dB。
  - **實際**：用前半段估計「一軌 → 另一軌」的轉移函數，套到後半段相減，量後半段真的少了多少。背景聲源會移動或時大時小時，實際會比上限差。
- 判讀：實際消除 10 dB 以上是「有效」，5–10 dB 是「部分有效」，不到 5 dB 是「效果很小」。
- 位準很低的頻段（接近錄音底噪）相干度一定低，那是麥克風自己的雜訊，不代表現場的背景音消不掉。

## 做了什麼

1. **同步**（B、C 對齊到 A）
   - 粗對齊：有同步嗶聲就用嗶聲到達時間差；沒有就用能量包絡互相關（±3 s）。
   - 精對齊：每 2 秒一窗的 GCC-PHAT（Hann 窗），取峰值清楚的窗。
   - 漂移：偏移對時間做直線擬合。不同手機的取樣時脈差約 20 ppm，37 秒就累積約 35 取樣點，所以要依直線平移加重取樣，不能只做固定偏移。
   - 驗證：對齊後再量一次，`after_alignment` 的偏移與漂移應接近 0。
2. **相位**（每一對 A–B、A–C、B–C）：相干度 >= 0.5 的頻帶才有相位值，其餘只標記無效。
3. **處理痕跡**：逐 0.5 秒軌間位準差與它跟整體響度的相關（`corr_with_level`）。
   注意：錄音中有停機或安靜段時，各軌只剩各自的底噪，位準差本來就會跟著響度變；固定增益的合成資料相關係數也有 0.97–0.99。只有機台穩定運轉的片段，相關高才代表可能有自動增益。
4. **背景移除**（只在特徵層；原始音檔不動）：各軌平均 → 依軌間短時相干度給增益（扣除錯開 1 秒對照組的偏差）→ 扣除穩態背景地板。

## 輸出（`--out` 資料夾）

- `fig1_sync.png`：每軌對 A 的逐窗偏移與漂移擬合；各軌位準。
- `fig2_phase_AB.png`、`fig2_phase_AC.png`、`fig2_phase_BC.png`：相干度、相位差、殘餘時間差、相位熱力圖。
- `fig3_background_removal.png`、`fig4_removal_spectra.png`：處理前後的時頻圖與平均頻譜。
- `*_aligned.wav`、`delay_and_sum.wav`、`coherence_filtered.wav`、`final_coherence_plus_floor.wav`、`removed_part.wav`。
- `summary.json`：所有數字。

## 限制

- 偏移＝錄音啟動時間差＋聲音到各手機的時間差，從音訊分不開；對齊後的時間差只是相對值，不能直接換算成聲源方向。
- 嗶聲到達時間含「主控手機到各手機」的傳播時間（每公尺約 2.9 ms），只當粗對齊；精對齊用機台聲。
- 背景移除需要三軌錄到一致的機台聲；軌間不一致時，它只會整體調小音量（真實錄音實例見 `docs/updates/2026-11-10-analysis-model-v1.md`）。
- 單軌的機台聲辨識與四種熱力圖（Hz、梅爾、階次、角度同步）還沒放進來，規劃在 v2。
