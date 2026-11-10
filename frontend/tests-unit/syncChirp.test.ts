// node --test tests-unit/（Node 22.18+／24 原生去除型別）
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import * as chirp from '../src/syncChirp.ts';

// analysis/sync_chirp.py 的 chirp_template(sr) 在這些位置的值（2026-11-10 以 numpy 計算）
const python:Record<number,{n:number;idx:number[];v:number[]}>={
  48000:{n:24000,idx:[0,1,100,480,1000,12000,23998,23999],v:[0.0,1.6715415057171355e-06,0.06718882089048041,-0.47022820183397607,-0.6346826722329999,-2.038010347584904e-13,-7.915399417980889e-06,-0.0]},
  44100:{n:22050,idx:[0,1,100,480,1000,12000,22048,22049],v:[0.0,2.15283645974114e-06,0.040191092230608245,0.18600130578420904,0.4650885157880274,0.37389202188523885,-8.565396213585312e-06,-0.0]},
};

test('前端嗶聲與 Python 範本逐點一致',()=>{
  for(const [sr,ref] of Object.entries(python)){
    const y=chirp.chirpSamples(Number(sr));
    assert.equal(y.length,ref.n);
    ref.idx.forEach((i,j)=>assert.ok(Math.abs(y[i]-ref.v[j])<1e-6,`sr=${sr} i=${i}: ${y[i]} vs ${ref.v[j]}`));
  }
});

test('常數與 analysis/sync_chirp.py 相同（跨語言契約）',()=>{
  const py=readFileSync(fileURLToPath(new URL('../../analysis/sync_chirp.py',import.meta.url)),'utf8');
  const value=(name:string)=>{const m=py.match(new RegExp('^'+name+'\\s*=\\s*([0-9.]+)','m'));assert.ok(m,name+' not found in sync_chirp.py');return Number(m![1]);};
  assert.equal(chirp.CHIRP_F0_HZ,value('CHIRP_F0_HZ'));
  assert.equal(chirp.CHIRP_F1_HZ,value('CHIRP_F1_HZ'));
  assert.equal(chirp.CHIRP_DURATION_S,value('CHIRP_DURATION_S'));
  assert.equal(chirp.CHIRP_FADE_S,value('CHIRP_FADE_S'));
  assert.equal(chirp.CHIRP_AMPLITUDE,value('CHIRP_AMPLITUDE'));
});

test('振幅上限與頭尾歸零',()=>{
  const y=chirp.chirpSamples(48000);
  assert.ok(Math.max(...Array.from(y,Math.abs))<=chirp.CHIRP_AMPLITUDE+1e-6);
  assert.equal(y[0],0);assert.equal(Math.abs(y[y.length-1]),0);
});
