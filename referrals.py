"""Tenant-scoped referral points, written inside the existing company transaction."""
import json


def referral_customer(db,form,previous=None):
    old=(previous or {}).get('data',{})
    if 'referred_by' not in form: return old.get('referred_by')
    value=form.get('referred_by','').strip()
    try: ident=int(value) if value else None
    except ValueError: raise ValueError('Choose a referring customer from the list.')
    if ident==((previous or {}).get('id')) and ident is not None: raise ValueError('A customer cannot refer themselves.')
    if ident!=old.get('referred_by') and previous and db.count('invoices',{'customer_id':previous['id']}):
        raise ValueError('Referred by cannot change after invoice history exists.')
    if ident and ident!=old.get('referred_by'):
        row=db.one('customers',{'id':ident})
        if not row or row.get('archived'): raise ValueError('Choose an active referring customer.')
    return ident


def redemption(db,customer,form,business,old,money):
    try: points=int(form.get('referral_points') or '0')
    except ValueError: raise ValueError('Referral points must be a whole number.')
    if points<0 or points>1000000: raise ValueError('Enter valid referral points.')
    previous=(old or {}).get('referral_points',0) if (old or {}).get('customer_id')==customer['id'] else 0
    available=customer['data'].get('referral_points',0)+previous
    if points>available: raise ValueError('This customer does not have enough referral points. Refresh billing.')
    if points and not customer['id']: raise ValueError('Select a customer to use referral points.')
    # Preserve the agreed discount on edits unless the redemption itself changes.
    unchanged=old and previous==points and old.get('customer_id')==customer['id']
    amount=(old['referral_discount'] if unchanged else points*business.get('referral_value',0)) if business.get('referral_mode','FIXED')=='FIXED' else money(form.get('referral_amount') or '0')
    if not points:
        if business.get('referral_mode')=='MANUAL' and amount: raise ValueError('Choose points to redeem with the referral discount.')
        return 0,0
    if amount<=0: raise ValueError('Set a positive referral point value or enter a discount amount.')
    return points,amount


def change_points(db,audit,customer_id,delta,invoice_id,reason,note=''):
    if not delta: return
    customer=db.one('customers',{'id':customer_id})
    if not customer: raise ValueError('Referral customer no longer exists.')
    balance=customer['data'].get('referral_points',0)+delta
    if balance<0: raise ValueError('Not enough referral points.')
    db.update('customers',{'id':customer_id},{'data.referral_points':balance})
    return audit(reason,'referral',customer_id,json.dumps(dict(points=delta,balance=balance,invoice_id=invoice_id,note=note)))


def apply_redemption(db,audit,old,current):
    before=(old or {}).get('referral_points',0);after=current.get('referral_points',0)
    if old and old['customer_id']==current['customer_id']:
        change_points(db,audit,current['customer_id'],before-after,current['id'],'redeem_adjustment')
    else:
        if before: change_points(db,audit,old['customer_id'],before,current['id'],'return_points')
        if after: change_points(db,audit,current['customer_id'],-after,current['id'],'redeem')


def award_first_payment(db,audit,inv):
    if not inv['customer_id'] or inv['status']!='FINAL' or inv.get('deleted'): return
    customer=db.one('customers',{'id':inv['customer_id']})
    if not customer: return
    data=customer['data'];referrer=data.get('referred_by')
    if not referrer or data.get('referral_awarded_invoice'): return
    first=db.find('invoices',{'customer_id':customer['id'],'status':'FINAL','deleted':{'$ne':True}},sort=[('id',1)],limit=1)
    if not first or first[0]['id']!=inv['id'] or inv['total']<=0: return
    paid=sum(p['amount'] for p in db.find('payments',{'invoice_id':inv['id']}))
    if paid<inv['total']: return
    db.update('customers',{'id':customer['id']},{'data.referral_awarded_invoice':inv['id']})
    change_points(db,audit,referrer,1,inv['id'],'earn')


def manual_points(db,audit,customer,form):
    token=form.get('submission','')
    if len(token)!=64 or any(c not in '0123456789abcdef' for c in token):
        raise ValueError('Refresh the customer page before adding points.')
    if db.one('audit_events',{'entity':'referral','entity_id':customer['id'],'submission':token}): return
    if customer.get('archived'): raise ValueError('Choose an active customer.')
    try: points=int(form.get('points',''))
    except ValueError: raise ValueError('Enter a whole number of referral points.')
    if not 1<=points<=1000000: raise ValueError('Add between 1 and 1,000,000 referral points.')
    note=form.get('reason','').strip()
    if not note or len(note)>300: raise ValueError('Enter a reason of up to 300 characters.')
    event=change_points(db,audit,customer['id'],points,None,'manual_add',note)
    db.update('audit_events',{'id':event},{'submission':token})
