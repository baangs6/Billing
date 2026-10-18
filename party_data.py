"""Party validation without making third-party GST lookup requests."""
import re


def validate_gstin(value):
    # Structural validation only; registration status requires an authorized provider.
    if not re.fullmatch(r'[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]',value):
        raise ValueError('GSTIN must contain 15 uppercase characters in the GSTIN format.')


def customer_fields(form,old,money):
    data=dict(old or {})
    for key in ('phone','email','address','gstin','state','pin','notes','shipping_address','pan','contact_person','category','bank'):
        if key in form: data[key]=form[key].strip()
        else: data.setdefault(key,'')
    if data['gstin']: validate_gstin(data['gstin'])
    if data['pan'] and not re.fullmatch(r'[A-Z]{5}[0-9]{4}[A-Z]',data['pan']): raise ValueError('Use a valid uppercase PAN format.')
    for key in ('credit_days',):
        if key in form:
            try: value=int(form[key] or '0')
            except ValueError: raise ValueError('Credit days must be a whole number.')
            if not 0<=value<=3650: raise ValueError('Credit days must be 0 to 3650.')
            data[key]=value
    if 'credit_limit' in form: data['credit_limit']=money(form['credit_limit'] or '0')
    if 'opening_balance' in form: data['opening_balance']=money(form['opening_balance'] or '0')*(-1 if form.get('opening_direction')=='PAY' else 1)
    return data
