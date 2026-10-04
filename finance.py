"""Cash movement tracking: manual entries plus existing invoice receipts."""
import calendar
import csv
import io
import json
import secrets
from datetime import date
from pathlib import Path
from flask import request, session, g, abort, flash, redirect, url_for, render_template, Response
from PIL import Image

ACCOUNTS=('Cash','Bank','Other')
METHODS=('Cash','UPI','Bank Transfer','Card','Cheque','Other')
CATEGORIES=('Purchases','Rent','Salaries','Transport','Electricity','Office expenses','Marketing','Maintenance','Other expenses','Other income','Interest','Opening balance')

def install_finance(app, db, owned, audit, money, today, payment_rows, pdf_document):
    def receipt(upload):
        if not upload or not upload.filename: return None
        upload.stream.seek(0); content=upload.stream.read(1024*1024+1)
        if len(content)>1024*1024: raise ValueError('Receipt must be under 1 MB.')
        suffix=Path(upload.filename).suffix.lower()
        if suffix=='.pdf' and content.startswith(b'%PDF-'):
            return dict(data=content,mime='application/pdf',filename='receipt.pdf')
        if suffix in ('.png','.jpg','.jpeg'):
            try:
                image=Image.open(io.BytesIO(content))
                if image.width*image.height>20_000_000: raise ValueError('Receipt image is too large.')
                image.verify()
                image=Image.open(io.BytesIO(content)); image.thumbnail((1600,1600))
                output=io.BytesIO(); image.convert('RGB').save(output,format='JPEG',quality=85)
                return dict(data=output.getvalue(),mime='image/jpeg',filename='receipt.jpg')
            except Exception as error: raise ValueError('Upload a valid PNG or JPEG receipt (at most 20 megapixels).') from error
        raise ValueError('Receipt must be a PDF, PNG or JPEG.')

    def movements():
        rows=[]
        for entry in db().find('finance_entries',{'status':'ACTIVE'},projection={'receipt.data':0}):
            rows.append(dict(entry,source='Manual',invoice_id=None))
        for payment in payment_rows():
            rows.append(dict(id=payment['id'],date=payment['date'],kind='INCOME',category='Invoice collections',title=payment['number']+' · '+payment['customer'],amount=payment['amount'],account='Cash' if payment['method']=='Cash' else 'Other' if payment['method']=='Other' else 'Bank',method=payment['method'],notes=payment.get('notes',''),reference=payment.get('reference',''),source='Invoice payment',invoice_id=payment['invoice_id'],receipt=None))
        return sorted(rows,key=lambda row:(row['date'],row['id']),reverse=True)

    @app.route('/finance',methods=['GET','POST'])
    def finance_page():
        if request.method=='POST':
            ident=request.form.get('id'); previous=owned('finance_entries',ident) if ident else None
            if previous and previous['status']!='ACTIVE': raise ValueError('Voided entries cannot be changed.')
            if previous and str(previous['version'])!=request.form.get('version'): raise ValueError('This entry changed. Refresh Finance before editing.')
            if request.form.get('action')=='void':
                if not previous: raise ValueError('Choose an entry to void.')
                db().update('finance_entries',{'id':previous['id']},{'status':'VOID'},inc={'version':1})
                audit('void','finance',previous['id']); flash('Entry voided. It remains in the audit trail.')
                return redirect(url_for('finance_page'))
            if not previous:
                token=request.form.get('submission','')
                if len(token)!=64: raise ValueError('Refresh Finance before saving.')
                if db().one('finance_entries',{'submission':token}): return redirect(url_for('finance_page'))
            kind=request.form.get('kind'); account=request.form.get('account'); method=request.form.get('method')
            if kind not in ('INCOME','EXPENSE','OPENING') or account not in ACCOUNTS or method not in METHODS: raise ValueError('Choose a valid entry type, account and payment method.')
            day=date.fromisoformat(request.form.get('date','')).isoformat()
            title=request.form.get('title','').strip(); category=request.form.get('category','').strip()
            if not title or not category: raise ValueError('Title and category are required.')
            if category.casefold()=='invoice collections': raise ValueError('Invoice collections are added automatically. Record invoice payments on the Payments page.')
            amount=money(request.form.get('amount',''))
            if amount<=0 and kind!='OPENING': raise ValueError('Income and expense amounts must be greater than zero.')
            if kind=='OPENING':
                existing=db().one('finance_entries',{'kind':'OPENING','account':account,'status':'ACTIVE'})
                if existing and (not previous or existing['id']!=previous['id']): raise ValueError('This account already has an opening balance. Edit that entry instead.')
            attachment=receipt(request.files.get('receipt'))
            values=dict(date=day,kind=kind,category=category,title=title,amount=amount,account=account,method=method,notes=request.form.get('notes','').strip(),reference=request.form.get('reference','').strip())
            if attachment: values['receipt']=attachment
            elif request.form.get('remove_receipt'): values['receipt']=None
            if previous:
                db().update('finance_entries',{'id':previous['id']},values,inc={'version':1}); eid=previous['id']
            else:
                eid=db().insert('finance_entries',dict(values,status='ACTIVE',version=1,submission=token,created_by=session['user']))
            audit('edit' if previous else 'record','finance',eid,json.dumps({key:value for key,value in values.items() if key!='receipt'}))
            flash('Finance entry saved.'); return redirect(url_for('finance_page'))
        month=today()[:7]; first=date.fromisoformat(month+'-01'); last=first.replace(day=calendar.monthrange(first.year,first.month)[1])
        start=request.args.get('from') or first.isoformat(); end=request.args.get('to') or last.isoformat()
        start=date.fromisoformat(start).isoformat(); end=date.fromisoformat(end).isoformat()
        if start>end: raise ValueError('From date must be before the To date.')
        account=request.args.get('account',''); category=request.args.get('category',''); kind=request.args.get('kind','')
        if account and account not in ACCOUNTS: raise ValueError('Choose a valid account.')
        if kind and kind not in ('INCOME','EXPENSE','OPENING'): raise ValueError('Choose a valid entry type.')
        all_rows=movements()
        opening_dates={row['account']:row['date'] for row in all_rows if row['kind']=='OPENING' and row['date']<=end}
        # Opening balances establish a baseline, rather than adding older invoice
        # collections to cash that the opening amount already represents.
        tracked=[row for row in all_rows if row['date']>=opening_dates.get(row['account'],'0001-01-01')]
        account_rows=[row for row in tracked if not account or row['account']==account]
        period=[row for row in account_rows if start<=row['date']<=end]
        rows=[row for row in period if (not category or row['category']==category) and (not kind or row['kind']==kind)]
        signed=lambda row:-row['amount'] if row['kind']=='EXPENSE' else row['amount']
        summary=dict(income=sum(row['amount'] for row in period if row['kind']=='INCOME'),expenses=sum(row['amount'] for row in period if row['kind']=='EXPENSE'),opening=sum(signed(row) for row in account_rows if row['date']<start),opening_added=sum(row['amount'] for row in period if row['kind']=='OPENING'))
        summary['net']=summary['income']-summary['expenses']
        summary['closing']=summary['opening']+summary['opening_added']+summary['net']
        breakdown={}
        for row in period:
            if row['kind']=='EXPENSE': breakdown[row['category']]=breakdown.get(row['category'],0)+row['amount']
        if request.args.get('export'):
            if 'report.export' not in g.access['permissions']: abort(403)
            headers=['Date','Type','Category','Title','Amount (INR)','Account','Method','Source','Reference','Notes']
            values=[[row[key] for key in ('date','kind','category','title')]+[f"{row['amount']/100:.2f}"]+[row.get(key,'') for key in ('account','method','source','reference','notes')] for row in rows]
            if request.args['export']=='csv':
                safe=lambda value:"'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value
                output=io.StringIO(); writer=csv.writer(output); writer.writerow(headers); writer.writerows([[safe(value) for value in row] for row in values])
                return Response('\ufeff'+output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=finance.csv'})
            if request.args['export']=='pdf':
                if not g.access['features'].get('pdf'): abort(403)
                # Short columns fit A4; full detail remains available in the CSV export.
                table=[['Date','Type','Category','Amount INR']]+[[row[0],row[1],row[2],row[4]] for row in values]
                totals=[f"Period: {start} to {end}; Account: {account or 'All accounts'}",'Summary covers the selected dates and account; table follows category/type filters.',f"Income: INR {summary['income']/100:,.2f}; Expenses: INR {summary['expenses']/100:,.2f}",f"Cash movement: INR {summary['net']/100:,.2f}; Closing balance: INR {summary['closing']/100:,.2f}"]
                return Response(pdf_document('Income & expenses',totals+[table]),mimetype='application/pdf',headers={'Content-Disposition':'attachment; filename=finance.pdf'})
            raise ValueError('Choose CSV or PDF export.')
        edit=owned('finance_entries',request.args['edit']) if request.args.get('edit') else None
        if edit and 'finance.manage' not in g.access['permissions']: abort(403)
        if edit and edit['status']!='ACTIVE': raise ValueError('Voided entries cannot be edited.')
        return render_template('finance.html',title='Income & expenses',rows=rows,summary=summary,breakdown=sorted(breakdown.items(),key=lambda item:item[1],reverse=True),categories=sorted(set(CATEGORIES)|{row['category'] for row in all_rows}),accounts=ACCOUNTS,methods=METHODS,start=start,end=end,edit=edit,submission=secrets.token_hex(32),export_args={key:value for key,value in request.args.items() if key!='export'})

    @app.get('/finance/<int:ident>/receipt')
    def finance_receipt(ident):
        entry=owned('finance_entries',ident); attachment=entry.get('receipt')
        if not attachment: abort(404)
        response=Response(attachment['data'],mimetype=attachment['mime'],headers={'Content-Disposition':f"attachment; filename={attachment['filename']}"})
        response.headers['Content-Security-Policy']="sandbox; default-src 'none'"
        return response
