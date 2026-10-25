from copy import deepcopy
import pytest
import pymupdf
from sales_invoice_pdf import build_sales_invoice_pdf
from product_units import line_rate_amount,mrp_discount


def test_rate_amount_keeps_discount_out_and_rounds_exact_unit_rates():
    assert line_rate_amount(dict(rate=900000,quantity=1000,discount=30000,total=870000))==900000
    assert line_rate_amount(dict(rate=0,unit_rate_decimal='0.335',quantity=3000))==101


@pytest.mark.parametrize('theme',['A5','A4_CLASSIC','THERMAL_58','THERMAL_80'])
def test_item_amount_before_discount_and_total_after_discount(theme):
    inv=sample_invoice(theme)
    inv.update(discount=30000,taxable=870000,total=870000,balance=870000,subtotal=900000,common_discount=30000)
    inv['items'][0].update(quantity=1000,rate=900000,mrp=1000000,discount=30000,taxable=870000,total=870000)
    with pymupdf.open(stream=build_sales_invoice_pdf(inv),filetype='pdf') as document:
        text=''.join(page.get_text() for page in document)
        text=text.replace(',','')
        assert '9000.00' in text and '8700.00' in text and '300.00' in text


def sample_invoice(theme='A4_CLASSIC',layout='CLASSIC'):
    business=dict(name='Example Store',address='Market Road',phone='9876543210',email='',gstin='',state='Tamil Nadu',pin='',logo='',signature='',signatory='Owner',bank='Example Bank',upi='',extended=dict(invoice_theme=theme,thermal_layout=layout,show_previous_balance=True))
    return dict(number='INV/26-27/001',date='2026-10-02',status='FINAL',type='NON-GST',total=20000,subtotal=20000,taxable=20000,discount=0,cgst=0,sgst=0,igst=0,received=0,balance=20000,copy_label='DUPLICATE COPY',snapshot=dict(business=business,customer=dict(name='Example Customer',data=dict(address='Customer Road',state='Tamil Nadu',pin='',phone='',gstin='',shipping_address='Delivery address',pan='ABCDE1234F')),previous_balance=1000,eway_bill='123456789012',terms='Thank you.',notes='Deliver carefully.'),items=[dict(name='Desk lamp',description='',quantity=2000,rate=10000,mrp=12000,discount=0,unit='PCS',hsn='9405',gst='0',tax=0,taxable=20000,total=20000)])


@pytest.mark.parametrize('theme',['A5','A4_CLASSIC','A4_SIMPLE','A4_ADVANCED'])
@pytest.mark.parametrize('gst',[False,True])
def test_mrp_discount_and_selling_amount_without_rate_column(theme,gst):
    inv=sample_invoice(theme)
    if gst: inv['type']='GST'
    inv['items'][0]['rate']=9876
    inv['items'].append(dict(name='Service charge',is_charge=True,quantity=1000,rate=5000,mrp=0,discount=0,unit='CHARGE',hsn='9987',gst='0',tax=0,taxable=5000,total=5000))
    with pymupdf.open(stream=build_sales_invoice_pdf(inv),filetype='pdf') as document:
        text=''.join(page.get_text() for page in document)
        assert 'RATE' not in text and '197.52' in text and '120.00' in text and '(17.70% OFF)' in text
        for page in document:
            assert all(block[0]>=0 and block[2]<=page.rect.width+1 for block in page.get_text('blocks'))


@pytest.mark.parametrize('theme',['THERMAL_58','THERMAL_80'])
@pytest.mark.parametrize('layout',['COMPACT','SIMPLE','CLASSIC','ADVANCED'])
def test_thermal_layouts_and_duplicate_fit_paper(theme,layout):
    inv=sample_invoice(theme,layout);before=deepcopy(inv)
    with pymupdf.open(stream=build_sales_invoice_pdf(inv),filetype='pdf') as document:
        text=''.join(page.get_text() for page in document)
        assert 'DUPLICATE COPY' in text and '123456789012' in text and 'Delivery address' in text
        assert 'Previous balance' in text and 'Desk lamp' in text
        assert document[0].rect.width==(164 if theme=='THERMAL_58' else 227)
        for page in document:
            for block in page.get_text('blocks'):
                assert block[0]>=0 and block[2]<=page.rect.width+1
    assert inv==before


@pytest.mark.parametrize('theme',['A5','A4_CLASSIC','A4_SIMPLE','A4_ADVANCED','THERMAL_58','THERMAL_80'])
def test_custom_headers_and_uploaded_identity_images(theme):
    import io,base64
    from PIL import Image
    blob=io.BytesIO();Image.new('RGB',(160,60),'blue').save(blob,format='PNG')
    asset='data:image/png;base64,'+base64.b64encode(blob.getvalue()).decode()
    inv=sample_invoice(theme);business=inv['snapshot']['business']
    business.update(logo=asset,signature=asset)
    business['extended']['custom_headers']=[dict(name='Alt number',value='555-0123')]
    before=deepcopy(inv)
    with pymupdf.open(stream=build_sales_invoice_pdf(inv),filetype='pdf') as document:
        assert '555-0123' in ''.join(page.get_text() for page in document)
        assert any(page.get_images() for page in document)
    assert inv==before


@pytest.mark.parametrize('theme',['A5','A4_CLASSIC','A4_SIMPLE','A4_ADVANCED','THERMAL_58','THERMAL_80'])
@pytest.mark.parametrize('amount',[0,-49])
def test_optional_totals_hide_zero_and_keep_nonzero(theme,amount):
    inv=sample_invoice(theme)
    inv.update(round_off=amount,credit=abs(amount),refunded=abs(amount))
    with pymupdf.open(stream=build_sales_invoice_pdf(inv),filetype='pdf') as document:
        text=''.join(page.get_text() for page in document)
        for label in ('Round off','Credit notes','Refunded'):
            assert (label in text)==bool(amount),(theme,label,text)


def test_mrp_discount_ignores_common_discount_and_handles_missing_mrp():
    assert mrp_discount(dict(mrp=1000000,rate=900000,discount=30000))=='10.00'
    assert mrp_discount(dict(mrp=0,rate=900000))=='0.00'
    assert mrp_discount(dict(mrp=100,rate=0,unit_rate_decimal='0.333333333'))=='66.67'
