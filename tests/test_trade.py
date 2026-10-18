import json
import secrets
from test_app import mongo_backend,workspace,payload,values


def purchase(**extra):
    return dict(supplier='1',date='2026-10-18',supplier_number='SUP-001',type='GST',items=json.dumps([dict(product_id=1,name='Desk lamp',quantity=3,rate='60',gst='18',hsn='9405')]),submission=secrets.token_hex(32))|extra


def supplier(post):
    assert post('/suppliers',dict(name='Parts supplier',state='Tamil Nadu')).status_code==302


def test_purchase_order_receipt_return_payment(workspace):
    client,post,backend=workspace;supplier(post)
    data=purchase();post('/purchases?orders=1',data)
    assert values(backend,'inventory','quantity')==[10000]
    data=purchase(order_id='1',paid='100',method='UPI');post('/purchases',data);post('/purchases',data)
    assert values(backend,'inventory','quantity')==[13000]
    assert backend.database.purchases.count_documents({})==1
    assert sum(values(backend,'trade_payments','amount'))==10000
    post('/purchases',purchase(order_id='1',supplier_number='SUP-002'))
    assert backend.database.purchases.count_documents({})==1
    token=secrets.token_hex(32)
    data=dict(action='return',date='2026-10-18',quantity_0='1',reason='Damaged',submission=token)
    post('/purchases/1',data);post('/purchases/1',data)
    assert values(backend,'inventory','quantity')==[12000]
    assert values(backend,'trade_returns','total')==[7080]
    post('/purchases/1',data|dict(quantity_0='3',submission=secrets.token_hex(32)))
    assert values(backend,'inventory','quantity')==[12000]
    for url in ['/suppliers','/suppliers?edit=1','/suppliers/1/ledger','/suppliers/1/ledger?export=csv','/suppliers/1/ledger?export=pdf','/purchases','/purchases?orders=1','/purchases?receive=1','/purchases/1','/purchases/1?export=pdf','/purchases/1?orders=1','/notes/purchase/1/pdf']:
        response=client.get(url);assert response.status_code==200,(url,response.data[:200])
    assert b'41.60' in client.get('/suppliers/1/ledger').data


def test_purchase_cross_tenant_and_permissions(workspace):
    client,post,backend=workspace;supplier(post)
    post('/purchases',purchase())
    bid=backend.database.businesses.find_one({})['id']
    role=backend.database.roles.find_one({'name':'BILLING_STAFF','business_id':bid})
    backend.database.users.update_one({'id':1},{'$set':{'role_id':role['id']}})
    assert client.get('/suppliers').status_code==403
    assert post('/purchases',purchase()).status_code==403
    assert values(backend,'inventory','quantity')==[13000]


def test_purchase_refund_and_atomic_failure(workspace):
    client,post,backend=workspace;supplier(post)
    post('/purchases',purchase(paid='212.40',method='Cash'))
    post('/purchases/1',dict(action='return',date='2026-10-18',quantity_0='3',reason='Full return',submission=secrets.token_hex(32)))
    post('/purchases/1',dict(action='SUPPLIER_REFUND',date='2026-10-18',amount='212.40',method='Cash',submission=secrets.token_hex(32)))
    assert b'0.00' in client.get('/suppliers/1/ledger').data
    assert values(backend,'inventory','quantity')==[10000]
    data=purchase(supplier_number='NEW',paid='999',method='Cash');post('/purchases',data)
    assert backend.database.purchases.count_documents({})==1
    assert values(backend,'inventory','quantity')==[10000]


def test_party_import_validation_and_idempotency(workspace):
    import io
    client,post,backend=workspace
    token=secrets.token_hex(32)
    def upload(content):
        return post('/party-import',dict(target='suppliers',submission=token,file=(io.BytesIO(content),'parties.csv')))
    assert upload(b'name,gstin\nNew supplier,invalid').status_code==422
    assert backend.database.suppliers.count_documents({})==0
    assert upload(b'name,phone\nNew supplier,9876543210').status_code==302
    assert upload(b'name,phone\nNew supplier,9876543210').status_code==302
    assert backend.database.suppliers.count_documents({})==1
    assert client.get('/party-import?target=customers&template=1&export=csv').status_code==200


def test_inclusive_purchase_preserves_gross_paise(workspace):
    client,post,backend=workspace;supplier(post)
    data=purchase(pricing='INCLUSIVE',items=json.dumps([dict(name='Service',quantity=3,rate='100',gst='18')]))
    post('/purchases',data)
    doc=backend.database.purchases.find_one({})
    assert doc['total']==30000 and doc['items'][0]['rate']==10000 and doc['pricing']=='INCLUSIVE'
    assert doc['taxable']+doc['cgst']+doc['sgst']==30000
    post('/purchases/1',dict(action='return',date='2026-10-18',quantity_0='1',reason='Partial inclusive return',submission=secrets.token_hex(32)))
    assert values(backend,'trade_returns','total')==[10000]
    note=backend.database.trade_returns.find_one({})
    assert note['round_off']+sum(i['taxable']+i['tax'] for i in note['items'])==note['total']
    assert values(backend,'inventory','quantity')==[10000]


def test_sales_return_credit_refund_and_protection(workspace):
    client,post,backend=workspace
    post('/billing',payload()|dict(received='236'))
    token=secrets.token_hex(32);data=dict(invoice='1',date='2026-10-18',quantity_0='1',reason='Return',submission=token)
    post('/sales-returns',data);post('/sales-returns',data)
    assert values(backend,'inventory','quantity')==[9000]
    assert values(backend,'sales_returns','total')==[11800]
    refund=dict(invoice='1',action='refund',date='2026-10-18',amount='118',method='UPI',submission=secrets.token_hex(32))
    post('/sales-returns',refund);post('/sales-returns',refund)
    assert backend.database.trade_payments.count_documents({'kind':'CUSTOMER_REFUND'})==1
    post('/sales-returns',data|dict(quantity_0='2',submission=secrets.token_hex(32)))
    assert values(backend,'inventory','quantity')==[9000]
    post('/billing',payload(id='1',version='1'));post('/invoices/1/cancel',{})
    assert values(backend,'inventory','quantity')==[9000]
    assert values(backend,'invoices','status')==['FINAL']
    for url in ['/sales-returns','/sales-returns?invoice=1','/sales-returns?invoice=1&export=pdf','/customers/1/ledger','/customers/1/ledger?export=csv','/invoices/1','/finance','/notes/sales/1/pdf']:
        response=client.get(url);assert response.status_code==200,(url,response.data[:200])
    assert b'Customer refund' in client.get('/customers/1/ledger').data


def test_named_accounts_balanced_transfers_and_source_postings(workspace):
    from accounts import ledger_rows
    from collections import defaultdict
    from test_finance import entry
    client,post,backend=workspace;supplier(post)
    for name,kind,opening in [('Cash box','Cash','1000'),('Current account','Bank','0')]:
        post('/accounts',dict(action='create',name=name,kind=kind,opening=opening,date='2026-10-01',submission=secrets.token_hex(32)))
    data=dict(action='transfer',from_account='1',to_account='2',amount='500',date='2026-10-02',submission=secrets.token_hex(32))
    post('/accounts',data);post('/accounts',data)
    assert backend.database.account_transfers.count_documents({})==1
    post('/accounts',data|dict(amount='600',submission=secrets.token_hex(32)))
    assert backend.database.account_transfers.count_documents({})==1
    post('/finance',entry(amount='100',ledger_account='2'))
    post('/billing',payload()|dict(received='100',ledger_account='2'))
    post('/purchases',purchase(paid='100',method='Bank Transfer',ledger_account='2'))
    balances=defaultdict(int)
    for row in ledger_rows(backend.scope(1)): balances[row['account']]+=row['amount']
    assert balances['1']==50000 and balances['2']==40000
    assert sum(balances.values())==90000
    assert client.get('/accounts?account=2').status_code==200


def test_foreign_records_and_concurrent_receipts_are_isolated(workspace):
    from concurrent.futures import ThreadPoolExecutor
    client,post,backend=workspace;supplier(post)
    backend.database.suppliers.insert_one(dict(id=9000,business_id=999,name='Foreign supplier',data={},archived=False))
    post('/purchases',purchase(supplier='9000'))
    assert backend.database.purchases.count_documents({})==0
    assert client.get('/suppliers/9000/ledger').status_code==404
    assert b'Foreign supplier' not in client.get('/suppliers').data
    post('/purchases?orders=1',purchase())
    app=client.application;cookie=client.get_cookie('session').value
    with client.session_transaction() as session: csrf=session['csrf']
    data=purchase(order_id='1',items=json.dumps([dict(product_id=1,name='Desk lamp',quantity=2,rate='60',gst='18')]))
    def receive(index):
        other=app.test_client();other.set_cookie('session',cookie)
        return other.post('/purchases',data=data|dict(csrf=csrf,supplier_number='Concurrent-'+str(index),submission=secrets.token_hex(32))).status_code
    with ThreadPoolExecutor(max_workers=2) as pool: assert list(pool.map(receive,range(2)))==[302,302]
    assert backend.database.purchases.count_documents({})==1
    assert values(backend,'inventory','quantity')==[12000]


def test_opening_settlements_are_bounded_and_post_once(workspace):
    from accounts import ledger_rows
    client,post,backend=workspace
    post('/customers',dict(id='1',name='Anita Stores',opening_balance='100',opening_direction='COLLECT'))
    post('/suppliers',dict(name='Supplier',opening_balance='200',opening_direction='PAY'))
    for kind,amount in [('customers','100'),('suppliers','200')]:
        data=dict(amount=amount,method='Cash',date='20261018',submission=secrets.token_hex(32))
        post('/parties/'+kind+'/1/opening-payment',data);post('/parties/'+kind+'/1/opening-payment',data)
        assert sum(p.get('opening_effect',0) for p in backend.database.trade_payments.find({'customer_id' if kind=='customers' else 'supplier_id':1}))==-int(amount)*100
        post('/parties/'+kind+'/1/opening-payment',data|dict(submission=secrets.token_hex(32)))
    assert backend.database.trade_payments.count_documents({})==2
    assert {p['date'] for p in backend.database.trade_payments.find({})}=={'2026-10-18'}
    assert sum(r['amount'] for r in ledger_rows(backend.scope(1)))==-10000
    assert client.get('/finance').status_code==200
    assert client.get('/accounting-reports?report=Payables').status_code==200


def test_party_import_four_thousand_records(workspace):
    import io
    client,post,backend=workspace
    content=('name,phone\n'+''.join(f'Customer {index},9876543210\n' for index in range(4000))).encode()
    data=dict(target='customers',submission=secrets.token_hex(32),file=(io.BytesIO(content),'customers.csv'))
    assert post('/party-import',data).status_code==302
    assert backend.database.customers.count_documents({})==4001
    assert backend.database.party_imports.count_documents({})==1


def test_zero_value_return_still_protects_stock(workspace):
    client,post,backend=workspace
    data=payload();items=json.loads(data['items']);items[0]['rate']='0';items[0]['mrp']='0';data['items']=json.dumps(items)
    post('/billing',data)
    post('/sales-returns',dict(invoice='1',date='2026-10-18',quantity_0='2',reason='Free item returned',submission=secrets.token_hex(32)))
    assert values(backend,'sales_returns','total')==[0]
    assert values(backend,'inventory','quantity')==[10000]
    post('/invoices/1/cancel',{});post('/billing',data|dict(id='1',version='1'))
    assert values(backend,'invoices','status')==['FINAL']
    assert values(backend,'inventory','quantity')==[10000]


def test_selective_purchase_reset_preserves_customer_settlements_and_expenses(workspace):
    from test_finance import entry
    client,post,backend=workspace;supplier(post)
    post('/customers',dict(id='1',name='Anita Stores',opening_balance='100',opening_direction='COLLECT'))
    post('/parties/customers/1/opening-payment',dict(amount='100',date='2026-10-18',method='Cash',submission=secrets.token_hex(32)))
    post('/finance',entry(amount='50'))
    post('/purchases',purchase(paid='100',method='Cash'))
    fields=dict(action='reset_sections',confirmation='RESET SELECTED COMPANY DATA',password='correct horse battery staple',sections=['purchases','inventory'])
    post('/settings',fields)
    assert backend.database.purchases.count_documents({})==0
    assert backend.database.trade_payments.count_documents({'supplier_id':{'$exists':True}})==0
    assert backend.database.trade_payments.count_documents({'customer_id':{'$exists':True}})==1
    assert backend.database.finance_entries.count_documents({})==1
    post('/settings',fields|dict(sections=['customers']))
    assert backend.database.customers.count_documents({})==1
    post('/settings',fields|dict(sections=['customers','payments']))
    assert backend.database.customers.count_documents({})==0
    assert backend.database.trade_payments.count_documents({'customer_id':{'$exists':True}})==0


def test_service_purchase_reset_does_not_require_unrelated_sales(workspace):
    client,post,backend=workspace;supplier(post)
    post('/billing',payload()|dict(received='100'))
    post('/purchases',purchase(items=json.dumps([dict(name='Maintenance',quantity=1,rate='50',gst='18')]),paid='59',method='Cash'))
    assert backend.database.purchases.count_documents({})==1
    stock=values(backend,'inventory','quantity')
    post('/settings',dict(action='reset_sections',confirmation='RESET SELECTED COMPANY DATA',password='correct horse battery staple',sections=['purchases']))
    assert backend.database.purchases.count_documents({})==0
    assert backend.database.invoices.count_documents({})==1
    assert backend.database.payments.count_documents({})==1
    assert values(backend,'inventory','quantity')==stock


def test_partial_return_pdf_credits_reconcile(workspace):
    from io import BytesIO
    from pypdf import PdfReader
    client,post,backend=workspace
    data=payload();items=json.loads(data['items']);items[0].update(rate='0.02',gst='28');data['items']=json.dumps(items)
    post('/billing',data)
    post('/sales-returns',dict(invoice='1',date='2026-10-18',quantity_0='1',reason='Partial return',submission=secrets.token_hex(32)))
    note=backend.database.sales_returns.find_one({})
    assert note['total']==3 and note['round_off']==-1
    response=client.get('/notes/sales/1/pdf');assert response.status_code==200
    text='\n'.join(page.extract_text() for page in PdfReader(BytesIO(response.data)).pages)
    assert '0.04' in text and 'Round off INR -0.01' in text and 'Total credit INR 0.03' in text


def product_settings(post,**extra):
    return post('/products',dict(id='1',name='Desk lamp',sku='LAMP-01',category='Lighting',description='',hsn='9405',unit='PCS',gst='18',min_stock='5',selling_price='100',purchase_price='60',mrp='120',kind='STOCK',alternate_unit='BOX',alternate_factor='2',wholesale_price='80')|extra)


def test_alternate_invoice_returns_and_edit_use_saved_stock(workspace):
    client,post,backend=workspace;product_settings(post)
    data=payload();items=json.loads(data['items']);items[0].update(quantity=2,unit_choice='ALT',unit_rate_decimal='160',rate='160',price_tier='WHOLESALE');data['items']=json.dumps(items)
    post('/billing',data)
    assert values(backend,'inventory','quantity')==[6000]
    original=backend.database.invoice_items.find_one({})
    assert original['stock_quantity']==4000 and original['unit']=='BOX'
    assert original['price_tier']=='WHOLESALE'
    product_settings(post,alternate_factor='3')
    items[0].update(id=original['id']);data['items']=json.dumps(items)
    post('/billing',data|dict(id='1',version='1'))
    assert values(backend,'inventory','quantity')==[6000]
    post('/sales-returns',dict(invoice='1',date='2026-10-18',quantity_0='1',reason='One box',submission=secrets.token_hex(32)))
    assert values(backend,'inventory','quantity')==[8000]
    assert backend.database.products.find_one({})['data']['wholesale_price']==8000


def test_service_products_and_historical_classification_are_safe(workspace):
    client,post,backend=workspace
    product_settings(post,kind='SERVICE')
    assert backend.database.products.find_one({'id':1})['data'].get('kind','STOCK')=='STOCK'
    fields=dict(name='Consultation',sku='SERVICE',unit='HOUR',gst='18',selling_price='118',mrp='0',stock='0',kind='SERVICE',pricing_mode='INCLUSIVE')
    post('/products',fields)
    service=backend.database.products.find_one({'sku':'SERVICE'});assert service
    data=payload();data['items']=json.dumps([dict(product_id=service['id'],name='Consultation',quantity=2,rate='118',mrp='0',gst='18',pricing_mode='INCLUSIVE')])
    post('/billing',data)
    assert values(backend,'invoices','total')==[23600]
    assert backend.database.invoice_items.find_one({})['stock_quantity']==0
    assert backend.database.inventory.find_one({'product_id':service['id']})['quantity']==0
    post('/invoices/1/cancel',{})
    assert backend.database.inventory.find_one({'product_id':service['id']})['quantity']==0


def test_order_receipt_preserves_original_alternate_factor(workspace):
    client,post,backend=workspace;supplier(post);product_settings(post)
    item=dict(product_id=1,name='Desk lamp',quantity=3,rate='120',gst='18',unit_choice='ALT')
    post('/purchases?orders=1',purchase(items=json.dumps([item])))
    product_settings(post,alternate_factor='3')
    post('/purchases',purchase(order_id='1',items=json.dumps([item|dict(quantity=1,order_line=0)])))
    assert values(backend,'inventory','quantity')==[12000]
    receipt=backend.database.purchases.find_one({})
    assert receipt['items'][0]['unit_factor']=='2'
    post('/purchases/1',dict(action='return',quantity_0='1',date='2026-10-18',reason='Return box',submission=secrets.token_hex(32)))
    assert values(backend,'inventory','quantity')==[10000]


def test_product_photo_access_import_and_basic_edit_preserve_options(workspace):
    import io
    from PIL import Image
    client,post,backend=workspace
    image=io.BytesIO();Image.new('RGB',(30,30),'red').save(image,format='PNG');image.seek(0)
    product_settings(post,photo=(image,'photo.png'))
    response=client.get('/products/1/photo');assert response.status_code==200 and response.mimetype=='image/jpeg'
    picker=json.loads(client.get('/billing').data.split(b'id="billing-data">')[1].split(b'</script>')[0])
    assert 'photo' not in picker['products'][0]['data'] and picker['products'][0]['data']['has_photo']
    product_settings(post)
    product=backend.database.products.find_one({'id':1});assert product['data']['has_photo'] and product['data']['photo']
    backend.database.products.insert_one(dict({k:v for k,v in product.items() if k!='_id'},id=999,business_id=999,sku='FOREIGN'))
    assert client.get('/products/999/photo').status_code==404
    post('/products',dict(action='import',file=(io.BytesIO(b'name,selling_price,kind,unit,alternate_unit,alternate_factor,wholesale_price\nImported service,118,SERVICE,HOUR,DAY,8,100\n'),'catalog.csv')))
    imported=backend.database.products.find_one({'name':'Imported service'})
    assert imported['data']['kind']=='SERVICE' and imported['data']['wholesale_price']==10000
