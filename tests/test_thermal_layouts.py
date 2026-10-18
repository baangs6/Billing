from copy import deepcopy
import pytest
import pymupdf
from sales_invoice_pdf import build_sales_invoice_pdf


def sample_invoice(theme='A4_CLASSIC',layout='CLASSIC'):
    business=dict(name='Example Store',address='Market Road',phone='9876543210',email='',gstin='',state='Tamil Nadu',pin='',logo='',signature='',signatory='Owner',bank='Example Bank',upi='',extended=dict(invoice_theme=theme,thermal_layout=layout,show_previous_balance=True))
    return dict(number='INV/26-27/001',date='2026-10-02',status='FINAL',type='NON-GST',total=20000,subtotal=20000,taxable=20000,discount=0,cgst=0,sgst=0,igst=0,received=0,balance=20000,copy_label='DUPLICATE COPY',snapshot=dict(business=business,customer=dict(name='Example Customer',data=dict(address='Customer Road',state='Tamil Nadu',pin='',phone='',gstin='',shipping_address='Delivery address',pan='ABCDE1234F')),previous_balance=1000,eway_bill='123456789012',terms='Thank you.',notes='Deliver carefully.'),items=[dict(name='Desk lamp',description='',quantity=2000,rate=10000,mrp=12000,discount=0,unit='PCS',hsn='9405',gst='0',tax=0,taxable=20000,total=20000)])


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
