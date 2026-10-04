"""Owner-only Flask service. No company billing routes are registered here."""
import base64
import hashlib
import hmac
import os
import re
import secrets
import struct
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo.errors import DuplicateKeyError, PyMongoError
from mongo_store import MongoBackend, load_configuration
from saas import Platform, FEATURES, PERMISSIONS, now, stamp, digest, parse_stamp, company_state, subscription_state

ROOT=Path(__file__).parent

def private_key(name,fernet=False):
    environment_name={'admin-encryption.key':'ADMIN_ENCRYPTION_KEY','admin-session.key':'ADMIN_SESSION_KEY'}[name]
    configured=os.environ.get(environment_name)
    if configured:
        value=configured.strip().encode()
        if fernet: Fernet(value)
        elif len(value)<32: raise ValueError(environment_name+' must contain at least 32 characters.')
        return value
    if os.environ.get('RENDER'):
        raise RuntimeError('Set '+environment_name+' in Render Environment before starting the admin service. Use the existing private key when migrating an owner account.')
    path=ROOT/'instance'/name
    path.parent.mkdir(exist_ok=True)
    if not path.exists():
        # Exclusive create prevents two server starts from generating different keys.
        try:
            with path.open('xb') as output: output.write(Fernet.generate_key() if fernet else secrets.token_hex(32).encode())
        except FileExistsError: pass
    return path.read_bytes().strip()

def totp(secret,counter):
    key=base64.b32decode(secret+'='*((8-len(secret)%8)%8))
    signature=hmac.new(key,struct.pack('>Q',counter),hashlib.sha1).digest(); offset=signature[-1]&15
    return str((struct.unpack('>I',signature[offset:offset+4])[0]&0x7fffffff)%1000000).zfill(6)

def verify_totp(secret,code,last=-1):
    if not re.fullmatch(r'\d{6}',code): return None
    for counter in (int(time.time())//30-1,int(time.time())//30,int(time.time())//30+1):
        if counter>last and hmac.compare_digest(totp(secret,counter),code): return counter
    return None

def create_admin_app(backend=None):
    backend=backend or MongoBackend(*load_configuration()); platform=Platform(backend)
    cipher=Fernet(private_key('admin-encryption.key',True))
    app=Flask(__name__)
    app.config.update(SECRET_KEY=private_key('admin-session.key'),SESSION_COOKIE_NAME='ledger_admin',SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=__import__('os').environ.get('HTTPS')=='1',PERMANENT_SESSION_LIFETIME=timedelta(hours=2),MAX_CONTENT_LENGTH=1024*1024)
    app.extensions.update(mongo=backend,platform=platform,cipher=cipher)
    app.jinja_env.filters['inr']=lambda value:f'₹{value/100:,.2f}'

    def audit_login(actor,action):
        platform.transaction(lambda ms,store:platform.audit(actor,action,None,None,None,ms,request.remote_addr or '',request.user_agent.string))
    def metadata(): return request.remote_addr or '',request.user_agent.string
    def current_admin():
        sid=session.get('admin_sid')
        if not sid: return None
        row=backend.database.admin_sessions.find_one({'_id':digest(sid),'expires_at':{'$gt':now().replace(tzinfo=None)}})
        if not row: return None
        user=backend.database.admin_users.find_one({'id':row['admin_id'],'active':True,'session_version':row['version']})
        return user
    @app.before_request
    def security():
        g.admin=current_admin()
        session.setdefault('csrf',secrets.token_hex(32))
        if request.method=='POST':
            if not secrets.compare_digest(session['csrf'],request.form.get('csrf','')): abort(400,'Refresh the page before submitting.')
            if any(len(value)>(2500 if key in ('reason','notes') else 300) for key,value in request.form.items()): abort(400,'A field is too long.')
        if request.endpoint not in ('login','setup','forgot_password','reset_password','static') and not g.admin: return redirect(url_for('login'))
    @app.after_request
    def headers(response):
        response.headers.update({'Cache-Control':'no-store','X-Frame-Options':'DENY','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"})
        return response
    @app.context_processor
    def context():
        return dict(csrf=session.get('csrf'),admin=g.get('admin'),today=stamp()[:10],features=FEATURES,permissions=PERMISSIONS,nav=[('dashboard','Overview','◫'),('companies','Companies','♧'),('subscriptions','Subscriptions','▤'),('plans','Plans','◇'),('users','Users','♙'),('payments','Payments','↗'),('audit','Audit history','▥'),('settings','System settings','⚙')])
    @app.errorhandler(ValueError)
    def invalid(error):
        flash(str(error),'error')
        if request.endpoint=='setup': return redirect(request.path)
        if request.endpoint=='login': return redirect(url_for('login'))
        return redirect(request.referrer if request.referrer and request.referrer.startswith(request.host_url) else url_for('dashboard'))
    @app.errorhandler(DuplicateKeyError)
    def duplicate(error): return invalid(ValueError('A record already exists. Reload and check the name or email.'))
    @app.errorhandler(PyMongoError)
    def unavailable(error): return 'Database temporarily unavailable. Please try again shortly.',503
    @app.errorhandler(InvalidToken)
    def encryption_unavailable(error):
        app.logger.error('Admin authenticator decryption failed. Configure ADMIN_ENCRYPTION_KEY with the original owner encryption key; do not replace the owner account.')
        return 'Admin authentication is temporarily unavailable because the server encryption key does not match. The service owner must restore the original ADMIN_ENCRYPTION_KEY.',503

    @app.route('/setup/<token>',methods=['GET','POST'])
    def setup(token):
        if request.remote_addr not in ('127.0.0.1','::1'): abort(403)
        record=backend.database.platform_meta.find_one({'_id':'bootstrap','token_hash':digest(token),'expires_at':{'$gt':stamp()}})
        if not record or backend.database.admin_users.count_documents({}): abort(404)
        if session.get('setup_token')!=digest(token):
            secret=base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')
            session['setup_secret']=cipher.encrypt(secret.encode()).decode(); session['setup_token']=digest(token)
        secret=cipher.decrypt(session['setup_secret'].encode()).decode()
        if request.method=='POST':
            email=request.form.get('email','').lower().strip(); password=request.form.get('password',''); name=request.form.get('name','').strip()
            if not name or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email): raise ValueError('Enter your name and a valid email.')
            if len(password)<14: raise ValueError('Choose a password with at least 14 characters.')
            key='admin-setup:'+(request.remote_addr or '')
            attempt=backend.login_attempt(key)
            if attempt and attempt['count']>=10 and time.time()-attempt['started']<900: abort(429,'Too many attempts. Wait 15 minutes.')
            counter=verify_totp(secret,request.form.get('code','').strip())
            if counter is None:
                backend.failed_login(key); raise ValueError('Enter the current six-digit code from your authenticator.')
            recovery=[secrets.token_hex(8) for _ in range(8)]
            password_hash=generate_password_hash(password)
            def create(ms,store):
                if backend.database.admin_users.count_documents({},session=ms) or not backend.database.platform_meta.find_one({'_id':'bootstrap','token_hash':digest(token),'expires_at':{'$gt':stamp()}},session=ms): raise ValueError('Setup was already completed or expired.')
                ident=platform.insert('admin_users',dict(name=name,email=email,password_hash=password_hash,totp_secret=cipher.encrypt(secret.encode()).decode(),last_totp_counter=counter,recovery_hashes=[digest(c) for c in recovery],active=True,session_version=0),ms)
                backend.database.platform_meta.delete_one({'_id':'bootstrap'},session=ms)
                platform.audit(ident,'admin.created',None,None,dict(name=name,email=email),ms,*metadata())
            platform.transaction(create)
            setup_file=ROOT/'instance'/'admin-setup-url.txt'
            if setup_file.exists() and setup_file.read_text(encoding='utf-8').endswith('/'+token): setup_file.unlink()
            backend.reset_login_attempt(key); session.clear(); session['csrf']=secrets.token_hex(32)
            # Recovery codes are shown once, never saved in plaintext.
            return render_template('admin/auth.html',recovery=recovery,title='Save your recovery codes')
        return render_template('admin/auth.html',setup=True,title='Create the owner account',secret=secret,otp_uri='otpauth://totp/'+quote('Ledger owner')+'?secret='+secret+'&issuer=Ledger')

    @app.route('/login',methods=['GET','POST'])
    def login():
        if g.admin: return redirect(url_for('dashboard'))
        if request.method=='POST':
            email=request.form.get('email','').strip().lower(); code=request.form.get('code','').strip()
            key='admin:'+(request.remote_addr or '')+':'+email
            attempt=backend.login_attempt(key)
            if attempt and attempt['count']>=10 and time.time()-attempt['started']<900: abort(429,'Too many attempts. Wait 15 minutes.')
            row=backend.database.admin_users.find_one({'email':email,'active':True})
            if row and check_password_hash(row['password_hash'],request.form.get('password','')):
                secret=cipher.decrypt(row['totp_secret'].encode()).decode(); counter=verify_totp(secret,code,row.get('last_totp_counter',-1))
                recovery=digest(code) if digest(code) in row.get('recovery_hashes',[]) else None
                if counter is not None or recovery:
                    sid=secrets.token_urlsafe(32)
                    def authenticate(ms,store):
                        current=backend.database.admin_users.find_one({'id':row['id'],'active':True},session=ms)
                        if not current or current['session_version']!=row['session_version']: raise ValueError('Account changed. Sign in again.')
                        if recovery:
                            result=backend.database.admin_users.update_one({'id':row['id'],'recovery_hashes':recovery},{'$pull':{'recovery_hashes':recovery},'$set':{'last_login_at':stamp()}},session=ms)
                        else:
                            result=backend.database.admin_users.update_one({'id':row['id'],'last_totp_counter':{'$lt':counter}},{'$set':{'last_totp_counter':counter,'last_login_at':stamp()}},session=ms)
                        if not result.modified_count: raise ValueError('This verification code was already used. Wait for a new code.')
                        backend.database.admin_sessions.insert_one({'_id':digest(sid),'admin_id':row['id'],'version':row['session_version'],'expires_at':now()+timedelta(hours=2)},session=ms)
                        platform.audit(row['id'],'admin.login',None,None,None,ms,*metadata())
                    platform.transaction(authenticate)
                    backend.reset_login_attempt(key); session.clear(); session.update(admin_sid=sid,csrf=secrets.token_hex(32)); session.permanent=True
                    return redirect(url_for('dashboard'))
            backend.failed_login(key); audit_login(None,'admin.login_failed'); flash('Email, password or verification code is incorrect.','error')
        return render_template('admin/auth.html',title='Owner sign in',has_owner=backend.database.admin_users.count_documents({})>0)

    @app.post('/logout')
    def logout():
        backend.database.admin_sessions.delete_one({'_id':digest(session.get('admin_sid',''))}); audit_login(g.admin['id'],'admin.logout')
        session.clear(); return redirect(url_for('login'))

    def enriched_companies():
        subscriptions={s['business_id']:s for s in platform.rows('subscriptions',{'current':True})}
        result=[]
        for company in platform.rows('businesses'):
            company['subscription']=subscriptions.get(company['id']); company['effective_status']=company_state(company,company['subscription'])
            result.append(company)
        return result

    @app.get('/')
    def dashboard():
        companies=enriched_companies(); subs=[c['subscription'] for c in companies if c['subscription']]
        monthly=stamp()[:7]
        revenue=sum(p['amount'] for p in platform.rows('subscription_payments',{'date':{'$gte':monthly+'-01','$lt':monthly+'-32'}}))
        metrics={'Total companies':len(companies),'Pending approvals':sum(c['effective_status']=='PENDING' for c in companies),'Active companies':sum(c['effective_status']=='ACTIVE' for c in companies),'Trials':sum(subscription_state(s)=='TRIAL' for s in subs),'Expired subscriptions':sum(subscription_state(s)=='EXPIRED' for s in subs),'Suspended companies':sum(c['effective_status']=='SUSPENDED' for c in companies),'Company users':backend.database.users.count_documents({}),'New this month':sum((c.get('created_at') or '')[:7]==monthly for c in companies)}
        expiring=[c for c in companies if c['subscription'] and c['subscription'].get('expiry_at') and stamp()<c['subscription']['expiry_at']<=stamp(now()+timedelta(days=14))]
        return render_template('admin/dashboard.html',title='Platform overview',metrics=metrics,revenue=revenue,companies=companies[:8],expiring=expiring)

    @app.get('/companies')
    def companies():
        rows=enriched_companies(); query=request.args.get('q','').lower().strip(); status=request.args.get('status'); plan=request.args.get('plan')
        rows=[c for c in rows if (not query or query in ' '.join(str(c.get(k,'')) for k in ('name','owner_name','contact_email','phone')).lower()) and (not status or c['effective_status']==status) and (not plan or (c['subscription'] and str(c['subscription']['plan']['id'])==plan)) and (not request.args.get('registered_from') or c.get('created_at','')[:10]>=request.args['registered_from']) and (not request.args.get('registered_to') or c.get('created_at','')[:10]<=request.args['registered_to']) and (not request.args.get('expiry_to') or c['subscription'] and c['subscription'].get('expiry_at') and c['subscription']['expiry_at'][:10]<=request.args['expiry_to'])]
        return render_template('admin/companies.html',title='Pending approvals' if status=='PENDING' else 'Companies',companies=rows,plans=platform.rows('plans'))

    @app.route('/companies/<int:bid>',methods=['GET','POST'])
    def company(bid):
        row=platform.one('businesses',{'id':bid})
        if not row: abort(404)
        if request.method=='POST':
            platform.company_action(g.admin['id'],bid,request.form.get('action'),request.form,*metadata())
            flash('Company updated. The change is recorded in audit history.'); return redirect(url_for('company',bid=bid))
        subs=platform.rows('subscriptions',{'business_id':bid}); sub=next((s for s in subs if s.get('current')),None)
        return render_template('admin/company.html',title=row['name'],company=row,sub=sub,state=company_state(row,sub),subscriptions=subs,usage=platform.usage(bid),users=platform.rows('users',{'business_id':bid}),plans=platform.rows('plans',{'active':True}),events=platform.rows('admin_audit',{'business_id':bid},50),renewals=platform.rows('renewal_requests',{'business_id':bid}))

    @app.route('/plans',methods=['GET','POST'])
    def plans():
        from app import money
        if request.method=='POST':
            name=request.form.get('name','').strip()
            if not name: raise ValueError('Plan name is required.')
            def integer(field,unlimited=False):
                if unlimited and request.form.get('unlimited_'+field.removeprefix('max_'))=='1': return None
                raw=request.form.get(field,'').strip()
                if unlimited and raw=='': return None
                value=int(raw)
                if not 0<=value<=1000000: raise ValueError('Limits must be between zero and 1,000,000; blank means unlimited.')
                return value
            values=dict(name=name,description=request.form.get('description','').strip(),active=request.form.get('active')=='1',monthly_price=money(request.form.get('monthly_price','0')),yearly_price=money(request.form.get('yearly_price','0')),trial_days=integer('trial_days'),features={k:request.form.get(k)=='1' for k in FEATURES},limits={k:integer('max_'+k,True) for k in ('users','invoices','products')})
            if values['trial_days']>365: raise ValueError('Trial days cannot exceed 365.')
            platform.save_plan(g.admin['id'],int(request.form['id']) if request.form.get('id') else None,values,*metadata())
            flash('Plan saved. Existing subscription snapshots are unchanged.'); return redirect(url_for('plans'))
        edit=platform.one('plans',{'id':int(request.args['edit'])}) if request.args.get('edit') else None
        return render_template('admin/plans.html',title='Subscription plans',plans=platform.rows('plans'),edit=edit)

    @app.get('/subscriptions')
    def subscriptions():
        rows=[c for c in enriched_companies() if c['subscription']]
        status=request.args.get('status'); expiring=request.args.get('expiring')
        rows=[c for c in rows if (not status or subscription_state(c['subscription'])==status) and (not expiring or c['subscription'].get('expiry_at') and stamp()<c['subscription']['expiry_at']<=stamp(now()+timedelta(days=14)))]
        for row in rows: row['subscription']['effective_status']=subscription_state(row['subscription'])
        return render_template('admin/subscriptions.html',title='Subscriptions',companies=rows,renewals=platform.rows('renewal_requests',{'status':'PENDING'}))

    @app.route('/users',methods=['GET','POST'])
    def users():
        if request.method=='POST':
            uid=int(request.form.get('id','0')); bid=int(request.form.get('business_id','0')); active=request.form.get('active')=='1'
            reason=request.form.get('reason','').strip()
            if not reason: raise ValueError('An account-change reason is required.')
            def change(ms,store):
                user=store.one('users',{'id':uid})
                if not user: raise ValueError('User does not belong to this company.')
                role=store.one('roles',{'id':user['role_id']})
                if not active and role and role.get('protected') and store.count('users',{'role_id':role['id'],'active':True})<=1: raise ValueError('The last company administrator cannot be disabled.')
                if active and not user.get('active'):
                    from saas import access,quota
                    policy=access(store,uid)
                    if not policy['features'].get('multiple_users') and store.count('users',{'active':True})>=1: raise ValueError('Plan does not allow multiple users.')
                    quota(store,policy,'users')
                store.update('users',{'id':uid},dict(active=active),inc={'session_version':1})
                platform.audit(g.admin['id'],'company.user_status',bid,dict(id=uid,active=user.get('active')),dict(id=uid,active=active,reason=reason),ms,*metadata())
            platform.transaction(change,bid); flash('User access updated.'); return redirect(url_for('users'))
        companies={c['id']:c['name'] for c in platform.rows('businesses')}; query=request.args.get('q','').lower()
        rows=[u for u in platform.rows('users') if query in (u.get('name','')+' '+u['email']+' '+companies.get(u['business_id'],'')).lower()]
        return render_template('admin/users.html',title='Company users',users=rows,companies=companies)

    @app.route('/payments',methods=['GET','POST'])
    def payments():
        from app import money
        if request.method=='POST':
            platform.payment(g.admin['id'],int(request.form.get('business_id','0')),request.form,money(request.form.get('amount','0')),*metadata())
            flash('Subscription payment recorded.'); return redirect(url_for('payments'))
        companies={c['id']:c['name'] for c in platform.rows('businesses')}
        return render_template('admin/payments.html',title='Subscription payments',payments=platform.rows('subscription_payments'),subscriptions=platform.rows('subscriptions'),companies=companies,submission=secrets.token_hex(32))

    @app.get('/audit')
    def audit():
        query={}
        if request.args.get('business_id'): query['business_id']=int(request.args['business_id'])
        if request.args.get('admin_id'): query['admin_id']=int(request.args['admin_id'])
        if request.args.get('action'): query['action']=request.args['action']
        if request.args.get('from'): query['created_at']={'$gte':request.args['from']}
        if request.args.get('to'): query.setdefault('created_at',{})['$lte']=request.args['to']+'T23:59:59Z'
        return render_template('admin/audit.html',title='Audit history',events=platform.rows('admin_audit',query,300),companies=platform.rows('businesses'),admins=platform.rows('admin_users'))

    @app.route('/settings',methods=['GET','POST'])
    def settings():
        if request.method=='POST':
            values=dict(registration_open=request.form.get('registration_open')=='1',renewal_contact=request.form.get('renewal_contact','').strip(),support_email=request.form.get('support_email','').strip())
            if values['support_email'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',values['support_email']): raise ValueError('Enter a valid support email.')
            def change(ms,store):
                old=platform.one('platform_settings',{'_id':'policy'},ms)
                backend.database.platform_settings.update_one({'_id':'policy'},{'$set':values},session=ms)
                platform.audit(g.admin['id'],'platform.settings',None,old,values,ms,*metadata())
            platform.transaction(change); flash('System settings saved.'); return redirect(url_for('settings'))
        return render_template('admin/settings.html',title='System settings',policy=platform.one('platform_settings',{'_id':'policy'}))
    from password_recovery import install_recovery
    install_recovery(app,backend,owner=True)
    return app

app=create_admin_app()
if __name__=='__main__':
    from waitress import serve
    serve(app,host='127.0.0.1',port=5001)
