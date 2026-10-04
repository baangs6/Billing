import csv
import io
import json
import os
import secrets
from functools import wraps
from copy import deepcopy
from pymongo.errors import DuplicateKeyError, PyMongoError
from mongo_store import MongoBackend, load_configuration
import time
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for, Response
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from xml.sax.saxutils import escape
from invoice_pdf import build_invoice_pdf
from saas import access, quota, seed_roles, Platform, PERMISSIONS, FEATURES, local_month, stamp, subscription_state

ROOT = Path(__file__).parent
DEFAULTS = dict(name='Your business', address='', phone='', email='', gstin='', state='Tamil Nadu', pin='', bank='', upi='', terms='Thank you for your business. Goods once sold are subject to the agreed return policy.', signatory='', logo='', signature='', prefix='INV/{fy}/{seq}', gst_rates='0,5,12,18,28', negative_stock=False)

def today():
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).date().isoformat()

def money(value):
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d < 0 or d > Decimal('1000000000'):
            raise ValueError('Enter a valid non-negative amount.')
        return int((d * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except (InvalidOperation, TypeError):
        raise ValueError('Enter a valid amount.')

def quantity(value, allow_zero=False):
    try:
        d = Decimal(str(value))
        if not d.is_finite() or d < 0 or (d == 0 and not allow_zero) or d > 100000000 or d * 1000 != (d * 1000).to_integral_value():
            raise ValueError('Quantity must be positive with at most three decimal places.')
        return int(d * 1000)
    except InvalidOperation:
        raise ValueError('Invalid quantity.')

def rounded(value):
    return int(Decimal(value).quantize(Decimal('1'), rounding=ROUND_HALF_UP))

def calculate(items, kind, interstate):
    totals = dict(subtotal=0, discount=0, taxable=0, cgst=0, sgst=0, igst=0, total=0)
    for item in items:
        base = rounded(Decimal(item['rate']) * item['quantity'] / 1000)
        if item['discount'] > base:
            raise ValueError('Line discount cannot exceed its amount.')
        taxable = base - item['discount']
        rate = Decimal(item['gst']) if kind == 'GST' else Decimal(0)
        if interstate:
            igst, cgst, sgst = rounded(Decimal(taxable) * rate / 100), 0, 0
        else:
            cgst = rounded(Decimal(taxable) * rate / 200)
            sgst, igst = cgst, 0
        item.update(taxable=taxable, tax=cgst+sgst+igst, total=taxable+cgst+sgst+igst)
        for key, val in dict(subtotal=base, discount=item['discount'], taxable=taxable, cgst=cgst, sgst=sgst, igst=igst, total=item['total']).items():
            totals[key] += val
    return totals

def create_app(database=None, backend=None):
    app = Flask(__name__)
    instance = ROOT / 'instance'
    instance.mkdir(exist_ok=True)
    keyfile = instance / 'secret.key'
    if not keyfile.exists():
        keyfile.write_text(secrets.token_hex(32))
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY') or keyfile.read_text(),  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.environ.get('HTTPS')=='1', MAX_CONTENT_LENGTH=4*1024*1024, PERMANENT_SESSION_LIFETIME=timedelta(hours=8))

    if backend is None:
        uri,name=load_configuration()
        backend=MongoBackend(uri,database or name)
    app.extensions['mongo']=backend
    app.config['MONGODB_DATABASE']=backend.name

    def db():
        if 'db' not in g: g.db=backend.scope(session.get('business'))
        return g.db

    def settings():
        r = db().one('business_settings')
        return DEFAULTS | (r['data'] if r else {})

    def owned(table, ident):
        row = db().one(table,{'id':ident})
        if not row:
            abort(404)
        return dict(row)

    def audit(action, entity, ident, details=''):
        db().insert('audit_events',dict(user_id=session['user'],action=action,entity=entity,entity_id=ident,details=details))

    def invoice(ident):
        inv = owned('invoices',ident)
        inv['snapshot'] = dict(inv['snapshot'])
        inv['items'] = db().find('invoice_items',{'invoice_id':ident},sort=[('id',1)])
        inv['payments'] = db().find('payments',{'invoice_id':ident},sort=[('date',1),('id',1)])
        inv['received'] = sum(p['amount'] for p in inv['payments'])
        inv['balance'] = inv['total']-inv['received']
        return inv

    def all_invoices():
        rows = db().find('invoices',sort=[('date',-1),('id',-1)])
        receipts={}
        for payment in db().find('payments'): receipts[payment['invoice_id']]=receipts.get(payment['invoice_id'],0)+payment['amount']
        for row in rows:
            row['customer']=row['snapshot']['customer']['name']
            row['received']=receipts.get(row['id'],0)
        result=[]
        for row in rows:
            r=dict(row); r['balance']=r['total']-r['received']; r['payment_status']='PAID' if not r['balance'] else 'PARTIAL' if r['received'] else 'UNPAID'
            if request.args.get('q','').lower() not in (r['number']+' '+r['customer']).lower(): continue
            if request.args.get('from') and r['date']<request.args['from']: continue
            if request.args.get('to') and r['date']>request.args['to']: continue
            if request.args.get('type') and r['type']!=request.args['type']: continue
            if request.args.get('payment') and r['payment_status']!=request.args['payment']: continue
            if request.args.get('customer') and str(r['customer_id'])!=request.args['customer']: continue
            result.append(r)
        return result

    @app.before_request
    def security():
        if 'user' in session:
            user=backend.session_user(session['user'],session.get('business'))
            if not user or not user.get('active',False) or user.get('session_version',0)!=session.get('version',0): session.clear()
        session.setdefault('csrf',secrets.token_hex(32))
        if request.method=='POST' and not secrets.compare_digest(session['csrf'],request.form.get('csrf','')):
            if request.endpoint in ('register','login'):
                flash('This page has expired. Please enter your password and submit again.','error')
                return render_template('auth.html',register=request.endpoint=='register'),400
            abort(400, 'Invalid security token. Refresh the page and try again.')
        if request.method=='POST':
            for key,value in request.form.items():
                if key!='items' and len(value)>(2500 if key in ('terms','notes','description') else 300):
                    raise ValueError('A form field is too long. Shorten it and try again.')
        if request.endpoint not in ('home','dashboard','login','register','forgot_password','reset_password','static') and 'user' not in session:
            return redirect(url_for('login'))

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
        response.headers['Cache-Control']='no-store'
        return response

    @app.context_processor
    def context():
        nav=[('dashboard','Dashboard','◫'),('billing','Billing','＋'),('proposals','Proposals','▧'),('invoices','Invoices','▤'),('customers','Customers','♧'),('products','Products','◇'),('inventory','Inventory','▦'),('payments','Payments','↗'),('reports','Reports','▥'),('settings_page','Settings','⚙'),('company_users','Users','♙'),('company_roles','Roles','◇'),('subscription_page','Subscription','▤')]
        policy=g.get('access')
        if policy:
            nav=[entry for entry in nav if entry[0]=='subscription_page' or (policy['state']=='ACTIVE' and required_permission(entry[0]) in policy['permissions'] and (entry[0] not in ('inventory','reports','company_users','company_roles') or policy['features'].get({'inventory':'inventory','reports':'reports','company_users':'multiple_users','company_roles':'multiple_users'}[entry[0]],False)))]
        plans=Platform(backend).rows('plans',{'active':True}) if request.endpoint=='register' else []
        return dict(business=settings() if 'user' in session else DEFAULTS, today=today(), csrf=session.get('csrf'), nav=nav, available_plans=plans, policy=policy,permissions=PERMISSIONS)

    app.jinja_env.filters['inr'] = lambda x: f'₹{x/100:,.2f}'
    app.jinja_env.filters['qty'] = lambda x: f'{x/1000:g}'

    @app.errorhandler(ValueError)
    def invalid(error):
        db().rollback(); flash(str(error),'error')
        return redirect(request.referrer if request.referrer and request.referrer.startswith(request.host_url) else url_for('dashboard'))

    @app.errorhandler(DuplicateKeyError)
    def conflict(error):
        if request.endpoint=='register':
            flash('An account with this email already exists. Use the Sign in link below.','error')
            return render_template('auth.html',register=True),409
        db().rollback(); flash('This record conflicts with an existing record. Check duplicate SKU or invoice number.','error')
        return redirect(url_for('dashboard'))

    @app.errorhandler(InvalidOperation)
    @app.errorhandler(TypeError)
    def malformed(error):
        return invalid(ValueError('Invalid numeric or invoice data. Check the form and try again.'))

    @app.route('/register',methods=['GET','POST'])
    def register():
        if 'user' in session: return redirect(url_for('dashboard'))
        if request.method=='POST':
            name=request.form.get('name','').strip(); email=request.form.get('email','').strip().lower(); password=request.form.get('password','')
            errors=[]
            platform=Platform(backend)
            policy=platform.one('platform_settings',{'_id':'policy'})
            if not policy or not policy.get('registration_open'): abort(403,'New company registration is currently closed.')
            plan=platform.one('plans',{'id':int(request.form.get('plan_id') or 0),'active':True})
            if not name: errors.append('Enter your business name.')
            import re
            if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): errors.append('Enter a valid email address.')
            if len(password)<12: errors.append('Use a password with at least 12 characters.')
            for field in ('owner_name','phone','address','state','pin','business_type'):
                if not request.form.get(field,'').strip(): errors.append('Enter '+field.replace('_',' ')+'.')
            if request.form.get('pin') and not re.fullmatch(r'\d{6}',request.form['pin']): errors.append('PIN must contain six digits.')
            if request.form.get('phone') and not re.fullmatch(r'[+0-9 ()-]{7,20}',request.form['phone']): errors.append('Enter a valid phone number.')
            if not plan: errors.append('Select an available subscription plan.')
            if errors:
                for error in errors: flash(error,'error')
                return render_template('auth.html',register=True),422
            with db():
                data={k:request.form.get(k,'').strip() for k in ('address','phone','state','pin','gstin')}
                upload=request.files.get('logo')
                if upload and upload.filename:
                    from PIL import Image as PILImage
                    import base64
                    try:
                        image=PILImage.open(upload.stream); image.thumbnail((600,250)); output=io.BytesIO(); image.convert('RGBA').save(output,format='PNG'); data['logo']='data:image/png;base64,'+base64.b64encode(output.getvalue()).decode()
                    except Exception: raise ValueError('Upload a valid PNG or JPEG logo.')
                # Re-read policy/plan in the registration transaction.
                if not backend.database.platform_settings.find_one({'_id':'policy','registration_open':True},session=db().mongo_session) or not backend.database.plans.find_one({'id':plan['id'],'active':True},session=db().mongo_session): raise ValueError('Registration or the selected plan is no longer available.')
                bid,uid=db().register_business(name,email,generate_password_hash(password),DEFAULTS|data|{'name':name,'email':email})
                store=backend.scope(bid); store.mongo_session=db().mongo_session; store.write_allowed=True
                roles=seed_roles(store)
                store.update('businesses',{},dict(status='PENDING',owner_name=request.form['owner_name'].strip(),contact_email=email,phone=data['phone'],address=data['address'],state=data['state'],pin=data['pin'],gstin=data['gstin'],business_type=request.form['business_type'].strip(),requested_plan_id=plan['id']))
                store.update('users',{'id':uid},dict(name=request.form['owner_name'].strip(),active=True,role_id=roles['COMPANY_ADMIN']['id'],session_version=0))
            session.clear(); session.update(user=uid,business=bid,version=0,csrf=secrets.token_hex(32)); session.permanent=True
            return redirect(url_for('subscription_page'))
        return render_template('auth.html',register=True)

    @app.route('/login',methods=['GET','POST'])
    def login():
        if 'user' in session: return redirect(url_for('dashboard'))
        if request.method=='POST':
            email=request.form.get('email','').lower().strip(); key=(request.remote_addr or '')+':'+email
            attempt=backend.login_attempt(key)
            if attempt and attempt['count']>=10 and time.time()-attempt['started']<900: raise ValueError('Too many attempts. Try again in 15 minutes.')
            row=backend.login_user(email)
            if row and row.get('active',False) and check_password_hash(row['password_hash'],request.form.get('password','')):
                backend.reset_login_attempt(key)
                store=backend.scope(row['business_id'])
                store.run_transaction(lambda:store.update('users',{'id':row['id']},{'last_login_at':stamp()}))
                session.clear(); session.update(user=row['id'],business=row['business_id'],version=row.get('session_version',0),csrf=secrets.token_hex(32)); session.permanent=True
                return redirect(url_for('dashboard'))
            backend.failed_login(key)
            flash('Email or password is incorrect.','error')
        return render_template('auth.html',register=False)

    @app.post('/logout')
    def logout():
        session.clear(); return redirect(url_for('login'))

    @app.get('/')
    def dashboard():
        if 'user' not in session: return public_home()
        if not {'invoice.view','payment.view','product.view'}.issubset(g.access['permissions']):
            return render_template('limited_dashboard.html',title='Company workspace')
        invoices=all_invoices(); active=[i for i in invoices if i['status']=='FINAL']; products=product_rows()
        pay=payment_rows()
        metrics=dict(today=sum(i['total'] for i in active if i['date']==today()),month=sum(i['total'] for i in active if i['date'][:7]==today()[:7]),outstanding=sum(i['balance'] for i in active),received=sum(p['amount'] for p in pay),invoices=len(active),products=len(products),low=sum(0<p['quantity']<=int(p['data']['min_stock']) for p in products),out=sum(p['quantity']<=0 for p in products))
        chart=[]
        for n in range(6,-1,-1):
            day=(date.fromisoformat(today())-timedelta(days=n)).isoformat()
            chart.append(dict(day=day[5:],sales=sum(i['total'] for i in active if i['date']==day),collections=sum(p['amount'] for p in pay if p['date']==day)))
        return render_template('dashboard.html',title='Business overview',metrics=metrics,invoices=invoices[:5],payments=pay[:5],chart=chart,maximum=max([c['sales'] for c in chart]+[c['collections'] for c in chart]+[1]))

    def public_home():
        platform=Platform(backend)
        policy=platform.one('platform_settings',{'_id':'policy'}) or {}
        return render_template('home.html',plans=platform.rows('plans',{'active':True,'legacy':{'$ne':True}}),registration_open=policy.get('registration_open',False),support_email=policy.get('support_email',''))

    @app.get('/home')
    def home():
        return public_home()

    def product_rows():
        rows=db().find('products',sort=[('name',1)])
        levels={i['product_id']:i['quantity'] for i in db().find('inventory')}
        for r in rows: r['quantity']=levels.get(r['id'],0)
        return rows

    def payment_rows():
        invoices={i['id']:i for i in db().find('invoices')}
        rows=db().find('payments',sort=[('date',-1),('id',-1)])
        for payment in rows:
            inv=invoices.get(payment['invoice_id'])
            if not inv: raise ValueError('Payment invoice link is invalid.')
            payment.update(number=inv['number'],customer=inv['snapshot']['customer']['name'])
        return rows

    def movement_rows(limit=0):
        names={p['id']:p['name'] for p in db().find('products')}
        rows=db().find('stock_movements',sort=[('id',-1)],limit=limit)
        for row in rows: row['name']=names.get(row['product_id'],'Archived product')
        return rows

    @app.post('/billing/customer')
    def billing_customer():
        name=request.form.get('name','').strip()
        if not name: return {'error':'Customer name is required.'},400
        data={k:request.form.get(k,'').strip() for k in ('phone','email','address','gstin','state','pin','notes')}
        ident=db().insert('customers',dict(name=name,data=data,archived=0))
        audit('save','customer',ident)
        return {'customer':dict(id=ident,name=name,data=data)},201

    @app.route('/customers',methods=['GET','POST'])
    def customers():
        if request.method=='POST':
            ident=request.form.get('id'); action=request.form.get('action','save')
            if ident: owned('customers',ident)
            with db():
                if action=='delete':
                    db().update('customers',{'id':ident},{'archived':1}); audit('archive','customer',ident)
                else:
                    name=request.form.get('name','').strip()
                    if not name: raise ValueError('Customer name is required.')
                    data={k:request.form.get(k,'').strip() for k in ('phone','email','address','gstin','state','pin','notes')}
                    if ident: db().update('customers',{'id':ident},{'name':name,'data':data})
                    else: ident=db().insert('customers',dict(name=name,data=data,archived=0))
                    audit('save','customer',ident)
            flash('Customer updated.'); return redirect(url_for('customers'))
        rows=db().find('customers',{'archived':0},sort=[('name',1)])
        balances={}
        for inv in all_invoices():
            if inv['status']=='FINAL': balances[inv['customer_id']]=balances.get(inv['customer_id'],0)+inv['balance']
        for r in rows: r['balance']=balances.get(r['id'],0)
        edit=owned('customers',request.args['edit']) if request.args.get('edit') else None
        if edit: edit['data']=dict(edit['data'])
        history=[i for i in all_invoices() if str(i['customer_id'])==request.args.get('view')] if request.args.get('view') else []
        profile=owned('customers',request.args['view']) if request.args.get('view') else None
        if profile: profile['data']=dict(profile['data'])
        return render_template('customers.html',title='Customers',rows=rows,edit=edit,history=history,profile=profile)

    @app.route('/products',methods=['GET','POST'])
    def products():
        if request.method=='POST':
            ident=request.form.get('id')
            if ident: owned('products',ident)
            with db():
                if request.form.get('action')=='delete':
                    db().update('products',{'id':ident},{'active':0}); audit('archive','product',ident)
                else:
                    name=request.form.get('name','').strip(); sku=request.form.get('sku','').strip()
                    if not name or not sku: raise ValueError('Product name and SKU are required.')
                    rates=[Decimal(r) for r in settings()['gst_rates'].split(',')]
                    gst=Decimal(request.form.get('gst','0'))
                    if gst not in rates: raise ValueError('Choose a configured GST rate.')
                    minimum=quantity(request.form.get('min_stock') or '0',allow_zero=True)
                    data={k:request.form.get(k,'').strip() for k in ('category','description','hsn','unit')}; data.update(gst=str(gst),min_stock=minimum)
                    category=db().one('categories',{'name':data['category']})
                    cid=category['id'] if category else db().insert('categories',{'name':data['category']})
                    active=int(request.form.get('active','1'))
                    if active not in (0,1): raise ValueError('Invalid product status.')
                    values=dict(name=name,sku=sku,data=data,selling_price=money(request.form['selling_price']),purchase_price=money(request.form['purchase_price']),mrp=money(request.form['mrp']),active=active,category_id=cid)
                    if ident: db().update('products',{'id':ident},values)
                    else:
                        ident=db().insert('products',values)
                        qty=quantity(request.form.get('stock') or '0',allow_zero=True)
                        db().insert('inventory',dict(product_id=ident,quantity=qty))
                        db().insert('stock_movements',dict(product_id=ident,invoice_id=None,quantity=qty,reason='Opening stock'))
                    audit('save','product',ident)
            flash('Product updated.'); return redirect(url_for('products'))
        rows=product_rows(); edit=next((p for p in rows if str(p['id'])==request.args.get('edit')),None)
        return render_template('products.html',title='Products',rows=rows,edit=edit)

    def move(pid, delta, reason, iid=None):
        if not g.access['features'].get('inventory'):
            raise ValueError('Inventory is disabled by your subscription. Use nonstock invoice lines or change the plan before billing tracked products.')
        if iid is not None and g.access['company'].get('inventory_reconciliation_required'):
            raise ValueError('The company administrator must reconcile stock after enabling inventory.')
        p=owned('products',pid)
        level=db().one('inventory',{'product_id':pid})
        if not level: raise ValueError('Inventory record missing.')
        current=level['quantity']
        if current+delta<0 and not settings()['negative_stock']: raise ValueError(f"Insufficient stock for {p['name']}.")
        db().update('inventory',{'product_id':pid},inc={'quantity':delta})
        db().insert('stock_movements',dict(product_id=pid,invoice_id=iid,quantity=delta,reason=reason))

    @app.route('/inventory',methods=['GET','POST'])
    def inventory():
        if request.method=='POST':
            pid=int(request.form['product']); qty=quantity(request.form['quantity'],allow_zero=request.form.get('direction')=='set'); reason=request.form.get('reason','').strip()
            if not reason: raise ValueError('A stock adjustment reason is required.')
            if request.form.get('direction') not in ('in','out','set'): raise ValueError('Invalid stock movement type.')
            with db():
                if request.form['direction']=='out': qty=-qty
                elif request.form['direction']=='set': qty-=db().one('inventory',{'product_id':owned('products',pid)['id']})['quantity']
                move(pid,qty,reason); audit('stock adjustment','product',pid,str(qty))
            flash('Stock updated.'); return redirect(url_for('inventory'))
        movements=movement_rows(limit=200)
        return render_template('inventory.html',title='Inventory',rows=product_rows(),movements=movements)

    @app.get('/proposals')
    def proposals():
        rows=db().find('proposals',sort=[('id',-1)])
        query=request.args.get('q','').strip().lower(); status=request.args.get('status','')
        rows=[row for row in rows if query in (row['number']+' '+row['title']+' '+row['snapshot']['customer']['name']).lower() and (not status or row['status']==status)]
        return render_template('proposals.html',title='Proposals',rows=rows)

    @app.route('/proposals/new',methods=['GET','POST'])
    def proposal_form():
        old=owned('proposals',request.form['id']) if request.method=='POST' and request.form.get('id') else owned('proposals',request.args['edit']) if request.args.get('edit') else None
        if old and old.get('invoice_id'): raise ValueError('Converted proposals are locked. Create a new proposal for revisions.')
        if request.method=='POST':
            if old and str(old['version'])!=request.form.get('version'): raise ValueError('Proposal changed in another window. Reload before editing.')
            token=request.form.get('submission','')
            if not old:
                if len(token)!=64: raise ValueError('Reload the proposal form before saving.')
                existing=db().one('proposals',{'submission':token})
                if existing: return redirect(url_for('view_proposal',ident=existing['id']))
            title=request.form.get('title','').strip(); day=request.form.get('date',''); until=request.form.get('valid_until','')
            if not title or len(title)>150: raise ValueError('Enter a proposal title of up to 150 characters.')
            if date.fromisoformat(until)<date.fromisoformat(day): raise ValueError('Validity date must be on or after the proposal date.')
            customer=owned('customers',request.form.get('customer'))
            if customer['archived']: raise ValueError('Choose an active customer.')
            business=settings(); kind=request.form.get('type','NON-GST'); status=request.form.get('status','DRAFT')
            if kind not in ('GST','NON-GST') or status not in ('DRAFT','SENT','ACCEPTED','DECLINED'): raise ValueError('Invalid proposal type or status.')
            if kind=='GST' and (not business['gstin'] or not business['state'] or not customer['data']['state']): raise ValueError('GST proposals require business GSTIN and business/customer states.')
            raw=json.loads(request.form.get('items','[]'))
            if not isinstance(raw,list) or not 1<=len(raw)<=200 or any(not isinstance(row,dict) for row in raw): raise ValueError('Add between 1 and 200 valid proposal items.')
            items=[]; rates=[Decimal(rate) for rate in business['gst_rates'].split(',')]
            for row in raw:
                product=owned('products',row['product_id']) if row.get('product_id') else None
                if product and not product['active']: raise ValueError('Choose an active product.')
                name=str(row.get('name','')).strip(); hsn=str(row.get('hsn','')); unit=product['data']['unit'] if product else str(row.get('unit','PCS'))
                gst=Decimal(str(row.get('gst','0')))
                if not name or len(name)>150 or len(hsn)>30 or len(unit)>30 or gst not in rates: raise ValueError('Check item names, HSN, units and configured GST rates.')
                items.append(dict(product_id=product['id'] if product else None,name=name,hsn=hsn,unit=unit,quantity=quantity(row.get('quantity')),rate=money(row.get('rate')),mrp=money(row.get('mrp',row.get('rate'))),discount=money(row.get('discount','0')),gst=str(gst)))
            totals=calculate(items,kind,business['state'].strip().lower()!=customer['data']['state'].strip().lower())
            if totals['total']>9_000_000_000_000_000: raise ValueError('Proposal total exceeds the supported financial limit.')
            snapshot=dict(business=business,customer=customer,terms=request.form.get('terms',''),installation='',service='')
            values=dict(title=title,date=day,valid_until=until,description=request.form.get('description','').strip(),customer_id=customer['id'],type=kind,status=status,snapshot=snapshot,items=items,**totals)
            if old:
                ident=old['id']; db().update('proposals',{'id':ident},values,inc={'version':1})
            else:
                number=f"PROP/{date.fromisoformat(day).year}/{db().count('proposals')+1:04d}"
                ident=db().insert('proposals',dict(values,number=number,version=1,submission=token))
            audit('edit' if old else 'create','proposal',ident,json.dumps(dict(previous=old,current=values)))
            flash('Proposal saved. Stock and payments are unchanged.'); return redirect(url_for('view_proposal',ident=ident))
        return render_template('proposal_form.html',title='Edit proposal' if old else 'Create proposal',edit=old,duplicate=False,products=product_rows(),customers=db().find('customers',{'archived':0},sort=[('name',1)]),submission=secrets.token_hex(32),valid_until=(date.fromisoformat(today())+timedelta(days=30)).isoformat())

    @app.get('/proposals/<int:ident>')
    def view_proposal(ident):
        return render_template('proposal.html',title='Proposal details',proposal=owned('proposals',ident))

    @app.get('/proposals/<int:ident>/pdf')
    def proposal_pdf(ident):
        document=owned('proposals',ident)
        return Response(build_invoice_pdf(document,proposal=True),mimetype='application/pdf',headers={'Content-Disposition':f"attachment; filename=proposal-{ident}.pdf"})

    @app.route('/billing',methods=['GET','POST'])
    def billing():
        if request.method=='POST':
            with db():
                ident=request.form.get('id'); old=invoice(ident) if ident else None
                source=owned('proposals',request.form['proposal_id']) if request.form.get('proposal_id') else None
                if source:
                    if old: raise ValueError('A proposal can only create a new invoice.')
                    if source.get('invoice_id'): return redirect(url_for('view_invoice',ident=source['invoice_id']))
                    if source['status']=='DECLINED' or source['valid_until']<today(): raise ValueError('This proposal is declined or expired. Revise it before conversion.')
                    if str(source['version'])!=request.form.get('proposal_version'): raise ValueError('Proposal changed. Reopen the conversion form before saving.')
                submission=request.form.get('submission','')
                if not old:
                    if len(submission)!=64: raise ValueError('Invalid submission token. Reload the billing page.')
                    existing=db().one('invoice_submissions',{'token':submission})
                    if existing: return redirect(url_for('view_invoice',ident=existing['invoice_id']))
                if old and old['status']!='FINAL': raise ValueError('Cancelled invoices cannot be edited.')
                if old and str(old['version'])!=request.form.get('version'): raise ValueError('Invoice changed in another window. Reload before editing.')
                customer=owned('customers',request.form['customer'])
                if customer['archived']: raise ValueError('Choose an active customer.')
                customer['data']=dict(customer['data']); business=settings()
                kind=request.form.get('type','GST')
                if kind not in ('GST','NON-GST'): raise ValueError('Invalid invoice type.')
                day=request.form.get('date'); date.fromisoformat(day)
                if kind=='GST' and (not business['gstin'] or not business['state'] or not customer['data']['state']): raise ValueError('GST invoices require business GSTIN and business/customer states.')
                items=[]
                raw_items=json.loads(request.form.get('items','[]'))
                if not isinstance(raw_items,list) or any(not isinstance(r,dict) for r in raw_items): raise ValueError('Invalid invoice items.')
                for raw in raw_items:
                    p=owned('products',raw['product_id']) if raw.get('product_id') else None
                    pd=p['data'] if p else {}
                    if p and not p['active']: raise ValueError('Inactive products cannot be billed.')
                    name=raw.get('name','').strip()
                    if not name or len(name)>150 or len(str(raw.get('hsn','')))>30: raise ValueError('Every item needs a name (up to 150 characters) and a valid HSN/SAC field.')
                    gst=Decimal(str(raw.get('gst','0')))
                    if gst not in [Decimal(r) for r in business['gst_rates'].split(',')]: raise ValueError('Invalid GST rate.')
                    items.append(dict(product_id=p['id'] if p else None,name=name,quantity=quantity(raw['quantity']),rate=money(raw['rate']),mrp=money(raw.get('mrp',raw['rate'])),gst=str(gst),hsn=str(raw.get('hsn','')),discount=money(raw.get('discount','0')),unit=pd.get('unit',raw.get('unit','PCS'))))
                if not items or len(items)>200: raise ValueError('Add between 1 and 200 items.')
                totals=calculate(items,kind,business['state'].strip().lower()!=customer['data']['state'].strip().lower())
                if totals['total']>9_000_000_000_000_000: raise ValueError('Invoice total exceeds the supported financial limit.')
                received=money(request.form.get('received','0')) if not old else old['received']
                if received>totals['total']: raise ValueError('Received amount cannot exceed invoice total. Resolve existing payments before reducing the invoice.')
                snapshot=dict(business=business,customer=customer,terms=request.form.get('terms',''),notes=request.form.get('notes','').strip(),installation=request.form.get('installation',''),service=request.form.get('service',''))
                for k in ('installation','service'):
                    if snapshot[k]: date.fromisoformat(snapshot[k])
                values=dict(customer_id=customer['id'],date=day,type=kind,snapshot=snapshot,**totals)
                if old:
                    for item in old['items']:
                        if item['product_id']: move(item['product_id'],item['quantity'],'Invoice edit reversal',old['id'])
                    db().update('invoices',{'id':old['id']},values,inc={'version':1})
                    db().delete('invoice_items',{'invoice_id':old['id']}); iid=old['id']
                else:
                    d=date.fromisoformat(day); year=d.year if d.month>=4 else d.year-1; fy=f'{year%100:02d}-{(year+1)%100:02d}'
                    seq=db().count('invoices')+1
                    number=business['prefix'].format(fy=fy,seq=f'{seq:03d}')
                    iid=db().insert('invoices',dict(values,number=number,status='FINAL',version=1))
                    db().update('invoices',{'id':iid},{'first_finalized_month':local_month()})
                    db().insert('invoice_submissions',dict(token=submission,invoice_id=iid))
                for item in items:
                    db().insert('invoice_items',dict(item,invoice_id=iid))
                    if item['product_id']: move(item['product_id'],-item['quantity'],'Invoice sale',iid)
                if received and not old:
                    method=request.form.get('method','Cash')
                    if method not in ('Cash','UPI','Bank Transfer','Card','Cheque','Other'): raise ValueError('Invalid payment method.')
                    pid=db().insert('payments',dict(invoice_id=iid,amount=received,date=day,method=method,reference='',notes='Initial payment'))
                    audit('record','payment',pid)
                audit('edit' if old else 'finalize','invoice',iid,json.dumps(dict(previous=old,current=dict(totals=totals,items=items,snapshot=snapshot))))
                if source:
                    db().update('proposals',{'id':source['id']},dict(status='CONVERTED',invoice_id=iid),inc={'version':1})
                    audit('convert','proposal',source['id'],str(iid))
            flash('Invoice saved and stock updated.'); return redirect(url_for('view_invoice',ident=iid))
        edit=invoice(request.args['edit']) if request.args.get('edit') else invoice(request.args['duplicate']) if request.args.get('duplicate') else None
        duplicate=bool(request.args.get('duplicate'))
        source=owned('proposals',request.args['proposal']) if request.args.get('proposal') else None
        if source:
            if source.get('invoice_id'): return redirect(url_for('view_invoice',ident=source['invoice_id']))
            if source['status']=='DECLINED' or source['valid_until']<today(): raise ValueError('This proposal is declined or expired. Revise it before conversion.')
            edit=source; duplicate=True
        customers=db().find('customers',{'archived':0},sort=[('name',1)])
        return render_template('billing.html',title='Create invoice' if not edit or duplicate else 'Edit invoice',products=product_rows(),customers=customers,edit=edit,duplicate=duplicate,submission=secrets.token_hex(32),proposal_source=source)

    @app.get('/invoices')
    def invoices():
        customers=db().find('customers',sort=[('name',1)])
        return render_template('invoices.html',title='Invoices',rows=all_invoices(),customers=customers)

    @app.get('/invoices/<int:ident>')
    def view_invoice(ident):
        return render_template('invoice.html',title='Invoice details',inv=invoice(ident))

    @app.post('/invoices/<int:ident>/cancel')
    def cancel(ident):
        with db():
            inv=invoice(ident)
            if inv['received']: raise ValueError('Invoices with payments cannot be cancelled. Record a documented refund through your accountant before cancellation; payment history is preserved.')
            if inv['status']=='FINAL':
                for item in inv['items']:
                    if item['product_id']: move(item['product_id'],item['quantity'],'Invoice cancellation',ident)
                db().update('invoices',{'id':ident},{'status':'CANCELLED'},inc={'version':1}); audit('cancel','invoice',ident,request.form.get('reason','Cancelled by owner'))
        flash('Invoice cancelled; stock restored.'); return redirect(url_for('view_invoice',ident=ident))

    @app.route('/payments',methods=['GET','POST'])
    def payments():
        if request.method=='POST':
            with db():
                inv=invoice(request.form['invoice']); amount=money(request.form['amount']); day=request.form['date']; date.fromisoformat(day)
                method=request.form['method']
                if method not in ('Cash','UPI','Bank Transfer','Card','Cheque','Other'): raise ValueError('Invalid payment method.')
                if inv['status']!='FINAL' or not 0<amount<=inv['balance']: raise ValueError('Payment must be positive and within the balance of an active invoice.')
                pid=db().insert('payments',dict(invoice_id=inv['id'],amount=amount,date=day,method=method,reference=request.form.get('reference',''),notes=request.form.get('notes','')))
                audit('record','payment',pid)
            flash('Payment recorded.'); return redirect(url_for('view_invoice',ident=inv['id']))
        rows=payment_rows()
        return render_template('payments.html',title='Payments',rows=rows,invoices=[i for i in all_invoices() if i['status']=='FINAL' and i['balance']>0])

    @app.route('/settings',methods=['GET','POST'])
    def settings_page():
        if request.method=='POST':
            if request.form.get('action')=='reconcile_inventory':
                if not g.access['features'].get('inventory'): raise ValueError('Inventory is disabled.')
                if request.form.get('confirmed')!='1': raise ValueError('Confirm that all product balances have been checked.')
                db().update('businesses',{},dict(inventory_reconciliation_required=False))
                audit('reconcile','inventory',session['business'],'Company administrator confirmed product balances after plan change.')
                flash('Inventory reconciliation confirmed. Tracked-product billing is available.'); return redirect(url_for('settings_page'))
            data=settings()
            for k in DEFAULTS:
                if k not in ('logo','signature','negative_stock'): data[k]=request.form.get(k,'').strip()
            if not data['name'] or not data['state']: raise ValueError('Business name and state are required.')
            if '{seq}' not in data['prefix']: raise ValueError('Numbering format must contain {seq}. Optional: {fy}.')
            try: data['prefix'].format(seq='001',fy='26-27')
            except (KeyError,ValueError): raise ValueError('Use only {seq} and {fy} in the numbering format.')
            try:
                rates=[Decimal(r) for r in data['gst_rates'].split(',')]
                if not rates or any(not r.is_finite() or r<0 or r>100 for r in rates): raise ValueError()
            except (InvalidOperation,ValueError): raise ValueError('GST rates must be comma-separated numbers from 0 to 100.')
            data['negative_stock']=bool(request.form.get('negative_stock'))
            from PIL import Image as PILImage
            import base64
            for k in ('logo','signature'):
                upload=request.files.get(k)
                if upload and upload.filename:
                    try:
                        image=PILImage.open(upload.stream); image.thumbnail((600,250)); output=io.BytesIO(); image.convert('RGBA').save(output,format='PNG'); data[k]='data:image/png;base64,'+base64.b64encode(output.getvalue()).decode()
                    except Exception: raise ValueError('Upload a valid PNG or JPEG image.')
                if request.form.get('remove_'+k): data[k]=''
            with db():
                db().update('business_settings',{}, {'data':data}); db().update('businesses',{}, {'name':data['name']}); audit('update','settings',session['business'])
            flash('Business settings saved.'); return redirect(url_for('settings_page'))
        events=db().find('audit_events',sort=[('id',-1)],limit=50)
        return render_template('settings.html',title='Business settings',events=events)

    def pdf_document(title, rows, business=None):
        output=io.BytesIO(); styles=getSampleStyleSheet(); story=[]
        def p(text,style='Normal'): return Paragraph(escape(str(text)).replace('\n','<br/>'),styles[style])
        story.append(p(title,'Title')); story.append(Spacer(1,18))
        for row in rows:
            if isinstance(row,list):
                table=Table([[p(v) for v in cells] for cells in row],colWidths=[(A4[0]-80)/len(row[0])]*len(row[0]),repeatRows=1,hAlign='LEFT')
                table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf0ed')),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#d3ddd7')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),8)])); story.append(table)
            elif isinstance(row,tuple) and row[0]=='image':
                import base64
                from PIL import Image as PILImage
                blob=base64.b64decode(row[1].split(',')[1]); im=PILImage.open(io.BytesIO(blob)); w,h=im.size; scale=min(130/w,60/h); story.append(Image(io.BytesIO(blob),width=w*scale,height=h*scale,hAlign='LEFT'))
            else: story.append(p(row))
            story.append(Spacer(1,12))
        def footer(canvas,doc):
            canvas.setFont('Helvetica',8); canvas.drawRightString(A4[0]-40,25,f'Page {doc.page}')
        SimpleDocTemplate(output,pagesize=A4,rightMargin=40,leftMargin=40,topMargin=35,bottomMargin=40).build(story,onFirstPage=footer,onLaterPages=footer)
        return output.getvalue()

    @app.get('/invoices/<int:ident>/pdf')
    def invoice_pdf(ident):
        inv=invoice(ident)
        return Response(build_invoice_pdf(inv),mimetype='application/pdf',headers={'Content-Disposition':f"{'inline' if request.args.get('preview') else 'attachment'}; filename=invoice-{ident}.pdf"})

    @app.get('/reports')
    def reports():
        kind=request.args.get('report','Sales'); invoices=[i for i in all_invoices() if i['status']=='FINAL']
        headers=['Invoice','Date','Customer','Total (INR)','Received (INR)','Balance (INR)']; rows=[]
        if kind in ('Inventory','Low stock'):
            headers=['Product','SKU','Category','Stock','Minimum','Unit']
            rows=[[p['name'],p['sku'],p['data']['category'],p['quantity']/1000,p['data']['min_stock']/1000,p['data']['unit']] for p in product_rows() if kind!='Low stock' or p['quantity']<=p['data']['min_stock']]
        elif kind in ('Collections','Stock movement','Product sales'):
            if kind=='Collections':
                headers=['Date','Invoice','Method','Amount (INR)','Reference']; data=payment_rows(); rows=[[r['date'],r['number'],r['method'],r['amount']/100,r['reference']] for r in data if (not request.args.get('from') or r['date']>=request.args['from']) and (not request.args.get('to') or r['date']<=request.args['to'])]
            elif kind=='Stock movement':
                headers=['Date','Product','Quantity','Reason']; data=movement_rows(); rows=[[r['created_at'],r['name'],r['quantity']/1000,r['reason']] for r in data if (not request.args.get('from') or r['created_at'][:10]>=request.args['from']) and (not request.args.get('to') or r['created_at'][:10]<=request.args['to'])]
            else:
                headers=['Product','Quantity','Sales (INR)']; aggregate={}
                for inv in invoices:
                    for item in invoice(inv['id'])['items']:
                        k=(item['product_id'],item['name']); a=aggregate.setdefault(k,[item['name'],0,0]); a[1]+=item['quantity']/1000; a[2]+=item['total']/100
                rows=list(aggregate.values())
        else:
            if kind=='Daily sales': invoices=[i for i in invoices if i['date']==request.args.get('from',today())]
            if kind=='Monthly sales': invoices=[i for i in invoices if i['date'][:7]==request.args.get('from',today())[:7]]
            if kind=='GST sales': invoices=[i for i in invoices if i['type']=='GST']
            if kind=='Non-GST sales': invoices=[i for i in invoices if i['type']=='NON-GST']
            if kind=='Outstanding': invoices=[i for i in invoices if i['balance']>0]
            rows=[[i['number'],i['date'],i['customer'],i['total']/100,i['received']/100,i['balance']/100] for i in invoices]
        if request.args.get('export')=='csv':
            output=io.StringIO(); writer=csv.writer(output)
            def safe(v): return "'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v
            writer.writerow(headers); writer.writerows([[safe(v) for v in r] for r in rows]); return Response('\ufeff'+output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=report.csv'})
        if request.args.get('export')=='pdf': return Response(pdf_document(kind,[[headers]+rows]),mimetype='application/pdf',headers={'Content-Disposition':'attachment; filename=report.pdf'})
        return render_template('reports.html',title='Reports',headers=headers,rows=rows,kind=kind)

    @app.errorhandler(PyMongoError)
    def database_unavailable(error):
        # Do not render driver errors: they may include connection metadata.
        return 'Database temporarily unavailable. Please try again shortly.',503

    def required_permission(endpoint):
        return {'proposals':'invoice.view','proposal_form':'invoice.create','view_proposal':'invoice.view','proposal_pdf':'invoice.view','dashboard':'dashboard.view','billing':'invoice.create','invoices':'invoice.view','view_invoice':'invoice.view','invoice_pdf':'invoice.view','cancel':'invoice.cancel','customers':'customer.view','products':'product.view','inventory':'inventory.view','payments':'payment.view','reports':'report.view','settings_page':'settings.manage','company_users':'user.manage','company_roles':'role.manage'}.get(endpoint)

    def authorize(endpoint):
        policy=access(db(),session['user']); g.access=policy
        if not policy['user'] or not policy['user'].get('active') or policy['user'].get('session_version',0)!=session.get('version',0):
            session.clear(); return redirect(url_for('login'))
        if endpoint=='subscription_page':
            if request.method=='POST' and 'subscription.manage' not in policy['permissions']: abort(403)
            if request.method=='POST' and policy['state'] in ('PENDING','REJECTED','ARCHIVED'): abort(403,'This account cannot request renewal yet.')
            return
        if policy['state']!='ACTIVE': return redirect(url_for('subscription_page'))
        permission=required_permission(endpoint)
        if endpoint=='billing_customer': permission='customer.manage'
        if request.method=='POST':
            permission={'customers':'customer.manage','products':'product.manage','inventory':'inventory.adjust','payments':'payment.record'}.get(endpoint,permission)
        if endpoint=='billing' and (request.form.get('id') or request.args.get('edit')): permission='invoice.edit'
        if endpoint=='proposal_form' and (request.form.get('id') or request.args.get('edit')): permission='invoice.edit'
        if endpoint=='billing' and (request.form.get('id') or request.args.get('edit')) and 'invoice.view' not in policy['permissions']: abort(403)
        if permission and permission not in policy['permissions']: abort(403,'Your role does not permit this action.')
        feature={'inventory':'inventory','reports':'reports','invoice_pdf':'pdf','proposal_pdf':'pdf','company_users':'multiple_users','company_roles':'multiple_users'}.get(endpoint)
        if feature and not policy['features'].get(feature): abort(403,'This feature is not included in your plan.')
        if endpoint=='reports' and request.args.get('export'):
            if 'report.export' not in policy['permissions']: abort(403)
            if request.args['export']=='pdf' and not policy['features'].get('pdf'): abort(403)
        if endpoint=='billing' and request.method=='POST':
            if request.form.get('type','GST')=='GST' and not policy['features'].get('gst'): raise ValueError('GST billing is disabled by your subscription plan.')
            if not request.form.get('id'):
                existing=db().one('invoice_submissions',{'token':request.form.get('submission','')})
                source=owned('proposals',request.form['proposal_id']) if request.form.get('proposal_id') else None
                if not existing and not (source and source.get('invoice_id')): quota(db(),policy,'invoices')
        if endpoint in ('proposal_form','billing') and (request.args.get('proposal') or request.form.get('proposal_id')) and 'invoice.view' not in policy['permissions']: abort(403)
        if endpoint=='proposal_form' and request.method=='POST' and request.form.get('type')=='GST' and not policy['features'].get('gst'): raise ValueError('GST proposals are disabled by your subscription plan.')
        if endpoint=='products' and request.method=='POST' and not request.form.get('action'):
            previous=db().one('products',{'id':request.form['id']}) if request.form.get('id') else None
            if request.form.get('active','1')=='1' and (not previous or not previous['active']): quota(db(),policy,'products')
            if not policy['features'].get('inventory') and quantity(request.form.get('stock') or '0',allow_zero=True): raise ValueError('Opening stock is unavailable while inventory is disabled by your plan.')

    @app.route('/subscription',methods=['GET','POST'])
    def subscription_page():
        platform=Platform(backend)
        if request.method=='POST':
            plan=platform.one('plans',{'id':int(request.form.get('plan_id') or 0),'active':True},db().mongo_session)
            cycle=request.form.get('cycle')
            if not plan or cycle not in ('monthly','yearly'): raise ValueError('Select an available plan and billing cycle.')
            if db().one('renewal_requests',{'status':'PENDING'}): raise ValueError('A renewal request is already awaiting review.')
            rid=db().insert('renewal_requests',dict(plan_id=plan['id'],cycle=cycle,status='PENDING',notes=request.form.get('notes','').strip(),requested_by=session['user']))
            audit('request','renewal',rid); flash('Renewal request sent to the software owner.'); return redirect(url_for('subscription_page'))
        sub=g.access['subscription']; usages=dict(users=db().count('users',{'active':True}),products=db().count('products',{'active':1}),invoices=db().count('invoices',{'first_finalized_month':local_month()}))
        return render_template('subscription.html',title='Company subscription',sub=sub,state=g.access['state'],usage=usages,plans=platform.rows('plans',{'active':True}),renewals=db().find('renewal_requests',sort=[('id',-1)]),policy_settings=platform.one('platform_settings',{'_id':'policy'}),features=FEATURES,subscription_payments=platform.rows('subscription_payments',{'business_id':session['business']},session=db().mongo_session) if 'subscription.manage' in g.access['permissions'] else [])

    @app.route('/company-users',methods=['GET','POST'])
    def company_users():
        if request.method=='POST':
            ident=int(request.form['id']) if request.form.get('id') else None
            previous=owned('users',ident) if ident else None
            role=owned('roles',request.form.get('role_id'))
            if any(permission not in g.access['permissions'] for permission in role['permissions']): abort(403,'You cannot assign permissions beyond your own role.')
            active=request.form.get('active')=='1'
            if previous:
                old_role=owned('roles',previous['role_id'])
                if old_role.get('protected') and (not active or role['id']!=old_role['id']) and db().count('users',{'role_id':old_role['id'],'active':True})<=1: raise ValueError('The last company administrator cannot be disabled or demoted.')
                if ident==session['user'] and (not active or not role.get('protected')): raise ValueError('Use another company administrator to change your own access.')
            if active and (not previous or not previous.get('active')): quota(db(),g.access,'users')
            import re
            email=request.form.get('email','').strip().lower(); name=request.form.get('name','').strip(); password=request.form.get('password','')
            if not name or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise ValueError('Enter a name and valid email.')
            if (not previous or password) and len(password)<12: raise ValueError('Use a password with at least 12 characters.')
            values=dict(name=name,email=email,role_id=role['id'],active=active)
            if password: values['password_hash']=generate_password_hash(password)
            if previous:
                db().update('users',{'id':ident},values,inc={'session_version':1})
                if ident==session['user']: session['version']=previous.get('session_version',0)+1
            else: ident=db().insert('users',values|{'session_version':0})
            audit('update' if previous else 'create','user',ident,json.dumps(dict(name=name,email=email,role_id=role['id'],active=active)))
            flash('Company user saved.'); return redirect(url_for('company_users'))
        return render_template('company_users.html',title='Company users',users=db().find('users',sort=[('id',1)]),roles=db().find('roles'),edit=owned('users',request.args['edit']) if request.args.get('edit') else None)

    @app.route('/company-roles',methods=['GET','POST'])
    def company_roles():
        if request.method=='POST':
            ident=int(request.form['id']) if request.form.get('id') else None
            old=owned('roles',ident) if ident else None
            if old and old.get('protected'): raise ValueError('The Company Admin role retains all company permissions.')
            name=request.form.get('name','').strip(); permissions=request.form.getlist('permissions')
            if not name or name=='COMPANY_ADMIN' or any(p not in PERMISSIONS for p in permissions): raise ValueError('Choose a role name and valid company permissions.')
            if any(p not in g.access['permissions'] for p in permissions): abort(403)
            values=dict(name=name,permissions=permissions,protected=False)
            if ident: db().update('roles',{'id':ident},values)
            else: ident=db().insert('roles',values)
            audit('save','role',ident,json.dumps(values)); flash('Role permissions saved.'); return redirect(url_for('company_roles'))
        return render_template('company_roles.html',title='Company roles',roles=db().find('roles'),edit=owned('roles',request.args['edit']) if request.args.get('edit') else None)

    def transactional(view):
        @wraps(view)
        def guarded(*args,**kwargs):
            if request.method!='POST':
                if 'user' in session:
                    def read():
                        response=authorize(request.endpoint)
                        return response if response is not None else view(*args,**kwargs)
                    return db().run_snapshot(read)
                return view(*args,**kwargs)
            initial_session=deepcopy(dict(session))
            store=db()
            def run():
                session.clear(); session.update(deepcopy(initial_session))
                if request.endpoint!='register':
                    response=authorize(request.endpoint)
                    if response is not None: return response
                return view(*args,**kwargs)
            try: return store.run_transaction(run)
            except Exception:
                session.clear(); session.update(initial_session)
                raise
        return guarded

    for endpoint in ('register','billing_customer','customers','products','inventory','billing','cancel','payments','settings_page','dashboard','invoices','view_invoice','invoice_pdf','reports','subscription_page','company_users','company_roles','proposals','proposal_form','view_proposal','proposal_pdf'):
        app.view_functions[endpoint]=transactional(app.view_functions[endpoint])

    from password_recovery import install_recovery
    install_recovery(app,backend,owner=False)
    return app

app=create_app()
if __name__=='__main__':
    from waitress import serve
    serve(app,host=os.environ.get('HOST','127.0.0.1'),port=int(os.environ.get('PORT','5000')))
