import json
import secrets
import pytest
import pymupdf
from test_app import mongo_backend,workspace,payload,values
from test_proposals import proposal_data


def test_merged_navigation_preserves_finance_reports_and_data(workspace):
    from bson import json_util
    from test_finance import entry
    from test_trade import supplier,purchase
    client,post,backend=workspace
    post('/billing',payload()|dict(received='50'));post('/finance',entry())
    supplier(post);post('/purchases',purchase(paid='100',method='Cash'))
    names=('invoices','invoice_items','payments','finance_entries','inventory','stock_movements','purchases','trade_payments','bank_accounts')
    snapshot=lambda:{name:json_util.dumps(list(backend.database[name].find({}).sort('_id',1)),sort_keys=True) for name in names}
    before=snapshot()
    for path in ['/finance','/accounts']:
        response=client.get(path);assert response.status_code==200
        sidebar=response.data.split(b'<nav>')[1].split(b'</nav>')[0]
        assert b'href="/finance"' in sidebar and b'href="/accounts"' not in sidebar
        assert b'aria-label="Finance views"' in response.data and b'Cash &amp; bank accounts' in response.data
    response=client.get('/reports');assert b'value="Outstanding"' in response.data and b'value="Receivables"' in response.data
    assert b'value="Inventory"' in response.data and b'value="Stock valuation"' in response.data
    for kind in ['Purchases','Receivables','Payables','Sales credit notes','Purchase debit notes','HSN sales','GST summary','Stock valuation']:
        response=client.get('/reports',query_string=dict(report=kind,**{'from':'','to':''}),follow_redirects=True)
        assert response.status_code==200,kind
        assert b'Export Excel' in response.data and b'name="report"' in response.data
    for format in ['csv','xlsx','pdf']:
        response=client.get('/reports',query_string=dict(report='Purchases',export=format),follow_redirects=True)
        assert response.status_code==200 and (response.data.startswith(b'%PDF') if format=='pdf' else True)
    assert b'Stock valuation report' in client.get('/inventory').data
    assert snapshot()==before


def test_merged_sections_keep_permission_boundaries(workspace):
    client,post,backend=workspace
    role=backend.database.roles.find_one({'name':'BILLING_STAFF','business_id':1})
    backend.database.roles.update_one({'id':role['id']},{'$set':{'permissions':['report.view','finance.view']}})
    backend.database.users.update_one({'id':1},{'$set':{'role_id':role['id']}})
    assert client.get('/finance').status_code==200 and client.get('/accounts').status_code==200
    page=client.get('/reports').data
    assert b'value="Purchases"' not in page and b'value="Receivables"' not in page and b'value="Stock valuation"' not in page
    assert client.get('/reports?report=Purchases',follow_redirects=True).status_code==403
    assert client.get('/reports?report=Receivables',follow_redirects=True).status_code==403
    assert post('/accounts',dict(action='create',name='Unauthorized',date='2026-10-18',kind='Cash',opening='10',submission=secrets.token_hex(32))).status_code==403
    assert backend.database.bank_accounts.count_documents({})==0


def test_challan_dispatch_conversion_and_cancel(workspace):
    client,post,backend=workspace
    post('/proposals/new',proposal_data(document_kind='CHALLAN'))
    post('/documents/1/dispatch',dict(action='dispatch'));post('/documents/1/dispatch',dict(action='dispatch'))
    assert values(backend,'inventory','quantity')==[8000]
    post('/proposals',dict(id='1',version='2',status='DECLINED'))
    assert values(backend,'proposals','status')==['ACCEPTED']
    post('/billing',payload(3)|dict(proposal_id='1',proposal_version='2'))
    assert backend.database.invoices.count_documents({})==0
    data=payload()|dict(proposal_id='1',proposal_version='2');post('/billing',data);post('/billing',data)
    assert values(backend,'inventory','quantity')==[8000]
    assert backend.database.invoices.count_documents({})==1
    post('/invoices/1/cancel',{})
    assert values(backend,'inventory','quantity')==[10000]
    post('/proposals/new',proposal_data(document_kind='CHALLAN'))
    post('/documents/2/dispatch',dict(action='dispatch'));post('/documents/2/dispatch',dict(action='cancel'))
    assert values(backend,'inventory','quantity')==[10000]


@pytest.mark.parametrize('theme',['A5','A4_SIMPLE','A4_CLASSIC','A4_ADVANCED','THERMAL_58','THERMAL_80'])
def test_print_formats_preserve_snapshot(workspace,theme):
    client,post,backend=workspace
    post('/business-profile',dict(invoice_theme=theme,payment_details='BOTH',business_type='Retail',show_gst_columns='1',show_qr='1',empty_signature_box='1',city='Chennai'))
    post('/billing',payload()|dict(po_number='PO-100',vehicle_number='TN 01 A 1234'))
    response=client.get('/invoices/1/pdf');assert response.status_code==200 and response.data.startswith(b'%PDF')
    with pymupdf.open(stream=response.data,filetype='pdf') as document:
        assert 'Desk lamp' in ''.join(page.get_text() for page in document)
        if theme.startswith('THERMAL'): assert document[0].rect.width<230
        elif theme.startswith('A4'): assert document[0].rect.height>800
        else: assert document[0].rect.height<430
    assert backend.database.invoices.find_one({})['snapshot']['business']['extended']['invoice_theme']==theme
    assert client.get('/business-profile').status_code==200


def test_customer_fields_credit_limit_and_reports(workspace):
    client,post,backend=workspace
    post('/customers',dict(id='1',name='Anita Stores',credit_days='30',credit_limit='100',opening_balance='10',opening_direction='COLLECT',pan='ABCDE1234F',shipping_address='Shipping address'))
    post('/billing',payload())
    assert backend.database.invoices.count_documents({})==0
    post('/billing',payload()|dict(received='200'))
    assert backend.database.invoices.count_documents({})==1
    assert backend.database.invoices.find_one({})['snapshot']['due_date']=='2026-11-01'
    for kind in ['Purchases','Receivables','Payables','Sales credit notes','Purchase debit notes','HSN sales','GST summary','Stock valuation']:
        for format in ['', 'csv','xlsx','pdf']:
            response=client.get('/accounting-reports',query_string=dict(report=kind,export=format))
            assert response.status_code==200,(kind,format,response.data[:100])


def test_large_money_display_keeps_exact_paise(workspace):
    client,post,backend=workspace
    assert client.application.jinja_env.filters['inr'](9000000000000001)=='₹90,000,000,000,000.01'
    assert client.application.jinja_env.filters['qty'](99999999123)=='99999999.123'


def test_qr_uses_balance_and_thermal_paper_fits_content(workspace,monkeypatch):
    import sales_invoice_pdf
    from reportlab.platypus import Spacer
    client,post,backend=workspace
    backend.database.business_settings.update_one({'business_id':1},{'$set':{'data.upi':'test-merchant@upi','data.extended':dict(invoice_theme='THERMAL_58',show_qr=True)}})
    captured=[]
    def qr(business,amount): captured.append(amount);return Spacer(1,72)
    monkeypatch.setattr(sales_invoice_pdf,'upi_qr',qr)
    post('/billing',payload()|dict(received='50'))
    response=client.get('/invoices/1/pdf')
    assert response.status_code==200 and captured==[18600]
    with pymupdf.open(stream=response.data,filetype='pdf') as document:
        assert len(document)==1 and document[0].rect.height<600


def test_legacy_customer_and_proposal_exports_escape_formulas(workspace):
    client,post,backend=workspace
    post('/customers',dict(id='1',name='=1+1'))
    assert b"'=1+1" in client.get('/customers?export=csv').data
    post('/proposals/new',proposal_data(title='=1+1'))
    assert b"'=1+1" in client.get('/proposals?export=csv').data


def test_finance_and_accounts_reconcile_transfers_without_income_inflation(workspace):
    from test_finance import entry
    from flask import template_rendered
    from accounts import ledger_rows
    client,post,backend=workspace
    post('/finance',entry(kind='OPENING',date='2026-10-01',amount='1000'))
    post('/accounts',dict(action='create',name='Bank',kind='Bank',opening='500',date='2026-10-01',submission=secrets.token_hex(32)))
    post('/accounts',dict(action='transfer',from_account='legacy:Cash',to_account='1',amount='200',date='2026-10-02',submission=secrets.token_hex(32)))
    post('/billing',payload()|dict(received='100',ledger_account='1'))
    contexts=[]
    def rendered(sender,template,context,**extra): contexts.append(context)
    for account,expected,income in [('Cash',80000,0),('Bank',80000,10000)]:
        with template_rendered.connected_to(rendered,client.application):
            assert client.get('/finance?account='+account).status_code==200
        summary=contexts[-1]['summary']
        assert summary['closing']==expected and summary['income']==income and summary['expenses']==0
    assert sum(row['amount'] for row in ledger_rows(backend.scope(1)))==160000


def test_customer_payment_submission_is_idempotent(workspace):
    client,post,backend=workspace
    post('/billing',payload())
    data=dict(invoice='1',amount='50',date='2026-10-18',method='Cash',submission=secrets.token_hex(32))
    post('/payments',data);post('/payments',data)
    assert backend.database.payments.count_documents({})==1
    assert backend.database.payments.find_one({})['amount']==5000


def test_invoice_template_accepts_legacy_optional_totals(workspace):
    from flask import render_template,session,g
    from saas import access
    client,post,backend=workspace
    post('/billing',payload())
    inv=backend.database.invoices.find_one({})
    inv.update(items=list(backend.database.invoice_items.find({})),payments=[],received=0,balance=inv['total'])
    with client.session_transaction() as saved: credentials=dict(saved)
    with client.application.test_request_context('/invoices/1'):
        session.update(credentials);g.access=access(backend.scope(1),session['user'])
        html=render_template('invoice.html',title='Legacy invoice',inv=inv,filename='Customer.pdf')
        assert 'Desk lamp' in html and 'Grand total' in html


def test_unprepared_schema_preserves_existing_pages_and_hides_new_controls(workspace):
    client,post,backend=workspace
    marker=backend.database.counters.find_one({'_id':'account_transfers'})
    backend.database.counters.delete_one({'_id':'account_transfers'})
    try:
        billing=client.get('/billing');assert billing.status_code==200
        assert b'name="po_number"' not in billing.data and b'href="/purchases"' not in billing.data
        assert b'name="document_kind"' not in client.get('/proposals/new').data
        assert client.get('/customers').status_code==200
        assert client.get('/suppliers').status_code==503
    finally: backend.database.counters.insert_one(marker)


def test_legacy_finance_account_edit_follows_account_choice(workspace):
    from test_finance import entry
    from accounts import ledger_rows
    client,post,backend=workspace
    post('/finance',entry(amount='50'))
    post('/finance',entry(id='1',version='1',account='Bank',method='UPI',amount='50'))
    record=backend.database.finance_entries.find_one({})
    assert record['account']=='Bank' and record['ledger_account']=='legacy:Bank'
    assert [row['account'] for row in ledger_rows(backend.scope(1))]==['legacy:Bank']


def test_large_amount_exports_preserve_the_last_paisa(workspace):
    from test_trade import supplier,purchase
    client,post,backend=workspace;supplier(post)
    items=[dict(name='Bulk service',quantity='99999999.999',rate='900000',gst='0'),dict(name='Adjustment',quantity='1',rate='0.01',gst='0')]
    data=payload();data.update(type='GST',items=json.dumps(items))
    post('/billing',data)
    assert backend.database.invoices.find_one({})['total']==8999999999910001
    expected=b'89999999999100.01'
    assert expected in client.get('/customers/1/ledger?export=csv').data
    assert expected in client.get('/accounting-reports?report=HSN+sales&export=csv').data
    assert expected in client.get('/accounting-reports?report=GST+summary&export=csv').data
    response=client.get('/invoices/1/pdf');assert response.status_code==200
    with pymupdf.open(stream=response.data,filetype='pdf') as document:
        text=''.join(''.join(page.get_text().split()) for page in document)
        assert '89,999,999,999,100.01' in text
    post('/purchases',purchase(type='GST',items=json.dumps(items)))
    assert expected in client.get('/suppliers/1/ledger?export=csv').data
    assert expected in client.get('/accounting-reports?report=Purchases&export=csv').data
    response=client.get('/purchases/1?export=pdf');assert response.status_code==200
    with pymupdf.open(stream=response.data,filetype='pdf') as document:
        text=''.join(''.join(page.get_text().split()) for page in document)
        assert expected.decode() in text
