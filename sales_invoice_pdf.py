"""Compact, bordered sales invoices without third-party branding."""
import io
import base64
from datetime import date
from xml.sax.saxutils import escape
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A5, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image


def build_sales_invoice_pdf(inv):
    output=io.BytesIO(); page=landscape(A5); width=page[0]-32
    normal=ParagraphStyle('invoice',fontName='Helvetica',fontSize=7.5,leading=10)
    bold=ParagraphStyle('bold',parent=normal,fontName='Helvetica-Bold')
    center=ParagraphStyle('center',parent=normal,alignment=1)
    heading=ParagraphStyle('heading',parent=bold,fontSize=11,leading=14,alignment=1)
    right=ParagraphStyle('right',parent=normal,alignment=2)
    def p(value,style=normal): return Paragraph(escape(str(value or '')).replace('\n','<br/>'),style)
    def money(value): return f'INR {value/100:,.2f}'
    def image(data,maxw,maxh):
        blob=base64.b64decode(data.split(',',1)[1]); im=PILImage.open(io.BytesIO(blob)); w,h=im.size; scale=min(maxw/w,maxh/h)
        return Image(io.BytesIO(blob),width=w*scale,height=h*scale)
    def table(rows,widths,repeat=0,commands=()):
        result=Table(rows,colWidths=widths,repeatRows=repeat,hAlign='LEFT',splitInRow=1)
        result.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.5,colors.HexColor('#444444')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),3),('BOTTOMPADDING',(0,0),(-1,-1),3)]+list(commands)))
        return result
    snapshot=inv['snapshot']; business=snapshot['business']; customer=snapshot['customer']; gst=inv['type']=='GST'
    title='TAX INVOICE' if gst else 'BILL OF SUPPLY'
    story=[table([[p(title,bold),p('ORIGINAL FOR RECIPIENT',right)]],[width/2,width/2],commands=[('GRID',(0,0),(-1,-1),0,colors.white)]),Spacer(1,3)]
    seller=[p(business['name'],heading),p(' '.join(filter(None,[business.get('address'),business.get('state'),business.get('pin')])),center)]
    contacts=' | '.join(filter(None,[('Mobile: '+business['phone']) if business.get('phone') else '',business.get('email','')]))
    if contacts: seller.append(p(contacts,center))
    if gst and business.get('gstin'): seller.append(p('GSTIN: '+business['gstin'],center))
    if business.get('logo'):
        header=table([[image(business['logo'],48,44),seller]],[65,width-65],commands=[('LINEAFTER',(0,0),(0,0),0,colors.white)])
    else: header=table([[seller]],[width])
    story.append(header)
    bill=[p('BILL TO'),p(customer['name'],bold)]
    address=' '.join(filter(None,[customer['data'].get('address'),customer['data'].get('state'),customer['data'].get('pin')]))
    if address: bill.append(p(address))
    if customer['data'].get('phone'): bill.append(p('Mobile: '+customer['data']['phone']))
    if gst and customer['data'].get('gstin'): bill.append(p('GSTIN: '+customer['data']['gstin']))
    number=[p('Invoice No.',bold),p(inv['number'])]
    if inv['status']!='FINAL': number.append(p('Status: '+inv['status']))
    dated=[p('Invoice Date',bold),p(date.fromisoformat(inv['date']).strftime('%d/%m/%Y'))]
    for key,label in [('installation','Installation'),('service','Service')]:
        if snapshot.get(key): dated.append(p(label+': '+snapshot[key]))
    story.append(table([[bill,number,dated]],[width*.5,width*.25,width*.25]))
    headings=['S.NO.','ITEMS / HSN' if gst else 'ITEMS','QTY.','MRP']+(['GST / TAX'] if gst else [])+['AMOUNT']
    widths=[36,width-36-48-70-95-(68 if gst else 0),48,70]+([68] if gst else [])+[95]
    rows=[[p(label,bold) for label in headings]]
    products=[item for item in inv['items'] if not item.get('is_charge')]
    charges=[item for item in inv['items'] if item.get('is_charge')]
    for n,item in enumerate(products,1):
        label=item['name']+('\n'+item.get('hsn','') if gst and item.get('hsn') else '')
        mrp=f"{item['mrp']/100:,.2f}"
        basis=item['mrp']*item['quantity']/1000
        if 'common_discount' not in inv and basis>item['taxable'] and basis>0: mrp+=f"\n({(basis-item['taxable'])/basis*100:.2f}% OFF)"
        values=[p(n,center),p(label),p(f"{item['quantity']/1000:g} {item['unit']}",center),p(mrp,right)]
        if gst: values.append(p(f"{item['gst']}%\n{money(item['tax'])}",right))
        values.append(p(money(item['total']),right)); rows.append(values)
    for item in charges:
        values=[p(''),p(item['name']+('\nHSN/SAC: '+item['hsn'] if item.get('hsn') else ''),right),p('-',center),p('-',right)]
        if gst: values.append(p(f"{item['gst']}%\n{money(item['tax'])}",right))
        values.append(p(money(item['total']),right)); rows.append(values)
    if inv['discount']:
        rows.append([p(''),p('Discount',right)]+[p('') for _ in headings[2:-1]]+[p(money(inv['discount']),right)])
    if gst:
        for label,key in [('Taxable amount','taxable'),('CGST','cgst'),('SGST','sgst'),('IGST','igst')]:
            if key!='taxable' and not inv[key]: continue
            rows.append([p(''),p(label,right)]+[p('') for _ in headings[2:-1]]+[p(money(inv[key]),right)])
    if 'round_off' in inv:
        rows.append([p(''),p('Round off',right)]+[p('') for _ in headings[2:-1]]+[p(money(inv['round_off']),right)])
    quantity=sum(item['quantity'] for item in products)/1000
    rows.append([p(''),p('TOTAL' if gst else 'Total amount',bold),p(f'{quantity:g}',center),p('')]+([p('')] if gst else [])+[p(money(inv['total']),bold)])
    story.append(table(rows,widths,repeat=1,commands=[('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e2e2e2')),('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#e2e2e2'))]))
    story.append(Spacer(1,4))
    story.append(table([[p('Received Amount: '+money(inv['received'])),p('Balance due: '+money(inv['balance']),right)]],[width/2,width/2]))
    notes=[p('Terms and Conditions',bold),p(snapshot.get('terms',''))]
    if snapshot.get('notes'): notes.extend([Spacer(1,5),p('Notes',bold),p(snapshot['notes'])])
    bank='\n'.join(filter(None,[('Bank: '+business['bank']) if business.get('bank') else '',('UPI: '+business['upi']) if business.get('upi') else '']))
    if bank: notes.extend([Spacer(1,5),p(bank)])
    signature=[]
    if business.get('signature'): signature.append(image(business['signature'],110,45))
    else: signature.append(Spacer(1,22))
    if business.get('signatory'): signature.append(p(business['signatory'],center))
    signature.extend([p('Authorised Signatory For',center),p(business['name'],center)])
    story.append(table([[notes,signature]],[width*.55,width*.45]))
    def footer(canvas,doc):
        canvas.setFont('Helvetica',7); canvas.setFillColor(colors.HexColor('#666666'))
        canvas.drawString(16,10,inv['number']); canvas.drawRightString(page[0]-16,10,f'Page {doc.page}')
    SimpleDocTemplate(output,pagesize=page,leftMargin=16,rightMargin=16,topMargin=12,bottomMargin=22,title=inv['number'],author=business['name']).build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
