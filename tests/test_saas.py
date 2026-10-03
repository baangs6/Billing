import base64
import secrets
import time
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import pytest
from werkzeug.security import generate_password_hash
from admin_app import create_admin_app, totp
from app import create_app
from saas import Platform, stamp, now, digest, subscription_state, month_add, FEATURES
from test_app import mongo_backend, workspace, payload

@pytest.fixture
def owner(workspace):
    client,post,backend=workspace; platform=Platform(backend)
    app=create_admin_app(backend); app.config['TESTING']=True
    secret=base64.b32encode(secrets.token_bytes(20)).decode(); recovery=secrets.token_hex(8)
    password='owner secure QA password'
    def insert(ms,store):
        platform.insert('admin_users',dict(name='Platform Owner',email='admin@example.com',password_hash=generate_password_hash(password),totp_secret=app.extensions['cipher'].encrypt(secret.encode()).decode(),last_totp_counter=0,recovery_hashes=[digest(recovery)],active=True,session_version=0),ms)
    platform.transaction(insert)
    admin=app.test_client(); admin.get('/login')
    def submit(url,data):
        with admin.session_transaction() as state: missing='csrf' not in state
        if missing: admin.get('/login')
        with admin.session_transaction() as state: data=dict(data,csrf=state['csrf'])
        return admin.post(url,data=data)
    assert submit('/login',dict(email='admin@example.com',password=password,code=recovery)).status_code==302
    return admin,submit,backend,secret,password

def registration(backend,email='pending@example.com'):
    return dict(name='Pending company',owner_name='New Owner',phone='9876543210',address='22 Example Road',state='Tamil Nadu',pin='600001',business_type='Retail',email=email,password='new secure company password',plan_id=backend.database.plans.find_one({'active':True})['id'])

def register_pending(backend,email='pending@example.com'):
    app=create_app(backend=backend); app.config['TESTING']=True; client=app.test_client(); client.get('/register')
    with client.session_transaction() as state: token=state['csrf']
    response=client.post('/register',data=registration(backend,email)|dict(csrf=token))
    assert response.status_code==302
    with client.session_transaction() as state: bid=state['business']
    return client,bid

def test_owner_pages_and_auth_separation(owner,workspace):
    admin,post,backend,secret,password=owner
    for path in ['/','/companies','/companies?status=PENDING','/companies/1','/plans','/plans?edit=2','/subscriptions','/subscriptions?expiring=1','/users','/payments','/audit','/settings']:
        response=admin.get(path); assert response.status_code==200,(path,response.data)
        assert b'password_hash' not in response.data and b'recovery_hashes' not in response.data
    assert admin.get('/billing').status_code==404
    assert admin.post('/companies/1',data=dict(action='suspend',reason='no csrf')).status_code==400
    normal=workspace[0]
    anonymous=admin.application.test_client()
    # A company session signed by the company app cannot authenticate the owner service.
    serializer=normal.application.session_interface.get_signing_serializer(normal.application)
    with normal.session_transaction() as state: cookie=serializer.dumps(dict(state))
    anonymous.set_cookie('ledger_admin',cookie)
    assert anonymous.get('/companies').status_code==302
    assert anonymous.get('/companies').headers['Location']=='/login'

def test_legacy_company_without_registration_timestamp(owner):
    admin,post,backend,*_=owner
    backend.database.businesses.update_one({'id':1},{'$unset':{'created_at':''}})
    for path in ('/','/companies','/companies/1','/subscriptions'):
        response=admin.get(path)
        assert response.status_code==200,(path,response.data)
    assert b'Unknown' in admin.get('/').data

def test_approval_rejection_and_idempotency(owner):
    admin,post,backend,*_=owner; pending,bid=register_pending(backend)
    assert pending.get('/billing').headers['Location']=='/subscription'
    assert b'awaiting administrator approval' in pending.get('/subscription').data
    with pending.session_transaction() as state: csrf=state['csrf']
    assert pending.post('/products',data=dict(csrf=csrf,name='blocked')).headers['Location']=='/subscription'
    assert backend.database.products.count_documents({'business_id':bid})==0
    assert post(f'/companies/{bid}',dict(action='reject',reason='')).status_code==302
    assert backend.database.businesses.find_one({'id':bid})['status']=='PENDING'
    post(f'/companies/{bid}',dict(action='reject',reason='Missing details'))
    assert b'Missing details' in pending.get('/subscription').data
    post(f'/companies/{bid}',dict(action='review',reason='Details checked'))
    data=dict(action='approve',plan_id=registration(backend)['plan_id'],trial='1',reason='Approved')
    post(f'/companies/{bid}',data); post(f'/companies/{bid}',data)
    assert backend.database.subscriptions.count_documents({'business_id':bid})==1
    assert backend.database.admin_audit.count_documents({'business_id':bid,'action':'company.approve'})==1
    assert pending.get('/billing').status_code==200

def test_expiry_suspension_and_renewal(owner,workspace):
    admin,post,backend,*_=owner; company,company_post,_=workspace; store=backend.scope(1)
    post('/companies/1',dict(action='suspend',reason='Access review'))
    assert company.get('/invoices/1/pdf').headers['Location']=='/subscription'
    post('/companies/1',dict(action='reactivate',reason='Review complete'))
    assert company.get('/').status_code==200
    store.run_transaction(lambda:store.update('subscriptions',{'current':True},{'expiry_at':stamp(now()-timedelta(seconds=1))}))
    assert company_post('/billing',payload()).headers['Location']=='/subscription'
    assert backend.database.invoices.count_documents({})==0
    assert b'Your subscription has expired' in company.get('/subscription').data
    plan=registration(backend)['plan_id']
    company_post('/subscription',dict(plan_id=plan,cycle='monthly',notes='Please renew'))
    assert backend.database.renewal_requests.count_documents({'status':'PENDING'})==1
    post('/companies/1',dict(action='renew',plan_id=plan,cycle='monthly',reason='Renewal approved'))
    assert backend.database.renewal_requests.find_one({})['status']=='APPROVED'
    assert company.get('/billing').status_code==200
    assert backend.database.subscriptions.count_documents({'business_id':1,'current':True})==1

def test_plan_snapshots_features_and_quota(owner,workspace):
    admin,post,backend,*_=owner; company,company_post,_=workspace
    plan=backend.database.plans.find_one({'active':True}); original=backend.database.subscriptions.find_one({'current':True})['plan']
    fields=dict(id=plan['id'],name='Restricted',monthly_price='100',yearly_price='1000',trial_days='7',max_users='1',max_products='1',max_invoices='1',active='1')
    post('/plans',fields)
    assert backend.database.subscriptions.find_one({'current':True})['plan']['version']==original['version']
    post('/companies/1',dict(action='assign',plan_id=plan['id'],cycle='monthly',reason='Apply restricted rules'))
    for path in ['/inventory','/reports','/company-users','/company-roles','/invoices/999/pdf']:
        assert company.get(path).status_code==403,path
    company_post('/billing',payload()) # GST rejected.
    assert backend.database.invoices.count_documents({})==0
    free=payload(); free['type']='NON-GST'; free['items']='[{"name":"Service","quantity":1,"rate":100,"gst":0}]'
    company_post('/billing',free)
    assert backend.database.invoices.count_documents({})==1
    free['submission']=secrets.token_hex(32); company_post('/billing',free)
    assert backend.database.invoices.count_documents({})==1
    assert backend.database.inventory.find_one({})['quantity']==10000
    company_post('/products',dict(name='Second product',sku='SECOND',category='Other',unit='PCS',gst='0',stock='1',selling_price='1',purchase_price='1',mrp='1'))
    assert backend.database.products.count_documents({})==1
    # Zero quotas must mean zero, never unlimited.
    store=backend.scope(1); sub=store.one('subscriptions',{'current':True}); snapshot=sub['plan']; snapshot['limits']['invoices']=0
    store.run_transaction(lambda:store.update('subscriptions',{'id':sub['id']},{'plan':snapshot}))
    free['submission']=secrets.token_hex(32); company_post('/billing',free)
    assert backend.database.invoices.count_documents({})==1

def test_concurrent_monthly_invoice_limit(workspace):
    client,post,backend=workspace; store=backend.scope(1); sub=store.one('subscriptions',{'current':True}); plan=sub['plan']; plan['limits']['invoices']=1
    store.run_transaction(lambda:store.update('subscriptions',{'id':sub['id']},{'plan':plan}))
    with client.session_transaction() as state: credentials=dict(state)
    def create(_):
        peer=client.application.test_client()
        with peer.session_transaction() as state: state.update(credentials)
        return peer.post('/billing',data=payload()|dict(csrf=credentials['csrf']))
    with ThreadPoolExecutor(max_workers=2) as executor: list(executor.map(create,range(2)))
    assert backend.database.invoices.count_documents({})==1
    assert backend.database.inventory.find_one({})['quantity']==8000

def test_staff_permissions_revocation_and_last_admin(owner,workspace):
    admin,admin_post,backend,*_=owner; company,post,_=workspace
    role=backend.database.roles.find_one({'business_id':1,'name':'INVENTORY_STAFF'})
    post('/company-users',dict(name='Stock staff',email='stock@example.com',password='staff secure password',role_id=role['id'],active='1'))
    staff=company.application.test_client(); staff.get('/login')
    with staff.session_transaction() as state: token=state['csrf']
    staff.post('/login',data=dict(csrf=token,email='stock@example.com',password='staff secure password'))
    assert staff.get('/inventory').status_code==200
    for path in ['/billing','/invoices','/reports','/settings','/company-users','/company-roles']:
        assert staff.get(path).status_code==403,path
    assert b'Outstanding' not in staff.get('/').data
    with staff.session_transaction() as state: token=state['csrf']
    assert staff.post('/billing',data=payload()|dict(csrf=token)).status_code==403
    uid=backend.database.users.find_one({'email':'stock@example.com'})['id']
    admin_post('/users',dict(id=uid,business_id=1,active='0',reason='Disabled QA user'))
    assert staff.get('/inventory').headers['Location']=='/login'
    owner_role=backend.database.roles.find_one({'business_id':1,'protected':True})
    post('/company-users',dict(id=1,name='Owner',email='owner@example.com',role_id=role['id'],active='1'))
    assert backend.database.users.find_one({'id':1})['role_id']==owner_role['id']
    admin_post('/users',dict(id=1,business_id=1,active='0',reason='Attempt last-admin disable'))
    assert backend.database.users.find_one({'id':1})['active'] is True
    post('/company-roles',dict(id=owner_role['id'],name='Changed',permissions=[]))
    assert backend.database.roles.find_one({'id':owner_role['id']})['name']=='COMPANY_ADMIN'

def test_payment_ledger_tenant_validation_and_no_duplicate(owner,workspace):
    admin,post,backend,*_=owner; company,company_post,_=workspace
    plan=registration(backend)['plan_id']; post('/companies/1',dict(action='renew',plan_id=plan,cycle='monthly',reason='Create paid period'))
    sub=backend.database.subscriptions.find_one({'business_id':1,'current':True}); token=secrets.token_hex(32)
    payment=dict(business_id=1,subscription_id=sub['id'],amount='250.50',date=stamp()[:10],method='UPI',reference='QA-RECEIPT',submission=token)
    post('/payments',payment); post('/payments',payment)
    assert backend.database.subscription_payments.count_documents({})==1
    assert backend.database.subscription_payments.find_one({})['amount']==25050
    assert backend.database.payments.count_documents({})==0
    pending,bid=register_pending(backend)
    post('/payments',payment|dict(business_id=bid,submission=secrets.token_hex(32)))
    assert backend.database.subscription_payments.count_documents({})==1
    assert b'250.50' in admin.get('/').data

def test_owner_mfa_replay_recovery_and_expired_session(owner):
    admin,post,backend,secret,password=owner
    post('/logout',{})
    current=totp(secret,int(time.time())//30)
    assert post('/login',dict(email='admin@example.com',password=password,code=current)).headers['Location']=='/'
    post('/logout',{})
    # Same time step cannot be replayed after logout.
    response=post('/login',dict(email='admin@example.com',password=password,code=current))
    assert response.status_code==200
    assert admin.get('/').headers['Location']=='/login'
    # Recovery codes are consumed, not reusable.
    recovery=secrets.token_hex(8)
    backend.database.admin_users.update_one({'id':1},{'$push':{'recovery_hashes':digest(recovery)}})
    assert post('/login',dict(email='admin@example.com',password=password,code=recovery)).headers['Location']=='/'
    backend.database.admin_sessions.update_many({}, {'$set':{'expires_at':now()-timedelta(seconds=1)}})
    assert admin.get('/companies').headers['Location']=='/login'
    assert post('/login',dict(email='admin@example.com',password=password,code=recovery)).status_code==200

def test_first_owner_setup_one_use_local_only(workspace):
    backend=workspace[2]; token=secrets.token_urlsafe(32)
    backend.database.platform_meta.update_one({'_id':'bootstrap'},{'$set':dict(token_hash=digest(token),expires_at=stamp(now()+timedelta(hours=1)))},upsert=True)
    app=create_admin_app(backend); app.config['TESTING']=True; client=app.test_client(); path='/setup/'+token
    assert client.get(path,environ_overrides={'REMOTE_ADDR':'203.0.113.20'}).status_code==403
    assert client.get(path).status_code==200
    with client.session_transaction() as state:
        csrf=state['csrf']; secret=app.extensions['cipher'].decrypt(state['setup_secret'].encode()).decode()
    data=dict(csrf=csrf,name='New Owner',email='newowner@example.com',password='secure owner bootstrap password',code=totp(secret,int(time.time())//30))
    response=client.post(path,data=data)
    assert response.status_code==200 and b'recovery codes' in response.data
    assert backend.database.admin_users.count_documents({})==1
    assert client.get(path).status_code==404
    user=backend.database.admin_users.find_one({})
    assert secret not in user['totp_secret'] and len(user['recovery_hashes'])==8
    assert b'password_hash' not in response.data

def test_registration_closed_and_tenant_user_id(owner,workspace):
    admin,post,backend,*_=owner
    post('/settings',dict(renewal_contact='Call the owner',support_email='support@example.com'))
    guest=create_app(backend=backend).test_client(); guest.get('/register')
    with guest.session_transaction() as state: token=state['csrf']
    assert guest.post('/register',data=registration(backend)|dict(csrf=token)).status_code==403
    post('/settings',dict(registration_open='1',renewal_contact='Call the owner',support_email='support@example.com'))
    other,bid=register_pending(backend)
    role=backend.database.roles.find_one({'business_id':bid,'name':'COMPANY_ADMIN'})
    assert workspace[1]('/company-users',dict(id=1,name='Forged',email='owner@example.com',role_id=role['id'],active='1')).status_code==404
    assert backend.database.users.find_one({'id':1})['name']=='Owner'

def test_calendar_boundaries():
    from datetime import datetime,timezone
    assert month_add(datetime(2028,1,31,tzinfo=timezone.utc),1).day==29
    assert month_add(datetime(2028,2,29,tzinfo=timezone.utc),12).day==28
    assert subscription_state(dict(status='ACTIVE',expiry_at=stamp(now()-timedelta(seconds=1))))=='EXPIRED'

def test_plan_downgrade_staff_and_inventory_reconciliation(owner,workspace):
    admin,post,backend,*_=owner; company,company_post,_=workspace
    role=backend.database.roles.find_one({'business_id':1,'name':'BILLING_STAFF'})
    company_post('/company-users',dict(name='Billing staff',email='billing@example.com',password='staff secure billing password',role_id=role['id'],active='1'))
    staff=company.application.test_client(); staff.get('/login')
    with staff.session_transaction() as state: csrf=state['csrf']
    staff.post('/login',data=dict(csrf=csrf,email='billing@example.com',password='staff secure billing password'))
    assert staff.get('/billing').status_code==200
    plan=backend.database.plans.find_one({'active':True})
    fields=dict(id=plan['id'],name=plan['name'],monthly_price='0',yearly_price='0',trial_days='14',max_users='1',max_products='100',max_invoices='100',active='1',gst='1',reports='1',pdf='1')
    post('/plans',fields); post('/companies/1',dict(action='assign',plan_id=plan['id'],cycle='monthly',reason='Apply single-user plan'))
    assert staff.get('/billing').headers['Location']=='/subscription'
    assert b'does not include staff access' in staff.get('/subscription').data
    assert backend.database.users.count_documents({'active':True})==2 # preserved, not deleted.
    company_post('/billing',payload())
    assert backend.database.invoices.count_documents({})==0
    post('/plans',fields|dict(inventory='1',multiple_users='1',max_users='3'))
    post('/companies/1',dict(action='assign',plan_id=plan['id'],cycle='monthly',reason='Enable inventory'))
    assert backend.database.businesses.find_one({'id':1})['inventory_reconciliation_required'] is True
    company_post('/billing',payload())
    assert backend.database.invoices.count_documents({})==0
    company_post('/inventory',dict(product='1',quantity='12',direction='set',reason='Physical count'))
    assert backend.database.inventory.find_one({})['quantity']==12000
    company_post('/settings',dict(action='reconcile_inventory',confirmed='1'))
    company_post('/billing',payload())
    assert backend.database.inventory.find_one({})['quantity']==10000
    assert backend.database.invoices.count_documents({})==1

def test_admin_sessions_revoked_and_renewal_rejection(owner,workspace):
    admin,post,backend,*_=owner; company,company_post,_=workspace
    plan=registration(backend)['plan_id']
    company_post('/subscription',dict(plan_id=plan,cycle='yearly',notes='Requested'))
    renewal=backend.database.renewal_requests.find_one({})
    post('/companies/1',dict(action='reject_renewal',renewal_id=renewal['id'],reason='Payment not verified'))
    assert backend.database.renewal_requests.find_one({})['status']=='REJECTED'
    assert b'Payment not verified' in company.get('/subscription').data
    post('/companies/1',dict(action='suspend',reason='Company review'))
    post('/companies/1',dict(action='renew',plan_id=plan,cycle='monthly',reason='Renew during review'))
    assert backend.database.businesses.find_one({'id':1})['status']=='SUSPENDED'
    post('/companies/1',dict(action='reactivate',reason='Review complete'))
    assert company.get('/').status_code==200
    backend.database.admin_users.update_one({'id':1},{'$inc':{'session_version':1}})
    assert admin.get('/companies').headers['Location']=='/login'
