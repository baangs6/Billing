from copy import deepcopy
import pytest
import pymupdf
from test_thermal_layouts import sample_invoice
from ledger_invoice_pdf import build_ledger_invoice_pdf
from test_app import mongo_backend,workspace,payload


@pytest.mark.parametrize('count',[1,12,60])
@pytest.mark.parametrize('gst',[False,True])
def test_clean_default_fits_one_page_preserves_every_item_and_totals(count,gst):
    inv=sample_invoice('A4_LEDGER')
    if gst: inv['type']='GST'
    inv['items']=[dict(inv['items'][0],name='Filter replacement '+str(n)) for n in range(count)]
    inv.update(round_off=0,credit=0,refunded=0)
    before=deepcopy(inv)
    with pymupdf.open(stream=build_ledger_invoice_pdf(inv),filetype='pdf') as document:
        assert len(document)==1
        page=document[0];text=page.get_text()
        assert 'Grand total' in text and 'For Example Store' in text
        for n in range(count): assert 'Filter replacement '+str(n) in text
        for absent in ['127.0.0.1','Invoice details','Page 1','Round off','Credit notes','Refunded']: assert absent not in text
        assert 'RATE' not in text and 'MRP' in text
        assert all(block[0]>=0 and block[2]<=page.rect.width+1 and block[3]<=page.rect.height for block in page.get_text('blocks'))
    assert inv==before


def test_download_defaults_to_clean_a4_and_saved_format_remains_available(workspace):
    client,post,backend=workspace
    post('/business-profile',dict(invoice_theme='THERMAL_58',payment_details='BOTH'))
    post('/billing',payload())
    before=backend.database.invoices.find_one({})
    for url in ['/invoices/1/pdf','/invoices/1/pdf?preview=1']:
        response=client.get(url);assert response.status_code==200
        with pymupdf.open(stream=response.data,filetype='pdf') as document:
            assert len(document)==1 and document[0].rect.width>590
    with pymupdf.open(stream=client.get('/invoices/1/pdf?format=saved').data,filetype='pdf') as document:
        assert document[0].rect.width==164
    for suffix in ('','&preview=1'):
        response=client.get('/invoices/1/pdf?format=thermal80'+suffix)
        assert response.status_code==200
        assert response.headers['Content-Disposition'].startswith('inline' if suffix else 'attachment')
        with pymupdf.open(stream=response.data,filetype='pdf') as document:
            assert document[0].rect.width==227
            assert 'Desk lamp' in ''.join(page.get_text() for page in document)
    assert backend.database.invoices.find_one({})==before
    assert b'data-pdf-url="/invoices/1/pdf?preview=1"' in client.get('/invoices/1').data
