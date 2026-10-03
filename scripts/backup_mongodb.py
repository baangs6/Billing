"""Export a consistent Atlas snapshot into the private local backup directory."""
import sys
from datetime import datetime,timezone
from pathlib import Path
from bson import json_util
from pymongo.read_concern import ReadConcern
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mongo_store import MongoBackend,load_configuration,COLLECTIONS
from saas import PLATFORM_COLLECTIONS

def backup(backend):
    collections=sorted(COLLECTIONS | PLATFORM_COLLECTIONS | {'counters','migration_history'})
    with backend.client.start_session() as session:
        def read(_):
            return {name:list(backend.database[name].find({},session=session)) for name in collections}
        documents=session.with_transaction(read,read_concern=ReadConcern('snapshot'))
    root=Path(__file__).resolve().parents[1]/'instance'/'backups'
    root.mkdir(parents=True,exist_ok=True)
    path=root/('atlas-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'.json')
    path.write_text(json_util.dumps({'database':backend.name,'collections':documents}),encoding='utf-8')
    print('Private Atlas backup created:',str(path))
    print('Collection counts:',{name:len(rows) for name,rows in documents.items()})

if __name__=='__main__':
    backend=None
    try:
        backend=MongoBackend(*load_configuration()); backup(backend)
    except Exception as error:
        print('Backup failed. Error type:',type(error).__name__); sys.exit(1)
    finally:
        if backend: backend.client.close()
