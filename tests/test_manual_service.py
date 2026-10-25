import secrets
from test_app import mongo_backend,workspace


def test_manual_service_reminder_creation_completion_and_isolation(workspace):
    client,post,backend=workspace
    data=dict(action='add_manual',customer='1',service_due='2020-01-01',notes='Replace filter',submission=secrets.token_hex(32))
    assert post('/service-reminders',data).status_code==302
    post('/service-reminders',data)
    rows=backend.database.business_settings.find_one({'business_id':1})['data']['manual_service_reminders']
    assert len(rows)==1 and rows[0]['customer_name']=='Anita Stores'
    assert backend.database.invoices.count_documents({})==0
    assert b'Replace filter' in client.get('/service-reminders').data
    assert b'1 due' in client.get('/').data
    post('/service-reminders',dict(id=data['submission'],manual='1'))
    assert b'Replace filter' in client.get('/service-reminders?stage=completed').data
    assert b'Replace filter' not in client.get('/service-reminders').data
    assert b'1 due' not in client.get('/').data
    post('/service-reminders',data|dict(customer='999',submission=secrets.token_hex(32)))
    assert len(backend.database.business_settings.find_one({'business_id':1})['data']['manual_service_reminders'])==1


def test_manual_service_permission_and_invalid_date(workspace):
    client,post,backend=workspace
    data=dict(action='add_manual',customer='1',service_due='bad',submission=secrets.token_hex(32))
    post('/service-reminders',data)
    assert not backend.database.business_settings.find_one({})['data'].get('manual_service_reminders')
    role=backend.database.roles.find_one({'name':'BILLING_STAFF','business_id':1})
    backend.database.roles.update_one({'id':role['id']},{'$set':{'permissions':['invoice.view']}})
    backend.database.users.update_one({'id':1},{'$set':{'role_id':role['id']}})
    assert post('/service-reminders',data|dict(service_due='2020-01-01')).status_code==403


def test_reminder_customer_search_and_quick_add(workspace):
    client,post,backend=workspace
    page=client.get('/service-reminders?add=1').data
    assert b'id="customer-search"' in page and b'id="customer-popup"' in page
    assert b'customer-lookup-data' in page and b'Anita Stores' in page
    response=post('/billing/customer',dict(name='Service customer',phone='9876543211',state='Tamil Nadu'))
    assert response.status_code==201
    customer=response.json['customer']
    post('/service-reminders',dict(action='add_manual',customer=str(customer['id']),service_due='2020-01-01',submission=secrets.token_hex(32)))
    assert b'Service customer' in client.get('/service-reminders').data
