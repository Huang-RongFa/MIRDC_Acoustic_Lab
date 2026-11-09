# CNC Acoustic Lab｜手機端 × 錄音主機 × FastAPI 最小 API 規格 V1.2

本文件是建議的 API contract，**僅 SQL 已產出，這些 HTTP 路由尚未實作**。

## 手機可見功能

| API | 用途 | 寫入／查詢的主要表 |
|---|---|---|
| `GET /api/v1/catalog` | 讀取機台、材料、刀具、工具裝夾及麥克風選單 | `machines`, `materials`, `cutting_tools`, `tool_setups`, `workpiece_setups`, `microphones` |
| `POST /api/v1/experiments` | 建立研究群組 | `experiments` |
| `POST /api/v1/experiments/{id}/conditions` | 新增條件組 | `experiment_conditions` |
| `POST /api/v1/sessions` | 建立三聲道錄音批次與加工條件快照 | `recording_sessions`, `recording_channels` |
| `POST /api/v1/sessions/{id}/start` | 發出一鍵三聲道同步啟動指令 | `recording_control_events` + 主機確認後狀態更新 |
| `POST /api/v1/sessions/{id}/stop` | 發出停止指令 | `recording_control_events` |
| `GET /api/v1/sessions` | 查詢歷史 | `recording_sessions` |
| `GET /api/v1/sessions/{id}` | 查詢 Session、加工參數與三聲源狀態 | 相關錄音表 |
| `GET /api/v1/sessions/{id}/analysis` | 顯示 FFT／濾波／融合／推論結果 | `analysis_runs`, `channel_features`, `fusion_results` |
| `POST/PATCH /api/v1/admin/...` | 管理機台、材料、刀具、條件範本 | 各主檔表，需權限 |

## 錄音主機專用 API（不得直接暴露給手機未授權呼叫）

| API | 用途 |
|---|---|
| `POST /api/v1/recorder/sessions/{id}/ack` | 回報啟動確認、共同時鐘 ID、第一個 Frame 起點及錄音狀態 |
| `PUT /api/v1/recorder/sessions/{id}/chunks/{chunk_index}` | 分段上傳一筆**三通道交錯** PCM（binary body）與 frame/sha256 header |
| `POST /api/v1/recorder/sessions/{id}/finalize` | 完成錄音、校驗 chunk/frames/sha256，封存三通道 WAV 並更新狀態 |
| `POST /api/v1/recorder/sessions/{id}/heartbeat` | 維持設備使用狀態與補傳進度 |

## Chunk 輸入契約（示意）

- `session_id`：同一段加工錄音唯一 ID。
- `chunk_index`：從 0 開始、遞增，便於重試。
- `first_frame`：從 0 開始的共同 sample frame index；不是網路送達時間。
- `frame_count`：該 Chunk 每一聲道的 frame 數。
- `channel_count`：固定 3。
- `sample_format`：`pcm_s16le` 或 `pcm_s24le`。
- `sha256_hex`：對**原始 PCM 二進位內容**計算的 SHA256。
- binary body：按 A sample0、B sample0、C sample0、A sample1、B sample1、C sample1 ... 交錯排列。

資料庫 `audio_chunks` 會以 `(session_id, chunk_index)` 作為主鍵。網路重試同一筆，後端必須查出已存在資料，核對 SHA256 及 first_frame 完全一致後才回應成功；內容不同回應 Conflict 並保留原值。

## 開錄前 API 檢查

1. 登入使用者有錄音權限，並已選擇機台、材料、刀具、加工條件。
2. `recording_sessions` 有實體材料／刀具／裝夾關聯，按本研究規範決定必填。
3. 錄音設備沒有其他活動 Session。
4. A/B/C 三筆 `recording_channels` 存在，且綁定三支不同的實體麥克風。
5. 硬體可確實輸入三個 channel，共用採樣時鐘，採樣率及格式吻合。
6. 只有收到**錄音主機的開始確認**才更新到 `recording`，並將 `capture_clock_id` 與 `started_at` 寫入；未確認不得呈現「錄音中」。
7. 當停止／中斷，先完整性檢查，再決定 `completed` 或 `interrupted/failed`。

## 分析資料的責任分離

- `machining_presets` + `recording_sessions`：人工選擇／機台量測的加工條件。
- `channel_features`、`fusion_results`：Python 依據音訊實際計算的特徵。
- `model_predictions`：聲學模型推論，不能當作人工填寫的工況。
- `verified_labels`：根據實際檢驗、量測或其他證據才給出的真實標籤。
