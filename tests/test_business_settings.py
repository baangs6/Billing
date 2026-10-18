import secrets
import pytest
import pymupdf
from werkzeug.datastructures import MultiDict
from test_app import mongo_backend,workspace,payload,values
from saas import Platform
from company_profile import custom_headers
from fiscal_period import validate_period,close_date

PASSWORD='correct horse battery staple'


def test_header_validation_and_period_boundaries():
    assert custom_headers(MultiDict([('headers_present','1'),('header_name','Alt number'),('header_value','123')]),[])==[dict(name='Alt number',value='123')]
    for data in [MultiDict([('headers_present','1'),('header_name','A'),('header_value','')]),MultiDict([('headers_present','1'),('header_name','A'),('header_name','a'),('header_value','1'),('header_value','2')])]:
        with pytest.raises(ValueError): custom_headers(data,[])
    with pytest.raises(ValueError): validate_period('2026-03-31','payments',dict(date='2026-04-01'),dict(date='2026-03-01'))
    with pytest.raises(ValueError): validate_period('2026-03-31','customers',dict(data=dict(opening_balance=100)))
    with pytest.raises(ValueError): validate_period('2026-03-31','finance_entries',dict(kind='OPENING',date='2026-04-01'))
    assert close_date('2026-03-31','2026-10-19')=='2026-03-31'
    with pytest.raises(ValueError): close_date('2027-03-31','2026-10-19')


def test_multi_classification_headers_and_old_invoice_snapshot(workspace):
    client,post,backend=workspace
    post('/billing',payload())
    old=backend.database.invoices.find_one({})
    with client.session_transaction() as saved: csrf=saved['csrf']
    response=client.post('/business-profile',data=MultiDict([('csrf',csrf)]+[('types_present','1'),('business_types','Retail'),('business_types','Service'),('industry','Electronics'),('registration_type','Sole Proprietorship'),('headers_present','1'),('header_name','Alt number'),('header_value','555-0123'),('invoice_theme','A4_CLASSIC'),('payment_details','BOTH')]))
    assert response.status_code==302
    extra=backend.database.business_settings.find_one({})['data']['extended']
    assert extra['business_types']==['Retail','Service']
    assert extra['custom_headers']==[dict(name='Alt number',value='555-0123')]
    assert backend.database.invoices.find_one({})==old
    post('/billing',payload())
    for url in ['/invoices/2/pdf','/account','/business-profile']:
        response=client.get(url);assert response.status_code==200,url
        if url.endswith('pdf'):
            with pymupdf.open(stream=response.data,filetype='pdf') as document: assert '555-0123' in ''.join(page.get_text() for page in document)
    assert b'owner@example.com' in client.get('/account').data


def test_unregistered_business_hides_and_rejects_gst(workspace):
    from test_trade import supplier,purchase
    client,post,backend=workspace
    post('/billing',payload())
    original=backend.database.invoices.find_one({})
    post('/business-profile',dict(gst_registration='UNREGISTERED',invoice_theme='A5',payment_details='BOTH'))
    assert b'<option value="GST"' not in client.get('/billing').data
    assert b'<option value="GST"' not in client.get('/proposals/new').data
    post('/billing',payload());assert backend.database.invoices.count_documents({})==1
    supplier(post);post('/purchases',purchase(type='GST'))
    assert backend.database.purchases.count_documents({})==0
    assert backend.database.invoices.find_one({})==original
    post('/billing',payload()|dict(type='NON-GST'))
    assert backend.database.invoices.count_documents({})==2


def test_year_close_locks_old_money_but_carries_balances_and_service_history(workspace):
    client,post,backend=workspace
    post('/billing',payload()|dict(date='2025-10-02'))
    before=backend.database.invoices.find_one({})
    data=dict(end='2026-03-31',password=PASSWORD,confirmation='CLOSE FINANCIAL YEAR',expected_closed_through='')
    post('/business/close-year',data|dict(password='wrong'))
    assert 'closed_through' not in backend.database.business_settings.find_one({})['data']
    post('/business/close-year',data)
    assert backend.database.business_settings.find_one({})['data']['closed_through']=='2026-03-31'
    assert backend.database.invoices.find_one({})==before and values(backend,'inventory','quantity')==[8000]
    post('/invoices/1/cancel',{})
    post('/billing',payload()|dict(id='1',version='1',date='2026-10-02'))
    post('/payments',dict(invoice='1',amount='50',date='2026-03-01',method='Cash',submission=secrets.token_hex(32)))
    assert backend.database.invoices.find_one({})==before and backend.database.payments.count_documents({})==0
    post('/payments',dict(invoice='1',amount='50',date='2026-10-02',method='Cash',submission=secrets.token_hex(32)))
    assert backend.database.payments.count_documents({})==1
    post('/service-reminders',dict(id='1',version='1'))
    assert backend.database.invoices.find_one({})['service_completed_at']
    post('/billing',payload());assert backend.database.invoices.count_documents({})==2
    post('/customers',dict(id='1',name='Anita Stores',opening_balance='10'))
    assert backend.database.customers.find_one({})['data'].get('opening_balance',0)==0
    from test_finance import entry
    post('/finance',entry(kind='OPENING',date='2026-04-01'))
    assert backend.database.finance_entries.count_documents({})==0


@pytest.mark.parametrize('action',['delete','reset'])
def test_removing_company_preserves_other_root_and_staff_membership(workspace,action):
    from werkzeug.security import generate_password_hash
    client,post,backend=workspace
    alias=create_linked(client,post,backend)
    database=backend.database
    root=database.users.find_one({'id':1});root.pop('_id')
    root.update(id=900,email='second@example.com',password_hash=generate_password_hash(PASSWORD))
    database.users.insert_one(root)
    staff=database.roles.find_one({'business_id':2,'protected':{'$ne':True}})
    if not staff:
        database.roles.insert_one(dict(id=901,business_id=2,name='STAFF',permissions=['customer.view'],protected=False))
        staff=database.roles.find_one({'id':901})
    member=database.users.find_one({'id':alias['id']});member.pop('_id')
    member.update(id=902,identity_id=900,role_id=staff['id'],email='linked-second@internal.invalid')
    database.users.insert_one(member)
    before=database.business_settings.find_one({'business_id':2})
    if action=='delete': post('/business/delete',dict(password=PASSWORD,confirmation='DELETE BUSINESS'))
    else: post('/settings',dict(action='reset_company',password=PASSWORD,confirmation='RESET COMPANY'))
    survivor=backend.login_user('second@example.com')
    assert survivor and survivor['business_id']==2 and survivor['role_id']==staff['id']
    assert database.business_settings.find_one({'business_id':2})==before
    client.get('/login');post('/login',dict(email='second@example.com',password=PASSWORD))
    with client.session_transaction() as saved: assert saved['business']==2


def create_linked(client,post,backend):
    plan=backend.database.plans.find_one({'active':True})
    data=dict(action='create',name='Second Company',state='Kerala',plan_id=str(plan['id']),submission=secrets.token_hex(32))
    assert post('/businesses',data).status_code==302
    assert post('/businesses',data).status_code==302
    assert backend.database.businesses.count_documents({})==2
    company=backend.database.businesses.find_one({'id':2});assert company['status']=='PENDING'
    alias=backend.database.users.find_one({'business_id':2});assert alias['identity_id']==1
    assert backend.login_user(alias['email']) is None
    Platform(backend).company_action(99,2,'approve',dict(plan_id=str(plan['id']),trial='1',reason='Approved isolated linked business test'))
    return alias


def test_linked_businesses_are_isolated_and_root_credentials_revoke_sessions(workspace):
    client,post,backend=workspace
    post('/billing',payload())
    alias=create_linked(client,post,backend)
    assert post('/businesses',dict(action='switch',business='999')).status_code==403
    post('/businesses',dict(action='switch',business='2'))
    with client.session_transaction() as saved: assert saved['business']==2 and saved['identity_id']==1
    assert client.get('/invoices/1').status_code==404
    assert b'Anita Stores' not in client.get('/customers').data
    assert b'owner@example.com' in client.get('/account').data
    post('/customers',dict(name='Second customer',state='Kerala'))
    assert backend.database.customers.count_documents({'business_id':1})==1
    backend.database.users.update_one({'id':1},{'$inc':{'session_version':1}})
    assert client.get('/customers').status_code==302
    with client.session_transaction() as saved: assert 'user' not in saved


def test_delete_single_company_requires_password_and_removes_login(workspace):
    client,post,backend=workspace
    data=dict(password=PASSWORD,confirmation='DELETE BUSINESS')
    post('/business/delete',data|dict(password='wrong'))
    assert backend.database.businesses.count_documents({})==1
    assert post('/business/delete',data).status_code==302
    assert backend.database.businesses.count_documents({})==0
    assert backend.database.invoices.count_documents({})==0
    assert backend.login_user('owner@example.com') is None


def test_deleting_primary_business_retains_other_business_and_shared_login(workspace):
    client,post,backend=workspace
    create_linked(client,post,backend)
    before=backend.database.business_settings.find_one({'business_id':2})
    post('/business/delete',dict(password=PASSWORD,confirmation='DELETE BUSINESS'))
    assert backend.database.businesses.find_one({'id':1}) is None
    assert backend.database.business_settings.find_one({'business_id':2})==before
    root=backend.login_user('owner@example.com');assert root and root['business_id']==2
    client.get('/login')
    assert post('/login',dict(email='owner@example.com',password=PASSWORD)).status_code==302
    with client.session_transaction() as saved: assert saved['business']==2


def test_staff_cannot_close_delete_or_create_business(workspace):
    client,post,backend=workspace
    role=backend.database.roles.find_one({'name':'BILLING_STAFF','business_id':1})
    backend.database.users.update_one({'id':1},{'$set':{'role_id':role['id']}})
    for route,data in [('/business/delete',dict(password=PASSWORD,confirmation='DELETE BUSINESS')),('/business/close-year',dict(end='2026-03-31',password=PASSWORD,confirmation='CLOSE FINANCIAL YEAR')),('/businesses',dict(action='create'))]:
        assert post(route,data).status_code==403
    assert backend.database.businesses.count_documents({})==1


def test_snapshot_headers_on_purchase_and_note_exports(workspace):
    from test_trade import supplier,purchase
    client,post,backend=workspace
    post('/business-profile',dict(invoice_theme='A5',headers_present='1',header_name='Alt number',header_value='555-0123',empty_signature_box='1'))
    supplier(post);post('/purchases?orders=1',purchase());post('/purchases',purchase())
    post('/purchases/1',dict(action='return',date='2026-10-18',quantity_0='1',reason='Damaged',submission=secrets.token_hex(32)))
    for url in ['/purchases/1?export=pdf','/purchases/1?orders=1&export=pdf','/notes/purchase/1/pdf']:
        response=client.get(url);assert response.status_code==200
        with pymupdf.open(stream=response.data,filetype='pdf') as document:
            text=''.join(page.get_text() for page in document)
            assert '555-0123' in text and 'Authorized Signatory' in text,url
