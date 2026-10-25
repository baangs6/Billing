"""Clean A4 invoice matching the invoice-detail view, with adaptive spacing."""
import base64
import io
from decimal import Decimal
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer,Image,KeepInFrame
from product_units import line_rate_amount,mrp_discount
from company_profile import header_fields


def build_ledger_invoice_pdf(inv):
    business=inv['snapshot']['business'];snapshot=inv['snapshot'];customer=snapshot['customer'];preferences=business.get('extended',{})
    width=A4[0]-64;blue=colors.HexColor('#2563eb');line=colors.HexColor('#dfe5ee')
    gst=inv['type']=='GST';tax_column=gst and preferences.get('show_gst_columns',True)
    def money(value): return 'INR '+f'{Decimal(value)/100:,.2f}'
    def picture(data,max_width,max_height):
        from PIL import Image as PILImage
        blob=base64.b64decode(data.split(',',1)[1]);w,h=PILImage.open(io.BytesIO(blob)).size
        scale=min(max_width/w,max_height/h)
        return Image(io.BytesIO(blob),width=w*scale,height=h*scale)

    def story(font):
        normal=ParagraphStyle('body',fontName='Helvetica',fontSize=font,leading=font*1.4,textColor=colors.HexColor('#334155'))
        bold=ParagraphStyle('bold',parent=normal,fontName='Helvetica-Bold',textColor=colors.HexColor('#0f172a'))
        right=ParagraphStyle('right',parent=normal,alignment=2)
        grand=ParagraphStyle('grand',parent=bold,fontSize=font*1.25,leading=font*1.7,textColor=blue)
        grand_right=ParagraphStyle('grand-right',parent=grand,alignment=2)
        title=ParagraphStyle('title',parent=bold,fontSize=font*1.8,leading=font*2)
        def p(value,style=normal): return Paragraph(escape(str(value or '')).replace('\n','<br/>'),style)
        def table(rows,widths,header=False):
            result=Table(rows,colWidths=widths,repeatRows=1 if header else 0,hAlign='LEFT',splitInRow=1)
            commands=[('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),4),('RIGHTPADDING',(0,0),(-1,-1),4),('TOPPADDING',(0,0),(-1,-1),font*.6),('BOTTOMPADDING',(0,0),(-1,-1),font*.6)]
            if header: commands += [('BACKGROUND',(0,0),(-1,0),colors.HexColor('#f5f8fc')),('LINEBELOW',(0,0),(-1,0),.5,line)]
            result.setStyle(TableStyle(commands));return result
        seller=[p(business['name'],title),p(business.get('address',''))]
        seller.append(p(' · '.join(str(business.get(k,'')) for k in ('phone','email','state','pin') if business.get(k))))
        if gst and business.get('gstin'): seller.append(p('GSTIN: '+business['gstin']))
        seller += [p(label+': '+value) for label,value in header_fields(business)]
        identity=([picture(business['logo'],52,48),seller] if business.get('logo') else [seller])
        widths=([62,width-192] if business.get('logo') else [width-130])+[130]
        identity.append(p(('TAX INVOICE' if gst else 'BILL OF SUPPLY')+('\n'+inv['copy_label'] if inv.get('copy_label') else ''),right))
        header=table([identity],widths);header.setStyle(TableStyle([('LINEBELOW',(0,-1),(-1,-1),1,blue)]))
        result=[header,Spacer(1,font*1.3)]
        party=[p('BILL TO'),p(customer['name'],bold)]
        for key in ('address','state','pin','phone'):
            if customer['data'].get(key): party.append(p(customer['data'][key]))
        for key,label in [('gstin','GSTIN'),('pan','PAN'),('shipping_address','Ship to')]:
            if customer['data'].get(key) and (key!='gstin' or gst): party.append(p(label+': '+customer['data'][key]))
        if preferences.get('show_previous_balance') and snapshot.get('previous_balance'): party.append(p('Previous balance: '+money(snapshot['previous_balance'])))
        metadata=[p(inv['number'],bold),p('Invoice date: '+inv['date'],right)]
        for key,label in [('due_date','Due date'),('installation','Installation'),('service','Service'),('po_number','PO number'),('eway_bill','E-way bill'),('vehicle_number','Vehicle')]:
            if snapshot.get(key): metadata.append(p(label+': '+snapshot[key],right))
        if preferences.get('show_time') and inv.get('created_at'): metadata.append(p('Created: '+inv['created_at']+' UTC',right))
        result += [table([[party,metadata]],[width*.58,width*.42]),Spacer(1,font*1.3)]
        headings=['#','ITEM / HSN' if gst else 'ITEM','QTY','MRP']+(['GST / TAX'] if tax_column else [])+['AMOUNT']
        widths=[24,width-24-48-82-100-(66 if tax_column else 0),48,82]+([66] if tax_column else [])+[100]
        rows=[[p(label,bold) for label in headings]]
        for n,item in enumerate(inv['items'],1):
            charge=item.get('is_charge');name=item['name']
            if item.get('hsn') and (gst or charge): name+='\n'+item['hsn']
            if preferences.get('show_description') and item.get('description'): name+='\n'+item['description']
            if gst and item.get('pricing_mode')=='INCLUSIVE': name+='\nSelling price includes GST'
            row=[p(n),p(name,bold),p('-' if charge else f"{Decimal(item['quantity'])/1000:g} {item['unit']}"),p('-' if charge else money(item['mrp'])+'\n('+mrp_discount(item)+'% off)',right)]
            if tax_column: row.append(p(str(item['gst'])+'%\n'+money(item['tax']),right))
            row.append(p(money(line_rate_amount(item)),right));rows.append(row)
        result += [table(rows,widths,True),Spacer(1,font*1.5)]
        totals=[]
        for label,key in [('Subtotal','subtotal'),('Discount','discount'),('Taxable amount' if gst else 'Total amount','taxable'),('CGST','cgst'),('SGST','sgst'),('IGST','igst'),('Credit notes','credit'),('Refunded','refunded'),('Round off','round_off'),('Grand total','total'),('Received','received'),('Balance due','balance')]:
            if key in ('discount','cgst','sgst','igst','credit','refunded','round_off') and not inv.get(key): continue
            totals.append([p(label,grand if key=='total' else normal),p(money(inv.get(key,0)),grand_right if key=='total' else right)])
        total_table=table(totals,[170,110]);total_table.hAlign='RIGHT';total_table.setStyle(TableStyle([('LINEBELOW',(0,0),(-1,-1),.4,line)]))
        result += [total_table,Spacer(1,font*1.5)]
        notes=[p('Terms & conditions',bold),p(snapshot.get('terms',''))]
        if snapshot.get('notes'): notes += [p('Notes',bold),p(snapshot['notes'])]
        mode=preferences.get('payment_details','BOTH')
        for key,label in [('bank','Bank'),('upi','UPI')]:
            if business.get(key) and not (key=='bank' and mode=='UPI' or key=='upi' and mode=='BANK'): notes.append(p(label+': '+business[key]))
        if preferences.get('show_qr') and business.get('upi') and mode!='BANK' and inv.get('balance',inv['total'])>0:
            from sales_invoice_pdf import upi_qr
            notes.append(upi_qr(business,inv.get('balance',inv['total'])))
        signature=[]
        if business.get('signature'): signature.append(picture(business['signature'],100,44))
        elif preferences.get('empty_signature_box'):
            box=table([[p('Authorized Signatory')]], [130]);box.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.5,line),('TOPPADDING',(0,0),(-1,-1),24)]));signature.append(box)
        signature += [p(business.get('signatory',''),right),p('Authorised Signatory\nFor '+business['name'],right)]
        footer=table([[notes,signature]],[width*.65,width*.35]);footer.setStyle(TableStyle([('LINEABOVE',(0,0),(-1,0),.5,line)]));result.append(footer)
        return result

    # Reduce spacing first, then scale unusually long invoices without dropping content.
    for font in (9,8,7):
        content=story(font)
        height=sum(flowable.wrap(width,100000)[1] for flowable in content)
        if height<=A4[1]-76: break
    output=io.BytesIO()
    fitted=KeepInFrame(width-12,A4[1]-60,content,mode='shrink',hAlign='LEFT',vAlign='TOP')
    SimpleDocTemplate(output,pagesize=A4,leftMargin=32,rightMargin=32,topMargin=24,bottomMargin=24,title=inv['number'],author=business['name']).build([fitted])
    return output.getvalue()
