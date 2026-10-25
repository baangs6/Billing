"""Additive business profile and printing preferences; historical snapshots stay unchanged."""
from flask import flash, redirect, render_template, request, url_for

THEMES={'A4_LEDGER':'A4 clean invoice (default)','A5':'A5 compact','A4_CLASSIC':'A4 classic','A4_SIMPLE':'A4 simple','A4_ADVANCED':'A4 advanced','THERMAL_58':'2-inch thermal','THERMAL_80':'3-inch thermal'}
FIELDS={'city':'City','pan':'PAN','msme':'MSME / Udyam number','drug_licence':'Drug licence','website':'Website','additional_info':'Additional business information','industry':'Industry','registration_type':'Business registration type','accountant_email':'Accountant email','accountant_phone':'Accountant phone'}


BUSINESS_TYPES=('Retail','Wholesale','Distributor','Manufacturing','Service')
INDUSTRIES=('Agriculture','Automobiles','Battery','Broadband / Cable / Internet','Building materials','Clothing / Textiles','Education','Electronics','Food / Grocery','Furniture','Healthcare / Pharmacy','Hotels / Restaurants','Jewellery','Manufacturing','Professional services','Repair / Maintenance','Transport / Logistics','Other')
REGISTRATION_TYPES=('Private Limited Company','Public Limited Company','Partnership Firm','One Person Company (OPC)','Sole Proprietorship','Limited Liability Partnership (LLP)','Business Not Registered')


def custom_headers(form, previous):
    if 'headers_present' not in form: return previous
    names=form.getlist('header_name');values=form.getlist('header_value')
    if len(names)!=len(values) or len(names)>10: raise ValueError('Add at most 10 custom header fields.')
    result=[]
    for name,value in zip(names,values):
        name=name.strip();value=value.strip()
        if not name and not value: continue
        if not name or not value or len(name)>50 or len(value)>300: raise ValueError('Each header needs a name (up to 50 characters) and value (up to 300).')
        if name.casefold() in [row['name'].casefold() for row in result]: raise ValueError('Custom header names must be unique.')
        result.append(dict(name=name,value=value))
    return result


def header_fields(business):
    extra=business.get('extended',{})
    fields=[(label,extra[key]) for key,label in [('city','City'),('pan','PAN'),('msme','MSME'),('drug_licence','Drug licence'),('website','Website'),('additional_info','Additional information')] if extra.get(key)]
    return fields+[(row['name'],row['value']) for row in extra.get('custom_headers',[])]


def install_profile(app,db,audit,settings):
    @app.route('/business-profile',methods=['GET','POST'])
    def business_profile():
        values=settings();extra=dict(values.get('extended',{}))
        if request.method=='POST':
            extra.update({key:request.form.get(key,'').strip() for key in FIELDS})
            if extra['pan']:
                import re
                if not re.fullmatch(r'[A-Z]{5}[0-9]{4}[A-Z]',extra['pan']): raise ValueError('Enter PAN in uppercase format.')
            theme=request.form.get('invoice_theme','A4_LEDGER');payment=request.form.get('payment_details','BOTH');kind=request.form.get('business_type','Retail')
            if theme not in THEMES or payment not in ('BANK','UPI','BOTH') or kind not in BUSINESS_TYPES: raise ValueError('Choose valid profile options.')
            layout=request.form.get('thermal_layout','CLASSIC')
            if layout not in ('COMPACT','SIMPLE','CLASSIC','ADVANCED'): raise ValueError('Choose a valid thermal layout.')
            kinds=request.form.getlist('business_types') if 'types_present' in request.form else [kind]
            if not kinds or any(value not in BUSINESS_TYPES for value in kinds): raise ValueError('Choose at least one valid business type.')
            extra['business_types']=list(dict.fromkeys(kinds));kind=kinds[0]
            extra['custom_headers']=custom_headers(request.form,extra.get('custom_headers',[]))
            extra.update(invoice_theme=theme,payment_details=payment,business_type=kind,thermal_layout=layout)
            for key in ('show_description','show_time','show_gst_columns','show_previous_balance','show_qr','empty_signature_box'):
                extra[key]=request.form.get(key)=='1'
            registration=request.form.get('gst_registration')
            if registration is not None:
                if registration not in ('REGISTERED','UNREGISTERED'): raise ValueError('Choose GST registration status.')
                gstin=request.form.get('gstin','').strip()
                if registration=='REGISTERED':
                    from party_data import validate_gstin
                    validate_gstin(gstin)
                    values['gstin']=gstin
                else: values['gstin']=''
                extra['gst_registered']=registration=='REGISTERED'
            values['extended']=extra
            db().update('business_settings',{},dict(data=values));audit('save','printing_profile',0)
            flash('Business profile and print preferences saved. Existing invoice snapshots are unchanged.')
            return redirect(url_for('business_profile'))
        return render_template('business_profile.html',title='Business profile & printing',extra=extra,fields=FIELDS,themes=THEMES,gstin=values.get('gstin',''),business_types=BUSINESS_TYPES,industries=INDUSTRIES,registration_types=REGISTRATION_TYPES)
    return {'business_profile':('settings.manage','settings.manage')}
