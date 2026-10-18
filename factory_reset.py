"""Explicit password confirmation for permanent data resets."""
import time
from werkzeug.security import check_password_hash


def preserve_shared_identities(database, ms, business_id, keep_user=None):
    """Move credentials to a surviving membership before removing tenant users."""
    roots=list(database.users.find({'business_id':business_id,'identity_id':{'$exists':False}},session=ms))
    for root in roots:
        if root['id']==keep_user: continue
        for target in database.users.find({'identity_id':root['id'],'business_id':{'$ne':business_id},'active':True},session=ms):
            if not database.businesses.find_one({'id':target['business_id']},session=ms): continue
            if not database.roles.find_one({'id':target.get('role_id'),'business_id':target['business_id']},session=ms): continue
            database.users.update_one({'id':root['id']},{'$set':{'business_id':target['business_id'],'role_id':target['role_id']},'$inc':{'session_version':1}},session=ms)
            database.users.update_one({'id':target['id']},{'$set':{'active':False},'$inc':{'session_version':1}},session=ms)
            break


def confirm_reset(backend, user, fields, phrase, kind):
    if user.get('identity_id'):
        user=backend.database.users.find_one({'id':user['identity_id'],'active':True})
        if not user: raise ValueError('Shared account is no longer active.')
    if fields.get('confirmation','') != phrase:
        raise ValueError('Type '+phrase+' exactly to confirm permanent deletion.')
    key='factory-reset:'+kind+':'+str(user['id'])
    attempt=backend.login_attempt(key)
    if attempt and attempt['count']>=5 and time.time()-attempt['started']<900:
        raise ValueError('Too many password attempts. Try again in 15 minutes.')
    if not check_password_hash(user['password_hash'],fields.get('password','')):
        backend.failed_login(key)
        raise ValueError('Current password is incorrect. Nothing was deleted.')
    backend.reset_login_attempt(key)


def reset_sections(backend, ms, scope, selected):
    """Delete explicitly selected sections only, after checking all live links."""
    selected=set(selected)
    allowed={'billing','proposals','invoices','customers','inventory','products','payments','finance','reports','purchases','suppliers','accounts'}
    if not selected or selected-allowed: raise ValueError('Select valid sections to reset.')
    if 'billing' in selected: selected.add('invoices'); selected.remove('billing')
    selected.discard('reports')
    if not selected: raise ValueError('Reports are calculated. Select the source data you want to reset.')
    database=backend.database
    def query(extra=None):
        return {'$and':[scope,extra]} if extra else scope
    def exists(name,extra=None):
        return database[name].find_one(query(extra),{'_id':1},session=ms) is not None
    required=set()
    if 'suppliers' in selected and (exists('purchases') or exists('purchase_orders') or exists('trade_payments',{'supplier_id':{'$exists':True}})): required.add('purchases')
    product_links={'items':{'$elemMatch':{'product_id':{'$exists':True,'$ne':None}}}}
    stock_links={'items':{'$elemMatch':{'product_id':{'$exists':True,'$ne':None},'is_service':{'$ne':True}}}}
    stocked_purchases=exists('purchases',stock_links)
    if 'products' in selected and (exists('purchases',product_links) or exists('purchase_orders',product_links)): required.add('purchases')
    if 'inventory' in selected and stocked_purchases: required.add('purchases')
    if 'purchases' in selected and stocked_purchases: required.add('inventory')
    if 'accounts' in selected:
        if exists('payments',{'ledger_account':{'$regex':'^[0-9]+$'}}): required.add('payments')
        if exists('trade_payments',{'ledger_account':{'$regex':'^[0-9]+$'},'supplier_id':{'$exists':True}}): required.add('purchases')
        if exists('trade_payments',{'ledger_account':{'$regex':'^[0-9]+$'},'customer_id':{'$exists':True}}): required.add('payments')
        if exists('finance_entries',{'ledger_account':{'$regex':'^[0-9]+$'}}): required.add('finance')

    if 'customers' in selected:
        if exists('trade_payments',{'customer_id':{'$exists':True}}): required.add('payments')
        if exists('invoices'): required.add('invoices')
        if exists('proposals'): required.add('proposals')
    if 'products' in selected:
        if exists('inventory') or exists('stock_movements'): required.add('inventory')
        if exists('invoice_items',{'product_id':{'$ne':None}}): required.add('invoices')
        if exists('proposals',{'items.product_id':{'$ne':None}}): required.add('proposals')
    if 'inventory' in selected:
        if exists('invoice_items',{'product_id':{'$ne':None},'is_service':{'$ne':True}}) or exists('stock_movements',{'invoice_id':{'$ne':None}}): required.add('invoices')
    if 'invoices' in selected:
        if exists('trade_payments',{'kind':'CUSTOMER_REFUND'}): required.add('payments')
        if exists('payments'): required.add('payments')
        if exists('invoice_items',{'product_id':{'$ne':None},'is_service':{'$ne':True}}) or exists('stock_movements',{'invoice_id':{'$ne':None}}): required.add('inventory')
        if exists('proposals',{'invoice_id':{'$ne':None}}): required.add('proposals')
    missing=required-selected
    if missing: raise ValueError('Nothing reset. Also select linked sections: '+', '.join(sorted(missing))+'.')
    collections=set()
    for section,names in {'accounts':('bank_accounts','account_transfers'),'purchases':('purchases','purchase_orders','trade_returns'),'suppliers':('suppliers',),'invoices':('invoices','invoice_items','invoice_submissions','sales_returns'),'proposals':('proposals',),'customers':('customers',),'products':('products','categories'),'payments':('payments',),'finance':('finance_entries',),'inventory':('stock_movements',)}.items():
        if section in selected: collections.update(names)
    if 'purchases' in selected: database.trade_payments.delete_many(query({'supplier_id':{'$exists':True}}),session=ms)
    if 'payments' in selected: database.trade_payments.delete_many(query({'customer_id':{'$exists':True}}),session=ms)
    if 'invoices' in selected: database.trade_payments.delete_many(query({'kind':'CUSTOMER_REFUND'}),session=ms)
    for name in sorted(collections): database[name].delete_many(scope,session=ms)
    if 'inventory' in selected:
        if 'products' in selected: database.inventory.delete_many(scope,session=ms)
        else: database.inventory.update_many(scope,{'$set':{'quantity':0}},session=ms)
    return sorted(selected)
