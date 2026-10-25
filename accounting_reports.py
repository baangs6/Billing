"""Reconciled management exports; not a GST filing integration."""
import csv
import io
from decimal import Decimal
from collections import defaultdict
from report_totals import report_period,total_row
from flask import abort,g,request,render_template,Response,send_file

REPORT_TYPES=('Purchases','Receivables','Payables','Sales credit notes','Purchase debit notes','HSN sales','GST summary','Stock valuation')


def install_accounting_reports(app,db,money,today,products,pdf):
    @app.get('/accounting-reports')
    def accounting_reports():
        kind=request.args.get('report','Purchases');start,end=report_period(request.args,today())
        if not g.access['features'].get('reports'): abort(403)
        kinds=REPORT_TYPES
        if kind not in kinds: raise ValueError('Choose a report.')
        if kind in ('Purchases','Payables','Purchase debit notes','GST summary') and 'purchase.view' not in g.access['permissions']: abort(403)
        if kind in ('Receivables','Sales credit notes','HSN sales','GST summary') and 'invoice.view' not in g.access['permissions']: abort(403)
        within=lambda row:start<=row['date']<=end
        invoices=db().find('invoices',{'status':'FINAL','deleted':{'$ne':True}});purchases=db().find('purchases',{'status':'FINAL'})
        credits=db().find('sales_returns');debits=db().find('trade_returns');headers=[];rows=[]
        if kind=='Purchases':
            headers=['Date','Supplier','Original invoice','Taxable INR','CGST INR','SGST INR','IGST INR','Total INR']
            rows=[[p['date'],p['snapshot']['supplier']['name'],p['supplier_number'],*[f"{Decimal(p[k])/100:.2f}" for k in ('taxable','cgst','sgst','igst','total')]] for p in purchases if within(p)]
        elif kind in ('Sales credit notes','Purchase debit notes'):
            notes=credits if kind=='Sales credit notes' else debits;headers=['Note','Date','Original document','Taxable INR','Tax INR','Round off INR','Credit INR','Reason']
            rows=[[n['id'],n['date'],n.get('invoice_id',n.get('purchase_id')),f"{Decimal(sum(i['taxable'] for i in n['items']))/100:.2f}",f"{Decimal(sum(i['tax'] for i in n['items']))/100:.2f}",f"{Decimal(n.get('round_off',0))/100:.2f}",f"{Decimal(n['total'])/100:.2f}",n['reason']] for n in notes if within(n)]
        elif kind in ('Receivables','Payables'):
            customer=kind=='Receivables';party='customers' if customer else 'suppliers';field='customer_id' if customer else 'supplier_id'
            documents=invoices if customer else purchases;notes=credits if customer else debits
            headers=['Party','Opening INR','Invoices INR','Credit notes INR','Net paid INR','Balance INR']
            gross=defaultdict(int);credit=defaultdict(int);paid=defaultdict(int)
            invoice_parties={document['id']:document[field] for document in documents if document['date']<=end}
            for document in documents:
                if document['date']<=end: gross[document[field]]+=document['total']
            for note in notes:
                if note['date']<=end: credit[note[field]]+=note['total']
            if customer:
                for payment in db().find('payments',{'invoice_id':{'$in':list(invoice_parties)},'date':{'$lte':end}}): paid[invoice_parties[payment['invoice_id']]]+=payment['amount']
            for payment in db().find('trade_payments',{field:{'$exists':True},'date':{'$lte':end}}):
                ident=payment[field]
                if 'opening_effect' in payment: paid[ident]-=payment['opening_effect']
                elif customer and payment['kind']=='CUSTOMER_REFUND': paid[ident]-=payment['amount']
                elif not customer and payment['kind'] in ('PAYMENT_OUT','SUPPLIER_REFUND'): paid[ident]+=payment['amount']*(-1 if payment['kind']=='SUPPLIER_REFUND' else 1)
            parties=db().find(party)
            if customer and (gross[0] or credit[0] or paid[0]): parties.append(dict(id=0,name='Walk-in sales',data={}))
            for party_row in parties:
                ident=party_row['id'];opening=party_row['data'].get('opening_balance',0)
                rows.append([party_row['name'],*[f'{Decimal(v)/100:.2f}' for v in (opening,gross[ident],credit[ident],paid[ident],opening+gross[ident]-credit[ident]-paid[ident])]])
        elif kind=='HSN sales':
            headers=['HSN / SAC','Taxable INR','Tax INR'];aggregate=defaultdict(lambda:[0,0])
            ids=[inv['id'] for inv in invoices if within(inv)]
            for item in db().find('invoice_items',{'invoice_id':{'$in':ids}}): aggregate[item.get('hsn','')][0]+=item['taxable'];aggregate[item.get('hsn','')][1]+=item['tax']
            for note in credits:
                if within(note):
                    for item in note['items']: aggregate[item.get('hsn','')][0]-=item['taxable'];aggregate[item.get('hsn','')][1]-=item['tax']
            rows=[[key or 'Not specified',f'{Decimal(values[0])/100:.2f}',f'{Decimal(values[1])/100:.2f}'] for key,values in sorted(aggregate.items())]
        elif kind=='GST summary':
            headers=['Source','Taxable INR','CGST INR','SGST INR','IGST INR'];keys=('taxable','cgst','sgst','igst')
            for label,documents,notes in [('Sales',invoices,credits),('Purchases',purchases,debits)]:
                values={k:sum(d[k] for d in documents if d['type']=='GST' and within(d)) for k in keys}
                taxable_ids={d['id'] for d in documents if d['type']=='GST'}
                for note in notes:
                    if within(note) and note.get('invoice_id',note.get('purchase_id')) in taxable_ids:
                        for line in note['items']:
                            for k in keys: values[k]-=line.get(k,0)
                rows.append([label,*[f'{Decimal(values[k])/100:.2f}' for k in keys]])
        else:
            if not g.access['features'].get('inventory') or 'inventory.view' not in g.access['permissions']: abort(403)
            headers=['Product','SKU','Stock units','Catalog cost INR','Value INR','Unit']
            rows=[[p['name'],p['sku'],f"{Decimal(p['quantity'])/1000:g}",f"{Decimal(p['purchase_price'])/100:.2f}",f"{Decimal(p['quantity'])*p['purchase_price']/100000:.2f}",p['data'].get('unit','')] for p in products()]
        totals=total_row(kind,headers,rows)
        format=request.args.get('export')
        if format:
            if 'report.export' not in g.access['permissions']: abort(403)
            if format=='pdf':
                if not g.access['features'].get('pdf'): abort(403)
                return Response(pdf(kind+' | '+start+' to '+end,[[headers]+rows+[totals]]),mimetype='application/pdf',headers={'Content-Disposition':'attachment; filename=accounting-report.pdf'})
            if format=='xlsx':
                from openpyxl import Workbook
                workbook=Workbook();sheet=workbook.active;sheet.append(headers)
                for row in rows+[totals]: sheet.append(["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in row])
                output=io.BytesIO();workbook.save(output);output.seek(0)
                return send_file(output,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',as_attachment=True,download_name='accounting-report.xlsx')
            if format!='csv': raise ValueError('Choose CSV, XLSX or PDF.')
            output=io.StringIO();writer=csv.writer(output);writer.writerow(headers);writer.writerows([["'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v for v in row] for row in rows+[totals]])
            return Response('\ufeff'+output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=accounting-report.csv'})
        return render_template('accounting_reports.html',title='Reports',kind=kind,kinds=kinds,start=start,end=end,headers=headers,rows=rows,totals=totals)
    return {'accounting_reports':('report.view',None)}
