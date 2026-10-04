import io
import secrets
from PIL import Image
from test_app import mongo_backend, workspace, payload, count

def entry(**changes):
    return dict(kind='EXPENSE',date='2026-10-04',amount='100',category='Rent',title='Office rent',account='Cash',method='Cash',reference='',notes='',submission=secrets.token_hex(32))|changes

def test_finance_summary_invoice_income_opening_and_exports(workspace):
    client,post,backend=workspace
    post('/finance',entry(kind='OPENING',date='2026-10-01',amount='1000',category='Opening balance',title='Starting cash'))
    post('/finance',entry())
    post('/finance',entry(kind='INCOME',amount='50',category='Other income',title='Other receipt'))
    post('/billing',payload()|dict(received='50'))
    # The fixture invoice receipt is dated October 2; this is cash received,
    # not the invoice's full value of INR 236.
    response=client.get('/finance?from=2026-10-01&to=2026-10-31')
    assert response.status_code==200
    text=response.get_data(as_text=True)
    assert '₹1,000.00' in text and 'Invoice payment' in text and 'INV/26-27/001' in text
    assert '₹236.00' not in text
    assert count(backend,'finance_entries')==3
    csv=client.get('/finance?from=2026-10-01&to=2026-10-31&export=csv')
    assert csv.status_code==200 and b'Invoice payment' in csv.data
    assert client.get('/finance?export=pdf').data.startswith(b'%PDF')
    assert client.get('/finance?from=2026-11-01&to=2026-10-01').status_code==302

def test_finance_idempotence_edit_void_and_receipts(workspace):
    client,post,backend=workspace
    image=io.BytesIO(); Image.new('RGB',(20,20),'white').save(image,'PNG'); image.seek(0)
    data=entry(notes='<script>alert(1)</script>')
    post('/finance',data|{'receipt':(image,'bill.png')})
    post('/finance',data)
    assert count(backend,'finance_entries')==1
    record=backend.database.finance_entries.find_one({})
    url=f"/finance/{record['id']}/receipt"
    receipt=client.get(url)
    assert receipt.status_code==200 and receipt.data.startswith(b'\xff\xd8')
    assert 'attachment' in receipt.headers['Content-Disposition']
    assert b'&lt;script&gt;' in client.get('/finance').data
    post('/finance',entry(id=str(record['id']),version='1',amount='200'))
    updated=backend.database.finance_entries.find_one({'id':record['id']})
    assert updated['amount']==20000 and updated['version']==2 and updated['receipt']==record['receipt']
    post('/finance',entry(id=str(record['id']),version='1',amount='999'))
    assert backend.database.finance_entries.find_one({'id':record['id']})['amount']==20000
    post('/finance',dict(id=str(record['id']),version='2',action='void'))
    assert backend.database.finance_entries.find_one({'id':record['id']})['status']=='VOID'
    assert b'Office rent' not in client.get('/finance').data
    assert client.get(url).status_code==200

def test_finance_opening_baseline_and_invalid_entries(workspace):
    client,post,backend=workspace
    post('/billing',payload()|dict(received='50'))
    post('/finance',entry(kind='OPENING',date='2026-10-03',amount='1000',category='Opening balance',title='Starting cash'))
    post('/finance',entry(amount='100'))
    csv=client.get('/finance?from=2026-10-01&to=2026-10-31&export=csv')
    assert b'Invoice payment' not in csv.data
    assert b'Closing balance' in client.get('/finance').data and '₹900.00' in client.get('/finance').get_data(as_text=True)
    post('/finance',entry(kind='OPENING',amount='500'))
    assert count(backend,'finance_entries')==2
    for changes in (dict(amount='0'),dict(amount='-1'),dict(kind='BAD'),dict(account='BAD'),dict(category='Invoice collections'),dict(date='bad'),dict(submission='bad')):
        post('/finance',entry(**changes))
        assert count(backend,'finance_entries')==2
    post('/finance',entry(receipt=(io.BytesIO(b'bad'),'receipt.exe')))
    assert count(backend,'finance_entries')==2
    assert client.post('/finance',data=entry()).status_code==400

def test_finance_tenant_isolation_and_role_enforcement(workspace):
    client,post,backend=workspace
    post('/finance',entry(receipt=(io.BytesIO(b'%PDF-1.4\nQA'),'receipt.pdf')))
    record=backend.database.finance_entries.find_one({})
    post('/logout',{})
    client.get('/register')
    post('/register',dict(name='Other company',email='other@example.com',password='another secure password'))
    assert b'Office rent' not in client.get('/finance').data
    assert client.get(f"/finance/{record['id']}/receipt").status_code==404
    assert client.get(f"/finance?edit={record['id']}").status_code==404
    role=backend.database.roles.find_one({'business_id':2,'name':'BILLING_STAFF'})
    backend.database.users.update_one({'business_id':2},{'$set':{'role_id':role['id']}})
    assert client.get('/finance').status_code==403
    assert post('/finance',entry()).status_code==403
    backend.database.roles.update_one({'id':role['id']},{'$push':{'permissions':'finance.view'}})
    assert client.get('/finance').status_code==200
    assert post('/finance',entry()).status_code==403
    assert client.get('/finance?export=csv').status_code==403


def test_zero_opening_balance_and_account_filter(workspace):
    client,post,backend=workspace
    post('/finance',entry(kind='OPENING',account='Bank',method='Bank Transfer',amount='0',category='Opening balance',title='Start bank tracking'))
    record=backend.database.finance_entries.find_one({'kind':'OPENING'})
    assert record and record['amount']==0
    post('/finance',entry(kind='INCOME',account='Bank',method='UPI',amount='50',category='Other income',title='Bank income'))
    post('/finance',entry(amount='20',title='Cash expense'))
    csv=client.get('/finance?account=Bank&export=csv')
    assert b'Bank income' in csv.data and b'Cash expense' not in csv.data
    backend.ensure_finance_storage()
    assert count(backend,'finance_entries')==3
