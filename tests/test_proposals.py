import json
import secrets
from datetime import date,timedelta
import fitz
from app import today
from test_app import mongo_backend,workspace,payload

def proposal_data(**changes):
    data=payload()
    data.update(title='Shop lighting supply',description='Supply and installation of energy-efficient lighting.',valid_until=(date.fromisoformat(today())+timedelta(days=30)).isoformat(),status='DRAFT')
    data.update(changes)
    return data

def test_proposal_drafts_snapshots_pdf_and_no_financial_effect(workspace,tmp_path):
    client,post,backend=workspace; data=proposal_data()
    assert post('/proposals/new',data).headers['Location']=='/proposals/1'
    post('/proposals/new',data) # Duplicate click.
    assert backend.database.proposals.count_documents({})==1
    assert backend.database.invoices.count_documents({})==0
    assert backend.database.payments.count_documents({})==0
    assert backend.database.inventory.find_one({})['quantity']==10000
    for route in ('/proposals','/proposals/new','/proposals/new?edit=1','/proposals/1','/billing?proposal=1'):
        response=client.get(route); assert response.status_code==200,(route,response.data)
    assert backend.database.proposals.find_one({})['total']==23600
    pdf=client.get('/proposals/1/pdf'); assert pdf.status_code==200 and pdf.data.startswith(b'%PDF')
    document=fitz.open(stream=pdf.data,filetype='pdf'); text=''.join(page.get_text() for page in document)
    assert 'PROPOSAL / QUOTATION' in text and 'not a tax invoice' in text
    assert 'Received' not in text and 'Balance due' not in text
    root=__import__('pathlib').Path('tmp/review');root.mkdir(parents=True,exist_ok=True)
    (root/'proposal.pdf').write_bytes(pdf.data);document[0].get_pixmap(matrix=fitz.Matrix(1.5,1.5)).save(str(root/'proposal.png'))

def test_proposal_edit_conversion_is_atomic_and_once(workspace):
    client,post,backend=workspace
    post('/proposals/new',proposal_data())
    post('/proposals/new',proposal_data(id='1',version='1',status='ACCEPTED'))
    post('/proposals/new',proposal_data(id='1',version='1',title='Stale edit'))
    assert backend.database.proposals.find_one({})['title']=='Shop lighting supply'
    conversion=payload(20)|dict(proposal_id='1',proposal_version='2')
    post('/billing',conversion)
    assert backend.database.invoices.count_documents({})==0
    assert backend.database.proposals.find_one({})['status']=='ACCEPTED'
    conversion=payload()|dict(proposal_id='1',proposal_version='2')
    post('/billing',conversion)
    assert backend.database.proposals.find_one({})['status']=='CONVERTED'
    assert backend.database.proposals.find_one({})['invoice_id']==1
    assert backend.database.inventory.find_one({})['quantity']==8000
    post('/billing',payload()|dict(proposal_id='1',proposal_version='2'))
    assert backend.database.invoices.count_documents({})==1
    assert backend.database.inventory.find_one({})['quantity']==8000
    assert client.get('/billing?proposal=1').headers['Location']=='/invoices/1'
    post('/proposals/new',proposal_data(id='1',version='3',title='Locked revision'))
    assert backend.database.proposals.find_one({})['title']=='Shop lighting supply'

def test_proposal_validation_decline_expiry_and_tenant_isolation(workspace):
    client,post,backend=workspace
    post('/proposals/new',proposal_data(valid_until='2025-01-01'))
    assert backend.database.proposals.count_documents({})==0
    wrong=json.loads(payload()['items']);wrong[0]['product_id']=987654
    assert post('/proposals/new',proposal_data(items=json.dumps(wrong))).status_code==404
    post('/proposals/new',proposal_data(status='DECLINED'))
    post('/billing',payload()|dict(proposal_id='1',proposal_version='1'))
    assert backend.database.invoices.count_documents({})==0
    post('/proposals/new',proposal_data(id='1',version='1',status='SENT',date='2025-01-01',valid_until='2025-01-10'))
    post('/billing',payload()|dict(proposal_id='1',proposal_version='2'))
    assert backend.database.invoices.count_documents({})==0
    assert backend.scope(987654).find('proposals')==[]
    assert backend.scope(987654).one('proposals',{'id':1}) is None
    # Forged tenant parameter cannot change the authenticated company's proposal scope.
    assert b'Shop lighting supply' in client.get('/proposals?business_id=987654').data

def test_proposal_quotas_features_and_role_enforcement(workspace):
    client,post,backend=workspace; store=backend.scope(1); sub=store.one('subscriptions',{'current':True})
    plan=sub['plan'];plan['limits']['invoices']=0;plan['features']['pdf']=False;plan['features']['gst']=False
    store.run_transaction(lambda:store.update('subscriptions',{'id':sub['id']},{'plan':plan}))
    post('/proposals/new',proposal_data())
    assert backend.database.proposals.count_documents({})==0
    post('/proposals/new',proposal_data(type='NON-GST'))
    assert backend.database.proposals.count_documents({})==1 # Quotes do not consume invoice quota.
    assert client.get('/proposals/1/pdf').status_code==403
    post('/billing',payload()|dict(type='NON-GST',proposal_id='1',proposal_version='1'))
    assert backend.database.invoices.count_documents({})==0
    role=backend.database.roles.find_one({'business_id':1,'name':'INVENTORY_STAFF'})
    store.run_transaction(lambda:store.update('users',{'id':1},{'role_id':role['id']}))
    assert client.get('/proposals').status_code==403
    assert post('/proposals/new',proposal_data(type='NON-GST')).status_code==403
