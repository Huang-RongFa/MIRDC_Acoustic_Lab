-- CNC Acoustic Lab | PostgreSQL schema v1.2 (NEW database, includes ALL prior v1.1 columns)
-- Design: 3 microphone inputs, ONE shared capture clock / ONE session,
--         synchronized three-channel interleaved PCM chunks while recording.
-- Use PostgreSQL 14+; execute with a role permitted to CREATE tables.
-- Fresh install ONLY. Do not apply this file to an existing database with data.
-- This file creates tables only; it does not migrate the old SQLite schema.
BEGIN;

CREATE TABLE app_users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'researcher'
        CHECK (role IN ('admin','researcher')),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE machines (
    machine_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    machine_code TEXT NOT NULL UNIQUE,
    machine_name TEXT NOT NULL,
    machine_type TEXT,
    manufacturer TEXT,
    model TEXT,
    controller_model TEXT,
    spindle_max_rpm NUMERIC(12,2) CHECK (spindle_max_rpm > 0),
    spindle_power_kw NUMERIC(12,3) CHECK (spindle_power_kw > 0),
    location TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE materials (
    material_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    material_code TEXT NOT NULL UNIQUE,
    material_name TEXT NOT NULL,
    specification TEXT,
    material_grade TEXT,
    material_standard TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE cutting_tools (
    tool_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_code TEXT NOT NULL UNIQUE,
    tool_name TEXT NOT NULL,
    tool_type TEXT NOT NULL,
    tool_material TEXT,
    manufacturer TEXT,
    model TEXT,
    coating_type TEXT,
    corner_radius_mm NUMERIC(10,3) CHECK (corner_radius_mm >= 0),
    helix_angle_deg NUMERIC(8,3) CHECK (helix_angle_deg BETWEEN 0 AND 90),
    diameter_mm NUMERIC(10,3) CHECK (diameter_mm > 0),
    flute_count SMALLINT CHECK (flute_count > 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE capture_devices (
    device_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    device_code TEXT NOT NULL UNIQUE,
    device_name TEXT NOT NULL,
    input_channel_capacity SMALLINT NOT NULL CHECK (input_channel_capacity >= 3),
    shared_clock BOOLEAN NOT NULL DEFAULT TRUE,
    manufacturer TEXT,
    model TEXT,
    interface_serial_no TEXT,
    recording_host_name TEXT,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

-- Presets are editable. Sessions store a COPY of the actual parameters.
CREATE TABLE machining_presets (
    preset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    preset_name TEXT NOT NULL UNIQUE,
    machine_id UUID REFERENCES machines(machine_id) ON DELETE RESTRICT,
    material_id UUID REFERENCES materials(material_id) ON DELETE RESTRICT,
    tool_id UUID REFERENCES cutting_tools(tool_id) ON DELETE RESTRICT,
    process_type TEXT NOT NULL
        CHECK (process_type IN ('milling','turning','drilling','other')),
    spindle_rpm NUMERIC(12,2) CHECK (spindle_rpm >= 0),
    feed_mm_min NUMERIC(12,3) CHECK (feed_mm_min >= 0),
    axial_depth_mm NUMERIC(10,3) CHECK (axial_depth_mm >= 0),
    radial_width_mm NUMERIC(10,3) CHECK (radial_width_mm >= 0),
    coolant_mode TEXT CHECK (coolant_mode IN ('dry','wet','mql','other')),
    operation_name TEXT,
    nc_program_code TEXT,
    toolpath_type TEXT,
    cutting_direction TEXT CHECK (cutting_direction IN ('climb','conventional','not_applicable','other')),
    feed_per_tooth_mm NUMERIC(12,6) CHECK (feed_per_tooth_mm >= 0),
    cutting_speed_m_min NUMERIC(12,4) CHECK (cutting_speed_m_min >= 0),
    extra_params JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(extra_params) = 'object'),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- RESEARCH ORGANIZATION: one experiment can contain multiple planned conditions
-- and repeated synchronous three-channel recording sessions.
CREATE TABLE experiments (
    experiment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_code TEXT NOT NULL UNIQUE,
    experiment_name TEXT NOT NULL,
    research_objective TEXT,
    owner_user_id UUID NOT NULL REFERENCES app_users(user_id) ON DELETE RESTRICT,
    status TEXT NOT NULL DEFAULT 'planned'
        CHECK (status IN ('planned','active','closed','archived')),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ
);

CREATE TABLE experiment_conditions (
    condition_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id UUID NOT NULL REFERENCES experiments(experiment_id) ON DELETE RESTRICT,
    condition_code TEXT NOT NULL,
    condition_name TEXT NOT NULL,
    preset_id UUID REFERENCES machining_presets(preset_id) ON DELETE SET NULL,
    planned_parameters JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(planned_parameters) = 'object'),
    planned_repeats INTEGER CHECK (planned_repeats > 0),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (experiment_id, condition_code),
    UNIQUE (condition_id, experiment_id)
);

-- Each physical workpiece and each physical tool is traceable independently
-- from the catalog specification (material grade/tool model).
CREATE TABLE workpiece_samples (
    workpiece_sample_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sample_code TEXT NOT NULL UNIQUE,
    material_id UUID NOT NULL REFERENCES materials(material_id) ON DELETE RESTRICT,
    batch_no TEXT,
    heat_treatment TEXT,
    hardness_value NUMERIC(10,3) CHECK (hardness_value >= 0),
    hardness_scale TEXT CHECK (hardness_scale IN ('HB','HRC','HRB','HV','other')),
    length_mm NUMERIC(12,3) CHECK (length_mm > 0),
    width_mm NUMERIC(12,3) CHECK (width_mm > 0),
    height_mm NUMERIC(12,3) CHECK (height_mm > 0),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workpiece_sample_id, material_id),
    CONSTRAINT workpiece_hardness_pair CHECK (
        (hardness_value IS NULL) = (hardness_scale IS NULL)
    )
);

CREATE TABLE tool_instances (
    tool_instance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tool_id UUID NOT NULL REFERENCES cutting_tools(tool_id) ON DELETE RESTRICT,
    instance_code TEXT NOT NULL UNIQUE,
    manufacturer_lot_no TEXT,
    first_used_at TIMESTAMPTZ,
    cumulative_cutting_min NUMERIC(12,3) NOT NULL DEFAULT 0
        CHECK (cumulative_cutting_min >= 0),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tool_instance_id, tool_id)
);

-- Tool setup is an actual physical mounting, associated with machine and tool.
CREATE TABLE tool_setups (
    tool_setup_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    setup_code TEXT NOT NULL UNIQUE,
    tool_instance_id UUID NOT NULL,
    tool_id UUID NOT NULL,
    machine_id UUID NOT NULL REFERENCES machines(machine_id) ON DELETE RESTRICT,
    holder_type TEXT NOT NULL,
    holder_code TEXT,
    tool_overhang_mm NUMERIC(10,3) NOT NULL CHECK (tool_overhang_mm > 0),
    gauge_length_mm NUMERIC(10,3) CHECK (gauge_length_mm > 0),
    clamping_method TEXT,
    measured_runout_um NUMERIC(10,3) CHECK (measured_runout_um >= 0),
    assembled_by UUID REFERENCES app_users(user_id) ON DELETE RESTRICT,
    assembled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    FOREIGN KEY (tool_instance_id, tool_id)
        REFERENCES tool_instances(tool_instance_id, tool_id) ON DELETE RESTRICT,
    UNIQUE (tool_setup_id, tool_id, machine_id)
);

-- Calibration is versioned; the recording channel binds the calibration used
-- at acquisition and keeps actual placement coordinates for each session.
CREATE TABLE microphones (
    microphone_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    microphone_code TEXT NOT NULL UNIQUE,
    manufacturer TEXT,
    model TEXT,
    serial_no TEXT,
    microphone_type TEXT,
    frequency_min_hz NUMERIC(12,2) CHECK (frequency_min_hz > 0),
    frequency_max_hz NUMERIC(12,2) CHECK (frequency_max_hz > 0),
    nominal_sensitivity NUMERIC(14,6),
    sensitivity_unit TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    notes TEXT,
    CONSTRAINT microphone_freq_bounds CHECK (
        frequency_min_hz IS NULL OR frequency_max_hz IS NULL OR
        frequency_min_hz < frequency_max_hz
    ),
    CONSTRAINT microphone_sensitivity_pair CHECK (
        (nominal_sensitivity IS NULL) = (sensitivity_unit IS NULL)
    )
);

CREATE TABLE microphone_calibrations (
    calibration_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    microphone_id UUID NOT NULL REFERENCES microphones(microphone_id) ON DELETE RESTRICT,
    calibrated_at TIMESTAMPTZ NOT NULL,
    valid_until TIMESTAMPTZ,
    calibration_method TEXT NOT NULL,
    sensitivity_value NUMERIC(14,6),
    sensitivity_unit TEXT,
    calibrator_code TEXT,
    certificate_uri TEXT,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (calibration_id, microphone_id),
    CONSTRAINT calibration_valid_dates CHECK (
        valid_until IS NULL OR valid_until > calibrated_at
    ),
    CONSTRAINT calibration_sensitivity_pair CHECK (
        (sensitivity_value IS NULL) = (sensitivity_unit IS NULL)
    )
);

-- The unit of synchronized acquisition is ONE session, not 3 separate recordings.
CREATE TABLE recording_sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_by UUID NOT NULL REFERENCES app_users(user_id) ON DELETE RESTRICT,
    experiment_id UUID REFERENCES experiments(experiment_id) ON DELETE RESTRICT,
    experiment_condition_id UUID,
    trial_no INTEGER CHECK (trial_no > 0),
    machine_id UUID NOT NULL REFERENCES machines(machine_id) ON DELETE RESTRICT,
    material_id UUID NOT NULL REFERENCES materials(material_id) ON DELETE RESTRICT,
    workpiece_sample_id UUID,
    tool_id UUID NOT NULL REFERENCES cutting_tools(tool_id) ON DELETE RESTRICT,
    tool_setup_id UUID,
    preset_id UUID REFERENCES machining_presets(preset_id) ON DELETE SET NULL,
    capture_device_id UUID NOT NULL REFERENCES capture_devices(device_id) ON DELETE RESTRICT,
    process_type TEXT NOT NULL
        CHECK (process_type IN ('milling','turning','drilling','other')),
    spindle_rpm NUMERIC(12,2) CHECK (spindle_rpm >= 0),
    feed_mm_min NUMERIC(12,3) CHECK (feed_mm_min >= 0),
    axial_depth_mm NUMERIC(10,3) CHECK (axial_depth_mm >= 0),
    radial_width_mm NUMERIC(10,3) CHECK (radial_width_mm >= 0),
    coolant_mode TEXT CHECK (coolant_mode IN ('dry','wet','mql','other')),
    operation_name TEXT,
    nc_program_code TEXT,
    nc_program_revision TEXT,
    pass_no INTEGER CHECK (pass_no > 0),
    toolpath_type TEXT,
    cutting_direction TEXT CHECK (cutting_direction IN ('climb','conventional','not_applicable','other')),
    feed_per_tooth_mm NUMERIC(12,6) CHECK (feed_per_tooth_mm >= 0),
    cutting_speed_m_min NUMERIC(12,4) CHECK (cutting_speed_m_min >= 0),
    recording_notes TEXT,
    -- Freeze material/tool labels, values, microphone layout and other metadata.
    condition_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(condition_snapshot) = 'object'),
    channel_count SMALLINT NOT NULL DEFAULT 3 CHECK (channel_count = 3),
    sample_rate_hz INTEGER NOT NULL DEFAULT 48000 CHECK (sample_rate_hz > 0),
    sample_format TEXT NOT NULL DEFAULT 'pcm_s16le'
        CHECK (sample_format IN ('pcm_s16le','pcm_s24le')),
    target_duration_ms INTEGER CHECK (target_duration_ms > 0),
    -- Device-defined capture clock identifier; do not infer synchronization from HTTP timestamps.
    capture_clock_id TEXT, -- supplied by recording host at successful start
    status TEXT NOT NULL DEFAULT 'prepared'
        CHECK (status IN ('prepared','recording','finalizing','completed','interrupted','failed')),
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    total_frames BIGINT CHECK (total_frames >= 0),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT valid_session_times CHECK (
        finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at
    ),
    CONSTRAINT capture_clock_required_after_start CHECK (
        status NOT IN ('recording','finalizing','completed')
        OR (started_at IS NOT NULL AND capture_clock_id IS NOT NULL)
    ),
    CONSTRAINT completed_session_has_media_extent CHECK (
        status <> 'completed'
        OR (started_at IS NOT NULL AND finished_at IS NOT NULL AND total_frames > 0)
    ),
    CONSTRAINT condition_requires_experiment CHECK (
        experiment_condition_id IS NULL OR experiment_id IS NOT NULL
    ),
    CONSTRAINT trial_requires_experiment CHECK (
        trial_no IS NULL OR experiment_id IS NOT NULL
    ),
    FOREIGN KEY (experiment_condition_id, experiment_id)
        REFERENCES experiment_conditions(condition_id, experiment_id) ON DELETE RESTRICT,
    FOREIGN KEY (workpiece_sample_id, material_id)
        REFERENCES workpiece_samples(workpiece_sample_id, material_id) ON DELETE RESTRICT,
    FOREIGN KEY (tool_setup_id, tool_id, machine_id)
        REFERENCES tool_setups(tool_setup_id, tool_id, machine_id) ON DELETE RESTRICT
);

-- Prevent multiple users from starting simultaneous sessions on one capture device.
CREATE UNIQUE INDEX one_active_session_per_device
    ON recording_sessions(capture_device_id)
    WHERE status IN ('prepared','recording','finalizing');
CREATE INDEX recording_sessions_machine_time_idx
    ON recording_sessions(machine_id, created_at DESC);
CREATE INDEX recording_sessions_user_time_idx
    ON recording_sessions(created_by, created_at DESC);
CREATE INDEX experiment_conditions_experiment_idx
    ON experiment_conditions(experiment_id);
CREATE INDEX tool_setups_instance_idx
    ON tool_setups(tool_instance_id);
CREATE INDEX microphone_calibrations_mic_idx
    ON microphone_calibrations(microphone_id, calibrated_at DESC);
CREATE INDEX recording_sessions_experiment_idx
    ON recording_sessions(experiment_id, experiment_condition_id, trial_no);
CREATE UNIQUE INDEX unique_condition_trial
    ON recording_sessions(experiment_condition_id, trial_no)
    WHERE experiment_condition_id IS NOT NULL AND trial_no IS NOT NULL;

-- Exactly three distinct channel positions must be present before capture starts.
-- DB guarantees at most 3; FastAPI must validate that A, B, C ALL exist.
CREATE TABLE recording_channels (
    session_id UUID NOT NULL REFERENCES recording_sessions(session_id) ON DELETE RESTRICT,
    channel_no SMALLINT NOT NULL CHECK (channel_no BETWEEN 1 AND 3),
    source_label CHAR(1) NOT NULL CHECK (source_label IN ('A','B','C')),
    microphone_code TEXT NOT NULL, -- frozen human-readable code
    microphone_id UUID NOT NULL REFERENCES microphones(microphone_id) ON DELETE RESTRICT,
    calibration_id UUID,
    mount_position TEXT,
    coordinate_frame TEXT NOT NULL DEFAULT 'workpiece_center'
        CHECK (coordinate_frame IN ('workpiece_center','spindle_center','machine_origin','custom')),
    position_x_mm NUMERIC(12,3),
    position_y_mm NUMERIC(12,3),
    position_z_mm NUMERIC(12,3),
    orientation_yaw_deg NUMERIC(8,3) CHECK (orientation_yaw_deg BETWEEN -180 AND 180),
    orientation_pitch_deg NUMERIC(8,3) CHECK (orientation_pitch_deg BETWEEN -90 AND 90),
    mounting_method TEXT,
    mic_distance_mm NUMERIC(10,2) CHECK (mic_distance_mm >= 0),
    gain_db NUMERIC(8,3),
    channel_delay_samples INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (session_id, channel_no),
    FOREIGN KEY (calibration_id, microphone_id)
        REFERENCES microphone_calibrations(calibration_id, microphone_id) ON DELETE RESTRICT,
    UNIQUE (session_id, source_label),
    CONSTRAINT channel_label_mapping CHECK (
       (channel_no = 1 AND source_label = 'A') OR
       (channel_no = 2 AND source_label = 'B') OR
       (channel_no = 3 AND source_label = 'C')
    )
);

-- Payload is ONE interleaved 3-channel PCM block, NOT 3 unrelated audio files.
-- It can be stored in SQL while recording; archive to an external 3-channel WAV later.
CREATE TABLE audio_chunks (
    session_id UUID NOT NULL REFERENCES recording_sessions(session_id) ON DELETE RESTRICT,
    chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
    first_frame BIGINT NOT NULL CHECK (first_frame >= 0),
    frame_count INTEGER NOT NULL CHECK (frame_count > 0),
    sample_format TEXT NOT NULL CHECK (sample_format IN ('pcm_s16le','pcm_s24le')),
    channel_count SMALLINT NOT NULL DEFAULT 3 CHECK (channel_count = 3),
    pcm_data BYTEA NOT NULL,
    sha256_hex CHAR(64) NOT NULL CHECK (sha256_hex ~ '^[0-9a-f]{64}$'),
    received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (session_id, chunk_index),
    CONSTRAINT chunk_payload_size_matches_pcm CHECK (
        octet_length(pcm_data) = frame_count * channel_count *
          CASE WHEN sample_format = 'pcm_s16le' THEN 2 ELSE 3 END
    )
);
CREATE INDEX audio_chunks_frame_idx
    ON audio_chunks(session_id, first_frame);

-- One final archived lossless 3-channel audio asset per session.
CREATE TABLE audio_assets (
    asset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL UNIQUE REFERENCES recording_sessions(session_id) ON DELETE RESTRICT,
    storage_uri TEXT NOT NULL,
    container_format TEXT NOT NULL DEFAULT 'wav'
        CHECK (container_format IN ('wav','flac')),
    channel_count SMALLINT NOT NULL DEFAULT 3 CHECK (channel_count = 3),
    sample_rate_hz INTEGER NOT NULL CHECK (sample_rate_hz > 0),
    total_frames BIGINT NOT NULL CHECK (total_frames > 0),
    file_size_bytes BIGINT NOT NULL CHECK (file_size_bytes > 0),
    sha256_hex CHAR(64) NOT NULL CHECK (sha256_hex ~ '^[0-9a-f]{64}$'),
    archived_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- Post-capture quality assurance; processing/prediction must not overwrite raw data.
CREATE TABLE audio_quality_checks (
    quality_check_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES recording_sessions(session_id) ON DELETE RESTRICT,
    checker_version TEXT NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    channel_mapping_ok BOOLEAN NOT NULL,
    common_clock_verified BOOLEAN NOT NULL,
    missing_frames BIGINT NOT NULL DEFAULT 0 CHECK (missing_frames >= 0),
    clipping_samples_by_channel JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(clipping_samples_by_channel) = 'object'),
    quality_status TEXT NOT NULL CHECK (quality_status IN ('pass','warning','fail')),
    details JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(details) = 'object'),
    notes TEXT,
    UNIQUE (session_id, checker_version)
);
CREATE INDEX audio_quality_checks_session_idx
    ON audio_quality_checks(session_id, checked_at DESC);

-- For time-varying machining conditions, annotate the specific sample frame.
CREATE TABLE machining_parameter_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES recording_sessions(session_id) ON DELETE RESTRICT,
    at_frame BIGINT NOT NULL CHECK (at_frame >= 0),
    parameter_name TEXT NOT NULL,
    parameter_value JSONB NOT NULL,
    parameter_unit TEXT,
    source_reference TEXT,
    source TEXT NOT NULL DEFAULT 'manual'
        CHECK (source IN ('manual','machine_controller','sensor')),
    noted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX machining_parameter_events_session_idx
    ON machining_parameter_events(session_id, at_frame);

-- Derived signals and features must never overwrite the original chunks/asset.
CREATE TABLE analysis_runs (
    analysis_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES recording_sessions(session_id) ON DELETE RESTRICT,
    analysis_type TEXT NOT NULL
        CHECK (analysis_type IN ('preprocess','features','fusion','inference')),
    method_name TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    parameters JSONB NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(parameters) = 'object'),
    result_uri TEXT, -- optional derived waveform, spectrogram, model artifact, etc.
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','running','completed','failed')),
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    UNIQUE (analysis_id, session_id)
);
CREATE INDEX analysis_runs_session_idx
    ON analysis_runs(session_id, created_at DESC);

CREATE TABLE channel_features (
    analysis_id UUID NOT NULL,
    session_id UUID NOT NULL,
    channel_no SMALLINT NOT NULL,
    window_index INTEGER NOT NULL CHECK (window_index >= 0),
    start_frame BIGINT NOT NULL CHECK (start_frame >= 0),
    frame_count INTEGER NOT NULL CHECK (frame_count > 0),
    rms NUMERIC(16,8) CHECK (rms >= 0),
    peak NUMERIC(16,8) CHECK (peak >= 0),
    dominant_freq_hz NUMERIC(12,4) CHECK (dominant_freq_hz >= 0),
    spectral_centroid_hz NUMERIC(12,4) CHECK (spectral_centroid_hz >= 0),
    band_energy JSONB,
    mfcc JSONB,
    PRIMARY KEY (analysis_id, channel_no, window_index),
    FOREIGN KEY (analysis_id, session_id)
        REFERENCES analysis_runs(analysis_id, session_id) ON DELETE RESTRICT,
    FOREIGN KEY (session_id, channel_no)
        REFERENCES recording_channels(session_id, channel_no) ON DELETE RESTRICT
);

CREATE TABLE fusion_results (
    analysis_id UUID NOT NULL,
    session_id UUID NOT NULL,
    window_index INTEGER NOT NULL CHECK (window_index >= 0),
    start_frame BIGINT NOT NULL CHECK (start_frame >= 0),
    frame_count INTEGER NOT NULL CHECK (frame_count > 0),
    fusion_method TEXT NOT NULL,
    fused_features JSONB NOT NULL,
    PRIMARY KEY (analysis_id, window_index),
    FOREIGN KEY (analysis_id, session_id)
        REFERENCES analysis_runs(analysis_id, session_id) ON DELETE RESTRICT
);

-- Model estimates are NEVER input machining conditions.
CREATE TABLE model_predictions (
    prediction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analysis_id UUID NOT NULL,
    session_id UUID NOT NULL,
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    predicted_label TEXT, -- e.g. normal/suspected_anomaly/unknown
    anomaly_score NUMERIC(12,6),
    threshold NUMERIC(12,6),
    output JSONB NOT NULL DEFAULT '{}'::jsonb,
    predicted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (analysis_id, session_id)
        REFERENCES analysis_runs(analysis_id, session_id) ON DELETE RESTRICT
);

-- Independent verification / ground-truth labels (not inferred labels).
CREATE TABLE verified_labels (
    label_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL REFERENCES recording_sessions(session_id) ON DELETE RESTRICT,
    verification_method TEXT NOT NULL, -- inspection, metrology, process log, etc.
    verified_label TEXT NOT NULL,
    evidence_uri TEXT,
    verified_by UUID REFERENCES app_users(user_id) ON DELETE RESTRICT,
    verified_at TIMESTAMPTZ NOT NULL DEFAULT now()
);



-- ================================================================
-- V1.2: additional collection fields and domain entities.
-- All statements below are part of ONE clean fresh-install transaction.
-- ================================================================

-- Machine inventory (metadata, not acoustic ground truth).
ALTER TABLE machines
  ADD COLUMN machine_serial_no TEXT,
  ADD COLUMN axis_count SMALLINT CHECK (axis_count > 0),
  ADD COLUMN machine_enclosure TEXT,
  ADD COLUMN commissioning_date DATE;

ALTER TABLE materials
  ADD COLUMN material_family TEXT,
  ADD COLUMN nominal_density_kg_m3 NUMERIC(12,3) CHECK (nominal_density_kg_m3 > 0);

ALTER TABLE cutting_tools
  ADD COLUMN cutting_edge_length_mm NUMERIC(10,3) CHECK (cutting_edge_length_mm > 0),
  ADD COLUMN edge_radius_um NUMERIC(10,3) CHECK (edge_radius_um >= 0),
  ADD COLUMN nominal_tool_length_mm NUMERIC(10,3) CHECK (nominal_tool_length_mm > 0);

ALTER TABLE capture_devices
  ADD COLUMN recording_host_os TEXT,
  ADD COLUMN audio_driver_version TEXT,
  ADD COLUMN firmware_version TEXT,
  ADD COLUMN recording_service_version TEXT,
  ADD COLUMN supported_sample_rates_hz INTEGER[],
  ADD COLUMN input_channel_map JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(input_channel_map) = 'object'),
  ADD COLUMN last_seen_at TIMESTAMPTZ;

ALTER TABLE machining_presets
  ADD COLUMN nc_program_revision TEXT,
  ADD COLUMN pass_no INTEGER CHECK (pass_no > 0),
  ADD COLUMN fixture_type TEXT,
  ADD COLUMN workholding_method TEXT,
  ADD COLUMN notes TEXT;

ALTER TABLE experiments
  ADD COLUMN research_protocol_version TEXT,
  ADD COLUMN study_location TEXT,
  ADD COLUMN target_sample_rate_hz INTEGER CHECK (target_sample_rate_hz > 0);

ALTER TABLE experiment_conditions
  ADD COLUMN condition_factors JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(condition_factors) = 'object'),
  ADD COLUMN randomized_order INTEGER CHECK (randomized_order > 0);

ALTER TABLE workpiece_samples
  ADD COLUMN workpiece_serial_no TEXT,
  ADD COLUMN surface_condition TEXT,
  ADD COLUMN material_certificate_uri TEXT;

ALTER TABLE tool_instances
  ADD COLUMN life_cycle_status TEXT NOT NULL DEFAULT 'new'
    CHECK (life_cycle_status IN ('new','in_use','retired','unknown'));

ALTER TABLE tool_setups
  ADD COLUMN holder_manufacturer TEXT,
  ADD COLUMN holder_model TEXT,
  ADD COLUMN collet_or_chuck_type TEXT,
  ADD COLUMN clamping_torque_nm NUMERIC(10,3) CHECK (clamping_torque_nm >= 0),
  ADD COLUMN runout_measurement_method TEXT;

-- One actual fixturing of ONE workpiece on ONE CNC. New setup on reclamping.
CREATE TABLE workpiece_setups (
  workpiece_setup_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  setup_code TEXT NOT NULL UNIQUE,
  workpiece_sample_id UUID NOT NULL REFERENCES workpiece_samples(workpiece_sample_id) ON DELETE RESTRICT,
  machine_id UUID NOT NULL REFERENCES machines(machine_id) ON DELETE RESTRICT,
  fixture_type TEXT NOT NULL,
  fixture_code TEXT,
  clamping_method TEXT,
  estimated_clamping_force_n NUMERIC(12,3) CHECK (estimated_clamping_force_n >= 0),
  workpiece_orientation TEXT,
  fixture_notes TEXT,
  assembled_by UUID REFERENCES app_users(user_id) ON DELETE RESTRICT,
  assembled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  UNIQUE (workpiece_setup_id, workpiece_sample_id, machine_id)
);
CREATE INDEX workpiece_setups_workpiece_idx ON workpiece_setups(workpiece_sample_id, assembled_at DESC);

ALTER TABLE microphones
  ADD COLUMN polar_pattern TEXT,
  ADD COLUMN connector_type TEXT;

ALTER TABLE microphone_calibrations
  ADD COLUMN calibration_frequency_hz NUMERIC(12,3) CHECK (calibration_frequency_hz > 0),
  ADD COLUMN uncertainty_db NUMERIC(8,4) CHECK (uncertainty_db >= 0),
  ADD COLUMN calibration_environment JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(calibration_environment) = 'object');

ALTER TABLE recording_sessions
  ADD COLUMN session_code TEXT UNIQUE,
  ADD COLUMN operator_user_id UUID REFERENCES app_users(user_id) ON DELETE RESTRICT,
  ADD COLUMN workpiece_setup_id UUID,
  ADD COLUMN environment_temperature_c NUMERIC(7,3),
  ADD COLUMN environment_humidity_pct NUMERIC(6,3)
    CHECK (environment_humidity_pct BETWEEN 0 AND 100),
  ADD COLUMN background_noise_note TEXT,
  ADD COLUMN machine_door_state TEXT
    CHECK (machine_door_state IN ('open','closed','not_applicable','unknown')),
  ADD COLUMN coolant_flow_l_min NUMERIC(10,3) CHECK (coolant_flow_l_min >= 0),
  ADD COLUMN recording_host_software_version TEXT,
  ADD COLUMN host_capture_recording_id TEXT,
  ADD COLUMN device_lock_expires_at TIMESTAMPTZ,
  ADD COLUMN recording_settings JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(recording_settings) = 'object'),
  ADD CONSTRAINT workpiece_setup_requires_sample CHECK (
    workpiece_setup_id IS NULL OR workpiece_sample_id IS NOT NULL
  ),
  ADD CONSTRAINT recording_session_workpiece_setup_fk
    FOREIGN KEY (workpiece_setup_id, workpiece_sample_id, machine_id)
    REFERENCES workpiece_setups(workpiece_setup_id, workpiece_sample_id, machine_id) ON DELETE RESTRICT;

ALTER TABLE recording_channels
  ADD COLUMN cable_code TEXT,
  ADD COLUMN position_measurement_method TEXT,
  ADD COLUMN acoustic_windscreen_used BOOLEAN,
  ADD COLUMN microphone_power_mode TEXT,
  ADD COLUMN channel_polarity_inverted BOOLEAN NOT NULL DEFAULT FALSE,
  ADD CONSTRAINT unique_session_microphone UNIQUE (session_id, microphone_id);

ALTER TABLE audio_chunks
  ADD COLUMN captured_at_host TIMESTAMPTZ,
  ADD COLUMN first_frame_monotonic_ns BIGINT CHECK (first_frame_monotonic_ns >= 0);

ALTER TABLE audio_assets
  ADD COLUMN sample_format TEXT CHECK (sample_format IN ('pcm_s16le','pcm_s24le')),
  ADD COLUMN storage_state TEXT NOT NULL DEFAULT 'verified'
    CHECK (storage_state IN ('pending','verified','missing','corrupt')),
  ADD COLUMN immutable_raw BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE audio_quality_checks
  ADD COLUMN frame_sequence_ok BOOLEAN,
  ADD COLUMN sample_rate_verified BOOLEAN,
  ADD COLUMN corrupt_chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (corrupt_chunk_count >= 0),
  ADD COLUMN dropped_chunk_count INTEGER NOT NULL DEFAULT 0 CHECK (dropped_chunk_count >= 0),
  ADD COLUMN per_channel_noise_floor_dbfs JSONB
    CHECK (per_channel_noise_floor_dbfs IS NULL OR jsonb_typeof(per_channel_noise_floor_dbfs) = 'object');

ALTER TABLE machining_parameter_events
  ADD COLUMN controller_recorded_at TIMESTAMPTZ;

ALTER TABLE analysis_runs
  ADD COLUMN input_asset_id UUID REFERENCES audio_assets(asset_id) ON DELETE RESTRICT,
  ADD COLUMN code_commit TEXT,
  ADD COLUMN processing_started_at TIMESTAMPTZ,
  ADD COLUMN analysis_owner_user_id UUID REFERENCES app_users(user_id) ON DELETE RESTRICT,
  ADD COLUMN output_unit_spec JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(output_unit_spec) = 'object');

ALTER TABLE channel_features
  ADD COLUMN rms_unit TEXT,
  ADD COLUMN peak_unit TEXT,
  ADD COLUMN crest_factor NUMERIC(12,5) CHECK (crest_factor >= 0),
  ADD COLUMN spectral_flatness NUMERIC(12,6) CHECK (spectral_flatness BETWEEN 0 AND 1),
  ADD COLUMN zero_crossing_rate NUMERIC(12,6) CHECK (zero_crossing_rate BETWEEN 0 AND 1),
  ADD COLUMN extra_features JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(extra_features) = 'object');

ALTER TABLE fusion_results
  ADD COLUMN alignment_method TEXT,
  ADD COLUMN fusion_parameters JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(fusion_parameters) = 'object'),
  ADD COLUMN fusion_quality_flags JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(fusion_quality_flags) = 'object');

ALTER TABLE model_predictions
  ADD COLUMN model_artifact_uri TEXT,
  ADD COLUMN confidence NUMERIC(8,6) CHECK (confidence BETWEEN 0 AND 1),
  ADD COLUMN start_frame BIGINT CHECK (start_frame >= 0),
  ADD COLUMN frame_count INTEGER CHECK (frame_count > 0),
  ADD CONSTRAINT inference_window_complete CHECK (
    (start_frame IS NULL) = (frame_count IS NULL)
  );

ALTER TABLE verified_labels
  ADD COLUMN label_scope TEXT NOT NULL DEFAULT 'session'
    CHECK (label_scope IN ('session','window')),
  ADD COLUMN start_frame BIGINT CHECK (start_frame >= 0),
  ADD COLUMN frame_count INTEGER CHECK (frame_count > 0),
  ADD COLUMN verification_notes TEXT,
  ADD CONSTRAINT verified_label_window CHECK (
    (label_scope = 'session' AND start_frame IS NULL AND frame_count IS NULL)
    OR (label_scope = 'window' AND start_frame IS NOT NULL AND frame_count IS NOT NULL)
  );

-- API-issued start/stop commands and recorder acknowledgements.
CREATE TABLE recording_control_events (
  control_event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES recording_sessions(session_id) ON DELETE RESTRICT,
  command_id UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  command TEXT NOT NULL CHECK (command IN ('prepare','start','stop','abort','heartbeat','recover')),
  issued_by UUID REFERENCES app_users(user_id) ON DELETE RESTRICT,
  issued_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  acknowledged_at TIMESTAMPTZ,
  command_status TEXT NOT NULL DEFAULT 'issued'
    CHECK (command_status IN ('issued','accepted','rejected','timed_out','completed')),
  recorder_response JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(recorder_response) = 'object'),
  error_message TEXT,
  CONSTRAINT recorder_ack_after_command CHECK (acknowledged_at IS NULL OR acknowledged_at >= issued_at)
);
CREATE INDEX recording_control_events_session_idx ON recording_control_events(session_id, issued_at DESC);

-- Optional: actual CNC controller readings mapped to audio sample frame.
-- Zero audio-frame index is the shared origin of the three recorded channels.
CREATE TABLE machine_telemetry_samples (
  telemetry_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  session_id UUID NOT NULL REFERENCES recording_sessions(session_id) ON DELETE RESTRICT,
  audio_frame BIGINT NOT NULL CHECK (audio_frame >= 0),
  measured_at TIMESTAMPTZ,
  actual_spindle_rpm NUMERIC(12,3) CHECK (actual_spindle_rpm >= 0),
  actual_feed_mm_min NUMERIC(12,4) CHECK (actual_feed_mm_min >= 0),
  spindle_load_pct NUMERIC(7,3) CHECK (spindle_load_pct BETWEEN 0 AND 100),
  spindle_power_kw NUMERIC(12,4) CHECK (spindle_power_kw >= 0),
  controller_state TEXT,
  extra_measurements JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(extra_measurements) = 'object'),
  measured_source TEXT NOT NULL DEFAULT 'cnc_controller',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (session_id, audio_frame, measured_source)
);
CREATE INDEX machine_telemetry_session_frame_idx ON machine_telemetry_samples(session_id, audio_frame);

-- Large derived FFT spectra, STFT spectrograms, filtered WAVs: store as files;
-- SQL stores provenance, structure and immutable paths, not arrays per sample.
CREATE TABLE analysis_artifacts (
  artifact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  analysis_id UUID NOT NULL,
  session_id UUID NOT NULL,
  channel_no SMALLINT,
  artifact_kind TEXT NOT NULL CHECK (artifact_kind IN
    ('filtered_audio','fft_spectrum','stft_spectrogram','waveform_preview','feature_matrix','other')),
  storage_uri TEXT NOT NULL,
  mime_type TEXT,
  shape_json JSONB CHECK (shape_json IS NULL OR jsonb_typeof(shape_json) = 'object'),
  sha256_hex CHAR(64) CHECK (sha256_hex IS NULL OR sha256_hex ~ '^[0-9a-f]{64}$'),
  produced_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  FOREIGN KEY (analysis_id, session_id)
    REFERENCES analysis_runs(analysis_id, session_id) ON DELETE RESTRICT,
  FOREIGN KEY (session_id, channel_no)
    REFERENCES recording_channels(session_id, channel_no) ON DELETE RESTRICT
);
CREATE INDEX analysis_artifacts_analysis_idx ON analysis_artifacts(analysis_id);

CREATE INDEX recording_sessions_condition_index
  ON recording_sessions(experiment_condition_id, trial_no, created_at DESC);
CREATE INDEX recording_sessions_tool_setup_idx ON recording_sessions(tool_setup_id);
CREATE INDEX machine_telemetry_recording_time_idx ON machine_telemetry_samples(session_id, measured_at);

COMMIT;
