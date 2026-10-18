from company_profile import header_fields
"""Tenant-scoped purchasing, supplier ledgers and quantity-linked purchase returns."""
import csv
import io
import json
import secrets
from datetime import date
from decimal import Decimal
from accounts import account_key
from product_units import line_units,line_pricing,primary_quantity,return_stock_quantity,rate_text
from flask import abort, flash, g, redirect, render_template, request, Response, url_for

METHODS=('Cash','UPI','Bank Transfer','Card','Cheque','Other')


def return_amounts(item,already,qty,interstate,rounded):
    def share(value):
        return rounded(Decimal(value)*(already+qty)/item['quantity'])-rounded(Decimal(value)*already/item['quantity'])
    taxable=share(item['taxable'])
    half=rounded(Decimal(item['tax'])/2)
    taxes=dict(cgst=0,sgst=0,igst=share(item['tax'])) if interstate else dict(cgst=share(half),sgst=share(item['tax']-half),igst=0)
    tax=sum(taxes.values())
    return dict(taxable=taxable,tax=tax,total=share(item['total']),**taxes)


def install_trade(app,db,owned,audit,money,quantity,calculate,rounded,today,settings,products,move,pdf):
    def text(key,required=False):
        value=request.form.get(key,'').strip()
        if required and not value: raise ValueError(key.replace('_',' ').title()+' is required.')
        return value

    def export(title,headers,rows):
        if request.args.get('export')=='pdf':
            if not g.access['features'].get('pdf'): abort(403)
            return Response(pdf(title,[[headers]+rows]),mimetype='application/pdf',headers={'Content-Disposition':'attachment; filename=statement.pdf'})
        output=io.StringIO();writer=csv.writer(output);writer.writerow(headers)
        writer.writerows([["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in row] for row in rows])
        return Response('\ufeff'+output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=statement.csv'})

    def settlement_totals():
        from collections import defaultdict
        amounts=defaultdict(lambda:dict(paid=0,credit=0));openings=defaultdict(int)
        for note in db().find('trade_returns',projection={'purchase_id':1,'total':1}): amounts[note['purchase_id']]['credit']+=note['total']
        for payment in db().find('trade_payments'):
            if payment.get('opening_effect') and payment.get('supplier_id'): openings[payment['supplier_id']]+=payment['opening_effect']
            if payment.get('purchase_id') and payment['kind'] in ('PAYMENT_OUT','SUPPLIER_REFUND'): amounts[payment['purchase_id']]['paid']+=payment['amount']*(1 if payment['kind']=='PAYMENT_OUT' else -1)
        return amounts,openings

    def totals(document,amounts=None):
        if amounts is None: amounts,_=settlement_totals()
        values=amounts[document['id']]
        return dict(document,**values,balance=document['total']-values['credit']-values['paid'])

    def suppliers_list():
        rows=db().find('suppliers',sort=[('name',1)]);amounts,openings=settlement_totals()
        balances={row['id']:row['data'].get('opening_balance',0)+openings[row['id']] for row in rows}
        for document in db().find('purchases',{'status':'FINAL'},projection={'id':1,'supplier_id':1,'total':1}):
            ident=document['supplier_id'];balances[ident]=balances.get(ident,0)+totals(document,amounts)['balance']
        for row in rows: row['balance']=balances[row['id']]
        return rows

    @app.route('/party-import',methods=['GET','POST'])
    def party_import():
        target=request.values.get('target','customers')
        if target not in ('customers','suppliers'): raise ValueError('Choose Customers or Suppliers.')
        permission='customer.manage' if target=='customers' else 'supplier.manage'
        if permission not in g.access['permissions']: abort(403)
        columns=('name','phone','email','address','shipping_address','state','pin','gstin','pan','contact_person','category','bank','notes')
        if request.method=='POST':
            token=text('submission')
            if len(token)!=64: raise ValueError('Refresh before importing.')
            if db().one('party_imports',{'submission':token}): return redirect('/'+target)
            from product_import import read_products
            from party_data import validate_gstin
            records=read_products(request.files.get('file'),columns=columns,required=('name',),maximum=4000)
            prepared=[];errors=[]
            for number,row in records:
                name=row.get('name','').strip()
                if not name or len(name)>150: errors.append(f'Row {number}: name must be 1 to 150 characters.');continue
                try:
                    if row.get('gstin'): validate_gstin(row['gstin'])
                except ValueError as error: errors.append(f'Row {number}: {error}');continue
                prepared.append(dict(name=name,data={k:row.get(k,'') for k in columns if k!='name'},archived=False))
            if errors: return render_template('party_import.html',title='Import parties',target=target,errors=errors,submission=secrets.token_hex(32)),422
            ids=db().insert_many(target,prepared);db().insert('party_imports',dict(target=target,date=today(),submission=token,count=len(ids)));audit('import',target,0,str(len(ids))+' records; validated batches of 200.')
            flash(str(len(ids))+' parties imported.');return redirect('/'+target)
        if request.args.get('template'):
            return export('Party import',list(columns),[])
        return render_template('party_import.html',title='Import parties',target=target,errors=[],submission=secrets.token_hex(32))

    @app.route('/suppliers',methods=['GET','POST'])
    def suppliers_page():
        if request.method=='POST':
            ident=request.form.get('id');old=owned('suppliers',ident) if ident else None
            if text('action')=='archive':
                if not old: abort(404)
                db().update('suppliers',{'id':old['id']},{'archived':True});audit('archive','supplier',old['id'])
            else:
                data={key:text(key) for key in ('phone','email','address','shipping_address','state','pin','gstin','pan','contact_person','category','bank','notes')}
                if data['gstin']:
                    from party_data import validate_gstin
                    validate_gstin(data['gstin'])
                data['opening_balance']=money(text('opening_balance') or '0')*(-1 if text('opening_direction')=='COLLECT' else 1)
                data['credit_limit']=money(text('credit_limit') or '0')
                try: data['credit_days']=int(text('credit_days') or '0')
                except ValueError: raise ValueError('Credit days must be a whole number.')
                if not 0<=data['credit_days']<=3650: raise ValueError('Credit days must be 0 to 3650.')
                if old and data['opening_balance']!=old['data'].get('opening_balance',0) and (db().count('purchases',{'supplier_id':old['id']}) or db().count('trade_payments',{'supplier_id':old['id']})): raise ValueError('Opening balance cannot change after purchase history exists.')
                values=dict(name=text('name',True),data=data,archived=False)
                if old: db().update('suppliers',{'id':old['id']},values)
                else: ident=db().insert('suppliers',values)
                audit('save','supplier',int(ident))
            return redirect(url_for('suppliers_page'))
        rows=suppliers_list();query=request.args.get('q','').casefold()
        rows=[r for r in rows if (not r.get('archived') or request.args.get('archived')=='1') and query in (r['name']+' '+r['data'].get('phone','')).casefold()]
        if request.args.get('export'):
            if 'report.export' not in g.access['permissions']: abort(403)
            return export('Suppliers',['Supplier','Phone','GSTIN','Balance payable INR'],[[r['name'],r['data'].get('phone',''),r['data'].get('gstin',''),f"{Decimal(r['balance'])/100:.2f}"] for r in rows])
        return render_template('suppliers.html',title='Suppliers',rows=rows,edit=owned('suppliers',request.args['edit']) if request.args.get('edit') else None)

    def prepare_items():
        try: raw=json.loads(request.form.get('items','[]'))
        except json.JSONDecodeError: raise ValueError('Invalid purchase items.')
        if not isinstance(raw,list) or not 1<=len(raw)<=200: raise ValueError('Add between 1 and 200 items.')
        items=[];rates=[Decimal(r) for r in settings()['gst_rates'].split(',')]
        for item in raw:
            if not isinstance(item,dict): raise ValueError('Invalid purchase item.')
            product=owned('products',item.get('product_id')) if item.get('product_id') else None
            if product and not product['active']: raise ValueError('Choose an active product.')
            name=str(item.get('name','')).strip();hsn=str(item.get('hsn',''))
            if not name or len(name)>150 or len(hsn)>30: raise ValueError('Use an item name under 150 characters and HSN under 30.')
            rate=Decimal(str(item.get('gst','0')))
            if not rate.is_finite() or rate not in rates: raise ValueError('Choose a configured GST rate.')
            unit_price=money(item.get('rate','0'))
            items.append(dict(product_id=product['id'] if product else None,name=name,hsn=hsn,unit=product['data']['unit'] if product else 'PCS',quantity=quantity(item.get('quantity','0')),rate=unit_price,discount=money(item.get('discount','0')),gst=str(rate),mrp=0))
            if 'order_line' in item:
                try: items[-1]['order_line']=int(item['order_line'])
                except (ValueError,TypeError): raise ValueError('Invalid source order line.')
            original=None
            if request.form.get('order_id'):
                source=owned('purchase_orders',request.form['order_id'])
                index=items[-1].get('order_line')
                if index is None:
                    matches=[i for i,line in enumerate(source['items']) if line['product_id']==items[-1]['product_id']]
                    if len(matches)==1: index=matches[0];items[-1]['order_line']=index
                if index is not None and 0<=index<len(source['items']): original=source['items'][index]
            units=line_units(item,product,quantity,original)
            items[-1].update(units)
            items[-1].update(line_pricing(dict(item,pricing_mode=request.form.get('pricing') or 'EXCLUSIVE'),product,units,request.form.get('type'),money,rounded))
        return items

    @app.route('/purchases',methods=['GET','POST'])
    def purchases_page():
        order_mode=request.args.get('orders')=='1';collection='purchase_orders' if order_mode else 'purchases'
        if request.method=='POST':
            token=text('submission')
            if len(token)!=64: raise ValueError('Refresh before saving.')
            if db().one(collection,{'submission':token}): return redirect(url_for('purchases_page',orders='1' if order_mode else None))
            supplier=owned('suppliers',text('supplier',True))
            if supplier.get('archived'): raise ValueError('Choose an active supplier.')
            day=date.fromisoformat(text('date',True)).isoformat()
            kind=text('type')
            if kind not in ('GST','NON-GST'): raise ValueError('Choose GST or Non-GST.')
            if kind=='GST' and not g.access['features'].get('gst'): abort(403)
            if kind=='GST' and not settings().get('gstin'): raise ValueError('Register the business GSTIN before creating a GST purchase.')
            if kind=='GST' and not supplier['data'].get('state','').strip(): raise ValueError('Enter the supplier state before recording a GST purchase.')
            if not order_mode and not g.access['features'].get('inventory'): abort(403)
            pricing=text('pricing') or 'EXCLUSIVE'
            if pricing not in ('INCLUSIVE','EXCLUSIVE'): raise ValueError('Choose inclusive or exclusive prices.')
            items=prepare_items();source=None
            if text('order_id'):
                source=owned('purchase_orders',text('order_id'))
                if order_mode or source['supplier_id']!=supplier['id'] or source['status']!='OPEN': raise ValueError('Choose an open order for this supplier.')
                receipts=db().find('purchases',{'order_id':source['id'],'status':'FINAL'})
                for item in items:
                    if 'order_line' not in item:
                        matches=[i for i,line in enumerate(source['items']) if line['product_id']==item['product_id']]
                        if len(matches)!=1: raise ValueError('Select the source order line for this receipt.')
                        item['order_line']=matches[0]
                    index=item['order_line']
                    if not 0<=index<len(source['items']) or source['items'][index]['product_id']!=item['product_id']: raise ValueError('Receipt item does not match its source order line.')
                    original=source['items'][index]
                    if item.get('unit_choice','PRIMARY')!=original.get('unit_choice','PRIMARY'): raise ValueError('Receive in the original order unit.')
                    item.update(stock_quantity=return_stock_quantity(original,item['quantity']),unit=original['unit'],unit_factor=original.get('unit_factor','1'),is_service=original.get('is_service',False))
                for index,line in enumerate(source['items']):
                    received=sum(i['quantity'] for receipt in receipts for i in receipt['items'] if i.get('order_line')==index)
                    current=sum(i['quantity'] for i in items if i['order_line']==index)
                    if received+current>line['quantity']: raise ValueError('Receipt exceeds the remaining order quantity.')
            result=calculate(items,kind,settings()['state'].strip().casefold()!=supplier['data'].get('state','').strip().casefold(),common_discount=money(text('common_discount') or '0'),round_total=text('round_total')=='1')
            if result['total']>9_000_000_000_000_000: raise ValueError('Purchase total exceeds the supported financial limit.')
            number=text('supplier_number',not order_mode)
            if not order_mode and db().one('purchases',{'supplier_id':supplier['id'],'supplier_number':number,'status':'FINAL'}): raise ValueError('This supplier invoice number already exists.')
            doc=dict(supplier_id=supplier['id'],supplier_number=number,date=day,type=kind,pricing=pricing if kind=='GST' else 'EXCLUSIVE',status='OPEN' if order_mode else 'FINAL',items=items,snapshot=dict(supplier=supplier,business=settings()),submission=token,notes=text('notes'),order_id=source['id'] if source else None,**result)
            ident=db().insert(collection,doc)
            if not order_mode:
                for item in items:
                    if item['product_id'] and primary_quantity(item): move(item['product_id'],primary_quantity(item),'Purchase #'+str(ident))
                paid=money(text('paid') or '0')
                if paid>doc['total']: raise ValueError('Payment exceeds the purchase total.')
                limit=supplier['data'].get('credit_limit',0)
                amounts,_=settlement_totals()
                outstanding=supplier['data'].get('opening_balance',0)+sum(p.get('opening_effect',0) for p in db().find('trade_payments',{'supplier_id':supplier['id']}))+sum(totals(p,amounts)['balance'] for p in db().find('purchases',{'supplier_id':supplier['id'],'status':'FINAL','id':{'$ne':ident}}))
                if limit and outstanding+doc['total']-paid>limit: raise ValueError('This purchase would exceed the supplier credit limit.')
                if paid: record_payment(doc|dict(id=ident),'PAYMENT_OUT',paid,day,text('method') or 'Cash',token)
            if source:
                received_documents=db().find('purchases',{'order_id':source['id'],'status':'FINAL'})
                if all(sum(item['quantity'] for receipt in received_documents for item in receipt['items'] if item.get('order_line')==index)==line['quantity'] for index,line in enumerate(source['items'])): db().update('purchase_orders',{'id':source['id']},{'status':'RECEIVED'})
            audit('create',collection,ident);flash('Purchase order saved.' if order_mode else 'Purchase posted and stock received.')
            return redirect(url_for('purchase_detail',ident=ident,orders='1' if order_mode else None))
        amounts,_=settlement_totals()
        documents=[totals(p,amounts) if not order_mode else p for p in db().find(collection,sort=[('date',-1),('id',-1)])]
        source=owned('purchase_orders',request.args['receive']) if request.args.get('receive') else None
        if source:
            receipts=db().find('purchases',{'order_id':source['id'],'status':'FINAL'})
            source['items']=[dict(line,order_line=index,quantity=line['quantity']-sum(item['quantity'] for receipt in receipts for item in receipt['items'] if item.get('order_line')==index)) for index,line in enumerate(source['items'])]
            source['items']=[line for line in source['items'] if line['quantity']>0]
        return render_template('purchases.html',title='Purchase orders' if order_mode else 'Purchases',orders=order_mode,documents=documents,suppliers=[s for s in suppliers_list() if not s.get('archived')],products=products(),source=source,submission=secrets.token_hex(32),methods=METHODS)

    def record_payment(document,kind,amount,day,method,token):
        if method not in METHODS or not amount: raise ValueError('Choose a method and positive amount.')
        ledger=account_key(db(),request.form.get('ledger_account'),'Cash' if method=='Cash' else 'Other' if method=='Other' else 'Bank',day)
        db().insert('trade_payments',dict(ledger_account=ledger,purchase_id=document['id'],supplier_id=document['supplier_id'],kind=kind,amount=amount,date=day,method=method,reference=text('reference'),submission=token))

    @app.route('/purchases/<int:ident>',methods=['GET','POST'])
    def purchase_detail(ident):
        order_mode=request.args.get('orders')=='1';collection='purchase_orders' if order_mode else 'purchases'
        document=owned(collection,ident)
        if request.method=='POST':
            action=text('action');token=text('submission');day=date.fromisoformat(text('date',True)).isoformat()
            if len(token)!=64: raise ValueError('Refresh before saving.')
            if document['status'] not in ('OPEN','FINAL'): raise ValueError('Document is closed.')
            if order_mode:
                if action!='close': raise ValueError('Invalid order action.')
                db().update(collection,{'id':ident},{'status':'CLOSED'});audit('close',collection,ident)
            elif action in ('PAYMENT_OUT','SUPPLIER_REFUND'):
                if db().one('trade_payments',{'submission':token}): return redirect(url_for('purchase_detail',ident=ident))
                amount=money(text('amount',True));balance=totals(document)['balance']
                available=balance if action=='PAYMENT_OUT' else -balance
                if amount>available: raise ValueError('Amount exceeds the available payable or supplier credit.')
                record_payment(document,action,amount,day,text('method'),token);audit(action,'purchase',ident)
            elif action=='return':
                if not g.access['features'].get('inventory') or 'return.manage' not in g.access['permissions']: abort(403)
                if db().one('trade_returns',{'submission':token}): return redirect(url_for('purchase_detail',ident=ident))
                previous=db().find('trade_returns',{'purchase_id':ident});lines=[]
                for index,item in enumerate(document['items']):
                    qty=quantity(request.form.get('quantity_'+str(index)) or '0',allow_zero=True)
                    if not qty: continue
                    already=sum(line['quantity'] for r in previous for line in r['items'] if line['line']==index)
                    if already+qty>item['quantity']: raise ValueError('Return exceeds the unreturned purchased quantity.')
                    values=return_amounts(item,already,qty,document['snapshot']['business']['state'].casefold()!=document['snapshot']['supplier']['data'].get('state','').casefold(),rounded)
                    lines.append(dict(line=index,quantity=qty,**values))
                    if item['product_id'] and primary_quantity(item): move(item['product_id'],-return_stock_quantity(item,qty),'Purchase return #'+str(ident))
                if not lines: raise ValueError('Enter at least one return quantity.')
                total=sum(line['total'] for line in lines)
                returned=sum(r['total'] for r in previous)
                complete=all(sum(line['quantity'] for r in previous for line in r['items'] if line['line']==i)+sum(line['quantity'] for line in lines if line['line']==i)==item['quantity'] for i,item in enumerate(document['items']))
                if complete: total=document['total']-returned
                if returned+total>document['total']: total=document['total']-returned
                rid=db().insert('trade_returns',dict(purchase_id=ident,supplier_id=document['supplier_id'],date=day,items=lines,total=total,round_off=total-sum(line['taxable']+line['tax'] for line in lines),reason=text('reason',True),submission=token))
                audit('return','purchase',ident,str(rid));flash('Purchase return posted as a supplier debit note.')
            else: raise ValueError('Invalid purchase action.')
            return redirect(url_for('purchase_detail',ident=ident,orders='1' if order_mode else None))
        doc=document if order_mode else totals(document)
        payments=db().find('trade_payments',{'purchase_id':ident},sort=[('date',1)]) if not order_mode else []
        returns=db().find('trade_returns',{'purchase_id':ident}) if not order_mode else []
        if request.args.get('export'):
            if not g.access['features'].get('pdf'): abort(403)
            rows=[['Item','Quantity','Rate INR','GST %','Amount INR']]+[[i['name'],Decimal(i['quantity'])/1000,rate_text(i),i['gst'] if document['type']=='GST' else '—',Decimal(i['total'])/100] for i in document['items']]
            business=document['snapshot']['business'];extra=business.get('extended',{})
            contents=([('image',business['logo'])] if business.get('logo') else [])+[business['name'],business.get('address',''),' · '.join(str(business.get(key,'')) for key in ('state','pin','phone','email') if business.get(key)),*(['GSTIN: '+business['gstin']] if business.get('gstin') and document['type']=='GST' else []),*[label+': '+value for label,value in header_fields(business)],document['snapshot']['supplier']['name'],document['supplier_number'],document['date'],'Rates '+('include GST' if document.get('pricing')=='INCLUSIVE' else 'exclude GST'),rows,'Total INR '+f"{Decimal(document['total'])/100:.2f}",document['notes']]
            if business.get('signature'): contents.append(('image',business['signature']))
            elif extra.get('empty_signature_box'): contents.append(('signature_box',True))
            return Response(pdf('Purchase order' if order_mode else 'Supplier purchase invoice',contents),mimetype='application/pdf',headers={'Content-Disposition':'attachment; filename=purchase.pdf'})
        return render_template('purchase_detail.html',title='Purchase order' if order_mode else 'Purchase details',doc=doc,orders=order_mode,payments=payments,returns=returns,submission=secrets.token_hex(32),methods=METHODS)

    @app.post('/parties/<party_kind>/<int:ident>/opening-payment')
    def opening_payment(party_kind,ident):
        if party_kind not in ('customers','suppliers'): abort(404)
        if ('payment.record' if party_kind=='customers' else 'purchase.manage') not in g.access['permissions']: abort(403)
        party=owned(party_kind,ident);field='customer_id' if party_kind=='customers' else 'supplier_id'
        token=text('submission');day=date.fromisoformat(text('date',True)).isoformat()
        if len(token)!=64: raise ValueError('Refresh before recording a payment.')
        if db().one('trade_payments',{'submission':token}): return redirect(url_for('customer_ledger' if party_kind=='customers' else 'supplier_ledger',ident=ident))
        remaining=party['data'].get('opening_balance',0)+sum(p.get('opening_effect',0) for p in db().find('trade_payments',{field:ident}))
        amount=money(text('amount',True));method=text('method')
        if not 0<amount<=abs(remaining) or method not in METHODS: raise ValueError('Amount exceeds the remaining opening balance or payment method is invalid.')
        incoming=(remaining>0)==(party_kind=='customers')
        ledger=account_key(db(),request.form.get('ledger_account'),'Cash' if method=='Cash' else 'Other' if method=='Other' else 'Bank',day)
        pid=db().insert('trade_payments',dict({field:ident},kind='OPENING_IN' if incoming else 'OPENING_OUT',opening_effect=-amount if remaining>0 else amount,amount=amount,method=method,date=day,reference=text('reference'),ledger_account=ledger,submission=token))
        audit('opening_settlement',party_kind,ident,str(pid))
        return redirect(url_for('customer_ledger' if party_kind=='customers' else 'supplier_ledger',ident=ident))

    @app.get('/suppliers/<int:ident>/ledger')
    def supplier_ledger(ident):
        supplier=owned('suppliers',ident);rows=[]
        opening=supplier['data'].get('opening_balance',0)
        rows.append(dict(date='',title='Opening balance',amount=opening))
        for p in db().find('purchases',{'supplier_id':ident,'status':'FINAL'}): rows.append(dict(date=p['date'],title='Purchase '+p['supplier_number'],amount=p['total']))
        for r in db().find('trade_returns',{'supplier_id':ident}): rows.append(dict(date=r['date'],title='Debit note #'+str(r['id']),amount=-r['total']))
        for p in db().find('trade_payments',{'supplier_id':ident}): rows.append(dict(date=p['date'],title=p['kind']+' · '+p['method'],amount=p.get('opening_effect',p['amount']*(-1 if p['kind']=='PAYMENT_OUT' else 1))))
        balance=0
        for row in sorted(rows,key=lambda r:r['date']): balance+=row['amount'];row['balance']=balance
        rows=sorted(rows,key=lambda r:r['date'])
        if request.args.get('export'):
            if 'report.export' not in g.access['permissions']: abort(403)
            return export('Supplier ledger: '+supplier['name'],['Date','Entry','Change payable INR','Balance payable INR'],[[r['date'],r['title'],f"{Decimal(r['amount'])/100:.2f}",f"{Decimal(r['balance'])/100:.2f}"] for r in rows])
        return render_template('supplier_ledger.html',title='Supplier ledger',supplier=supplier,rows=rows,submission=secrets.token_hex(32),methods=METHODS)

    @app.get('/notes/<note_kind>/<int:ident>/pdf')
    def note_pdf(note_kind,ident):
        if note_kind not in ('sales','purchase'): abort(404)
        sales=note_kind=='sales'
        if ('invoice.view' if sales else 'purchase.view') not in g.access['permissions'] or not g.access['features'].get('pdf'): abort(403)
        note=owned('sales_returns' if sales else 'trade_returns',ident)
        original=owned('invoices' if sales else 'purchases',note['invoice_id'] if sales else note['purchase_id'])
        original_items=db().find('invoice_items',{'invoice_id':original['id']}) if sales else original['items']
        rows=[['Item','Qty','Taxable INR','Tax INR','Credit INR']]
        for line in note['items']:
            name=line['name'] if sales else original_items[line['line']]['name']
            rows.append([name,f"{Decimal(line['quantity'])/1000:g}",f"{Decimal(line['taxable'])/100:.2f}",f"{Decimal(line['tax'])/100:.2f}",f"{Decimal((line['taxable']+line['tax']))/100:.2f}"])
        snapshot=original['snapshot'];party=snapshot['customer'] if sales else snapshot['supplier']
        business=snapshot['business']
        contents=([('image',business['logo'])] if business.get('logo') else [])+[business['name'],business.get('address',''),' · '.join(str(business.get(key,'')) for key in ('state','pin','phone','email') if business.get(key)),*(['GSTIN: '+business['gstin']] if business.get('gstin') and original['type']=='GST' else []),*[label+': '+value for label,value in header_fields(business)],party['name'],'Original document: '+str(original.get('number',original.get('supplier_number'))),'Note #'+str(ident)+' / '+note['date'],rows,'Round off INR '+f"{Decimal(note.get('round_off',0))/100:.2f}",'Total credit INR '+f"{Decimal(note['total'])/100:.2f}",note['reason']]
        if business.get('signature'): contents.append(('image',business['signature']))
        elif business.get('extended',{}).get('empty_signature_box'): contents.append(('signature_box',True))
        return Response(pdf('Sales credit note' if sales else 'Purchase debit note',contents),mimetype='application/pdf',headers={'Content-Disposition':f'attachment; filename=note-{ident}.pdf'})

    @app.post('/documents/<int:ident>/dispatch')
    def document_dispatch(ident):
        document=owned('proposals',ident)
        if document.get('document_kind')!='CHALLAN' or document.get('invoice_id'): raise ValueError('Choose an unconverted delivery challan.')
        if not g.access['features'].get('inventory') or g.access['company'].get('inventory_reconciliation_required'): raise ValueError('Enable and reconcile inventory before dispatch.')
        action=text('action')
        if action not in ('dispatch','cancel'): raise ValueError('Choose a dispatch action.')
        dispatched=bool(document.get('stock_dispatched'))
        desired=action=='dispatch'
        if desired!=dispatched:
            for item in document['items']:
                if item.get('product_id') and primary_quantity(item): move(item['product_id'],primary_quantity(item)*(-1 if desired else 1),('Challan dispatch #' if desired else 'Challan cancellation #')+str(ident))
            db().update('proposals',{'id':ident},dict(stock_dispatched=desired,status='ACCEPTED' if desired else 'DRAFT'),inc={'version':1})
            audit(action,'challan',ident)
        return redirect(url_for('view_proposal',ident=ident))

    @app.route('/sales-returns',methods=['GET','POST'])
    def sales_returns_page():
        ident=request.values.get('invoice')
        inv=owned('invoices',ident) if ident else None
        items=db().find('invoice_items',{'invoice_id':inv['id']},sort=[('id',1)]) if inv else []
        if request.method=='POST':
            if not inv or inv['status']!='FINAL' or inv.get('deleted'): raise ValueError('Choose a final invoice.')
            token=text('submission');day=date.fromisoformat(text('date',True)).isoformat()
            if len(token)!=64: raise ValueError('Refresh before posting.')
            previous=db().find('sales_returns',{'invoice_id':inv['id']})
            if text('action')=='refund':
                if db().one('trade_payments',{'submission':token}): return redirect(url_for('sales_returns_page',invoice=ident))
                credited=sum(r['total'] for r in previous)
                received=sum(p['amount'] for p in db().find('payments',{'invoice_id':inv['id']}))
                refunded=sum(p['amount'] for p in db().find('trade_payments',{'invoice_id':inv['id'],'kind':'CUSTOMER_REFUND'}))
                available=credited+received-inv['total']-refunded;amount=money(text('amount',True));method=text('method')
                if not 0<amount<=available or method not in METHODS: raise ValueError('Refund exceeds the customer credit or payment method is invalid.')
                ledger=account_key(db(),request.form.get('ledger_account'),'Cash' if method=='Cash' else 'Other' if method=='Other' else 'Bank',day)
                pid=db().insert('trade_payments',dict(ledger_account=ledger,invoice_id=inv['id'],customer_id=inv['customer_id'],date=day,amount=amount,method=method,kind='CUSTOMER_REFUND',reference=text('reference'),submission=token))
                audit('refund','invoice',inv['id'],str(pid))
            else:
                if db().one('sales_returns',{'submission':token}): return redirect(url_for('sales_returns_page',invoice=ident))
                lines=[]
                for index,item in enumerate(items):
                    qty=quantity(request.form.get('quantity_'+str(index)) or '0',allow_zero=True)
                    if not qty: continue
                    already=sum(line['quantity'] for r in previous for line in r['items'] if line['item_id']==item['id'])
                    if already+qty>item['quantity']: raise ValueError('Return quantity exceeds the quantity still available on the original invoice.')
                    values=return_amounts(item,already,qty,inv['snapshot']['business']['state'].casefold()!=inv['snapshot']['customer']['data'].get('state','').casefold(),rounded)
                    lines.append(dict(item_id=item['id'],product_id=item.get('product_id'),name=item['name'],hsn=item.get('hsn',''),gst=item['gst'],quantity=qty,**values))
                    if item.get('product_id') and primary_quantity(item):
                        if not g.access['features'].get('inventory'): abort(403)
                        move(item['product_id'],return_stock_quantity(item,qty),'Sales return invoice #'+str(inv['id']),inv['id'])
                if not lines: raise ValueError('Enter a return quantity.')
                total=sum(line['total'] for line in lines);credited=sum(r['total'] for r in previous)
                complete=all(sum(line['quantity'] for r in previous for line in r['items'] if line['item_id']==item['id'])+sum(line['quantity'] for line in lines if line['item_id']==item['id'])==item['quantity'] for item in items)
                if complete: total=inv['total']-credited
                total=min(total,inv['total']-credited)
                rid=db().insert('sales_returns',dict(invoice_id=inv['id'],customer_id=inv['customer_id'],date=day,items=lines,total=total,round_off=total-sum(line['taxable']+line['tax'] for line in lines),reason=text('reason',True),snapshot=inv['snapshot'],submission=token))
                audit('credit_note','invoice',inv['id'],str(rid))
            flash('Customer return / refund recorded.');return redirect(url_for('sales_returns_page',invoice=ident))
        documents=db().find('invoices',{'status':'FINAL','deleted':{'$ne':True}},sort=[('date',-1)])
        notes=db().find('sales_returns',{'invoice_id':inv['id']} if inv else {},sort=[('date',-1)])
        refunds=db().find('trade_payments',{'invoice_id':inv['id'],'kind':'CUSTOMER_REFUND'}) if inv else []
        if request.args.get('export'):
            if not g.access['features'].get('pdf') or 'report.export' not in g.access['permissions']: abort(403)
            rows=[['Credit note','Date','Invoice','Amount INR','Reason']]+[[str(n['id']),n['date'],str(n['invoice_id']),f"{Decimal(n['total'])/100:.2f}",n['reason']] for n in notes]
            return Response(pdf('Sales credit notes',[rows]),mimetype='application/pdf',headers={'Content-Disposition':'attachment; filename=credit-notes.pdf'})
        return render_template('sales_returns.html',title='Sales returns & credit notes',inv=inv,items=items,documents=documents,notes=notes,refunds=refunds,submission=secrets.token_hex(32),methods=METHODS)

    @app.get('/customers/<int:ident>/ledger')
    def customer_ledger(ident):
        customer=owned('customers',ident);rows=[dict(date='',title='Opening balance',amount=customer['data'].get('opening_balance',0))]
        invoices=db().find('invoices',{'customer_id':ident,'status':'FINAL','deleted':{'$ne':True}});ids=[i['id'] for i in invoices]
        for inv in invoices: rows.append(dict(date=inv['date'],title=inv['number'],amount=inv['total']))
        for pay in db().find('payments',{'invoice_id':{'$in':ids}}): rows.append(dict(date=pay['date'],title='Receipt · '+pay['method'],amount=-pay['amount']))
        for note in db().find('sales_returns',{'customer_id':ident}): rows.append(dict(date=note['date'],title='Credit note #'+str(note['id']),amount=-note['total']))
        for pay in db().find('trade_payments',{'customer_id':ident,'kind':'CUSTOMER_REFUND'}): rows.append(dict(date=pay['date'],title='Customer refund',amount=pay['amount']))
        for pay in db().find('trade_payments',{'customer_id':ident,'opening_effect':{'$exists':True}}): rows.append(dict(date=pay['date'],title='Opening balance settlement',amount=pay['opening_effect']))
        rows.sort(key=lambda r:r['date']);balance=0
        for row in rows: balance+=row['amount'];row['balance']=balance
        if request.args.get('export'):
            if 'report.export' not in g.access['permissions']: abort(403)
            return export('Customer ledger: '+customer['name'],['Date','Entry','Change receivable INR','Balance receivable INR'],[[r['date'],r['title'],f"{Decimal(r['amount'])/100:.2f}",f"{Decimal(r['balance'])/100:.2f}"] for r in rows])
        return render_template('supplier_ledger.html',title='Customer ledger',supplier=customer,rows=rows,customer_ledger=True,submission=secrets.token_hex(32),methods=METHODS)

    return {'note_pdf':('invoice.view',None),'opening_payment':('payment.view','payment.record'),'document_dispatch':('invoice.view','invoice.edit'),'sales_returns_page':('invoice.view','return.manage'),'customer_ledger':('customer.view',None),'party_import':('customer.view','customer.manage'),'suppliers_page':('supplier.view','supplier.manage'),'supplier_ledger':('supplier.view',None),'purchases_page':('purchase.view','purchase.manage'),'purchase_detail':('purchase.view','purchase.manage')}
