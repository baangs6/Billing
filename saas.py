"""Company authorization and platform operations. Admin access is a separate service."""
import calendar
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from bson.int64 import Int64
from pymongo import ReturnDocument
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern
from mongo_store import clean, fixed_integers

PERMISSIONS = {
    'dashboard.view':'Dashboard', 'customer.view':'View customers', 'customer.manage':'Manage customers',
    'product.view':'View products', 'product.manage':'Manage products', 'inventory.view':'View inventory',
    'inventory.adjust':'Adjust stock', 'invoice.view':'View invoices', 'invoice.create':'Create invoices',
    'invoice.edit':'Edit invoices', 'invoice.cancel':'Cancel invoices', 'payment.view':'View payments',
    'payment.record':'Record payments', 'report.view':'View reports', 'report.export':'Export reports',
    'settings.manage':'Company settings', 'user.manage':'Company users', 'role.manage':'Company roles',
    'subscription.manage':'Renewal requests',
    'finance.view':'View income and expenses', 'finance.manage':'Manage income and expenses',
}
ROLE_DEFAULTS = {
    'COMPANY_ADMIN':list(PERMISSIONS),
    'MANAGER':['dashboard.view','customer.view','customer.manage','product.view','inventory.view','invoice.view','payment.view','report.view','report.export'],
    'BILLING_STAFF':['dashboard.view','customer.view','product.view','invoice.view','invoice.create','payment.view','payment.record'],
    'INVENTORY_STAFF':['dashboard.view','product.view','product.manage','inventory.view','inventory.adjust'],
}
FEATURES={'inventory':'Inventory','gst':'GST billing','reports':'Reports','pdf':'PDF exports','multiple_users':'Multiple users'}
PLATFORM_COLLECTIONS={'admin_users','admin_sessions','admin_audit','plans','subscription_payments','platform_meta','platform_settings'}

def now(): return datetime.now(timezone.utc)
def stamp(value=None): return (value or now()).strftime('%Y-%m-%dT%H:%M:%SZ')
def parse_stamp(value): return datetime.strptime(value,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
def local_month(): return (now()+timedelta(hours=5,minutes=30)).strftime('%Y-%m')
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def month_add(value,months):
    index=value.year*12+value.month-1+months; year,month=divmod(index,12); month+=1
    return value.replace(year=year,month=month,day=min(value.day,calendar.monthrange(year,month)[1]))
def subscription_state(sub):
    if not sub: return 'NONE'
    if sub['status'] in ('CANCELLED','SUSPENDED'): return sub['status']
    if sub.get('expiry_at') and sub['expiry_at']<=stamp(): return 'EXPIRED'
    return sub['status']
def company_state(company,sub):
    if company.get('status')!='ACTIVE': return company.get('status','PENDING')
    state=subscription_state(sub)
    return 'ACTIVE' if state in ('TRIAL','ACTIVE') else state

def seed_roles(store):
    roles={r['name']:r for r in store.find('roles')}
    for name,permissions in ROLE_DEFAULTS.items():
        if name not in roles:
            ident=store.insert('roles',dict(name=name,permissions=permissions,protected=name=='COMPANY_ADMIN'))
            roles[name]=dict(id=ident,name=name,permissions=permissions,protected=name=='COMPANY_ADMIN')
    return roles

def access(store,uid):
    user=store.one('users',{'id':uid})
    company=store.one('businesses'); sub=store.one('subscriptions',{'current':True})
    role=store.one('roles',{'id':user.get('role_id')}) if user and user.get('role_id') else None
    permissions=set(role.get('permissions',[])) if role else set()
    if role and role.get('protected'):
        permissions.update(('finance.view','finance.manage'))
    state=company_state(company,sub)
    if state=='ACTIVE' and not sub['plan']['features'].get('multiple_users') and not (role and role.get('protected')): state='STAFF_RESTRICTED'
    return dict(user=user,company=company,subscription=sub,permissions=permissions,
                state=state,features=sub['plan'].get('features',{}) if sub else {},
                limits=sub['plan'].get('limits',{}) if sub else {})

def quota(store,policy,kind):
    maximum=policy['limits'].get(kind)
    if maximum is None: return
    if kind=='users': used=store.count('users',{'active':True})
    elif kind=='products': used=store.count('products',{'active':1})
    else: used=store.count('invoices',{'first_finalized_month':local_month()})
    if used>=maximum: raise ValueError(f'Your plan allows {maximum} {kind}. Ask the company administrator to request a plan change.')

class Platform:
    """Platform-only repository. No tenant financial document reading or impersonation."""
    def __init__(self,backend): self.backend=backend; self.db=backend.database
    def rows(self,name,query=None,limit=0,session=None):
        if name not in PLATFORM_COLLECTIONS|{'businesses','users','subscriptions','renewal_requests'}: raise PermissionError('Not a platform collection.')
        projection={'_id':0}
        if name=='users': projection.update(password_hash=0)
        if name=='admin_users': projection.update(password_hash=0,totp_secret=0,recovery_hashes=0)
        cursor=self.db[name].find(query or {},projection,session=session).sort('id',-1)
        if limit: cursor=cursor.limit(limit)
        return list(cursor)
    def one(self,name,query,session=None):
        rows=self.rows(name,query,1,session); return rows[0] if rows else None
    def next_id(self,name,session):
        row=self.db.counters.find_one_and_update({'_id':name},{'$inc':{'value':Int64(1)}},upsert=True,return_document=ReturnDocument.AFTER,session=session)
        return int(row['value'])
    def insert(self,name,document,session):
        if name not in PLATFORM_COLLECTIONS: raise PermissionError('Not a platform collection.')
        document=dict(document,id=self.next_id(name,session),created_at=stamp())
        self.db[name].insert_one(fixed_integers(document),session=session); return document['id']
    def audit(self,actor,action,bid,before,after,session,ip='',agent=''):
        return self.insert('admin_audit',dict(admin_id=actor,action=action,business_id=bid,before=before,after=after,ip=ip,user_agent=agent[:300]),session)
    def transaction(self,callback,bid=None):
        with self.backend.client.start_session() as session:
            def run(_):
                self.db.platform_meta.update_one({'_id':'write_lock'},{'$inc':{'version':1}},session=session)
                if bid is not None:
                    if not self.db.businesses.update_one({'id':bid},{'$inc':{'lock_version':Int64(1)}},session=session).matched_count: raise ValueError('Company not found.')
                store=self.backend.scope(bid); store.mongo_session=session; store.write_allowed=True
                return callback(session,store)
            return session.with_transaction(run,read_concern=ReadConcern('snapshot'),write_concern=WriteConcern('majority'),max_commit_time_ms=10000)
    def usage(self,bid):
        # Only aggregate usage counts, never tenant invoices/customers themselves.
        result={name:self.db[name].count_documents({'business_id':bid}) for name in ('users','invoices','products','customers')}
        from mongo_store import TENANT_COLLECTIONS
        size=0
        for name in TENANT_COLLECTIONS:
            rows=list(self.db[name].aggregate([{'$match':{'business_id':bid}},{'$group':{'_id':None,'bytes':{'$sum':{'$bsonSize':'$$ROOT'}}}}]))
            size+=rows[0]['bytes'] if rows else 0
        result['stored bytes']=size
        return result
    def save_plan(self,actor,ident,values,ip='',agent=''):
        def change(session,store):
            previous=self.one('plans',{'id':ident},session) if ident else None
            if ident and not previous: raise ValueError('Plan not found.')
            values['version']=(previous or {}).get('version',0)+1
            if ident: self.db.plans.update_one({'id':ident},{'$set':fixed_integers(values)},session=session); result=ident
            else: result=self.insert('plans',values,session)
            self.audit(actor,'plan.updated' if ident else 'plan.created',None,previous,dict(values,id=result),session,ip,agent)
            return result
        return self.transaction(change)
    def company_action(self,actor,bid,action,fields,ip='',agent=''):
        reason=fields.get('reason','').strip()
        if not reason: raise ValueError('A reason or approval note is required.')
        def change(session,store):
            company=store.one('businesses'); previous=dict(company)
            sub=store.one('subscriptions',{'current':True})
            state=company['status']
            def assign(trial=False,renew=False):
                plan=self.one('plans',{'id':int(fields.get('plan_id') or company.get('requested_plan_id') or 0),'active':True},session)
                if not plan: raise ValueError('Select an active plan.')
                cycle=fields.get('cycle','monthly')
                if cycle not in ('monthly','yearly'): raise ValueError('Invalid billing cycle.')
                base=now()
                if renew and sub and sub.get('expiry_at') and sub['expiry_at']>stamp(): base=parse_stamp(sub['expiry_at'])
                expiry=base+timedelta(days=plan['trial_days']) if trial else month_add(base,12 if cycle=='yearly' else 1)
                if trial and plan['trial_days']<=0: raise ValueError('This plan does not allow a trial.')
                if sub: store.update('subscriptions',{'id':sub['id']},{'current':False,'ended_at':stamp()})
                amount=0 if trial else plan[cycle+'_price']
                sid=store.insert('subscriptions',dict(current=True,status='TRIAL' if trial else 'ACTIVE',plan=plan,start_at=stamp(),expiry_at=stamp(expiry),cycle=cycle,amount=amount,payment_status='FREE' if amount==0 else 'UNPAID',trial_start_at=stamp() if trial else None,trial_end_at=stamp(expiry) if trial else None))
                store.update('businesses',{},dict(status='SUSPENDED' if state=='SUSPENDED' else 'ACTIVE',approved_at=company.get('approved_at') or stamp(),approved_by=company.get('approved_by') or actor,status_reason=reason))
                return sid
            if action=='approve':
                if state=='ACTIVE': return # Idempotent re-submission.
                if state!='PENDING': raise ValueError('Only pending registrations can be approved.')
                assign(fields.get('trial')=='1')
            elif action=='reject':
                if state=='REJECTED': return
                if state!='PENDING': raise ValueError('Only pending registrations can be rejected.')
                store.update('businesses',{},dict(status='REJECTED',status_reason=reason))
            elif action=='review':
                if state!='REJECTED': raise ValueError('Only rejected registrations can return to review.')
                store.update('businesses',{},dict(status='PENDING',status_reason=reason))
            elif action=='suspend':
                if state not in ('ACTIVE','SUSPENDED'): raise ValueError('Only approved companies can be suspended.')
                store.update('businesses',{},dict(status='SUSPENDED',status_reason=reason))
            elif action=='reactivate':
                if state!='SUSPENDED' or subscription_state(sub) not in ('TRIAL','ACTIVE'): raise ValueError('Renew an expired subscription before reactivation.')
                store.update('businesses',{},dict(status='ACTIVE',status_reason=reason))
            elif action=='archive': store.update('businesses',{},dict(status='ARCHIVED',status_reason=reason,archived_at=stamp()))
            elif action in ('renew','assign'):
                if state not in ('ACTIVE','SUSPENDED'): raise ValueError('Approve this company before assigning a subscription.')
                previous_features=sub['plan']['features'] if sub else {}
                sid=assign(renew=action=='renew')
                fresh=store.one('subscriptions',{'id':sid})
                if not previous_features.get('inventory') and fresh['plan']['features'].get('inventory'):
                    store.update('businesses',{},dict(inventory_reconciliation_required=True))
                for renewal in store.find('renewal_requests',{'status':'PENDING','plan_id':fresh['plan']['id'],'cycle':fresh['cycle']}):
                    store.update('renewal_requests',{'id':renewal['id']},dict(status='APPROVED',reviewed_by=actor,reviewed_at=stamp(),notes=reason))
            elif action=='expiry':
                if not sub: raise ValueError('No current subscription.')
                selected=datetime.strptime(fields.get('expiry',''),'%Y-%m-%d').replace(tzinfo=timezone(timedelta(hours=5,minutes=30)))+timedelta(days=1)
                expiry=stamp(selected.astimezone(timezone.utc))
                if expiry<=sub['start_at']: raise ValueError('Expiry must be later than the subscription start.')
                store.update('subscriptions',{'id':sub['id']},dict(expiry_at=expiry,status='ACTIVE',trial_end_at=None))
            elif action in ('cancel_subscription','suspend_subscription'):
                if not sub: raise ValueError('No current subscription.')
                store.update('subscriptions',{'id':sub['id']},dict(status='CANCELLED' if action=='cancel_subscription' else 'SUSPENDED'))
            elif action=='reject_renewal':
                renewal=store.one('renewal_requests',{'id':int(fields.get('renewal_id') or 0),'status':'PENDING'})
                if not renewal: raise ValueError('Select a pending renewal request for this company.')
                store.update('renewal_requests',{'id':renewal['id']},dict(status='REJECTED',notes=reason,reviewed_by=actor,reviewed_at=stamp()))
            else: raise ValueError('Unknown action.')
            after=dict(company=store.one('businesses'),subscription=store.one('subscriptions',{'current':True}))
            self.audit(actor,'company.'+action,bid,dict(company=previous,subscription=sub),after,session,ip,agent)
        return self.transaction(change,bid)
    def payment(self,actor,bid,fields,amount,ip='',agent=''):
        token=fields.get('submission','')
        if len(token)!=64: raise ValueError('Reload this payment form.')
        if amount<=0: raise ValueError('Subscription payment must be positive.')
        if fields.get('method') not in ('Cash','UPI','Bank Transfer','Card','Cheque','Other'): raise ValueError('Invalid payment method.')
        if not fields.get('reference','').strip(): raise ValueError('A receipt/reference is required.')
        datetime.strptime(fields.get('date',''),'%Y-%m-%d')
        def change(session,store):
            if self.one('subscription_payments',{'submission':token},session): return
            sub=store.one('subscriptions',{'id':int(fields.get('subscription_id') or 0)})
            if not sub: raise ValueError('Subscription does not belong to this company.')
            pid=self.insert('subscription_payments',dict(business_id=bid,subscription_id=sub['id'],amount=amount,date=fields['date'],method=fields['method'],reference=fields['reference'].strip(),notes=fields.get('notes','').strip(),recorded_by=actor,submission=token),session)
            paid=sum(p['amount'] for p in self.rows('subscription_payments',{'business_id':bid,'subscription_id':sub['id']},session=session))
            store.update('subscriptions',{'id':sub['id']},dict(payment_status='PAID' if paid>=sub['amount'] else 'PARTIAL'))
            self.audit(actor,'subscription.payment',bid,None,dict(id=pid,amount=amount,subscription_id=sub['id']),session,ip,agent)
        return self.transaction(change,bid)

def initialize_saas(backend):
    backend.initialize(); db=backend.database; platform=Platform(backend)
    for name in PLATFORM_COLLECTIONS:
        if name not in db.list_collection_names(): db.create_collection(name)
    db.platform_meta.update_one({'_id':'write_lock'},{'$setOnInsert':{'version':0}},upsert=True)
    db.platform_settings.update_one({'_id':'policy'},{'$setOnInsert':dict(registration_open=True,renewal_contact='',support_email='',id=1)},upsert=True)
    db.plans.create_index('id',unique=True); db.plans.create_index('name',unique=True)
    db.admin_users.create_index('email',unique=True); db.admin_users.create_index('id',unique=True)
    db.admin_sessions.create_index('expires_at',expireAfterSeconds=0)
    db.subscription_payments.create_index('submission',unique=True)
    db.subscription_payments.create_index([('business_id',1),('date',-1)])
    db.subscriptions.create_index('business_id',unique=True,partialFilterExpression={'current':True},name='one_current_subscription')
    db.roles.create_index([('business_id',1),('name',1)],unique=True)
    db.admin_audit.create_index([('business_id',1),('created_at',-1)])
    db.businesses.create_index([('status',1),('created_at',-1)])
    def defaults(session,store):
        if not platform.one('plans',{'legacy':True},session):
            platform.insert('plans',dict(name='Existing workspace',active=False,legacy=True,version=1,monthly_price=0,yearly_price=0,trial_days=0,features={k:True for k in FEATURES},limits=dict(users=None,products=None,invoices=None)),session)
        if not platform.one('plans',{'legacy':{'$ne':True}},session):
            platform.insert('plans',dict(name='Trial',active=True,legacy=False,version=1,monthly_price=0,yearly_price=0,trial_days=14,features={k:True for k in FEATURES},limits=dict(users=3,products=1000,invoices=500)),session)
        for name,limits in [('Subscription',dict(users=10,products=5000,invoices=2000)),('Unlimited',dict(users=None,products=None,invoices=None))]:
            if not platform.one('plans',{'name':name},session):
                platform.insert('plans',dict(name=name,description='Free launch offer. Paid pricing may be introduced for future subscriptions.',active=True,legacy=False,version=1,monthly_price=0,yearly_price=0,trial_days=0,features={k:True for k in FEATURES},limits=limits),session)
    platform.transaction(defaults)
    for company in platform.rows('businesses',{'status':{'$exists':False}}):
        def migrate(session,store):
            if store.one('businesses').get('status'): return
            roles=seed_roles(store)
            for user in store.find('users'):
                store.update('users',{'id':user['id']},dict(active=True,name=user.get('name') or user['email'],role_id=roles['COMPANY_ADMIN']['id'],session_version=0))
            legacy=platform.one('plans',{'legacy':True},session)
            store.insert('subscriptions',dict(current=True,status='ACTIVE',plan=legacy,start_at=stamp(),expiry_at=None,cycle='legacy',amount=0,payment_status='FREE'))
            store.update('businesses',{},dict(status='ACTIVE',owner_name=company.get('owner_name',''),contact_email=store.one('users')['email'],phone='',approved_at=stamp(),status_reason='Preserved existing workspace during SaaS migration.'))
            platform.audit(None,'company.migrated',company['id'],company,dict(status='ACTIVE',legacy_plan=legacy['id']),session)
        platform.transaction(migrate,company['id'])
    return platform

def bootstrap_link(backend):
    """Private local-only token; calling again rotates unused tokens, never creates users."""
    if backend.database.admin_users.count_documents({}): return None
    token=secrets.token_urlsafe(32)
    backend.database.platform_meta.update_one({'_id':'bootstrap'},{'$set':dict(token_hash=digest(token),expires_at=stamp(now()+timedelta(hours=24)))},upsert=True)
    path=Path(__file__).parent/'instance'/'admin-setup-url.txt'
    path.write_text('http://127.0.0.1:5001/setup/'+token,encoding='utf-8')
    return str(path)
