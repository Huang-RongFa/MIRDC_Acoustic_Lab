-- Run on an empty V1.2 verification database. Fixtures are rolled back.
\set ON_ERROR_STOP on
BEGIN;
CREATE FUNCTION pg_temp.expect(ok boolean, scenario text) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'FAILED %', scenario; END IF;
  RAISE NOTICE 'PASS %', scenario;
END $$;
SELECT pg_temp.expect(count(*)=423 AND count(DISTINCT table_name)=28,'public schema counts')
FROM information_schema.columns WHERE table_schema='public';
SELECT pg_temp.expect(bool_and(convalidated),'all constraints validated') FROM pg_constraint WHERE connamespace='public'::regnamespace;
INSERT INTO app_users(display_name,email) VALUES ('One','one@example.test'),('Two','two@example.test');
INSERT INTO machines(machine_code,machine_name) VALUES ('M1','First'),('M2','Second');
INSERT INTO materials(material_code,material_name) VALUES ('MAT','Sample');
INSERT INTO cutting_tools(tool_code,tool_name,tool_type) VALUES ('T','Mill','end mill');
INSERT INTO capture_devices(device_code,device_name,input_channel_capacity) VALUES ('D1','Host one',3),('D2','Host two',3);
INSERT INTO workpiece_samples(sample_code,material_id) SELECT 'W',material_id FROM materials;
INSERT INTO tool_instances(tool_id,instance_code) SELECT tool_id,'I' FROM cutting_tools;
INSERT INTO tool_setups(setup_code,tool_instance_id,tool_id,machine_id,holder_type,tool_overhang_mm)
SELECT machine_code,tool_instance_id,tool_id,machine_id,'collet',15 FROM machines CROSS JOIN tool_instances;
INSERT INTO workpiece_setups(setup_code,workpiece_sample_id,machine_id,fixture_type)
SELECT machine_code,workpiece_sample_id,machine_id,'vise' FROM machines CROSS JOIN workpiece_samples;
INSERT INTO machining_presets(preset_name,process_type,spindle_rpm) VALUES ('P','milling',2400);
INSERT INTO recording_sessions(created_by,machine_id,material_id,tool_id,capture_device_id,process_type,workpiece_sample_id,workpiece_setup_id,tool_setup_id,preset_id,spindle_rpm,condition_snapshot)
SELECT user_id,m.machine_id,w.material_id,t.tool_id,device_id,p.process_type,w.workpiece_sample_id,f.workpiece_setup_id,t.tool_setup_id,p.preset_id,p.spindle_rpm,jsonb_build_object('rpm',p.spindle_rpm)
FROM machines m JOIN tool_setups t USING(machine_id) JOIN workpiece_setups f USING(machine_id)
JOIN workpiece_samples w USING(workpiece_sample_id) JOIN app_users ON display_name=CASE machine_code WHEN 'M1' THEN 'One' ELSE 'Two' END
JOIN capture_devices ON device_code='D'||right(machine_code,1) CROSS JOIN machining_presets p;
SELECT pg_temp.expect(count(DISTINCT created_by)=2 AND count(DISTINCT machine_id)=2,'two operators with associated setups') FROM recording_sessions;
SELECT session_id AS sid FROM recording_sessions JOIN machines USING(machine_id) WHERE machine_code='M1' \gset
UPDATE recording_sessions SET status='failed',finished_at=now() WHERE session_id<>:'sid';
SELECT pg_temp.expect(count(*)=1,'failure before start') FROM recording_sessions WHERE status='failed' AND started_at IS NULL AND capture_clock_id IS NULL;
UPDATE machining_presets SET spindle_rpm=3600;
SELECT pg_temp.expect(bool_and(spindle_rpm=2400 AND condition_snapshot->>'rpm' IN ('2400.00','2400')),'historical conditions') FROM recording_sessions;
INSERT INTO microphones(microphone_code) VALUES ('A'),('B'),('C');
INSERT INTO recording_channels(session_id,channel_no,source_label,microphone_id,microphone_code)
SELECT :'sid',ascii(microphone_code)-64,microphone_code,microphone_id,microphone_code FROM microphones;
UPDATE recording_sessions SET status='recording',capture_clock_id='clock-1',started_at=now() WHERE session_id=:'sid';
SELECT pg_temp.expect(string_agg(source_label,'' ORDER BY channel_no)='ABC' AND count(DISTINCT microphone_id)=3 AND min(capture_clock_id)='clock-1','three channels share one session clock')
FROM recording_channels JOIN recording_sessions USING(session_id) WHERE session_id=:'sid';
INSERT INTO audio_chunks(session_id,chunk_index,first_frame,frame_count,sample_format,pcm_data,sha256_hex)
SELECT :'sid',i,i,1,'pcm_s16le',b,encode(sha256(b),'hex') FROM (VALUES (0,decode('010002000300','hex')),(1,decode('040005000600','hex'))) v(i,b);
SELECT pg_temp.expect(string_agg(encode(pcm_data,'hex'),'' ORDER BY chunk_index)='010002000300040005000600','raw interleaved PCM round trip') FROM audio_chunks;
DO $$ BEGIN
 BEGIN INSERT INTO audio_chunks SELECT * FROM audio_chunks LIMIT 1; RAISE EXCEPTION 'duplicate accepted'; EXCEPTION WHEN unique_violation THEN NULL; END;
 BEGIN UPDATE recording_channels SET microphone_id=gen_random_uuid(); RAISE EXCEPTION 'orphan accepted'; EXCEPTION WHEN foreign_key_violation THEN NULL; END;
 BEGIN UPDATE audio_chunks SET pcm_data=''::bytea; RAISE EXCEPTION 'invalid length accepted'; EXCEPTION WHEN check_violation THEN NULL; END;
 BEGIN UPDATE machines SET machine_code='duplicate'; RAISE EXCEPTION 'duplicate machine accepted'; EXCEPTION WHEN unique_violation THEN NULL; END;
END $$;
INSERT INTO analysis_runs(session_id,analysis_type,method_name,pipeline_version) VALUES (:'sid','features','fixture','1') RETURNING analysis_id \gset
INSERT INTO channel_features(analysis_id,session_id,channel_no,window_index,start_frame,frame_count,rms) VALUES (:'analysis_id',:'sid',1,0,0,2,0.1);
INSERT INTO fusion_results(analysis_id,session_id,window_index,start_frame,frame_count,fusion_method,fused_features) VALUES (:'analysis_id',:'sid',0,0,2,'fixture','{}');
INSERT INTO model_predictions(analysis_id,session_id,model_name,model_version,predicted_label) VALUES (:'analysis_id',:'sid','fixture','1','normal');
INSERT INTO verified_labels(session_id,verification_method,verified_label) VALUES (:'sid','inspection','abnormal');
SELECT pg_temp.expect(predicted_label='normal' AND verified_label='abnormal','independent model and inspection labels') FROM model_predictions JOIN verified_labels USING(session_id);
-- Diagnostic queries must distinguish each injected fault, even when length is valid.
UPDATE audio_chunks SET pcm_data=decode('ff0002000300','hex') WHERE chunk_index=0;
SELECT pg_temp.expect(count(*)=1,'digest detects equal-length corruption') FROM audio_chunks WHERE encode(sha256(pcm_data),'hex')<>sha256_hex;
UPDATE audio_chunks SET first_frame=2 WHERE chunk_index=1;
SELECT pg_temp.expect(first_frame<>lag_end,'missing frame') FROM (SELECT chunk_index,first_frame,lag(first_frame+frame_count) OVER (ORDER BY chunk_index) lag_end FROM audio_chunks) q WHERE chunk_index=1;
UPDATE audio_chunks SET first_frame=1-chunk_index;
SELECT pg_temp.expect(first_frame<>0,'index/frame order mismatch') FROM audio_chunks WHERE chunk_index=0;
ROLLBACK;
