import json
from mongo_store import MongoBackend,load_configuration,COLLECTIONS
import secrets
from concurrent.futures import ThreadPoolExecutor
import pytest
from app import create_app, calculate, money, quantity, DEFAULTS
from saas import initialize_saas, Platform, PLATFORM_COLLECTIONS

@pytest.fixture(scope='session')
def mongo_backend():
    uri,_=load_configuration()
    name='ledger_test_'+secrets.token_hex(8)
    backend=MongoBackend(uri,name)
    initialize_saas(backend)
    backend.test_plans=list(backend.database.plans.find({}))
    try: yield backend
    finally:
        assert backend.name.startswith('ledger_test_')
        backend.client.drop_database(backend.name)
        backend.client.close()

@pytest.fixture
def workspace(mongo_backend):
    assert mongo_backend.name.startswith('ledger_test_')
    for collection in COLLECTIONS | {'login_attempts'}:
        mongo_backend.database[collection].delete_many({})
    for collection in PLATFORM_COLLECTIONS-{'platform_meta','platform_settings','plans'}:
        mongo_backend.database[collection].delete_many({})
    mongo_backend.database.plans.delete_many({})
    mongo_backend.database.plans.insert_many(mongo_backend.test_plans)
    mongo_backend.database.platform_settings.update_one({'_id':'policy'},{'$set':{'registration_open':True,'renewal_contact':'','support_email':''}})
    mongo_backend.database.counters.update_many({'_id':{'$ne':'plans'}}, {'$set':{'value':0}})
    path=mongo_backend; app=create_app(backend=path); app.config['TESTING']=True
    client=app.test_client(); client.get('/register')
    with client.session_transaction() as s: token=s['csrf']
    registration=dict(owner_name='Owner',phone='9876543210',address='12 Market Road',state='Tamil Nadu',pin='600001',business_type='Retail',plan_id=str(mongo_backend.database.plans.find_one({'active':True})['id']))
    response=client.post('/register',data=dict(registration,csrf=token,name='Acme Electronics',email='owner@example.com',password='correct horse battery staple'))
    assert response.status_code==302
    Platform(path).company_action(99,1,'approve',dict(plan_id=registration['plan_id'],trial='1',reason='Approved QA workspace'))
    def post(url,data):
        if url=='/register': data=registration|data
        with client.session_transaction() as s: data=dict(data,csrf=s['csrf'])
        response=client.post(url,data=data)
        if url=='/register' and response.status_code==302:
            with client.session_transaction() as s: bid=s['business']
            Platform(path).company_action(99,bid,'approve',dict(plan_id=registration['plan_id'],trial='1',reason='Approved QA workspace'))
        return response
    post('/customers',dict(name='Anita Stores',state='Tamil Nadu',address='12 Market Road',phone='9876543210'))
    post('/products',dict(name='Desk lamp',sku='LAMP-01',category='Lighting',description='',hsn='9405',unit='PCS',gst='18',min_stock='5',selling_price='100',purchase_price='60',mrp='120',stock='10'))
    post('/settings',{k:v for k,v in (DEFAULTS|dict(name='Acme Electronics',gstin='33ABCDE1234F1Z5',state='Tamil Nadu')).items() if k!='negative_stock'})
    return client,post,path

def payload(qty=2,**extra):
    return dict(customer='1',date='2026-10-02',type='GST',terms='Payment due within 15 days.',received='0',submission=secrets.token_hex(32),items=json.dumps([dict(product_id=1,name='Desk lamp',quantity=qty,rate='100',mrp='120',discount='0',gst='18',hsn='9405')]),**extra)

def values(backend,collection,field):
    return [row[field] for row in backend.database[collection].find({}, {'_id':0,field:1}).sort('id',1)]

def count(backend,collection):
    return backend.database[collection].count_documents({})

def test_calculations():
    assert money('1.005')==101
    assert quantity('1.234')==1234
    with pytest.raises(ValueError): quantity('0')
    with pytest.raises(ValueError): money('NaN')
    item=dict(rate=10000,quantity=2000,discount=1000,gst='18')
    result=calculate([item],'GST',False)
    assert result==dict(subtotal=20000,discount=1000,taxable=19000,cgst=1710,sgst=1710,igst=0,total=22420)
    assert calculate([item.copy()],'GST',True)['igst']==3420
    assert calculate([item.copy()],'NON-GST',False)['total']==19000

def test_pages_and_exports(workspace):
    client,post,path=workspace
    assert post('/billing',payload()).status_code==302
    for url in ['/','/customers','/customers?edit=1','/customers?view=1','/products','/products?edit=1','/inventory','/billing','/billing?edit=1','/billing?duplicate=1','/invoices','/invoices/1','/payments','/settings','/reports']:
        response=client.get(url); assert response.status_code==200,(url,response.data)
    for kind in ['Sales','Daily sales','Monthly sales','GST sales','Non-GST sales','Outstanding','Collections','Product sales','Inventory','Low stock','Stock movement']:
        for export in ['', 'csv','pdf']:
            r=client.get('/reports',query_string=dict(report=kind,export=export)); assert r.status_code==200,(kind,export)
    pdf=client.get('/invoices/1/pdf'); assert pdf.data.startswith(b'%PDF')

def test_stock_edit_cancel_idempotency(workspace):
    client,post,path=workspace
    post('/billing',payload()); assert values(path,'inventory','quantity')==[8000]
    post('/billing',payload(3,id='1',version='1')); assert values(path,'inventory','quantity')==[7000]
    post('/billing',payload(4,id='1',version='1')); assert values(path,'inventory','quantity')==[7000]
    post('/invoices/1/cancel',{}); assert values(path,'inventory','quantity')==[10000]
    post('/invoices/1/cancel',{}); assert values(path,'inventory','quantity')==[10000]

def test_oversell_rolls_back(workspace):
    client,post,path=workspace
    post('/billing',payload(20)); assert values(path,'inventory','quantity')==[10000]
    assert count(path,'invoices')==0

def test_duplicate_submission(workspace):
    client,post,path=workspace; data=payload()
    post('/billing',data); post('/billing',data)
    assert values(path,'inventory','quantity')==[8000]
    assert count(path,'invoices')==1

def test_payments_snapshots_and_limits(workspace):
    client,post,path=workspace
    post('/billing',payload()); post('/payments',dict(invoice='1',amount='100',date='2026-10-02',method='UPI'))
    post('/payments',dict(invoice='1',amount='200',date='2026-10-02',method='Cash'))
    assert sum(values(path,'payments','amount'))==10000
    post('/invoices/1/cancel',{}); assert values(path,'invoices','status')==['FINAL']
    post('/payments',dict(invoice='1',amount='136',date='2026-10-02',method='Cash'))
    assert sum(values(path,'payments','amount'))==23600
    path.database.products.update_one({'id':1},{'$set':{'name':'Renamed','selling_price':99999}})
    assert b'Desk lamp' in client.get('/invoices/1').data

def test_security(workspace):
    client,post,path=workspace
    assert client.post('/products',data={}).status_code==400
    second=create_app(backend=path).test_client(); assert second.get('/').status_code==200
    assert second.get('/invoices').status_code==302
    second.get('/register')
    with second.session_transaction() as s: token=s['csrf']
    plan=path.database.plans.find_one({'active':True})
    second.post('/register',data=dict(csrf=token,name='Other company',email='other@example.com',password='another secure password',owner_name='Owner',phone='9876543210',address='Other address',state='Tamil Nadu',pin='600001',business_type='Retail',plan_id=plan['id']))
    Platform(path).company_action(99,2,'approve',dict(plan_id=plan['id'],trial='1',reason='Approved second QA workspace'))
    post('/billing',payload())
    assert second.get('/invoices/1').status_code==404
    assert b'Desk lamp' not in second.get('/products').data

def test_removed_user_session_is_cleared(workspace):
    client,post,path=workspace
    with client.session_transaction() as session: session['user']=99999
    response=client.get('/')
    assert response.status_code==200 and b'Customer login' in response.data
    assert client.get('/login').status_code==200

def test_signed_in_user_goes_to_dashboard(workspace):
    client,post,path=workspace
    for url in ('/register','/login'):
        response=client.get(url)
        assert response.status_code==302 and response.headers['Location']=='/'

def test_registration_errors_preserve_form(workspace):
    client,post,path=workspace
    post('/logout',{})
    client.get('/register')
    response=post('/register',dict(name='My shop',email='new@example.com',password='short'))
    assert response.status_code==422
    assert b'at least 12 characters' in response.data and b'My shop' in response.data
    response=post('/register',dict(name='My shop',email='owner@example.com',password='a strong password here'))
    assert response.status_code==409 and b'already exists' in response.data
    assert count(path,'businesses')==1
    response=client.post('/register',data=dict(name='My shop',email='new@example.com',password='a strong password here',csrf='stale'))
    assert response.status_code==400 and b'page has expired' in response.data
    assert b'new@example.com' in response.data
    response=post('/register',dict(name='My shop',email='new@example.com',password='a strong password here'))
    assert response.status_code==302 and client.get('/').status_code==200

def concurrent_posts(client,url,data):
    with client.session_transaction() as session: credentials=dict(session)
    def send(_):
        peer=client.application.test_client()
        with peer.session_transaction() as session: session.update(credentials)
        return peer.post(url,data=dict(data,csrf=credentials['csrf']))
    with ThreadPoolExecutor(max_workers=2) as executor: return list(executor.map(send,range(2)))

def test_concurrent_duplicate_submission(workspace):
    client,post,backend=workspace
    responses=concurrent_posts(client,'/billing',payload())
    assert all(r.status_code==302 for r in responses)
    assert count(backend,'invoices')==1
    assert values(backend,'inventory','quantity')==[8000]

def test_concurrent_oversell(workspace):
    client,post,backend=workspace
    with client.session_transaction() as session: credentials=dict(session)
    def send(_):
        peer=client.application.test_client()
        with peer.session_transaction() as session: session.update(credentials)
        return peer.post('/billing',data=dict(payload(6),csrf=credentials['csrf']))
    with ThreadPoolExecutor(max_workers=2) as executor: list(executor.map(send,range(2)))
    assert count(backend,'invoices')==1
    assert values(backend,'inventory','quantity')==[4000]

def test_concurrent_overpayment(workspace):
    client,post,backend=workspace
    post('/billing',payload())
    concurrent_posts(client,'/payments',dict(invoice='1',amount='150',date='2026-10-02',method='Cash'))
    assert sum(values(backend,'payments','amount'))==15000

def test_child_tenant_filters(workspace):
    client,post,backend=workspace
    post('/billing',payload())
    other=backend.scope(987654321)
    for collection in ('invoices','invoice_items','payments','stock_movements','inventory','business_settings'):
        assert other.find(collection)==[]
    assert other.one('invoice_items',{'invoice_id':1}) is None
    with pytest.raises(PermissionError): backend.scope().find('invoices')


def test_inline_billing_customer(workspace):
    client,post,backend=workspace
    response=post('/billing/customer',dict(name='Popup customer',phone='9876543210',state='Kerala',email='popup@example.com',address='Inline address'))
    assert response.status_code==201
    customer=response.json['customer']
    row=backend.database.customers.find_one({'id':customer['id']})
    assert row['business_id']==1 and row['data']['state']=='Kerala'
    assert backend.database.audit_events.find_one({'business_id':1,'entity':'customer','entity_id':customer['id']})
    assert post('/billing/customer',dict(name='')).status_code==400
    assert client.post('/billing/customer',data=dict(name='No CSRF')).status_code==400
    assert client.application.test_client().post('/billing/customer',data=dict(name='Anonymous')).status_code in (302,400)
    assert b'customer-search' in client.get('/billing').data
    assert backend.database.invoices.count_documents({})==0

def test_inline_customer_respects_permissions(workspace):
    client,post,backend=workspace
    user=backend.database.users.find_one({'email':'owner@example.com'})
    role=backend.database.roles.find_one({'business_id':1,'id':user['role_id']})
    backend.database.roles.update_one({'id':role['id'],'business_id':1},{'$pull':{'permissions':'customer.manage'}})
    assert post('/billing/customer',dict(name='Forbidden customer')).status_code==403
    assert backend.database.customers.count_documents({'name':'Forbidden customer'})==0


@pytest.mark.parametrize('invoice_type', ['GST', 'NON-GST'])
def test_invoice_gstin_visibility(workspace, invoice_type):
    import pymupdf
    client, post, backend = workspace
    customer_gstin = '33XYZAB9876C1Z2'
    backend.database.customers.update_one({'id': 1}, {'$set': {'data.gstin': customer_gstin}})
    data = payload()
    data['type'] = invoice_type
    assert post('/billing', data).status_code == 302
    html = client.get('/invoices/1').get_data(as_text=True)
    response = client.get('/invoices/1/pdf')
    assert response.status_code == 200
    with pymupdf.open(stream=response.data, filetype='pdf') as document:
        pdf_text = ''.join(page.get_text() for page in document)
    for rendered in (html, pdf_text):
        assert 'Acme Electronics' in rendered and 'Anita Stores' in rendered
        assert 'Tamil Nadu' in rendered
        assert ('Taxable amount' in rendered) == (invoice_type == 'GST')
        assert ('Total amount' in rendered) == (invoice_type == 'NON-GST')
        for value in ('GSTIN:', '33ABCDE1234F1Z5', customer_gstin):
            assert (value in rendered) == (invoice_type == 'GST')
    snapshot = backend.database.invoices.find_one({'id': 1})['snapshot']
    assert snapshot['business']['gstin'] == '33ABCDE1234F1Z5'
    assert snapshot['customer']['data']['gstin'] == customer_gstin


def test_invoice_notes_save_edit_duplicate_and_exports(workspace):
    import pymupdf
    from html import escape
    client, post, backend = workspace
    notes = 'Deliver after 6 PM.\nCall before arrival <please> & confirm.'
    assert post('/billing', payload(notes=notes)).status_code == 302
    assert backend.database.invoices.find_one({'id': 1})['snapshot']['notes'] == notes
    for url in ('/invoices/1', '/billing?edit=1', '/billing?duplicate=1'):
        assert escape(notes) in client.get(url).get_data(as_text=True)
    with pymupdf.open(stream=client.get('/invoices/1/pdf').data, filetype='pdf') as document:
        text = ''.join(page.get_text() for page in document)
        assert 'Deliver after 6 PM.' in text and '<please> & confirm.' in text
    assert post('/billing', payload(id='1', version='1', notes='Updated delivery instructions')).status_code == 302
    assert backend.database.invoices.find_one({'id': 1})['snapshot']['notes'] == 'Updated delivery instructions'
    backend.database.invoices.update_one({'id': 1}, {'$unset': {'snapshot.notes': ''}})
    for url in ('/invoices/1', '/billing?edit=1', '/invoices/1/pdf'):
        assert client.get(url).status_code == 200


@pytest.mark.parametrize('file_type', ['csv', 'xlsx'])
def test_product_import_formats_and_opening_stock(workspace, file_type):
    import io
    from openpyxl import Workbook
    client, post, backend = workspace
    rows=[['name','sku','selling_price','stock','gst'],['Imported lamp','IMPORT-01','123.45','2.125','18']]
    if file_type == 'xlsx':
        workbook=Workbook()
        for row in rows: workbook.active.append(row)
        stream=io.BytesIO(); workbook.save(stream); stream.seek(0)
    else:
        stream=io.BytesIO(b'name,sku,selling_price,stock,gst\nImported lamp,IMPORT-01,123.45,2.125,18\n')
    assert post('/products', {'action':'import','file':(stream,'products.'+file_type)}).status_code == 302
    product=backend.database.products.find_one({'sku':'IMPORT-01'})
    assert product['selling_price']==12345 and product['business_id']==1
    assert backend.database.inventory.find_one({'product_id':product['id']})['quantity']==2125
    assert backend.database.stock_movements.find_one({'product_id':product['id']})['reason']=='Opening stock (import)'
    assert client.get('/products?template=1').status_code==200


def test_product_import_rejects_bad_rows_duplicates_and_quota_atomically(workspace):
    import io
    client, post, backend=workspace
    original=count(backend,'products')
    files=[
        b'name,sku,selling_price\nValid,NEW-1,100\nInvalid,NEW-2,-1\n',
        b'name,sku,selling_price\nDuplicate,LAMP-01,100\n',
        b'name,sku,selling_price\nOne,NEW-1,100\nTwo,new-1,100\n',
        b'name,sku,selling_price\nFormula,NEW-1,=1+2\n',
    ]
    for content in files:
        response=post('/products',{'action':'import','file':(io.BytesIO(content),'products.csv')})
        assert response.status_code in (302,400,422)
        assert count(backend,'products')==original
    subscription=backend.database.subscriptions.find_one({'business_id':1,'current':True})
    backend.database.subscriptions.update_one({'_id':subscription['_id']},{'$set':{'plan.limits.products':1}})
    post('/products',{'action':'import','file':(io.BytesIO(b'name,sku,selling_price\nValid,NEW-1,100\n'),'products.csv')})
    assert count(backend,'products')==original
    assert client.post('/products',data={'action':'import','file':(io.BytesIO(files[0]),'products.csv')}).status_code==400

    role=backend.database.roles.find_one({'business_id':1,'name':'COMPANY_ADMIN'})
    backend.database.roles.update_one({'_id':role['_id']},{'$pull':{'permissions':'product.manage'}})
    response=post('/products',{'action':'import','file':(io.BytesIO(b'name,sku,selling_price\nValid,NEW-1,100\n'),'products.csv')})
    assert response.status_code==403
    assert count(backend,'products')==original
