"""Static consistency check only; not a PostgreSQL execution test."""
from pathlib import Path
import csv, json, re
root=Path(__file__).resolve().parent
sql=(root/'01_schema_complete.sql').read_text(encoding='utf-8')
comments=(root/'02_column_comments.sql').read_text(encoding='utf-8')
with (root/'03_data_dictionary.csv').open(encoding='utf-8-sig',newline='') as f:
    docs=list(csv.DictReader(f))
manifest=json.loads((root/'06_manifest.json').read_text(encoding='utf-8'))

def split_top(text):
    out=[];start=0;level=0;quoted=False;i=0
    while i<len(text):
        c=text[i]
        if c=="'":
            if quoted and i+1<len(text) and text[i+1]=="'":i+=2;continue
            quoted=not quoted
        elif not quoted:
            if c=='(':level+=1
            elif c==')':level-=1
            elif c==',' and level==0:
                out.append(text[start:i].strip());start=i+1
        i+=1
    out.append(text[start:].strip())
    return out

def columns_in(s):
    pat=r'^\s*(\w+)\s+(UUID|TEXT|INTEGER\[\]|INTEGER|SMALLINT|BIGINT|NUMERIC\(\d+,\d+\)|TIMESTAMPTZ|DATE|JSONB|BOOLEAN|CHAR\(\d+\)|BYTEA)(?:\s|$)'
    m=re.match(pat,s,re.I)
    if m and m.group(1).upper() not in ('CONSTRAINT','PRIMARY','UNIQUE','FOREIGN','CHECK'):
        return m.group(1),m.group(2)
    return None

clean=re.sub(r'--[^\n]*','',sql)
tables=[];found={}
for m in re.finditer(r'\bCREATE TABLE\s+(\w+)\s*\(',clean):
    table=m.group(1);tables.append(table);st=m.end();depth=1;idx=st;quoted=False
    while depth and idx<len(clean):
        c=clean[idx]
        if c=="'":
            if quoted and idx+1<len(clean) and clean[idx+1]=="'":idx+=2;continue
            quoted=not quoted
        elif not quoted:
            if c=='(':depth+=1
            elif c==')':depth-=1
        idx+=1
    assert depth==0,table
    for seg in split_top(clean[st:idx-1]):
        result=columns_in(seg)
        if result: found[(table,result[0])]=result[1]
for m in re.finditer(r'\bALTER TABLE\s+(\w+)\s+(.*?);',clean,re.S):
    table,body=m.groups()
    for seg in split_top(body):
        if seg.startswith('ADD COLUMN '):
            result=columns_in(seg[len('ADD COLUMN '):])
            assert result,(table,seg)
            assert (table,result[0]) not in found,(table,result[0])
            found[(table,result[0])]=result[1]
comment_fields=set(re.findall(r'\bCOMMENT ON COLUMN (\w+)\.(\w+) IS ',comments))
doc_fields={(d['table'],d['field']) for d in docs}
assert len(tables)==len(set(tables))==manifest['table_count']==28
assert len(doc_fields)==len(docs)==len(found)==len(comment_fields)==manifest['column_count']==423
assert set(found)==doc_fields==comment_fields
assert set(tables)==set(manifest['tables'])
assert all(sum(d['table']==t for d in docs)==manifest['tables'][t] for t in tables)
assert 'capture_clock_required_after_start' in sql
assert 'CREATE DATABASE' in (root/'00_create_database.sql').read_text(encoding='utf-8')
assert 'BEGIN;' in sql and sql.rstrip().endswith('COMMIT;')
assert ('audio_chunks','pcm_data') in found and found[('audio_chunks','pcm_data')]=='BYTEA'
print(f'STATIC OK: {len(tables)} tables, {len(found)} actual SQL columns, complete field dictionary and SQL comments')
print('NOTE: PostgreSQL execution and end-to-end audio recording tests have NOT been performed.')
