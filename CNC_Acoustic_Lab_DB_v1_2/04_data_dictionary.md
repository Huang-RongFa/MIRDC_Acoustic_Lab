# CNC Acoustic Lab｜完整 SQL 資料字典 V1.2

本檔案涵蓋新建 PostgreSQL 資料庫的 **所有資料表、全部欄位**，包含 24 張 V1.1 舊表、V1.2 擴充欄位與 4 張新表。

- 資料表總數：**28**
- 欄位總數：**423**
- 原始三聲道音訊為同時採樣、交錯排列的 PCM；不能把不同時間的三段音訊直接視為同步。
- `JSONB` 欄位允許擴充，但固定且需要統計／比較的參數優先用獨立欄位。
- 允許 NULL 的欄位代表「無資料／尚未量測」，不能自動當成 0。

## 目錄與用途

| 類別 | 表名 | 欄位數 | 用途 |
|---|---|---:|---|
| 基本資料 | `app_users` | 6 | 研究人員與系統管理者 |
| 加工設備 | `machines` | 16 | CNC 機台主檔 |
| 加工設備 | `materials` | 9 | 工件材料型錄 |
| 加工設備 | `cutting_tools` | 16 | 刀具型錄（規格） |
| 錄音設備 | `capture_devices` | 18 | 多通道音訊介面和錄音主機 |
| 加工設定 | `machining_presets` | 25 | 可編輯的常用加工條件範本 |
| 實驗管理 | `experiments` | 12 | 研究實驗群組 |
| 實驗管理 | `experiment_conditions` | 11 | 實驗內的條件組與計畫重複次數 |
| 加工設備 | `workpiece_samples` | 15 | 實體工件（材料批次、硬度、尺寸） |
| 加工設備 | `tool_instances` | 10 | 實體刀具識別與使用狀況 |
| 加工設定 | `tool_setups` | 20 | 刀具裝夾與伸出量 |
| 錄音設備 | `microphones` | 14 | 麥克風規格與實體識別 |
| 錄音設備 | `microphone_calibrations` | 14 | 麥克風校正歷史 |
| 錄音核心 | `recording_sessions` | 51 | 一次同步三通道錄音及當下加工條件 |
| 錄音核心 | `recording_channels` | 22 | A/B/C 對應的實際麥克風與安裝位置 |
| 錄音核心 | `audio_chunks` | 11 | 錄音中寫入 SQL 的三通道 PCM 區塊 |
| 錄音核心 | `audio_assets` | 13 | 封存三通道無損音檔及其雜湊 |
| 品質管理 | `audio_quality_checks` | 16 | 音訊完整性與品質檢查 |
| 加工設定 | `machining_parameter_events` | 10 | 錄音途中參數異動事件 |
| 後處理 | `analysis_runs` | 16 | 每次前處理／特徵／融合／推論執行紀錄 |
| 後處理 | `channel_features` | 18 | 各聲道各視窗的聲學數值特徵 |
| 後處理 | `fusion_results` | 10 | 三聲源融合後的視窗特徵 |
| 模型判定 | `model_predictions` | 14 | 模型推論，不是人工輸入的工況 |
| 模型判定 | `verified_labels` | 11 | 獨立量測或檢驗取得的真實標籤 |
| 加工設定 | `workpiece_setups` | 13 | 每次工件夾持姿態與治具 |
| 錄音核心 | `recording_control_events` | 10 | 手機指令與錄音主機回應紀錄 |
| 加工設定 | `machine_telemetry_samples` | 12 | CNC 實際運轉數值依音訊取樣位置對齊 |
| 後處理 | `analysis_artifacts` | 10 | 大容量衍生音訊、FFT／STFT 圖檔位置與雜湊 |

## 全欄位清單

### `app_users` — 研究人員與系統管理者

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `user_id` | `UUID` | 是 | — | 使用者唯一識別碼；由資料庫產生 |
| `display_name` | `TEXT` | 是 | — | 操作人員顯示名稱 |
| `email` | `TEXT` | 是 | — | 登入電子郵件，必須唯一 |
| `role` | `TEXT` | 是 | — | 角色：admin 管理員／researcher 研究員 |
| `is_active` | `BOOLEAN` | 是 | — | 帳號是否啟用 |
| `created_at` | `TIMESTAMPTZ` | 是 | — | 建立時間（含時區） |

### `machines` — CNC 機台主檔

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `machine_id` | `UUID` | 是 | — | 機台唯一識別碼 |
| `machine_code` | `TEXT` | 是 | — | 機台編號，例如 CNC-01；不可重複 |
| `machine_name` | `TEXT` | 是 | — | 機台顯示名稱 |
| `machine_type` | `TEXT` | 否 | — | 機台類別，例如三軸立式加工中心 |
| `manufacturer` | `TEXT` | 否 | — | 機台製造商 |
| `model` | `TEXT` | 否 | — | 機台型號 |
| `controller_model` | `TEXT` | 否 | — | CNC 控制器型號 |
| `spindle_max_rpm` | `NUMERIC(12,2)` | 否 | RPM | 主軸額定最高轉速 |
| `spindle_power_kw` | `NUMERIC(12,3)` | 否 | kW | 主軸額定功率 |
| `location` | `TEXT` | 否 | — | 實際設備所在地／線別 |
| `is_active` | `BOOLEAN` | 是 | — | 是否允許新實驗選用 |
| `created_at` | `TIMESTAMPTZ` | 是 | — | 機台主檔建立時間 |
| `machine_serial_no` | `TEXT` | 否 | — | 實際 CNC 機台原廠序號，用於辨識同型號不同機台 |
| `axis_count` | `SMALLINT` | 否 | — | 機台軸數 |
| `machine_enclosure` | `TEXT` | 否 | — | 機台外罩／隔音罩配置 |
| `commissioning_date` | `DATE` | 否 | — | 機台啟用日期 |

### `materials` — 工件材料型錄

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `material_id` | `UUID` | 是 | — | 材料類型唯一識別碼 |
| `material_code` | `TEXT` | 是 | — | 材料代碼，例如 AL6061-T6 |
| `material_name` | `TEXT` | 是 | — | 材料名稱 |
| `specification` | `TEXT` | 否 | — | 補充材料規格敘述 |
| `material_grade` | `TEXT` | 否 | — | 材料牌號／狀態，例如 6061-T6 |
| `material_standard` | `TEXT` | 否 | — | 材料採用的標準，例如 ASTM／JIS |
| `is_active` | `BOOLEAN` | 是 | — | 材料是否啟用 |
| `material_family` | `TEXT` | 否 | — | 材料族群，例如鋁合金、碳鋼、不鏽鋼 |
| `nominal_density_kg_m3` | `NUMERIC(12,3)` | 否 | kg/m³ | 材料名義密度，與本次量測值區分 |

### `cutting_tools` — 刀具型錄（規格）

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `tool_id` | `UUID` | 是 | — | 刀具型號唯一識別碼 |
| `tool_code` | `TEXT` | 是 | — | 刀具型號或庫存品號 |
| `tool_name` | `TEXT` | 是 | — | 刀具顯示名稱 |
| `tool_type` | `TEXT` | 是 | — | 刀具類型，例如平銑刀、面銑刀、鑽頭 |
| `tool_material` | `TEXT` | 否 | — | 刀具基材，例如硬質合金 |
| `manufacturer` | `TEXT` | 否 | — | 刀具製造商 |
| `model` | `TEXT` | 否 | — | 刀具製造型號 |
| `coating_type` | `TEXT` | 否 | — | 刀具塗層，例如 TiAlN |
| `corner_radius_mm` | `NUMERIC(10,3)` | 否 | mm | 刀角圓弧半徑 |
| `helix_angle_deg` | `NUMERIC(8,3)` | 否 | ° | 刀具螺旋角 |
| `diameter_mm` | `NUMERIC(10,3)` | 否 | mm | 刀具名義直徑 |
| `flute_count` | `SMALLINT` | 否 | — | 刀具刃數 Z |
| `is_active` | `BOOLEAN` | 是 | — | 是否可供新實驗選用 |
| `cutting_edge_length_mm` | `NUMERIC(10,3)` | 否 | mm | 有效切削刃長度 |
| `edge_radius_um` | `NUMERIC(10,3)` | 否 | µm | 切削刃鈍圓半徑 |
| `nominal_tool_length_mm` | `NUMERIC(10,3)` | 否 | mm | 刀具規格標稱長度，不等於裝夾伸出長度 |

### `capture_devices` — 多通道音訊介面和錄音主機

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `device_id` | `UUID` | 是 | — | 錄音設備唯一識別碼 |
| `device_code` | `TEXT` | 是 | — | 錄音介面代號，需唯一 |
| `device_name` | `TEXT` | 是 | — | 錄音設備名稱 |
| `input_channel_capacity` | `SMALLINT` | 是 | — | 可獨立擷取的音訊輸入通道數，至少三路 |
| `shared_clock` | `BOOLEAN` | 是 | — | 設備輸入是否共用採樣時鐘；資料庫不會代為驗證 |
| `manufacturer` | `TEXT` | 否 | — | 錄音介面製造商 |
| `model` | `TEXT` | 否 | — | 錄音介面型號 |
| `interface_serial_no` | `TEXT` | 否 | — | 錄音介面設備序號 |
| `recording_host_name` | `TEXT` | 否 | — | 實際擷取音訊的電腦／主機名稱 |
| `description` | `TEXT` | 否 | — | 裝置接線／設定備註 |
| `is_active` | `BOOLEAN` | 是 | — | 是否可啟用錄音 |
| `recording_host_os` | `TEXT` | 否 | — | 多通道錄音主機作業系統 |
| `audio_driver_version` | `TEXT` | 否 | — | 錄音設備驅動版本 |
| `firmware_version` | `TEXT` | 否 | — | 音訊介面韌體版本 |
| `recording_service_version` | `TEXT` | 否 | — | 錄音主機服務版本 |
| `supported_sample_rates_hz` | `INTEGER[]` | 否 | Hz | 設備支援的採樣率列表 |
| `input_channel_map` | `JSONB` | 是 | — | 硬體輸入端子與軟體聲道對應 JSON |
| `last_seen_at` | `TIMESTAMPTZ` | 否 | — | 錄音主機最後回報在線時間 |

### `machining_presets` — 可編輯的常用加工條件範本

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `preset_id` | `UUID` | 是 | — | 加工範本唯一識別碼 |
| `preset_name` | `TEXT` | 是 | — | 範本名稱，需唯一 |
| `machine_id` | `UUID` | 否 | — | 範本預選的機台 ID，可留空 |
| `material_id` | `UUID` | 否 | — | 範本預選的材料類型，可留空 |
| `tool_id` | `UUID` | 否 | — | 範本預選的刀具規格，可留空 |
| `process_type` | `TEXT` | 是 | — | 加工製程：milling／turning／drilling／other |
| `spindle_rpm` | `NUMERIC(12,2)` | 否 | RPM | 設定主軸轉速，不是控制器回報實際轉速 |
| `feed_mm_min` | `NUMERIC(12,3)` | 否 | mm/min | 設定進給速度 |
| `axial_depth_mm` | `NUMERIC(10,3)` | 否 | mm | 設定軸向切深 ap |
| `radial_width_mm` | `NUMERIC(10,3)` | 否 | mm | 設定徑向切寬 ae |
| `coolant_mode` | `TEXT` | 否 | — | 冷卻方式：dry／wet／mql／other |
| `operation_name` | `TEXT` | 否 | — | 加工操作名稱，例如端面銑削 |
| `nc_program_code` | `TEXT` | 否 | — | CNC 加工程式代碼 |
| `toolpath_type` | `TEXT` | 否 | — | 刀具路徑類型，例如 straight／slotting／contour |
| `cutting_direction` | `TEXT` | 否 | — | 切削方向：climb／conventional／not_applicable／other |
| `feed_per_tooth_mm` | `NUMERIC(12,6)` | 否 | mm/tooth | 每齒進給量 fz；可從進給、轉速與刃數計算 |
| `cutting_speed_m_min` | `NUMERIC(12,4)` | 否 | m/min | 切削速度 Vc；可由刀具直徑與轉速推得 |
| `extra_params` | `JSONB` | 是 | — | 特定製程的擴充參數 JSON 物件 |
| `is_active` | `BOOLEAN` | 是 | — | 範本是否提供選用 |
| `updated_at` | `TIMESTAMPTZ` | 是 | — | 範本最後更新時間；需由應用程式維護 |
| `nc_program_revision` | `TEXT` | 否 | — | 範本對應 NC 程式版本 |
| `pass_no` | `INTEGER` | 否 | — | 範本預設走刀編號 |
| `fixture_type` | `TEXT` | 否 | — | 預設夾具類型 |
| `workholding_method` | `TEXT` | 否 | — | 預設工件夾持方式 |
| `notes` | `TEXT` | 否 | — | 條件範本備註 |

### `experiments` — 研究實驗群組

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `experiment_id` | `UUID` | 是 | — | 實驗群組唯一識別碼 |
| `experiment_code` | `TEXT` | 是 | — | 研究用實驗代碼，例如 EXP-2026-01 |
| `experiment_name` | `TEXT` | 是 | — | 實驗群組名稱 |
| `research_objective` | `TEXT` | 否 | — | 研究問題或實驗目的 |
| `owner_user_id` | `UUID` | 是 | — | 實驗負責人 |
| `status` | `TEXT` | 是 | — | 研究群組狀態：planned／active／closed／archived |
| `notes` | `TEXT` | 否 | — | 實驗備註 |
| `created_at` | `TIMESTAMPTZ` | 是 | — | 建立時間 |
| `closed_at` | `TIMESTAMPTZ` | 否 | — | 研究群組結束時間 |
| `research_protocol_version` | `TEXT` | 否 | — | 研究／實驗操作規範版本 |
| `study_location` | `TEXT` | 否 | — | 實驗場域名稱 |
| `target_sample_rate_hz` | `INTEGER` | 否 | Hz | 計畫使用的三通道採樣率 |

### `experiment_conditions` — 實驗內的條件組與計畫重複次數

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `condition_id` | `UUID` | 是 | — | 條件組唯一識別碼 |
| `experiment_id` | `UUID` | 是 | — | 所屬實驗群組 |
| `condition_code` | `TEXT` | 是 | — | 條件組代碼；同一實驗不可重複 |
| `condition_name` | `TEXT` | 是 | — | 條件組名稱 |
| `preset_id` | `UUID` | 否 | — | 參考的參數範本；可留空 |
| `planned_parameters` | `JSONB` | 是 | — | 設計時的加工參數 JSON；不取代錄音當次快照 |
| `planned_repeats` | `INTEGER` | 否 | — | 計畫重複試驗次數 |
| `notes` | `TEXT` | 否 | — | 條件組備註 |
| `created_at` | `TIMESTAMPTZ` | 是 | — | 條件組建立時間 |
| `condition_factors` | `JSONB` | 是 | — | 研究變因與控制變因 JSON |
| `randomized_order` | `INTEGER` | 否 | — | 條件執行隨機化順序 |

### `workpiece_samples` — 實體工件（材料批次、硬度、尺寸）

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `workpiece_sample_id` | `UUID` | 是 | — | 實際工件唯一識別碼 |
| `sample_code` | `TEXT` | 是 | — | 工件個體／樣本代碼，例如 WP-001 |
| `material_id` | `UUID` | 是 | — | 所屬材料類型；需與錄音 Session 相符 |
| `batch_no` | `TEXT` | 否 | — | 材料批號／爐號 |
| `heat_treatment` | `TEXT` | 否 | — | 工件熱處理狀態 |
| `hardness_value` | `NUMERIC(10,3)` | 否 | 依 hardness_scale | 實測或出廠硬度數值 |
| `hardness_scale` | `TEXT` | 否 | — | 硬度尺度：HB／HRC／HRB／HV／other |
| `length_mm` | `NUMERIC(12,3)` | 否 | mm | 工件長度 |
| `width_mm` | `NUMERIC(12,3)` | 否 | mm | 工件寬度 |
| `height_mm` | `NUMERIC(12,3)` | 否 | mm | 工件高度／厚度 |
| `notes` | `TEXT` | 否 | — | 工件裝夾與外觀備註 |
| `created_at` | `TIMESTAMPTZ` | 是 | — | 工件樣本建檔時間 |
| `workpiece_serial_no` | `TEXT` | 否 | — | 實體工件序號 |
| `surface_condition` | `TEXT` | 否 | — | 工件表面狀態（量測前） |
| `material_certificate_uri` | `TEXT` | 否 | — | 材料證明／檢測報告檔案位置 |

### `tool_instances` — 實體刀具識別與使用狀況

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `tool_instance_id` | `UUID` | 是 | — | 實體刀具唯一識別碼 |
| `tool_id` | `UUID` | 是 | — | 所屬刀具型號 |
| `instance_code` | `TEXT` | 是 | — | 實體刀具編號，例如 TOOL-001 |
| `manufacturer_lot_no` | `TEXT` | 否 | — | 刀具出廠批次 |
| `first_used_at` | `TIMESTAMPTZ` | 否 | — | 首次使用時間 |
| `cumulative_cutting_min` | `NUMERIC(12,3)` | 是 | min | 目前累積實際切削分鐘數；須由應用程式更新 |
| `is_active` | `BOOLEAN` | 是 | — | 是否仍在使用 |
| `notes` | `TEXT` | 否 | — | 實體刀具備註 |
| `created_at` | `TIMESTAMPTZ` | 是 | — | 刀具建檔時間 |
| `life_cycle_status` | `TEXT` | 是 | — | 實際刀具使用階段（非模型聲學判定） |

### `tool_setups` — 刀具裝夾與伸出量

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `tool_setup_id` | `UUID` | 是 | — | 本次裝夾配置唯一識別碼 |
| `setup_code` | `TEXT` | 是 | — | 裝夾配置編號 |
| `tool_instance_id` | `UUID` | 是 | — | 被裝夾的實體刀具 |
| `tool_id` | `UUID` | 是 | — | 刀具規格 ID；複合外鍵確保符合實體刀具 |
| `machine_id` | `UUID` | 是 | — | 此裝夾配置使用的 CNC 機台 |
| `holder_type` | `TEXT` | 是 | — | 刀把種類，例如熱縮刀把、筒夾刀把 |
| `holder_code` | `TEXT` | 否 | — | 實際刀把代號 |
| `tool_overhang_mm` | `NUMERIC(10,3)` | 是 | mm | 刀具自固定基準伸出長度 |
| `gauge_length_mm` | `NUMERIC(10,3)` | 否 | mm | 刀具組合量測基準長度 |
| `clamping_method` | `TEXT` | 否 | — | 夾持方式及程序 |
| `measured_runout_um` | `NUMERIC(10,3)` | 否 | µm | 刀具組裝後量測之徑向偏擺 |
| `assembled_by` | `UUID` | 否 | — | 裝夾操作人員 |
| `assembled_at` | `TIMESTAMPTZ` | 是 | — | 裝夾完成／登錄時間 |
| `is_active` | `BOOLEAN` | 是 | — | 裝夾配置是否仍有效 |
| `notes` | `TEXT` | 否 | — | 裝夾補充資訊 |
| `holder_manufacturer` | `TEXT` | 否 | — | 刀把製造商 |
| `holder_model` | `TEXT` | 否 | — | 刀把型號 |
| `collet_or_chuck_type` | `TEXT` | 否 | — | 夾頭或筒夾種類 |
| `clamping_torque_nm` | `NUMERIC(10,3)` | 否 | N·m | 實際夾持扭矩 |
| `runout_measurement_method` | `TEXT` | 否 | — | 刀具偏擺量測方法 |

### `microphones` — 麥克風規格與實體識別

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `microphone_id` | `UUID` | 是 | — | 麥克風唯一識別碼 |
| `microphone_code` | `TEXT` | 是 | — | 麥克風代碼，例如 MIC-A001 |
| `manufacturer` | `TEXT` | 否 | — | 麥克風製造商 |
| `model` | `TEXT` | 否 | — | 麥克風型號 |
| `serial_no` | `TEXT` | 否 | — | 實體設備序號 |
| `microphone_type` | `TEXT` | 否 | — | 麥克風技術類型，例如電容式、MEMS |
| `frequency_min_hz` | `NUMERIC(12,2)` | 否 | Hz | 製造商標稱頻率響應下限 |
| `frequency_max_hz` | `NUMERIC(12,2)` | 否 | Hz | 製造商標稱頻率響應上限 |
| `nominal_sensitivity` | `NUMERIC(14,6)` | 否 | — | 標稱靈敏度數值，需搭配單位 |
| `sensitivity_unit` | `TEXT` | 否 | — | 標稱靈敏度單位，例如 mV/Pa |
| `is_active` | `BOOLEAN` | 是 | — | 麥克風是否可供使用 |
| `notes` | `TEXT` | 否 | — | 麥克風規格備註 |
| `polar_pattern` | `TEXT` | 否 | — | 麥克風指向性 |
| `connector_type` | `TEXT` | 否 | — | 麥克風接頭／供電介面 |

### `microphone_calibrations` — 麥克風校正歷史

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `calibration_id` | `UUID` | 是 | — | 校正紀錄唯一識別碼 |
| `microphone_id` | `UUID` | 是 | — | 此校正屬於哪一支實體麥克風 |
| `calibrated_at` | `TIMESTAMPTZ` | 是 | — | 實際校正日期時間 |
| `valid_until` | `TIMESTAMPTZ` | 否 | — | 校正有效期限；未提供表示未知而非永久有效 |
| `calibration_method` | `TEXT` | 是 | — | 校正程序／方法，例如聲校正器校正 |
| `sensitivity_value` | `NUMERIC(14,6)` | 否 | — | 校正後得到的靈敏度數值；不等於必然已換算為聲壓 |
| `sensitivity_unit` | `TEXT` | 否 | — | 校正靈敏度使用的單位 |
| `calibrator_code` | `TEXT` | 否 | — | 使用的校正器代碼 |
| `certificate_uri` | `TEXT` | 否 | — | 校正證書／文件位置 |
| `notes` | `TEXT` | 否 | — | 校正環境、條件或備註 |
| `created_at` | `TIMESTAMPTZ` | 是 | — | 紀錄建檔時間 |
| `calibration_frequency_hz` | `NUMERIC(12,3)` | 否 | Hz | 本次靈敏度校正使用的參考頻率 |
| `uncertainty_db` | `NUMERIC(8,4)` | 否 | dB | 校正不確定度 |
| `calibration_environment` | `JSONB` | 是 | — | 校正當下溫濕度等環境資訊 JSON |

### `recording_sessions` — 一次同步三通道錄音及當下加工條件

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `session_id` | `UUID` | 是 | — | 同步錄音 Session 唯一識別碼；三聲道共用 |
| `created_by` | `UUID` | 是 | — | 建立此 Session 的登入使用者 |
| `experiment_id` | `UUID` | 否 | — | 所屬實驗群組；舊資料允許留空 |
| `experiment_condition_id` | `UUID` | 否 | — | 所屬實驗條件組；需與 experiment_id 相符 |
| `trial_no` | `INTEGER` | 否 | — | 同一條件組中的第幾次重複錄音 |
| `machine_id` | `UUID` | 是 | — | 本次實際錄製的 CNC |
| `material_id` | `UUID` | 是 | — | 本次工件材料類型 |
| `workpiece_sample_id` | `UUID` | 否 | — | 本次實際工件；需符合 material_id |
| `tool_id` | `UUID` | 是 | — | 本次刀具型號 |
| `tool_setup_id` | `UUID` | 否 | — | 本次實體刀具裝夾；需符合 tool_id 和 machine_id |
| `preset_id` | `UUID` | 否 | — | 起始參考的加工範本，可留空 |
| `capture_device_id` | `UUID` | 是 | — | 三通道音訊設備唯一 ID |
| `process_type` | `TEXT` | 是 | — | 本次加工製程 |
| `spindle_rpm` | `NUMERIC(12,2)` | 否 | RPM | 本次設定主軸轉速；不是音訊推論或控制器實測值 |
| `feed_mm_min` | `NUMERIC(12,3)` | 否 | mm/min | 本次設定進給速度 |
| `axial_depth_mm` | `NUMERIC(10,3)` | 否 | mm | 本次設定軸向切深 ap |
| `radial_width_mm` | `NUMERIC(10,3)` | 否 | mm | 本次設定徑向切寬 ae |
| `coolant_mode` | `TEXT` | 否 | — | 本次冷卻條件 |
| `operation_name` | `TEXT` | 否 | — | 實際加工操作名稱 |
| `nc_program_code` | `TEXT` | 否 | — | 實際使用的 NC 程式編號 |
| `nc_program_revision` | `TEXT` | 否 | — | NC 程式版本／修改版次 |
| `pass_no` | `INTEGER` | 否 | — | 本次加工為第幾刀／第幾個走刀 |
| `toolpath_type` | `TEXT` | 否 | — | 實際刀具路徑類型 |
| `cutting_direction` | `TEXT` | 否 | — | 實際切削方向 |
| `feed_per_tooth_mm` | `NUMERIC(12,6)` | 否 | mm/tooth | 本次每齒進給；若自動計算要在快照標註衍生來源 |
| `cutting_speed_m_min` | `NUMERIC(12,4)` | 否 | m/min | 本次切削速度；若自動計算要在快照標註衍生來源 |
| `recording_notes` | `TEXT` | 否 | — | 現場非判定式觀察備註 |
| `condition_snapshot` | `JSONB` | 是 | — | 本次錄音條件完整不可變快照；含刀具、工件、版本與來源 |
| `channel_count` | `SMALLINT` | 是 | — | 同步聲道數；目前固定為 3 |
| `sample_rate_hz` | `INTEGER` | 是 | Hz | 採樣率；例如 48000 Hz |
| `sample_format` | `TEXT` | 是 | — | 原始 PCM 取樣格式：pcm_s16le／pcm_s24le |
| `target_duration_ms` | `INTEGER` | 否 | ms | 計畫錄音長度 |
| `capture_clock_id` | `TEXT` | 否 | — | 由錄音主機回報的共同採樣時鐘識別碼 |
| `status` | `TEXT` | 是 | — | Session 狀態：prepared／recording／finalizing／completed／interrupted／failed |
| `started_at` | `TIMESTAMPTZ` | 否 | — | 實際錄音啟動時間；供稽核，非聲源對齊基準 |
| `finished_at` | `TIMESTAMPTZ` | 否 | — | 錄音結束時間；供稽核 |
| `total_frames` | `BIGINT` | 否 | frame | 總採樣影格數；每個 frame 含三路 sample |
| `error_message` | `TEXT` | 否 | — | 錄音失敗或中斷的錯誤資訊 |
| `created_at` | `TIMESTAMPTZ` | 是 | — | Session 建立時間 |
| `session_code` | `TEXT` | 否 | — | 人類可讀的錄音編號，可不填由前端顯示 UUID |
| `operator_user_id` | `UUID` | 否 | — | 當次操作 CNC 加工的人員 ID，可與錄音建立者不同 |
| `workpiece_setup_id` | `UUID` | 否 | — | 本次工件實際夾持記錄 ID |
| `environment_temperature_c` | `NUMERIC(7,3)` | 否 | °C | 錄音環境溫度 |
| `environment_humidity_pct` | `NUMERIC(6,3)` | 否 | % | 錄音環境相對濕度 |
| `background_noise_note` | `TEXT` | 否 | — | 附近其他機台、抽風或人聲等背景噪音來源備註 |
| `machine_door_state` | `TEXT` | 否 | — | 錄音時 CNC 機門／外罩狀態 |
| `coolant_flow_l_min` | `NUMERIC(10,3)` | 否 | min | 錄音時冷卻液流量 |
| `recording_host_software_version` | `TEXT` | 否 | — | 該次使用的錄音主機軟體版本快照 |
| `host_capture_recording_id` | `TEXT` | 否 | — | 錄音主機內部的工作序號，利於重連對帳 |
| `device_lock_expires_at` | `TIMESTAMPTZ` | 否 | — | 錄音設備佔用租約到期時間（逾時需由後端解除鎖定） |
| `recording_settings` | `JSONB` | 是 | — | 本次錄音緩衝、通道順序、時鐘等額外設定 JSON |

### `recording_channels` — A/B/C 對應的實際麥克風與安裝位置

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `session_id` | `UUID` | 是 | — | 所屬同步錄音 Session |
| `channel_no` | `SMALLINT` | 是 | — | 硬體聲道位置 1、2、3 |
| `source_label` | `CHAR(1)` | 是 | — | 三路聲源代號：A、B、C |
| `microphone_code` | `TEXT` | 是 | — | 本次麥克風可讀代碼快照 |
| `microphone_id` | `UUID` | 是 | — | 對應的實體麥克風主檔 |
| `calibration_id` | `UUID` | 否 | — | 此次錄音採用的校正版本；需屬於同一麥克風 |
| `mount_position` | `TEXT` | 否 | — | 麥克風位置文字敘述，例如主軸前方 |
| `coordinate_frame` | `TEXT` | 是 | — | 三維座標基準：工件中心／主軸中心／機台原點／自訂 |
| `position_x_mm` | `NUMERIC(12,3)` | 否 | mm | 相對基準原點的 X 座標 |
| `position_y_mm` | `NUMERIC(12,3)` | 否 | mm | 相對基準原點的 Y 座標 |
| `position_z_mm` | `NUMERIC(12,3)` | 否 | mm | 相對基準原點的 Z 座標 |
| `orientation_yaw_deg` | `NUMERIC(8,3)` | 否 | ° | 麥克風收音軸的水平朝向角 |
| `orientation_pitch_deg` | `NUMERIC(8,3)` | 否 | ° | 麥克風收音軸的仰俯角 |
| `mounting_method` | `TEXT` | 否 | — | 麥克風固定方式，例如三腳架、磁座 |
| `mic_distance_mm` | `NUMERIC(10,2)` | 否 | mm | 麥克風至定義的目標點的實測距離 |
| `gain_db` | `NUMERIC(8,3)` | 否 | dB | 錄音通道增益設定值 |
| `channel_delay_samples` | `INTEGER` | 是 | sample | 已知硬體通道延遲校正量，單位為 sample |
| `cable_code` | `TEXT` | 否 | — | 收音訊號線／轉接線編號 |
| `position_measurement_method` | `TEXT` | 否 | — | 量測 X/Y/Z 位置的方式 |
| `acoustic_windscreen_used` | `BOOLEAN` | 否 | — | 是否使用麥克風防風罩 |
| `microphone_power_mode` | `TEXT` | 否 | — | 麥克風供電方式（48V／Plug-in／其他） |
| `channel_polarity_inverted` | `BOOLEAN` | 是 | — | 該通道是否設定極性反相 |

### `audio_chunks` — 錄音中寫入 SQL 的三通道 PCM 區塊

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `session_id` | `UUID` | 是 | — | 分段屬於哪次同步錄音 |
| `chunk_index` | `INTEGER` | 是 | — | 分段序號，從 0 開始 |
| `first_frame` | `BIGINT` | 是 | frame | 此分段第一個同步 frame 的絕對位置 |
| `frame_count` | `INTEGER` | 是 | frame | 此分段包含的 frame 數 |
| `sample_format` | `TEXT` | 是 | — | 音訊 PCM 位元格式 |
| `channel_count` | `SMALLINT` | 是 | — | 此分段包含的聲道數，固定 3 |
| `pcm_data` | `BYTEA` | 是 | — | 三聲道交錯 PCM 二進位內容；BYTEA |
| `sha256_hex` | `CHAR(64)` | 是 | — | 該音訊分段內容的 SHA-256 雜湊 |
| `received_at` | `TIMESTAMPTZ` | 是 | — | 伺服器收到分段的時間；不是採樣同步時間 |
| `captured_at_host` | `TIMESTAMPTZ` | 否 | — | 錄音主機回報該段起始時間（診斷用，不作同步基準） |
| `first_frame_monotonic_ns` | `BIGINT` | 否 | ns | 錄音主機單調時鐘時間戳（診斷用；同步仍以 frame index 為準） |

### `audio_assets` — 封存三通道無損音檔及其雜湊

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `asset_id` | `UUID` | 是 | — | 封存檔案的唯一 ID |
| `session_id` | `UUID` | 是 | — | 所屬同步錄音；本版每個 Session 一份原始封存檔 |
| `storage_uri` | `TEXT` | 是 | — | WAV／FLAC 原始音檔的私有儲存位置 |
| `container_format` | `TEXT` | 是 | — | 原始封裝格式：wav／flac |
| `channel_count` | `SMALLINT` | 是 | — | 音檔聲道數，固定 3 |
| `sample_rate_hz` | `INTEGER` | 是 | Hz | 音檔採樣率 |
| `total_frames` | `BIGINT` | 是 | frame | 音檔總 frame 數 |
| `file_size_bytes` | `BIGINT` | 是 | bytes | 音檔大小 |
| `sha256_hex` | `CHAR(64)` | 是 | — | 整份封存音檔的 SHA-256 |
| `archived_at` | `TIMESTAMPTZ` | 是 | — | 音檔確認封存時間 |
| `sample_format` | `TEXT` | 否 | — | 封存音訊的 PCM 位元格式 |
| `storage_state` | `TEXT` | 是 | — | 檔案封存及驗證狀態 |
| `immutable_raw` | `BOOLEAN` | 是 | — | 標示為不可改寫的原始音檔 |

### `audio_quality_checks` — 音訊完整性與品質檢查

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `quality_check_id` | `UUID` | 是 | — | 品質檢查唯一 ID |
| `session_id` | `UUID` | 是 | — | 受檢的同步錄音 |
| `checker_version` | `TEXT` | 是 | — | 品質檢查程式版本 |
| `checked_at` | `TIMESTAMPTZ` | 是 | — | 品質檢查執行時間 |
| `channel_mapping_ok` | `BOOLEAN` | 是 | — | 是否確認 A/B/C 與硬體輸入通道對應正確 |
| `common_clock_verified` | `BOOLEAN` | 是 | — | 錄音設備回報或測試確認三通道共用時鐘 |
| `missing_frames` | `BIGINT` | 是 | frame | 檢查發現的缺失 frame 數 |
| `clipping_samples_by_channel` | `JSONB` | 是 | samples | 各通道削波 sample 數 JSON，例如 {A:0,B:1,C:0} |
| `quality_status` | `TEXT` | 是 | — | 品質檢查結果：pass／warning／fail |
| `details` | `JSONB` | 是 | — | 檢查細節 JSON，例如雜湊與時序檢查結果 |
| `notes` | `TEXT` | 否 | — | 人工檢查備註 |
| `frame_sequence_ok` | `BOOLEAN` | 否 | — | 音訊分段 sample/frame 序列是否連續 |
| `sample_rate_verified` | `BOOLEAN` | 否 | — | 採樣率是否與錄音 Session 一致 |
| `corrupt_chunk_count` | `INTEGER` | 是 | — | 雜湊或長度驗證失敗的分段數 |
| `dropped_chunk_count` | `INTEGER` | 是 | — | 遺失／未收到的音訊分段數 |
| `per_channel_noise_floor_dbfs` | `JSONB` | 否 | dBFS | 各通道底噪估計值 JSON，單位 dBFS |

### `machining_parameter_events` — 錄音途中參數異動事件

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `event_id` | `BIGINT` | 是 | — | 事件流水編號 |
| `session_id` | `UUID` | 是 | — | 屬於哪一次錄音 |
| `at_frame` | `BIGINT` | 是 | frame | 變動對應的錄音採樣 frame；不能以 HTTP 抵達時間取代 |
| `parameter_name` | `TEXT` | 是 | — | 變動的加工參數名稱，例如 actual_spindle_rpm |
| `parameter_value` | `JSONB` | 是 | — | 事件值，以 JSON 表達數字或物件 |
| `parameter_unit` | `TEXT` | 否 | — | 數值單位，例如 RPM／mm/min |
| `source_reference` | `TEXT` | 否 | — | 機台控制器／感測器的來源識別碼 |
| `source` | `TEXT` | 是 | — | 來源：manual／machine_controller／sensor |
| `noted_at` | `TIMESTAMPTZ` | 是 | — | 事件被系統登錄的時間 |
| `controller_recorded_at` | `TIMESTAMPTZ` | 否 | — | CNC 控制器回報該參數事件的時間 |

### `analysis_runs` — 每次前處理／特徵／融合／推論執行紀錄

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `analysis_id` | `UUID` | 是 | — | 分析執行唯一 ID |
| `session_id` | `UUID` | 是 | — | 分析來源錄音 |
| `analysis_type` | `TEXT` | 是 | — | 分析類別：preprocess／features／fusion／inference |
| `method_name` | `TEXT` | 是 | — | 使用的分析方法，例如 butterworth_bandpass |
| `pipeline_version` | `TEXT` | 是 | — | 前處理或分析程式版本 |
| `parameters` | `JSONB` | 是 | — | 分析設定 JSON，包括濾波頻帶／FFT 視窗等 |
| `result_uri` | `TEXT` | 否 | — | 衍生音檔、圖像或模型輸出位置 |
| `status` | `TEXT` | 是 | — | 工作狀態：queued／running／completed／failed |
| `error_message` | `TEXT` | 否 | — | 分析失敗原因 |
| `created_at` | `TIMESTAMPTZ` | 是 | — | 工作建立時間 |
| `completed_at` | `TIMESTAMPTZ` | 否 | — | 工作完成時間 |
| `input_asset_id` | `UUID` | 否 | — | 本次分析所用的原始三通道音檔 ID |
| `code_commit` | `TEXT` | 否 | — | 分析程式 Git commit 版本 |
| `processing_started_at` | `TIMESTAMPTZ` | 否 | — | 分析實際啟動時間 |
| `analysis_owner_user_id` | `UUID` | 否 | — | 建立或啟動分析的人員 ID |
| `output_unit_spec` | `JSONB` | 是 | — | 輸出特徵欄位單位與校正方式 JSON |

### `channel_features` — 各聲道各視窗的聲學數值特徵

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `analysis_id` | `UUID` | 是 | — | 特徵所屬分析執行 |
| `session_id` | `UUID` | 是 | — | 來源錄音；與 analysis_id 配對核對 |
| `channel_no` | `SMALLINT` | 是 | — | 來源聲道 1、2、3 |
| `window_index` | `INTEGER` | 是 | — | 特徵分析的第幾個視窗 |
| `start_frame` | `BIGINT` | 是 | frame | 該視窗起始 frame |
| `frame_count` | `INTEGER` | 是 | frame | 視窗樣本 frame 數 |
| `rms` | `NUMERIC(16,8)` | 否 | — | 均方根振幅；未校正不得視為 dB SPL |
| `peak` | `NUMERIC(16,8)` | 否 | — | 峰值數位振幅；未校正不得視為聲壓 |
| `dominant_freq_hz` | `NUMERIC(12,4)` | 否 | Hz | 該視窗主峰頻率 |
| `spectral_centroid_hz` | `NUMERIC(12,4)` | 否 | Hz | 頻譜重心頻率 |
| `band_energy` | `JSONB` | 否 | — | 各頻帶能量 JSON，須在分析參數註明頻帶定義 |
| `mfcc` | `JSONB` | 否 | — | MFCC 向量 JSON，須記錄模型與參數版本 |
| `rms_unit` | `TEXT` | 否 | — | RMS 的單位，例如 FS／Pa（有校正才可用 Pa） |
| `peak_unit` | `TEXT` | 否 | — | Peak 的單位 |
| `crest_factor` | `NUMERIC(12,5)` | 否 | — | 峰值與 RMS 比值 |
| `spectral_flatness` | `NUMERIC(12,6)` | 否 | — | 頻譜平坦度 |
| `zero_crossing_rate` | `NUMERIC(12,6)` | 否 | — | 過零率 |
| `extra_features` | `JSONB` | 是 | — | 新增特徵的可擴充 JSON |

### `fusion_results` — 三聲源融合後的視窗特徵

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `analysis_id` | `UUID` | 是 | — | 三聲源融合分析執行 |
| `session_id` | `UUID` | 是 | — | 來源同步錄音 |
| `window_index` | `INTEGER` | 是 | — | 融合輸出的視窗序號 |
| `start_frame` | `BIGINT` | 是 | frame | 融合視窗起始 frame |
| `frame_count` | `INTEGER` | 是 | frame | 融合視窗長度 |
| `fusion_method` | `TEXT` | 是 | — | 融合策略，例如 feature_concat／weighted_feature |
| `fused_features` | `JSONB` | 是 | — | 三聲源組合後的特徵 JSON |
| `alignment_method` | `TEXT` | 否 | — | 三聲道特徵對齊方式 |
| `fusion_parameters` | `JSONB` | 是 | — | 特徵融合的方法參數 JSON |
| `fusion_quality_flags` | `JSONB` | 是 | — | 融合資料品質旗標 JSON |

### `model_predictions` — 模型推論，不是人工輸入的工況

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `prediction_id` | `UUID` | 是 | — | 推論結果唯一 ID |
| `analysis_id` | `UUID` | 是 | — | 使用哪次模型分析執行 |
| `session_id` | `UUID` | 是 | — | 來源錄音 |
| `model_name` | `TEXT` | 是 | — | 模型名稱 |
| `model_version` | `TEXT` | 是 | — | 模型版本 |
| `predicted_label` | `TEXT` | 否 | — | 模型預測的類別文字，非驗證真值 |
| `anomaly_score` | `NUMERIC(12,6)` | 否 | — | 模型輸出的異常分數 |
| `threshold` | `NUMERIC(12,6)` | 否 | — | 該次判定使用的分數門檻 |
| `output` | `JSONB` | 是 | — | 其他模型輸出 JSON，例如各類機率 |
| `predicted_at` | `TIMESTAMPTZ` | 是 | — | 模型推論時間 |
| `model_artifact_uri` | `TEXT` | 否 | — | 模型權重或檔案索引 |
| `confidence` | `NUMERIC(8,6)` | 否 | — | 模型置信度（若模型有定義） |
| `start_frame` | `BIGINT` | 否 | frame | 此預測所對應音訊視窗的起點 |
| `frame_count` | `INTEGER` | 否 | frame | 此預測所對應視窗的 frame 數 |

### `verified_labels` — 獨立量測或檢驗取得的真實標籤

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `label_id` | `UUID` | 是 | — | 驗證標籤唯一 ID |
| `session_id` | `UUID` | 是 | — | 被驗證的錄音 |
| `verification_method` | `TEXT` | 是 | — | 標籤驗證方法，例如量測、檢驗或加工紀錄 |
| `verified_label` | `TEXT` | 是 | — | 經獨立驗證的實際標籤 |
| `evidence_uri` | `TEXT` | 否 | — | 驗證報告、量測紀錄或影像的儲存位置 |
| `verified_by` | `UUID` | 否 | — | 執行驗證的人員 |
| `verified_at` | `TIMESTAMPTZ` | 是 | — | 驗證紀錄完成時間 |
| `label_scope` | `TEXT` | 是 | — | 檢驗標籤適用整段 Session 或部分視窗 |
| `start_frame` | `BIGINT` | 否 | frame | 驗證視窗第一個取樣 frame |
| `frame_count` | `INTEGER` | 否 | frame | 驗證標籤涵蓋的 frame 數 |
| `verification_notes` | `TEXT` | 否 | — | 實測／檢驗依據或備註 |

### `workpiece_setups` — 每次工件夾持姿態與治具

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `workpiece_setup_id` | `UUID` | 是 | — | 工件實際夾持記錄 UUID |
| `setup_code` | `TEXT` | 是 | — | 夾持識別代碼，不重複 |
| `workpiece_sample_id` | `UUID` | 是 | — | 本次被夾持的實體工件 |
| `machine_id` | `UUID` | 是 | — | 本次夾持所在的 CNC 機台 |
| `fixture_type` | `TEXT` | 是 | — | 夾具類型（例如虎鉗、治具） |
| `fixture_code` | `TEXT` | 否 | — | 夾具實體編號 |
| `clamping_method` | `TEXT` | 否 | — | 固定／夾緊方法 |
| `estimated_clamping_force_n` | `NUMERIC(12,3)` | 否 | N | 夾持力量（若可量測，註明估算） |
| `workpiece_orientation` | `TEXT` | 否 | — | 工件裝夾方向／基準面 |
| `fixture_notes` | `TEXT` | 否 | — | 本次裝夾備註 |
| `assembled_by` | `UUID` | 否 | — | 工件裝夾操作者 ID |
| `assembled_at` | `TIMESTAMPTZ` | 是 | — | 夾持安裝時間 |
| `is_active` | `BOOLEAN` | 是 | — | 該裝夾是否仍有效 |

### `recording_control_events` — 手機指令與錄音主機回應紀錄

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `control_event_id` | `BIGINT` | 是 | — | 錄音控制事件流水號 |
| `session_id` | `UUID` | 是 | — | 對應錄音 Session |
| `command_id` | `UUID` | 是 | — | 去重用的指令 UUID，網路重傳不得重複執行 |
| `command` | `TEXT` | 是 | — | 錄音控制指令（prepare、start、stop 等） |
| `issued_by` | `UUID` | 否 | — | 發出指令的使用者 ID |
| `issued_at` | `TIMESTAMPTZ` | 是 | — | 指令發送時間 |
| `acknowledged_at` | `TIMESTAMPTZ` | 否 | — | 錄音主機確認時間 |
| `command_status` | `TEXT` | 是 | — | 控制指令執行狀態 |
| `recorder_response` | `JSONB` | 是 | — | 錄音主機回應 JSON，例如時鐘 ID／錯誤碼 |
| `error_message` | `TEXT` | 否 | — | 失敗原因 |

### `machine_telemetry_samples` — CNC 實際運轉數值依音訊取樣位置對齊

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `telemetry_id` | `BIGINT` | 是 | — | CNC 控制器量測紀錄流水號 |
| `session_id` | `UUID` | 是 | — | 對應錄音 Session |
| `audio_frame` | `BIGINT` | 是 | frame | 對齊三通道音訊的 sample/frame 位置 |
| `measured_at` | `TIMESTAMPTZ` | 否 | — | 量測裝置回報時間 |
| `actual_spindle_rpm` | `NUMERIC(12,3)` | 否 | RPM | 實際主軸轉速 |
| `actual_feed_mm_min` | `NUMERIC(12,4)` | 否 | mm/min | 實際進給速度 |
| `spindle_load_pct` | `NUMERIC(7,3)` | 否 | % | 主軸負載百分比 |
| `spindle_power_kw` | `NUMERIC(12,4)` | 否 | kW | 主軸功率 |
| `controller_state` | `TEXT` | 否 | — | CNC 控制器工作狀態（非聲學 AI 判定） |
| `extra_measurements` | `JSONB` | 是 | — | 可擴充 CNC 訊號 JSON |
| `measured_source` | `TEXT` | 是 | — | 數值來源，例如 CNC 控制器 |
| `created_at` | `TIMESTAMPTZ` | 是 | — | 該筆量測資料寫入時間 |

### `analysis_artifacts` — 大容量衍生音訊、FFT／STFT 圖檔位置與雜湊

| 欄位 | SQL 型別 | 必填 | 單位 | 用途與說明 |
|---|---|---|---|---|
| `artifact_id` | `UUID` | 是 | — | 衍生分析檔案唯一 ID |
| `analysis_id` | `UUID` | 是 | — | 產生此檔案的分析 Run |
| `session_id` | `UUID` | 是 | — | 所屬錄音 Session |
| `channel_no` | `SMALLINT` | 否 | — | 若屬單一聲道則填 A/B/C 對應數字；跨聲道則留空 |
| `artifact_kind` | `TEXT` | 是 | — | 檔案種類：濾波音訊、FFT、STFT、圖像預覽等 |
| `storage_uri` | `TEXT` | 是 | — | 衍生檔案儲存位置，不覆蓋原始音檔 |
| `mime_type` | `TEXT` | 否 | — | 檔案內容類型 |
| `shape_json` | `JSONB` | 否 | — | 矩陣長寬、軸單位、窗長等 JSON |
| `sha256_hex` | `CHAR(64)` | 否 | — | 衍生檔案雜湊值 |
| `produced_at` | `TIMESTAMPTZ` | 是 | — | 檔案生成時間 |

## 特別注意事項

1. `recording_sessions` 是錄音當下加工條件的快照；`machining_presets` 可以編輯，但不得回寫已開始的 Session。
2. `recording_channels` 的 1/2/3 必須分別對應 A/B/C；錄音開始前由 API 驗證三筆全數存在。
3. `audio_chunks.pcm_data` 是每秒一次、三通道交錯 PCM BYTEA；`first_frame` 是共同採樣時間軸，網路接收時間不是同步基準。
4. `audio_assets.storage_uri` 指向封存原始音檔；FFT、濾波後的衍生大檔存 `analysis_artifacts`，不覆寫原檔。
5. 音訊的 dBFS、數位 RMS 與已校正的 Pa／dB SPL 不可混用。
6. `model_predictions` 是模型預測，`verified_labels` 是額外證據取得的真實驗證資料，兩者必須分開。
7. 此為 SQL 結構與欄位解釋，尚須由 FastAPI 檢查錄音硬體、三通道完整性、CRC/SHA256、分段連續性、同步時鐘及寫入權限。
