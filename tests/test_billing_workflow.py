import json
import secrets
from test_app import mongo_backend, workspace, payload, values


def test_walk_in_has_no_customer_record_and_requires_full_payment(workspace):
    client,post,backend=workspace
    data=payload()
    data.update(customer='walk-in',received='236')
    assert post('/billing',data).status_code==302
    inv=backend.database.invoices.find_one({})
    assert inv['customer_id']==0 and inv['snapshot']['walk_in']
    assert inv['snapshot']['customer']['data']['state']=='Tamil Nadu'
    assert backend.database.customers.count_documents({})==1
    assert values(backend,'inventory','quantity')==[8000]
    assert client.get('/invoices/1').status_code==200
    assert client.get('/invoices/1/pdf').data.startswith(b'%PDF')
    assert client.get('/accounting-reports?report=Receivables').status_code==200
    post('/billing',payload()|dict(customer='walk-in',received='0'))
    assert backend.database.invoices.count_documents({})==1
    assert values(backend,'inventory','quantity')==[8000]
    post('/sales-returns',dict(invoice='1',date='2026-10-18',quantity_0='1',reason='Walk-in return',submission=secrets.token_hex(32)))
    assert values(backend,'inventory','quantity')==[9000]
    report=client.get('/accounting-reports?report=Receivables&export=csv').data
    assert b'Walk-in sales' in report and b'-118.00' in report


def test_due_date_rounding_and_customer_balance_snapshot(workspace):
    client,post,backend=workspace
    post('/customers',dict(id='1',name='Anita Stores',credit_days='30',opening_balance='10'))
    post('/billing',payload()|dict(received='100',manual_round_off='-0.49',due_date='2026-11-15',eway_bill='123456789012'))
    inv=backend.database.invoices.find_one({})
    assert inv['total']==23551 and inv['round_off']==-49
    assert inv['snapshot']['previous_balance']==1000
    assert inv['snapshot']['due_date']=='2026-11-15'
    assert b'"previous_balance": 14551' in client.get('/billing').data
    for extra in [dict(round_total='1',manual_round_off='0.50'),dict(due_date='2026-01-01'),dict(eway_bill='bad'),dict(manual_round_off='-1.01')]:
        post('/billing',payload()|extra)
    assert backend.database.invoices.count_documents({})==1
    assert values(backend,'inventory','quantity')==[8000]


def test_quick_bank_idempotency_and_invoice_snapshot(workspace):
    client,post,backend=workspace
    with client.session_transaction() as saved: csrf=saved['csrf']
    data=dict(csrf=csrf,action='create',name='Invoice bank',kind='Bank',date='2026-10-01',opening='0',bank='Example Bank',holder='Business Owner',account_number='12345678',ifsc='TEST0000001',upi='shop@upi',submission=secrets.token_hex(32))
    for attempt in range(2):
        response=client.post('/accounts',data=data,headers={'Accept':'application/json'})
        assert response.status_code in (200,201) and response.json['account']['id']==1
    assert backend.database.bank_accounts.count_documents({})==1
    post('/billing',payload()|dict(print_account='1'))
    inv=backend.database.invoices.find_one({})
    assert '12345678' in inv['snapshot']['business']['bank']
    assert inv['snapshot']['business']['upi']=='shop@upi'
    backend.database.bank_accounts.update_one({'id':1},{'$set':{'data.account_number':'changed'}})
    assert '12345678' in backend.database.invoices.find_one({})['snapshot']['business']['bank']
    foreign=dict(backend.database.bank_accounts.find_one({}));foreign.pop('_id');foreign.update(id=99,business_id=2,submission=secrets.token_hex(32))
    backend.database.bank_accounts.insert_one(foreign)
    assert post('/billing',payload()|dict(print_account='99')).status_code==404
    assert backend.database.invoices.count_documents({})==1
    post('/billing',payload()|dict(id='1',version='1'))
    assert '12345678' in backend.database.invoices.find_one({})['snapshot']['business']['bank']


def test_print_options_and_duplicate_do_not_mutate_invoice(workspace):
    import pymupdf
    client,post,backend=workspace
    post('/customers',dict(id='1',name='Anita Stores',shipping_address='Delivery address',pan='ABCDE1234F'))
    post('/billing',payload()|dict(print_options='1',payment_details='BANK',thermal_layout='ADVANCED',show_previous_balance='1',show_time='1'))
    before=backend.database.invoices.find_one({})
    with pymupdf.open(stream=client.get('/invoices/1/pdf?copy=duplicate').data,filetype='pdf') as document:
        text=''.join(page.get_text() for page in document)
        assert 'DUPLICATE COPY' in text and 'Delivery address' in text and 'ABCDE1234F' in text
    assert backend.database.invoices.find_one({})==before
    assert client.get('/billing?edit=1').status_code==200
    post('/billing',payload()|dict(payment_details='invalid'))
    assert backend.database.invoices.count_documents({})==1


def test_quick_customer_validation_and_bank_permission(workspace):
    client,post,backend=workspace
    response=post('/billing/customer',dict(name='Quick party',gstin='bad'))
    assert response.status_code==400 and response.json['error']
    assert backend.database.customers.count_documents({})==1
    role=backend.database.roles.find_one({'name':'BILLING_STAFF','business_id':1})
    backend.database.roles.update_one({'id':role['id']},{'$set':{'permissions':['invoice.create']}})
    backend.database.users.update_one({'id':1},{'$set':{'role_id':role['id']}})
    assert b'id="open-bank-popup"' not in client.get('/billing').data
    assert post('/accounts',dict(action='create',date='2026-10-02',name='Forbidden',kind='Bank',submission=secrets.token_hex(32))).status_code==403
    assert backend.database.bank_accounts.count_documents({})==0


def test_walk_in_interstate_tax_and_no_orphan_customer(workspace):
    client,post,backend=workspace
    post('/billing',payload()|dict(customer='walk-in',walk_in_state='Karnataka',received='236'))
    inv=backend.database.invoices.find_one({})
    assert inv['igst']==3600 and inv['cgst']==0 and inv['sgst']==0
    assert backend.database.customers.count_documents({})==1
    assert client.get('/billing?edit=1').status_code==200
