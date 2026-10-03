"""MongoDB storage with mandatory tenant scoping and transactional business writes."""
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from bson.int64 import Int64
from pymongo import MongoClient, ReturnDocument, ASCENDING
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

TENANT_COLLECTIONS = {'users','business_settings','customers','categories','products','inventory','stock_movements','invoices','invoice_items','payments','audit_events','invoice_submissions','roles','subscriptions','renewal_requests','proposals'}
COLLECTIONS = TENANT_COLLECTIONS | {'businesses'}
ID_FIELDS = {'id','business_id','customer_id','product_id','invoice_id','category_id','user_id','entity_id'}
MONEY_FIELDS = {'selling_price','purchase_price','mrp','rate','subtotal','discount','taxable','cgst','sgst','igst','total','amount'}

def load_configuration():
    """Only the selected local .env is read. Values are never printed or logged."""
    path=Path(os.environ.get('BILLING_ENV_FILE',Path(__file__).parent/'instance'/'mongodb.env'))
    values={}
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            line=line.strip()
            if line and not line.startswith('#') and '=' in line:
                key,value=line.split('=',1); values[key.strip()]=value.strip().strip('"').strip("'")
    uri=os.environ.get('MONGODB_URI') or values.get('MONGODB_URI')
    name=os.environ.get('MONGODB_DATABASE') or values.get('MONGODB_DATABASE','ledger_billing')
    if not uri: raise RuntimeError('MongoDB is not configured. Set MONGODB_URI or instance/mongodb.env.')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}',name): raise RuntimeError('Invalid MongoDB database name.')
    return uri,name

def numeric_ids(query):
    converted={}
    for key,value in query.items():
        if key in ID_FIELDS and value is not None and not isinstance(value,dict):
            try: value=int(value)
            except (ValueError,TypeError): raise ValueError('Invalid record identifier.')
        converted[key]=value
    return converted

def fixed_integers(value):
    if isinstance(value,dict): return {k:fixed_integers(v) for k,v in value.items()}
    if isinstance(value,list): return [fixed_integers(v) for v in value]
    if isinstance(value,int) and not isinstance(value,bool): return Int64(value)
    return value

def clean(doc):
    if doc is None: return None
    return {k:v for k,v in doc.items() if k!='_id'}

class MongoBackend:
    def __init__(self, uri, name):
        self.name=name
        self.client=MongoClient(uri,serverSelectionTimeoutMS=10000,connectTimeoutMS=10000,socketTimeoutMS=20000,maxPoolSize=25,appname='LedgerBilling',retryWrites=True)
        self.database=self.client[name]

    def ping(self):
        self.client.admin.command('ping')

    def initialize(self):
        """Run at installation/migration, never during each web request."""
        required={
            'businesses':['id','name'], 'users':['id','business_id','email','password_hash'],
            'business_settings':['business_id','data'], 'customers':['id','business_id','name','data'],
            'categories':['id','business_id','name'], 'products':['id','business_id','name','sku','data','selling_price','purchase_price','mrp'],
            'inventory':['business_id','product_id','quantity'], 'stock_movements':['id','business_id','product_id','quantity','reason'],
            'invoices':['id','business_id','customer_id','number','date','type','status','total','snapshot'],
            'invoice_items':['id','business_id','invoice_id','name','quantity','rate','total'],
            'payments':['id','business_id','invoice_id','amount','date','method'],
            'audit_events':['id','business_id','user_id','action','entity','details'],
            'invoice_submissions':['business_id','token','invoice_id'],
            'roles':['id','business_id','name','permissions'],
            'subscriptions':['id','business_id','status','plan','start_at'],
            'renewal_requests':['id','business_id','status','plan_id','cycle'],
            'proposals':['id','business_id','customer_id','number','date','valid_until','title','type','status','version','total','snapshot','items','submission'],
        }
        existing=set(self.database.list_collection_names())
        for name,fields in required.items():
            properties={k:{'bsonType':['int','long']} for k in fields if k in ID_FIELDS or k in MONEY_FIELDS or k=='quantity'}
            properties.update({k:{'bsonType':['int','long'],'minimum':0} for k in MONEY_FIELDS if k in fields})
            if name=='payments': properties['amount']['minimum']=1
            if name=='invoice_items': properties['quantity']['minimum']=1
            if name in ('customers','products','business_settings'): properties['data']={'bsonType':'object'}
            if name=='invoices':
                properties.update(snapshot={'bsonType':'object'},type={'enum':['GST','NON-GST']},status={'enum':['FINAL','CANCELLED']})
            if name=='proposals':
                properties.update(snapshot={'bsonType':'object'},items={'bsonType':'array'},type={'enum':['GST','NON-GST']},status={'enum':['DRAFT','SENT','ACCEPTED','DECLINED','CONVERTED']})
            validator={'$jsonSchema':{'bsonType':'object','required':fields,'properties':properties}}
            if name not in existing: self.database.create_collection(name,validator=validator)
            else: self.database.command('collMod',name,validator=validator,validationLevel='strict',validationAction='error')
            if 'id' in fields: self.database[name].create_index('id',unique=True)
            if name in TENANT_COLLECTIONS: self.database[name].create_index('business_id')
        for name in ('counters','login_attempts','migration_history'):
            if name not in existing: self.database.create_collection(name)
        self.database.users.create_index('email',unique=True)
        for name,keys in [('categories',['business_id','name']),('products',['business_id','sku']),('invoices',['business_id','number']),('inventory',['business_id','product_id']),('business_settings',['business_id']),('invoice_submissions',['business_id','token'])]:
            specification=[(k,ASCENDING) for k in keys]
            equivalent=any(list(i['key'].items())==specification and i.get('unique') for i in self.database[name].list_indexes())
            if not equivalent: self.database[name].create_index(specification,unique=True,name='unique_'+'_'.join(keys))
        self.database.invoices.create_index([('business_id',1),('date',-1),('id',-1)])
        self.database.payments.create_index([('business_id',1),('invoice_id',1),('date',-1)])
        self.database.invoice_items.create_index([('business_id',1),('invoice_id',1)])
        self.database.stock_movements.create_index([('business_id',1),('product_id',1),('id',-1)])
        self.database.proposals.create_index([('business_id',1),('number',1)],unique=True)
        self.database.proposals.create_index([('business_id',1),('submission',1)],unique=True)
        self.database.login_attempts.create_index('expires_at',expireAfterSeconds=0)
        for name in required:
            if 'id' in required[name]:
                maximum=self.database[name].find_one(sort=[('id',-1)])
                self.database.counters.update_one({'_id':name},{'$max':{'value':Int64(maximum['id'] if maximum else 0)}},upsert=True)

    def scope(self,business_id=None):
        return MongoStore(self,int(business_id) if business_id is not None else None)

    def session_user(self,uid,bid):
        try: query={'id':int(uid),'business_id':int(bid)}
        except (ValueError,TypeError): return None
        return clean(self.database.users.find_one(query))

    def login_user(self,email):
        return clean(self.database.users.find_one({'email':str(email)}))

    def login_attempt(self,key):
        return clean(self.database.login_attempts.find_one({'_id':key}))

    def reset_login_attempt(self,key):
        self.database.login_attempts.delete_one({'_id':key})

    def failed_login(self,key):
        import time
        now=int(time.time()); expired={'$lt':[{'$ifNull':['$started',0]},now-900]}
        self.database.login_attempts.update_one({'_id':key},[{'$set':{
            'count':{'$cond':[expired,1,{'$add':[{'$ifNull':['$count',0]},1]}]},
            'started':{'$cond':[expired,now,'$started']},
            'expires_at':datetime.fromtimestamp(now+900,timezone.utc),
        }}],upsert=True)

class MongoStore:
    def __init__(self,backend,business_id):
        self.backend=backend; self.business_id=business_id; self.mongo_session=None
        self.write_allowed=False

    def _query(self,name,query=None):
        if name not in COLLECTIONS: raise ValueError('Unknown collection.')
        query=numeric_ids(query or {})
        if self.business_id is None: raise PermissionError('Tenant context required.')
        tenant={'id':self.business_id} if name=='businesses' else {'business_id':self.business_id}
        return {'$and':[query,tenant]}

    def one(self,name,query=None):
        return clean(self.backend.database[name].find_one(self._query(name,query),session=self.mongo_session))

    def find(self,name,query=None,sort=None,limit=0):
        cursor=self.backend.database[name].find(self._query(name,query),session=self.mongo_session)
        if sort: cursor=cursor.sort(sort)
        if limit: cursor=cursor.limit(limit)
        return [clean(r) for r in cursor]

    def count(self,name,query=None):
        return self.backend.database[name].count_documents(self._query(name,query),session=self.mongo_session)

    def _require_transaction(self):
        if not self.write_allowed or self.mongo_session is None or not self.mongo_session.in_transaction:
            raise RuntimeError('Business writes require a MongoDB transaction.')

    def insert(self,name,document):
        self._require_transaction()
        if name not in COLLECTIONS: raise ValueError('Unknown collection.')
        doc=numeric_ids(dict(document))
        if name in TENANT_COLLECTIONS:
            if self.business_id is None or doc.get('business_id',self.business_id)!=self.business_id: raise PermissionError('Tenant mismatch.')
            doc['business_id']=self.business_id
        if name not in ('inventory','business_settings','invoice_submissions'):
            seq=self.backend.database.counters.find_one_and_update({'_id':name},{'$inc':{'value':Int64(1)}},return_document=ReturnDocument.AFTER,session=self.mongo_session)
            if not seq: raise RuntimeError('Database not initialized. Run migration first.')
            doc['id']=int(seq['value'])
        doc.setdefault('created_at',datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))
        self.backend.database[name].insert_one(fixed_integers(doc),session=self.mongo_session)
        return doc.get('id')

    def update(self,name,query,values=None,inc=None):
        self._require_transaction(); values=values or {}
        if 'business_id' in values or 'id' in values: raise PermissionError('Record identity cannot change.')
        update={}
        if values: update['$set']=fixed_integers(values)
        if inc: update['$inc']=fixed_integers(inc)
        return self.backend.database[name].update_one(self._query(name,query),update,session=self.mongo_session)

    def delete(self,name,query):
        self._require_transaction()
        if name!='invoice_items': raise PermissionError('Financial records cannot be deleted.')
        return self.backend.database[name].delete_many(self._query(name,query),session=self.mongo_session)

    def run_transaction(self,callback):
        with self.backend.client.start_session() as mongo_session:
            self.mongo_session=mongo_session
            self.write_allowed=True
            def run(_):
                if self.business_id is not None:
                    # Serialize writes per company. This prevents payment/stock write skew.
                    result=self.backend.database.businesses.update_one({'id':self.business_id},{'$inc':{'lock_version':Int64(1)}},session=mongo_session)
                    if not result.matched_count: raise ValueError('Business no longer exists.')
                return callback()
            try:
                return mongo_session.with_transaction(run,read_concern=ReadConcern('snapshot'),write_concern=WriteConcern('majority'),max_commit_time_ms=10000)
            finally:
                self.mongo_session=None
                self.write_allowed=False

    def run_snapshot(self,callback):
        with self.backend.client.start_session() as mongo_session:
            self.mongo_session=mongo_session
            try:
                return mongo_session.with_transaction(lambda _:callback(),read_concern=ReadConcern('snapshot'),write_concern=WriteConcern('majority'),max_commit_time_ms=10000)
            finally:
                self.mongo_session=None

    def __enter__(self):
        self._require_transaction(); return self

    def __exit__(self,*args):
        return False

    def rollback(self):
        if self.mongo_session is not None and self.mongo_session.in_transaction: self.mongo_session.abort_transaction()

    def register_business(self,name,email,password_hash,settings):
        if self.business_id is not None: raise PermissionError('Registration requires an unauthenticated context.')
        bid=self.insert('businesses',{'name':name,'lock_version':0})
        self.business_id=bid
        try:
            uid=self.insert('users',{'email':email,'password_hash':password_hash})
            self.insert('business_settings',{'data':settings})
            return bid,uid
        finally:
            self.business_id=None
