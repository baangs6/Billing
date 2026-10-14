"""Explicit password confirmation for permanent data resets."""
import time
from werkzeug.security import check_password_hash


def confirm_reset(backend, user, fields, phrase, kind):
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
    allowed={'billing','proposals','invoices','customers','inventory','products','payments','finance','reports'}
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
    if 'customers' in selected:
        if exists('invoices'): required.add('invoices')
        if exists('proposals'): required.add('proposals')
    if 'products' in selected:
        if exists('inventory') or exists('stock_movements'): required.add('inventory')
        if exists('invoice_items',{'product_id':{'$ne':None}}): required.add('invoices')
        if exists('proposals',{'items.product_id':{'$ne':None}}): required.add('proposals')
    if 'inventory' in selected:
        if exists('invoice_items',{'product_id':{'$ne':None}}) or exists('stock_movements',{'invoice_id':{'$ne':None}}): required.add('invoices')
    if 'invoices' in selected:
        if exists('payments'): required.add('payments')
        if exists('invoice_items',{'product_id':{'$ne':None}}) or exists('stock_movements',{'invoice_id':{'$ne':None}}): required.add('inventory')
        if exists('proposals',{'invoice_id':{'$ne':None}}): required.add('proposals')
    missing=required-selected
    if missing: raise ValueError('Nothing reset. Also select linked sections: '+', '.join(sorted(missing))+'.')
    collections=set()
    for section,names in {'invoices':('invoices','invoice_items','invoice_submissions'),'proposals':('proposals',),'customers':('customers',),'products':('products','categories'),'payments':('payments',),'finance':('finance_entries',),'inventory':('stock_movements',)}.items():
        if section in selected: collections.update(names)
    for name in sorted(collections): database[name].delete_many(scope,session=ms)
    if 'inventory' in selected:
        if 'products' in selected: database.inventory.delete_many(scope,session=ms)
        else: database.inventory.update_many(scope,{'$set':{'quantity':0}},session=ms)
    return sorted(selected)
