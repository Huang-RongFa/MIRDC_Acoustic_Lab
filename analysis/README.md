# analysis/ — 多手機錄音分析模型（v1）

把網站錄下的 A／B／C 三個音檔對齊，算出聲道間相位，做背景雜音移除。
錄音與分析結果都**不進 Git**（`.gitignore` 已排除 wav 等音訊）；這裡只放程式與合成資料測試。

## 檔案

| 檔案 | 作用 |
|---|---|
| `analyze_multi_mic.py` | 主程式：2 或 3 軌的同步、相位、背景移除，輸出圖與 `summary.json` |
| `sync_chirp.py` | 同步嗶聲規格與偵測；常數必須與 `frontend/src/syncChirp.ts` 相同 |
| `tests/test_synthetic.py` | 合成三麥克風資料（已知偏移、25 ppm 時脈漂移、嗶聲）驗證整條流程 |
| `requirements.txt` | numpy、scipy、soundfile、matplotlib |

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

## 做了什麼

1. **同步**（B、C 對齊到 A）
   - 粗對齊：有同步嗶聲就用嗶聲到達時間差；沒有就用能量包絡互相關（±3 s）。
   - 精對齊：每 2 秒一窗的 GCC-PHAT（Hann 窗），取峰值清楚的窗。
   - 漂移：偏移對時間做直線擬合。不同手機的取樣時脈差約 20 ppm，37 秒就累積約 35 取樣點，所以要依直線平移加重取樣，不能只做固定偏移。
   - 驗證：對齊後再量一次，`after_alignment` 的偏移與漂移應接近 0。
2. **相位**（每一對 A–B、A–C、B–C）：相干度 >= 0.5 的頻帶才有相位值，其餘只標記無效。
3. **處理痕跡**：逐 0.5 秒軌間位準差。若它跟響度一起變（`corr_with_level` 高），就懷疑手機做了自動增益。
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
