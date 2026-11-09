# V1.2 DDL 結構清單

28 張表，423 欄。外鍵箭頭由引用端指向被引用端。

| 表 | 欄數 | 主鍵 | 外鍵 |
|---|---:|---|---|
| app_users | 6 | user_id |  |
| machines | 16 | machine_id |  |
| materials | 9 | material_id |  |
| cutting_tools | 16 | tool_id |  |
| capture_devices | 18 | device_id |  |
| machining_presets | 25 | preset_id | machine_id → machines(machine_id)<br>material_id → materials(material_id)<br>tool_id → cutting_tools(tool_id) |
| experiments | 12 | experiment_id | owner_user_id → app_users(user_id) |
| experiment_conditions | 11 | condition_id | experiment_id → experiments(experiment_id)<br>preset_id → machining_presets(preset_id) |
| workpiece_samples | 15 | workpiece_sample_id | material_id → materials(material_id) |
| tool_instances | 10 | tool_instance_id | tool_id → cutting_tools(tool_id) |
| tool_setups | 20 | tool_setup_id | machine_id → machines(machine_id)<br>assembled_by → app_users(user_id)<br>tool_instance_id, tool_id → tool_instances(tool_instance_id, tool_id) |
| microphones | 14 | microphone_id |  |
| microphone_calibrations | 14 | calibration_id | microphone_id → microphones(microphone_id) |
| recording_sessions | 51 | session_id | created_by → app_users(user_id)<br>experiment_id → experiments(experiment_id)<br>machine_id → machines(machine_id)<br>material_id → materials(material_id)<br>tool_id → cutting_tools(tool_id)<br>preset_id → machining_presets(preset_id)<br>capture_device_id → capture_devices(device_id)<br>experiment_condition_id, experiment_id → experiment_conditions(condition_id, experiment_id)<br>workpiece_sample_id, material_id → workpiece_samples(workpiece_sample_id, material_id)<br>tool_setup_id, tool_id, machine_id → tool_setups(tool_setup_id, tool_id, machine_id)<br>operator_user_id → app_users(user_id)<br>workpiece_setup_id, workpiece_sample_id, machine_id → workpiece_setups(workpiece_setup_id, workpiece_sample_id, machine_id) |
| recording_channels | 22 | session_id, channel_no | session_id → recording_sessions(session_id)<br>microphone_id → microphones(microphone_id)<br>calibration_id, microphone_id → microphone_calibrations(calibration_id, microphone_id) |
| audio_chunks | 11 | session_id, chunk_index | session_id → recording_sessions(session_id) |
| audio_assets | 13 | asset_id | session_id → recording_sessions(session_id) |
| audio_quality_checks | 16 | quality_check_id | session_id → recording_sessions(session_id) |
| machining_parameter_events | 10 | event_id | session_id → recording_sessions(session_id) |
| analysis_runs | 16 | analysis_id | session_id → recording_sessions(session_id)<br>input_asset_id → audio_assets(asset_id)<br>analysis_owner_user_id → app_users(user_id) |
| channel_features | 18 | analysis_id, channel_no, window_index | analysis_id, session_id → analysis_runs(analysis_id, session_id)<br>session_id, channel_no → recording_channels(session_id, channel_no) |
| fusion_results | 10 | analysis_id, window_index | analysis_id, session_id → analysis_runs(analysis_id, session_id) |
| model_predictions | 14 | prediction_id | analysis_id, session_id → analysis_runs(analysis_id, session_id) |
| verified_labels | 11 | label_id | session_id → recording_sessions(session_id)<br>verified_by → app_users(user_id) |
| workpiece_setups | 13 | workpiece_setup_id | workpiece_sample_id → workpiece_samples(workpiece_sample_id)<br>machine_id → machines(machine_id)<br>assembled_by → app_users(user_id) |
| recording_control_events | 10 | control_event_id | session_id → recording_sessions(session_id)<br>issued_by → app_users(user_id) |
| machine_telemetry_samples | 12 | telemetry_id | session_id → recording_sessions(session_id) |
| analysis_artifacts | 10 | artifact_id | analysis_id, session_id → analysis_runs(analysis_id, session_id)<br>session_id, channel_no → recording_channels(session_id, channel_no) |
