"""Read-only startup contract. Migrations are always an explicit operator action."""
import os
from backend.db import Database

DEFAULT_DATABASE_URL = 'postgresql://postgres@localhost:5432/cnc_acoustic_lab'
REQUIRED = {
    'recording_rooms': 'id code created_at expires_at closed_at required_recorder_count assignment_version event_version closing',
    'room_participants': 'id room_id source_label name token_hash is_host mic ready error leaving microphone_permission revoked recorder_id',
    'recording_sessions': 'id room_id status conditions starts_at started_at stopped_at created_at machine_id legacy_take',
    'participant_recordings': 'session_id participant_id room_id status mime_type actual_started_at start_perf_ms stopped_at expected_chunks interrupted error participant_recording_id sample_rate channel_count duration_ms server_started_at server_stopped_at source_position requested_sample_rate requested_channel_count',
    'audio_chunks': 'session_id participant_id chunk_index mime_type created_at received_at checksum audio_data participant_recording_id source_label byte_size',
    'audio_assets': 'session_id participant_id mime_type chunk_count byte_count checksum created_at',
    'device_clock_observations': 'id session_id participant_id client_sent_ms server_received_ms client_received_ms performance_ms',
    'analysis_results': 'id session_id result created_at',
    'catalog_items': 'id room_id kind name values',
    'recording_tracks': 'track_id session_id device_id device_name channel_index channel_label source_channel_count requested_sample_rate original_sample_rate actual_sample_rate analysis_sample_rate duration_seconds total_frames analysis_status',
    'track_analysis_runs': 'id session_id fingerprint start_seconds end_seconds status result created_at',
    'track_analysis_artifacts': 'run_id track_id kind content',
}


def check_schema(connection):
    target = connection.execute('SELECT current_database() AS name,inet_server_port() AS port').fetchone()
    rows = connection.execute("SELECT table_name,column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='mobile_capture'").fetchall()
    columns = {(row['table_name'], row['column_name']): row for row in rows}
    missing = [f'{table}.{column}' for table, fields in REQUIRED.items() for column in fields.split() if (table,column) not in columns]
    problems = []
    for field in ('leaving','revoked'):
        row = columns.get(('room_participants', field))
        if row and (row['data_type'] != 'boolean' or row['is_nullable'] != 'NO' or row['column_default'] != 'false'):
            problems.append(f'room_participants.{field} must be boolean NOT NULL DEFAULT false')
    source = columns.get(('room_participants','source_label'))
    if source and source['is_nullable'] != 'YES':
        problems.append('room_participants.source_label must allow NULL (departed participants / non-recording host)')
    for table, fields in {'machines':'machine_id machine_code machine_name machine_type model is_active', 'machining_presets':'preset_id preset_name machine_id process_type extra_params is_active updated_at'}.items():
        actual = {row['column_name'] for row in connection.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s", (table,))}
        missing.extend(f'public.{table}.{field}' for field in fields.split() if field not in actual)
    if missing or problems:
        raise RuntimeError(f"Schema incompatible: database={target['name']} port={target['port']}. Missing: {', '.join(missing) or 'none'}. {'; '.join(problems)}. Review backend/migrations/001..005 in order and 006_participant_state_compat.sql; see docs/startup-repair.md. No startup data updates were performed.")
    return target


if __name__ == '__main__':
    with Database(os.environ.get('DATABASE_URL') or DEFAULT_DATABASE_URL).transaction() as connection:
        connection.execute('SET TRANSACTION READ ONLY')
        target = check_schema(connection)
        print(f"Schema OK: database={target['name']} port={target['port']}")
