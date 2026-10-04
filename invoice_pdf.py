"""A4 invoice rendering from immutable invoice snapshots."""
import base64
import io
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether
from PIL import Image as PILImage

def build_invoice_pdf(inv,proposal=False):
    output=io.BytesIO(); width=A4[0]-72
    ink=colors.HexColor('#23352e'); green=colors.HexColor('#267a53'); line=colors.HexColor('#dfe7e1')
    normal=ParagraphStyle('body',fontName='Helvetica',fontSize=9,leading=13,textColor=ink)
    heading=ParagraphStyle('heading',parent=normal,fontSize=19,leading=24)
    right=ParagraphStyle('right',parent=normal,alignment=2)
    def p(text,style=normal): return Paragraph(escape(str(text)).replace('\n','<br/>'),style)
    def image(data,maxw=95,maxh=55):
        blob=base64.b64decode(data.split(',')[1]); im=PILImage.open(io.BytesIO(blob)); w,h=im.size; scale=min(maxw/w,maxh/h)
        return Image(io.BytesIO(blob),width=w*scale,height=h*scale)
    def table(data,widths,header=False):
        t=Table(data,colWidths=widths,repeatRows=1 if header else 0,hAlign='LEFT')
        commands=[('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8)]
        if header: commands += [('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf4ef')),('LINEBELOW',(0,0),(-1,0),.6,line),('LINEBELOW',(0,1),(-1,-1),.3,line)]
        t.setStyle(TableStyle(commands)); return t
    s=inv['snapshot']; b=s['business']; c=s['customer']; fmt=lambda n:f'INR {n/100:,.2f}'; story=[]
    gst=inv['type']=='GST'
    seller_gstin=f"\nGSTIN: {b['gstin'] or '-'}" if gst else ''
    customer_gstin=f"\nGSTIN: {c['data']['gstin'] or '-'}" if gst else ''
    title='PROPOSAL / QUOTATION' if proposal else 'TAX INVOICE' if inv['type']=='GST' else 'BILL OF SUPPLY'
    business=[p(b['name'],heading),Spacer(1,5),p(f"{b['address']}\n{b['state']} {b['pin']}\nPhone: {b['phone']} | {b['email']}{seller_gstin}")]
    if b['logo']: header=table([[image(b['logo']),business,p(title,right)]],[85,width-210,125])
    else: header=table([[business,p(title,right)]],[width-125,125])
    header.setStyle(TableStyle([('LINEBELOW',(0,0),(-1,-1),1.4,green)])); story.extend([header,Spacer(1,14)])
    details=f"{inv['number']}\nProposal date: {inv['date']}\nValid through: {inv['valid_until']}\nStatus: {inv['status']}" if proposal else f"{inv['number']}\nInvoice date: {inv['date']}\nInstallation: {s['installation'] or '-'}\nService: {s['service'] or '-'}\nStatus: {inv['status']}"
    parties=table([[p(f"{'PREPARED FOR' if proposal else 'BILL TO'}\n{c['name']}\n{c['data']['address']}\n{c['data']['state']} {c['data']['pin']}\nPhone: {c['data']['phone']}{customer_gstin}"),p(details,right)]],[width*.57,width*.43]); story.extend([parties,Spacer(1,14)])
    if proposal:
        story.extend([p(inv['title'],heading),p(inv.get('description','')),Spacer(1,12),p('Proposal only - not a tax invoice. No stock or payment has been recorded.'),Spacer(1,12)])
    headings=['#','Item / HSN' if gst else 'Item','Qty','Rate','MRP','Discount']+(['GST / Tax'] if gst else [])+['Amount']
    widths=[21,135,38,57,57,50]+([62] if gst else [])+[width-(21+135+38+57+57+50+(62 if gst else 0))]
    data=[[p(v) for v in headings]]
    for n,i in enumerate(inv['items'],1):
        values=[n,i['name']+ ('\n'+i['hsn'] if gst else ''),f"{i['quantity']/1000:g}\n{i['unit']}",f"{i['rate']/100:,.2f}",f"{i['mrp']/100:,.2f}",f"{i['discount']/100:,.2f}"]
        if gst: values.append(f"{i['gst']}%\n{i['tax']/100:,.2f}")
        values.append(f"{i['total']/100:,.2f}"); data.append([p(v) for v in values])
    story.extend([table(data,widths,True),Spacer(1,16)])
    totals=[]
    for label,key in [('Subtotal','subtotal'),('Discount','discount'),('Taxable amount' if gst else 'Total amount','taxable'),('CGST','cgst'),('SGST','sgst'),('IGST','igst'),('Grand total','total'),('Received','received'),('Balance due','balance')]:
        if proposal and key in ('received','balance'): continue
        if key in ('cgst','sgst','igst') and not inv[key]: continue
        totals.append([p(label),p(fmt(inv[key]),right)])
    total_table=table(totals,[145,120]); total_table.hAlign='RIGHT'; total_table.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5),('LINEABOVE',(0,-1 if proposal else -3),(-1,-1 if proposal else -3),.6,line),('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#edf4ef'))])); story.append(KeepTogether([total_table,Spacer(1,20)]))
    notes=[p('Terms & conditions'),Spacer(1,5),p(s['terms']),Spacer(1,10),p(f"Bank: {b['bank'] or '-'}\nUPI: {b['upi'] or '-'}")]
    signature=[]
    if b['signature']:
        img=image(b['signature'],130,60); img.hAlign='RIGHT'; signature.extend([img,Spacer(1,8)])
    else: signature.append(Spacer(1,35))
    signature.append(p(f"{b['signatory']}\nAuthorised Signatory\nFor {b['name']}",right))
    footer_table=table([[notes,signature]],[width*.6,width*.4]); footer_table.setStyle(TableStyle([('LINEABOVE',(0,0),(-1,0),.5,line)])); story.append(footer_table)
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8); canvas.setFillColor(colors.HexColor('#7a8780')); canvas.drawString(36,22,inv['number']); canvas.drawRightString(A4[0]-36,22,f'Page {doc.page}')
    SimpleDocTemplate(output,pagesize=A4,leftMargin=36,rightMargin=36,topMargin=32,bottomMargin=40,title=inv['number'],author=b['name']).build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
