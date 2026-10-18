"""Compact, bordered sales invoices without third-party branding."""
import io
import base64
from datetime import date
from decimal import Decimal
from product_units import rate_text
from company_profile import header_fields
from xml.sax.saxutils import escape
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle, Image


def build_sales_invoice_pdf(inv):
    preferences=inv['snapshot']['business'].get('extended',{})
    theme=preferences.get('invoice_theme','A5')
    if theme in ('THERMAL_58','THERMAL_80'): return build_thermal_pdf(inv,theme)
    output=io.BytesIO(); page=A4 if theme.startswith('A4_') else landscape(A5); width=page[0]-32
    normal=ParagraphStyle('invoice',fontName='Helvetica',fontSize=7.5,leading=10)
    bold=ParagraphStyle('bold',parent=normal,fontName='Helvetica-Bold')
    center=ParagraphStyle('center',parent=normal,alignment=1)
    heading=ParagraphStyle('heading',parent=bold,fontSize=11,leading=14,alignment=1)
    right=ParagraphStyle('right',parent=normal,alignment=2)
    def p(value,style=normal): return Paragraph(escape(str(value or '')).replace('\n','<br/>'),style)
    def money(value): return f'INR {Decimal(value)/100:,.2f}'
    def image(data,maxw,maxh):
        blob=base64.b64decode(data.split(',',1)[1]); im=PILImage.open(io.BytesIO(blob)); w,h=im.size; scale=min(maxw/w,maxh/h)
        return Image(io.BytesIO(blob),width=w*scale,height=h*scale)
    def table(rows,widths,repeat=0,commands=()):
        result=Table(rows,colWidths=widths,repeatRows=repeat,hAlign='LEFT',splitInRow=1)
        result.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.5,colors.HexColor('#444444')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]+list(commands)))
        return result
    snapshot=inv['snapshot']; business=snapshot['business']; customer=snapshot['customer']; gst=inv['type']=='GST'
    columns_gst=gst and preferences.get('show_gst_columns',True)
    title='TAX INVOICE' if gst else 'BILL OF SUPPLY'
    story=[table([[p(title,bold),p(inv.get('copy_label','ORIGINAL FOR RECIPIENT'),right)]],[width/2,width/2],commands=[('GRID',(0,0),(-1,-1),0,colors.white)]),Spacer(1,3)]
    seller=[p(business['name'],heading),p(' '.join(filter(None,[business.get('address'),business.get('state'),business.get('pin')])),center)]
    contacts=' | '.join(filter(None,[('Mobile: '+business['phone']) if business.get('phone') else '',business.get('email','')]))
    if contacts: seller.append(p(contacts,center))
    if gst and business.get('gstin'): seller.append(p('GSTIN: '+business['gstin'],center))
    for label,value in header_fields(business): seller.append(p(label+': '+value,center))
    if business.get('logo'):
        header=table([[image(business['logo'],48,44),seller]],[65,width-65],commands=[('LINEAFTER',(0,0),(0,0),0,colors.white)])
    else: header=table([[seller]],[width])
    story.append(header)
    bill=[p('BILL TO'),p(customer['name'],bold)]
    address=' '.join(filter(None,[customer['data'].get('address'),customer['data'].get('state'),customer['data'].get('pin')]))
    if address: bill.append(p(address))
    if customer['data'].get('phone'): bill.append(p('Mobile: '+customer['data']['phone']))
    if gst and customer['data'].get('gstin'): bill.append(p('GSTIN: '+customer['data']['gstin']))
    if customer['data'].get('shipping_address'): bill.append(p('Ship to: '+customer['data']['shipping_address']))
    if customer['data'].get('pan'): bill.append(p('PAN: '+customer['data']['pan']))
    if preferences.get('show_previous_balance') and 'previous_balance' in snapshot: bill.append(p('Previous balance: '+money(snapshot['previous_balance'])))
    number=[p('Invoice No.',bold),p(inv['number'])]
    if inv['status']!='FINAL': number.append(p('Status: '+inv['status']))
    dated=[p('Invoice Date',bold),p(date.fromisoformat(inv['date']).strftime('%d/%m/%Y'))]
    if preferences.get('show_time') and inv.get('created_at'): dated.append(p('Created: '+inv['created_at']+' UTC'))
    for key,label in [('po_number','PO number'),('vehicle_number','Vehicle'),('eway_bill','E-way bill'),('due_date','Due date'),('installation','Installation'),('service','Service')]:
        if snapshot.get(key): dated.append(p(label+': '+snapshot[key]))
    story.append(table([[bill,number,dated]],[width*.5,width*.25,width*.25]))
    headings=['S.NO.','ITEMS / HSN' if gst else 'ITEMS','QTY.','MRP']+(['GST / TAX'] if columns_gst else [])+['AMOUNT']
    widths=[36,width-36-48-70-95-(68 if columns_gst else 0),48,70]+([68] if columns_gst else [])+[95]
    rows=[[p(label,bold) for label in headings]]
    products=[item for item in inv['items'] if not item.get('is_charge')]
    charges=[item for item in inv['items'] if item.get('is_charge')]
    for n,item in enumerate(products,1):
        label=item['name']+('\n'+item.get('hsn','') if gst and item.get('hsn') else '')
        if item.get('unit_rate_decimal') or item.get('pricing_mode')=='INCLUSIVE': label+='\nRate: '+rate_text(item)+(' incl. GST' if gst and item.get('pricing_mode')=='INCLUSIVE' else '')
        if preferences.get('show_description') and item.get('description'): label+='\n'+item['description']
        mrp=f"{item['mrp']/100:,.2f}"
        basis=item['mrp']*Decimal(item['quantity'])/1000
        if 'common_discount' not in inv and basis>item['taxable'] and basis>0: mrp+=f"\n({(basis-item['taxable'])/basis*100:.2f}% OFF)"
        values=[p(n,center),p(label),p(f"{Decimal(item['quantity'])/1000:g} {item['unit']}",center),p(mrp,right)]
        if columns_gst: values.append(p(f"{item['gst']}%\n{money(item['tax'])}",right))
        values.append(p(money(item['total']),right)); rows.append(values)
    for item in charges:
        values=[p(''),p(item['name']+('\nHSN/SAC: '+item['hsn'] if item.get('hsn') else ''),right),p('-',center),p('-',right)]
        if columns_gst: values.append(p(f"{item['gst']}%\n{money(item['tax'])}",right))
        values.append(p(money(item['total']),right)); rows.append(values)
    if inv['discount']:
        rows.append([p(''),p('Discount',right)]+[p('') for _ in headings[2:-1]]+[p(money(inv['discount']),right)])
    if gst:
        for label,key in [('Taxable amount','taxable'),('CGST','cgst'),('SGST','sgst'),('IGST','igst')]:
            if key!='taxable' and not inv[key]: continue
            rows.append([p(''),p(label,right)]+[p('') for _ in headings[2:-1]]+[p(money(inv[key]),right)])
    if 'round_off' in inv:
        rows.append([p(''),p('Round off',right)]+[p('') for _ in headings[2:-1]]+[p(money(inv['round_off']),right)])
    quantity=Decimal(sum(item['quantity'] for item in products))/1000
    rows.append([p(''),p('TOTAL' if gst else 'Total amount',bold),p(f'{quantity:g}',center),p('')]+([p('')] if columns_gst else [])+[p(money(inv['total']),bold)])
    story.append(table(rows,widths,repeat=1,commands=[('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8eff8' if theme=='A4_ADVANCED' else '#f7f7f7' if theme=='A4_SIMPLE' else '#e2e2e2')),('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#e8eff8' if theme=='A4_ADVANCED' else '#f7f7f7' if theme=='A4_SIMPLE' else '#e2e2e2'))]))
    story.append(Spacer(1,4))
    story.append(table([[p('Received Amount: '+money(inv['received'])+(' | Refunded: '+money(inv['refunded']) if inv.get('refunded') else '')),p('Balance due: '+money(inv['balance'])+(' | Credit notes: '+money(inv['credit']) if inv.get('credit') else ''),right)]],[width/2,width/2]))
    notes=[p('Terms and Conditions',bold),p(snapshot.get('terms',''))]
    if snapshot.get('notes'): notes.extend([Spacer(1,5),p('Notes',bold),p(snapshot['notes'])])
    mode=preferences.get('payment_details','BOTH')
    bank='\n'.join(filter(None,[('Bank: '+business['bank']) if business.get('bank') and mode!='UPI' else '',('UPI: '+business['upi']) if business.get('upi') and mode!='BANK' else '']))
    if bank: notes.extend([Spacer(1,5),p(bank)])
    if preferences.get('show_qr') and business.get('upi') and mode!='BANK' and inv.get('balance',inv['total'])>0: notes.append(upi_qr(business,inv.get('balance',inv['total'])))
    signature=[]
    if business.get('signature'): signature.append(image(business['signature'],110,45))
    elif preferences.get('empty_signature_box'): signature.append(table([[p('Signature')]], [110],commands=[('TOPPADDING',(0,0),(-1,-1),22)]))
    else: signature.append(Spacer(1,22))
    if business.get('signatory'): signature.append(p(business['signatory'],center))
    signature.extend([p('Authorised Signatory For',center),p(business['name'],center)])
    story.append(table([[notes,signature]],[width*.55,width*.45]))
    def footer(canvas,doc):
        canvas.setFont('Helvetica',7); canvas.setFillColor(colors.HexColor('#666666'))
        canvas.drawString(16,10,inv['number']); canvas.drawRightString(page[0]-16,10,f'Page {doc.page}')
    SimpleDocTemplate(output,pagesize=page,leftMargin=16,rightMargin=16,topMargin=12,bottomMargin=22,title=inv['number'],author=business['name']).build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()


def upi_qr(business,amount):
    from urllib.parse import urlencode
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    value='upi://pay?'+urlencode(dict(pa=business['upi'],pn=business['name'],am=f'{Decimal(amount)/100:.2f}',cu='INR'))
    qr=QrCodeWidget(value);x,y,w,h=qr.getBounds();size=72
    drawing=Drawing(size,size,transform=[size/(w-x),0,0,size/(h-y),0,0]);drawing.add(qr)
    return drawing


def build_thermal_pdf(inv,theme):
    output=io.BytesIO();width=164 if theme=='THERMAL_58' else 227;usable=width-16
    preferences=inv['snapshot']['business'].get('extended',{});layout=preferences.get('thermal_layout','CLASSIC')
    size={'COMPACT':6,'SIMPLE':8,'CLASSIC':7,'ADVANCED':7.5}.get(layout,7)
    normal=ParagraphStyle('thermal',fontName='Helvetica',fontSize=size,leading=size+2)
    bold=ParagraphStyle('thermalbold',parent=normal,fontName='Helvetica-Bold')
    def p(value,strong=False): return Paragraph(escape(str(value or '')).replace('\n','<br/>'),bold if strong else normal)
    def amount(value): return f'INR {Decimal(value)/100:.2f}'
    business=inv['snapshot']['business'];customer=inv['snapshot']['customer'];preferences=business.get('extended',{});gst=inv['type']=='GST'
    story=[]
    def picture(data,maxw,maxh):
        blob=base64.b64decode(data.split(',',1)[1]);im=PILImage.open(io.BytesIO(blob));w,h=im.size;scale=min(maxw/w,maxh/h)
        return Image(io.BytesIO(blob),width=w*scale,height=h*scale)
    if business.get('logo'): story.append(picture(business['logo'],usable,40))
    story.extend([p(business['name'],True),p(business.get('address')),p(business.get('phone'))])
    if gst and business.get('gstin'): story.append(p('GSTIN '+business['gstin']))
    for label,value in header_fields(business): story.append(p(label+': '+value))
    story.extend([Spacer(1,8),p('TAX INVOICE' if gst else 'BILL OF SUPPLY',True),p(inv['number']),p(inv['date']),p('Bill to: '+customer['name'])])
    if gst and customer['data'].get('gstin'): story.append(p(customer['data']['gstin']))
    if customer['data'].get('shipping_address'): story.append(p('Ship to: '+customer['data']['shipping_address']))
    if customer['data'].get('pan'): story.append(p('PAN: '+customer['data']['pan']))
    if preferences.get('show_previous_balance') and 'previous_balance' in inv['snapshot']: story.append(p('Previous balance: '+amount(inv['snapshot']['previous_balance'])))
    for key,label in [('po_number','PO'),('vehicle_number','Vehicle'),('eway_bill','E-way bill'),('due_date','Due')]:
        if inv['snapshot'].get(key): story.append(p(label+': '+inv['snapshot'][key]))
    if inv.get('copy_label'): story.append(p(inv['copy_label'],True))
    if preferences.get('show_time') and inv.get('created_at'): story.append(p('Created: '+inv['created_at']+' UTC'))
    rows=[[p('Item',True),p('Amount',True)]]
    for item in inv['items']:
        label=item['name']
        if not item.get('is_charge'): label+=f"\n{Decimal(item['quantity'])/1000:g} {item['unit']} x {rate_text(item)}"+(' incl. GST' if gst and item.get('pricing_mode')=='INCLUSIVE' else '')
        if item.get('hsn'): label+='\nHSN/SAC '+item['hsn']
        if preferences.get('show_description') and item.get('description'): label+='\n'+item['description']
        if gst and preferences.get('show_gst_columns',True): label+=f"\nGST {item['gst']}%: {amount(item['tax'])}"
        rows.append([p(label),p(amount(item['total']))])
    for label,key in [('Discount','discount'),('CGST','cgst'),('SGST','sgst'),('IGST','igst'),('Round off','round_off'),('Total','total'),('Credit notes','credit'),('Refunded','refunded'),('Received','received'),('Balance','balance')]:
        if key in inv and (key not in ('cgst','sgst','igst') or inv[key]): rows.append([p(label,key=='total'),p(amount(inv[key]),key=='total')])
    table=Table(rows,colWidths=[usable*.62,usable*.38],repeatRows=1,hAlign='LEFT',splitInRow=1)
    table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),1),('RIGHTPADDING',(0,0),(-1,-1),1),('LINEBELOW',(0,0),(-1,0),.5,colors.black)]))
    if layout=='CLASSIC': table.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.5,colors.black)]))
    elif layout=='ADVANCED': table.setStyle(TableStyle([('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#eeeeee')]),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dddddd'))]))
    elif layout=='SIMPLE': table.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    else: table.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),1),('BOTTOMPADDING',(0,0),(-1,-1),1)]))
    story.extend([Spacer(1,6),table,Spacer(1,6),p(inv['snapshot'].get('notes')),p(inv['snapshot'].get('terms'))])
    mode=preferences.get('payment_details','BOTH')
    if mode!='UPI': story.append(p(business.get('bank')))
    if mode!='BANK':
        story.append(p(business.get('upi')))
        if preferences.get('show_qr') and business.get('upi') and inv.get('balance',inv['total'])>0: story.append(upi_qr(business,inv.get('balance',inv['total'])))
    if business.get('signature'): story.append(picture(business['signature'],usable,40))
    elif preferences.get('empty_signature_box'):
        box=Table([[p('Authorized Signatory')]],colWidths=[usable]);box.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.5,colors.black),('TOPPADDING',(0,0),(-1,-1),22)]));story.append(box)
    story.append(p('For '+business['name']))
    height=max(144,min(2800,sum(flowable.wrap(usable,10000)[1] for flowable in story)+26))
    document=BaseDocTemplate(output,pagesize=(width,height),title=inv['number'])
    document.addPageTemplates(PageTemplate(id='receipt',frames=[Frame(8,12,usable,height-22,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)]))
    document.build(story)
    return output.getvalue()
