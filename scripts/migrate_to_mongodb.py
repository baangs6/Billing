"""Read-only legacy SQLite import. Never deletes or overwrites Atlas business data."""
import hashlib
import json
import sqlite3
import sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mongo_store import MongoBackend,load_configuration,fixed_integers

ROOT=Path(__file__).resolve().parents[1]
TABLES=['businesses','users','business_settings','customers','categories','products','inventory','invoices','invoice_items','payments','stock_movements','audit_events','invoice_submissions']

def extract(path):
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as conn:
        conn.row_factory=sqlite3.Row
        data={table:[dict(r) for r in conn.execute(f'SELECT * FROM {table}')] for table in TABLES}
    product_tenants={r['id']:r['business_id'] for r in data['products']}
    invoice_tenants={r['id']:r['business_id'] for r in data['invoices']}
    customer_tenants={r['id']:r['business_id'] for r in data['customers']}
    category_tenants={r['id']:r['business_id'] for r in data['categories']}
    businesses={r['id'] for r in data['businesses']}
    for table,rows in data.items():
        for row in rows:
            if table=='businesses': row['lock_version']=0
            elif table=='inventory': row['business_id']=product_tenants[row['product_id']]
            elif table=='stock_movements': row['business_id']=product_tenants[row['product_id']]
            elif table in ('invoice_items','payments'): row['business_id']=invoice_tenants[row['invoice_id']]
            if table!='businesses' and row['business_id'] not in businesses: raise RuntimeError('Orphan tenant record in legacy database.')
            if 'data' in row and isinstance(row['data'],str): row['data']=json.loads(row['data'])
            if 'snapshot' in row and isinstance(row['snapshot'],str): row['snapshot']=json.loads(row['snapshot'])
            for field in ('id','business_id','product_id','invoice_id','customer_id','category_id','entity_id','user_id'):
                if row.get(field) is not None: row[field]=int(row[field])
            if row.get('product_id') is not None and product_tenants[row['product_id']]!=row['business_id']: raise RuntimeError('Cross-tenant product reference in source.')
            if row.get('invoice_id') is not None and invoice_tenants[row['invoice_id']]!=row['business_id']: raise RuntimeError('Cross-tenant invoice reference in source.')
            if row.get('customer_id') is not None and customer_tenants[row['customer_id']]!=row['business_id']: raise RuntimeError('Cross-tenant customer reference in source.')
            if row.get('category_id') is not None and category_tenants[row['category_id']]!=row['business_id']: raise RuntimeError('Cross-tenant category reference in source.')
    return data

def verify(backend,data):
    for table,rows in data.items():
        for row in rows:
            keys={'id':row['id']} if 'id' in row else {k:row[k] for k in ('business_id','product_id','token') if k in row}
            actual=backend.database[table].find_one(keys)
            if actual is None or any(actual.get(k)!=v for k,v in row.items() if k!='lock_version'):
                raise RuntimeError('Migration verification mismatch in '+table)

def migrate(path,backend):
    backup=ROOT/'instance'/'backups'/('billing-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'.db')
    backup.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(backup) as destination:
        source.backup(destination)
    data=extract(backup)
    fingerprint=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
    backend.ping(); backend.initialize()
    if backend.database.migration_history.find_one({'_id':fingerprint}):
        verify(backend,data); print('Existing migration verified; no records inserted.'); return
    if any(backend.database[t].count_documents({}) for t in TABLES):
        raise RuntimeError('Target contains business data; migration refuses to overwrite or merge it.')
    def insert(session):
        for table,rows in data.items():
            if rows: backend.database[table].insert_many([fixed_integers(r) for r in rows],session=session)
        backend.database.migration_history.insert_one({'_id':fingerprint,'source':'SQLite billing.db','counts':{t:len(r) for t,r in data.items()},'created_at':datetime.now(timezone.utc)},session=session)
    with backend.client.start_session() as session: session.with_transaction(insert)
    verify(backend,data); backend.initialize()
    print('Migration verified. Records by collection:',{t:len(r) for t,r in data.items()})
    print('SQLite backup preserved:',str(backup))

if __name__=='__main__':
    backend=None
    try:
        uri,name=load_configuration(); backend=MongoBackend(uri,name)
        migrate((ROOT/'instance'/'billing.db').resolve(),backend)
    except Exception as error:
        print('Migration failed safely. Error type:',type(error).__name__)
        sys.exit(1)
    finally:
        if backend: backend.client.close()
