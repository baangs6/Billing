import json
import pytest
import pymupdf
from test_app import mongo_backend,workspace,payload,DEFAULTS
from test_thermal_layouts import sample_invoice
from sales_invoice_pdf import build_sales_invoice_pdf


def points(db,ident=1):
    return db.database.customers.find_one({'id':ident})['data'].get('referral_points',0)


def config(post,mode='FIXED',value='10'):
    return post('/settings',DEFAULTS|dict(name='Acme Electronics',gstin='33ABCDE1234F1Z5',state='Tamil Nadu',referral_mode=mode,referral_value=value))


def test_referral_earn_redeem_edit_cancel_and_replay(workspace):
    client,post,db=workspace
    assert config(post).status_code==302
    response=post('/billing/customer',dict(name='Rahul',phone='123',state='Tamil Nadu',referred_by='1'))
    assert response.status_code==201
    assert points(db)==0 and points(db,2)==0
    data=payload();data.update(customer='2',received='100')
    assert post('/billing',data).status_code==302
    assert points(db)==0
    assert post('/payments',dict(invoice='1',amount='136',date='2026-10-02',method='Cash')).status_code==302
    assert points(db)==1
    post('/billing',data)
    assert points(db)==1
    # A second paid invoice must not award a second referral point.
    data2=payload();data2.update(customer='2',received='236')
    assert post('/billing',data2).status_code==302
    assert points(db)==1
    sale=payload();sale.update(common_discount='5',referral_points='1',referral_amount='999')
    assert post('/billing',sale).status_code==302
    saved=db.database.invoices.find_one({'id':3})
    assert saved['referral_discount']==1000 and saved['discount']==1500 and saved['total']==21830
    assert points(db)==0
    assert b'Referral discount' in client.get('/invoices/3').data
    assert b'Referral points: 0' in client.get('/customers').data
    assert b'earn' in client.get('/customers?view=1').data
    response=client.get('/billing?edit=3')
    with client.session_transaction() as session: flashes=session.get('_flashes',[])
    assert b'referral-points' in response.data,flashes
    edit=payload(id='3',version='1');edit.update(common_discount='5',referral_points='1',referral_amount='10.0')
    assert post('/billing',edit).status_code==302
    assert points(db)==0
    assert post('/invoices/3/delete',{}).status_code==302
    assert points(db)==1
    post('/invoices/3/delete',{})
    post('/invoices/3/restore',{})
    assert points(db)==1
    assert db.database.invoices.find_one({'id':3})['status']=='CANCELLED'
    assert client.get('/customers?add=1').status_code==200
    assert b'Search referring customer' in client.get('/billing').data
    assert b'Referral rewards' in client.get('/settings').data


def test_referral_validation_manual_and_atomic_rollback(workspace):
    client,post,db=workspace
    assert post('/customers',dict(id='1',name='Anita',referred_by='1')).status_code==302
    assert not db.database.customers.find_one({'id':1})['data'].get('referred_by')
    assert post('/billing/customer',dict(name='Invalid',referred_by='99999')).status_code==400
    assert db.database.customers.count_documents({})==1
    assert config(post,'MANUAL').status_code==302
    db.database.customers.update_one({'id':1},{'$set':{'data.referral_points':2}})
    bad=payload();bad.update(common_discount='0',referral_points='3',referral_amount='20')
    post('/billing',bad)
    assert points(db)==2 and db.database.invoices.count_documents({})==0
    bad.update(referral_points='1',referral_amount='1000');post('/billing',bad)
    assert points(db)==2 and db.database.invoices.count_documents({})==0
    bad.update(referral_amount='12.34');assert post('/billing',bad).status_code==302
    assert points(db)==1
    inv=db.database.invoices.find_one({});assert inv['referral_discount']==1234
    edit=payload(id=str(inv['id']),version='1');edit.update(common_discount='0',referral_points='0',referral_amount='0')
    assert post('/billing',edit).status_code==302
    assert points(db)==2
    # A customer's referrer is locked once invoice history exists.
    new=post('/billing/customer',dict(name='Other',state='Tamil Nadu')).get_json()['customer']
    post('/customers',dict(id='1',name='Anita',referred_by=str(new['id'])))
    assert not db.database.customers.find_one({'id':1})['data'].get('referred_by')
    sale=payload();sale.update(common_discount='0',referral_points='1',referral_amount='10')
    assert post('/billing',sale).status_code==302
    assert points(db)==1
    from factory_reset import reset_sections
    store=db.scope(1)
    store.run_transaction(lambda:reset_sections(db,store.mongo_session,{'business_id':1},['invoices','inventory']))
    assert points(db)==2 and db.database.invoices.count_documents({})==0


@pytest.mark.parametrize('theme',['A4_LEDGER','A4_CLASSIC','A5','THERMAL_58','THERMAL_80'])
def test_referral_label_and_amount_in_customer_pdf(theme):
    inv=sample_invoice(theme);inv.update(discount=1000,referral_discount=1000,referral_points=1)
    with pymupdf.open(stream=build_sales_invoice_pdf(inv),filetype='pdf') as doc:
        text=''.join(page.get_text() for page in doc)
        assert 'Referral discount' in text and '10.00' in text
        assert '\nDiscount\n' not in text
