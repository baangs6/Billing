"""Verify a private BSON JSON backup by restoring only into a random test database."""
import hashlib
import secrets
import sys
from pathlib import Path
from bson import json_util
from pymongo import IndexModel
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mongo_store import MongoBackend,load_configuration


def verify(path,uri):
    raw=Path(path).read_bytes()
    data=json_util.loads(raw)
    if not isinstance(data.get('collections'),dict): raise ValueError('Invalid backup format.')
    backend=MongoBackend(uri,'ledger_restore_test_'+secrets.token_hex(8))
    try:
        for name,rows in data['collections'].items():
            if not isinstance(name,str) or not name.replace('_','').isalnum() or not isinstance(rows,list): raise ValueError('Invalid backup collection.')
            metadata=data.get('metadata',{}).get(name,{})
            options={k:v for k,v in metadata.get('options',{}).items() if k in ('validator','validationLevel','validationAction','collation','capped','size','max')}
            backend.database.create_collection(name,**options)
            if rows: backend.database[name].insert_many(rows)
            indexes=[IndexModel(list(index['key'].items()),**{k:v for k,v in index.items() if k not in ('v','key','ns')}) for index in metadata.get('indexes',[]) if index['name']!='_id_']
            if indexes: backend.database[name].create_indexes(indexes)
            restored=list(backend.database[name].find({}))
            assert {json_util.dumps(row,sort_keys=True) for row in restored}=={json_util.dumps(row,sort_keys=True) for row in rows},name
        return dict(sha256=hashlib.sha256(raw).hexdigest(),collections=len(data['collections']),documents=sum(map(len,data['collections'].values())))
    finally:
        assert backend.name.startswith('ledger_restore_test_')
        backend.client.drop_database(backend.name); backend.client.close()

if __name__=='__main__':
    uri,_=load_configuration()
    path=Path(sys.argv[1]) if len(sys.argv)>1 else max((Path(__file__).resolve().parents[1]/'instance'/'backups').glob('atlas-*.json'))
    result=verify(path,uri)
    path.with_suffix('.verified.json').write_text(__import__('json').dumps(result,indent=2),encoding='utf-8')
    print('Backup restore verified:',result)
