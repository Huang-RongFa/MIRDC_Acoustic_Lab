import type {Identity,Room} from './types';
export const staticIdentity:Identity={room_code:'尚未建立',participant_id:'',session_id:'',source_label:'A',token:'',is_host:true};
export const staticRoom:Room={id:'',room_id:'',status:'waiting',conditions:{},started_at:null,starts_at:null,stopped_at:null,server_now:Date.now(),ready_count:0,participants:[],recordings:['A','B','C'].map(source_label=>({participant_id:source_label,source_label,status:'pending',mime_type:null,actual_started_at:null,expected_chunks:null,error:null,interrupted:false}))};
