# 2026-11-10 更新 v1：分析模型上線、收音設定紀錄、同步嗶聲

分支：`claude/analysis-model-sync-v1`（從 `feature/room-code-recording` 分出；`main` 目前沒有前後端原始碼）。
狀態：**已測試、已推送分支、尚未合併**。合併前請你審閱與實機測試。

## 一、這次改了什麼

### 1. 新增 `analysis/`（分析模型）

- `analyze_multi_mic.py`：把網站錄下的 A／B／C 音檔對齊，再做聲道間相位分析與背景雜音移除。支援 2 或 3 支手機。
- `sync_chirp.py`：同步嗶聲的規格與偵測。
- `tests/test_synthetic.py`：合成三麥克風資料測試。
- 用法與輸出見 [`analysis/README.md`](../../analysis/README.md)。

### 2. 前端：記錄瀏覽器「實際」採用的收音處理

- 檔案：`frontend/src/audioSettings.ts`（新）、`capture.ts`、`App.tsx`、`storage.ts`、`app.css`。
- 原程式已要求關閉回音消除、降噪、自動增益，但沒有記錄瀏覽器是否照做。現在授權後讀取 `getSettings()`。
- 「本機麥克風」卡顯示三種狀態：
  - 原始收音（三項都關閉）；
  - 收音被處理（列出仍開啟的項目）；
  - 無法確認（瀏覽器沒回報，例如 iOS Safari）。
- `prepared` WebSocket 訊息多帶一個 `processing` 欄位。現行後端只讀 `mime_type`、`sample_rate`、`channel_count`，其餘欄位忽略，所以**不需改後端也不會斷線**。尚未存進資料庫，見下一步。
- 新按鈕「下載收音設定 JSON」，下載 `<session>_<聲源>.meta.json`，內容：
  - 錄音起訖時間、收音處理狀態、嗶聲時間；
  - 瀏覽器 user agent；
  - 不含憑證。

### 3. 前端：同步嗶聲

- 檔案：`frontend/src/syncChirp.ts`（新）、`capture.ts`、`App.tsx`。
- 主控手機的「主控錄音台」多一個「播放同步嗶聲」按鈕。
- 嗶聲規格：1500 → 7500 Hz 線性掃頻，長 0.5 秒。
- 操作：錄音開始後按一次，停止前再按一次。分析程式用第一聲做粗對齊，兩聲的間隔可量時脈漂移。
- 錄音中按下時，播放時間會存進本機 IndexedDB 與 meta JSON。

### 4. 修正：`npm ci` 在 npm 10 和 npm 11 都無法執行

- `frontend/package.json` 的 overrides 原本寫 `"rollup": "npm:@rollup/wasm-node@4.68.0"`，與直接相依衝突（EOVERRIDE）。
- 改成 npm 官方寫法 `"rollup": "$rollup"`。
- `package-lock.json` 未變動，仍安裝 `@rollup/wasm-node` 4.68.0。
- 另新增 script `test:unit`。

## 二、重要更正：上一版兩手機分析報告有兩個結論是錯的

上一版本機分析（兩手機測試錄音 505d6c31，A／B）說了三件事：
- 兩軌共用時脈，漂移 1.7 ppm；
- 偏移是 2.5 ms 的整數倍；
- 高頻相位旋轉可能來自瀏覽器自動增益。

這次寫三麥克風版時，發現原程式的 GCC-PHAT 用矩形切窗。這會在「窗內延遲 0」產生假峰：
- 兩段**獨立**噪音的 PHAT 分數是 145，加 Hann 窗後是 5.6。
- 假峰把精對齊鎖在粗對齊值上。

修正後在同一份錄音上：

| 項目 | 上一版 | 修正後 |
|---|---|---|
| B 相對 A 偏移 | 129.997 ms | 129.750 ms |
| 時脈漂移 | 1.7 ppm（誤判為共用時脈） | **19.7 ppm**（兩支手機各自的石英，正常範圍） |
| 偏移是否為 2.5 ms 整數倍 | 是 | 否（上一版是假峰造成） |
| 對齊後殘餘偏移 | — | −0.12 取樣點，殘餘漂移 0.25 ppm |
| 相干度 >= 0.5 的頻帶比例 | 0.5% | 5.2% |
| 500 Hz–13 kHz 相干度中位數 | 0.04–0.11 | 0.20–0.29 |
| 軌間位準差與響度的相關 | — | 0.03（不像自動增益） |
| 背景移除：安靜幀／響幀衰減 | −3.1／−2.1 dB | −3.1／−2.0 dB |

結論改為：
- 「高頻相位隨時間旋轉」主要是 **20 ppm 時脈漂移**：37 秒累積約 35 取樣點，而上一版只做了固定偏移。
- 程式本來就要求關閉三項處理；位準差也不跟著響度走。所以「瀏覽器自動增益」的懷疑**降低**，但仍要靠新的 meta JSON 實際確認。
- 修正後相干度仍只有 0.2–0.3。可能原因：用喇叭在室內播放影片（反射多、兩手機距離喇叭不同）加上 Opus 有損壓縮。要在真實機台旁錄音才知道。
- 背景移除仍只有約 3 dB：這段錄音本來就沒有穩定的背景噪音可扣。

## 三、驗證證據（全部在本機實際執行）

| 檢查 | 指令 | 結果 |
|---|---|---|
| 特徵化：未加兩項修正前，新程式與原程式的數字 | `analyze_multi_mic.py` 跑真實 A/B，與原 `summary.json` 逐項比對 | 11 項**逐位相同** |
| 嗶聲偵測不誤報 | 同一份真實錄音（無嗶聲） | 偵測到 0 個。初版只用分數門檻時誤報 4 個，後來加「上掃／下掃比」條件 |
| 合成三麥克風 | `python -X utf8 analysis/tests/test_synthetic.py` | **5/5 通過** |
| 型別檢查＋建置 | `npm run build`、`npm run build:pages` | 通過 |
| 前端單元測試 | `npm run test:unit` | **9/9 通過**（含讀 `sync_chirp.py` 比對常數與波形的跨語言契約測試） |
| Chrome 實測收音設定 | `npx playwright test tests/audio-contract.spec.ts`（只需 `npm run dev`） | 通過 |
| GitHub Pages 靜態頁回歸 | `tests/pages.spec.ts` | 通過（含 375 px 不水平捲動） |

合成三麥克風測試的四項內容：
- B、C 偏移誤差 < 0.25 取樣點。
- C 的 25 ppm 漂移量得 24.8 ppm，對齊後殘餘 −0.02 取樣點。
- 三對相干度 >= 0.5 的頻帶都約 40%。
- 停機段衰減 11.6 dB，運轉段 0 dB，表示真的把噪音和機台聲分開了。

Chrome 實測的內容：
- 網頁的關閉要求確實生效，`getSettings()` 回報三項都是 false。
- 不指定時，Chrome 預設三項都開。這就是「必須明確關閉並記錄」的理由。
- 嗶聲經 Web Audio 輸出與規格誤差 < 1e-6。

**沒有驗證到的：**
- 後端測試（`backend/tests`）與完整錄音流程（`recording.spec.ts`、`recovery.spec.ts`）需要 PostgreSQL。這台電腦沒有 PostgreSQL，Docker 也沒啟動，所以**沒有跑**。後端程式本次沒有修改。
- 真實三支手機、iOS Safari 是否回報 `getSettings()`、嗶聲在真實機台噪音下三支手機是否都錄得到：都需要實機測試。
- `graphify update .`：本機沒有安裝 graphify，**沒有更新** `graphify-out/`。

## 四、你審閱時可以這樣測

```powershell
cd frontend
npm ci
npm run test:unit
npm run build
npm run dev              # 另一個終端
npx playwright test tests/audio-contract.spec.ts
```

```powershell
pip install -r analysis/requirements.txt
python -X utf8 analysis/tests/test_synthetic.py
```

手機實測：主控手機授權麥克風後，「本機麥克風」卡應顯示「原始收音」。錄音開始後按「播放同步嗶聲」，停止前再按一次。再到各手機按「下載收音設定 JSON」。

## 五、下一步（建議順序）

1. **實機錄一次三手機**（真實機台或至少安靜房間）：
   - 開頭與結尾各按一次嗶聲；開機前先錄 10 秒空白。
   - 三支手機各下載音檔與 meta JSON 給我。我用 `analyze_multi_mic.py` 驗證嗶聲對齊、漂移、相干度。
2. **後端保存收音設定**：新增 migration `004`，在 `participant_recordings` 加三個欄位（echo_cancellation、noise_suppression、auto_gain_control），後端在 `prepared` 時寫入，結果頁顯示。需要可用的 PostgreSQL 測試資料庫才能完成驗證。
3. **錄音中標記**：主控在錄音中按「背景開始／切削開始／異常／停止切削」，以伺服器時間存成事件。這是「正常／異常」標註的資料來源。需要你決定標記清單，以及異常判定由誰、何時做。
4. **分析 v2**：把單軌的機台聲辨識與四種熱力圖（Hz、梅爾、階次、角度同步）改成直接讀房間的加工條件（主軸轉速、刃數、刀徑），不再需要人工寫 segments.json。
5. **（選做）無損收音**：用 AudioWorklet 錄 PCM，取代 MediaRecorder 的 Opus。改動大，等第 1 步確認 Opus 是瓶頸再做。
