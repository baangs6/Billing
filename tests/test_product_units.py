from decimal import Decimal,ROUND_HALF_UP
import pytest
from product_units import line_units,line_pricing,default_rate,return_stock_quantity,rate_decimal


def qty(value): return int(Decimal(str(value))*1000)
def rounded(value): return int(Decimal(value).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
def money(value): return rounded(Decimal(value)*100)


def test_alternate_units_and_historical_return_conversion():
    product=dict(selling_price=10000,data=dict(unit='PCS',alternate_unit='BOX',alternate_factor='10',wholesale_price=8000))
    units=line_units(dict(quantity='2',unit_choice='ALT'),product,qty)
    assert units['stock_quantity']==20000 and units['unit']=='BOX'
    assert default_rate(product,'WHOLESALE','10')==Decimal('800')
    price=line_pricing(dict(gst='18'),product,units,'GST',money,rounded)
    assert price['base_amount']==200000
    assert return_stock_quantity(units,500)==5000
    product['data']['alternate_factor']='12'
    assert return_stock_quantity(units,1000)==10000


def test_sub_paise_rate_preserves_whole_line_amount():
    product=dict(selling_price=1,data=dict(unit='KG',alternate_unit='G',alternate_factor='0.001'))
    units=line_units(dict(quantity='1000',unit_choice='ALT'),product,qty)
    price=line_pricing(dict(gst='0'),product,units,'NON-GST',money,rounded)
    assert units['stock_quantity']==1000 and price['rate']==0 and price['base_amount']==1
    assert Decimal(price['unit_rate_decimal'])==Decimal('0.00001')
    with pytest.raises(ValueError): line_units(dict(quantity='0.1',unit_choice='ALT'),product,qty)


def test_inclusive_gross_and_legacy_rate_rounding():
    units=line_units(dict(quantity='2'),None,qty)
    inclusive=line_pricing(dict(rate='118',gst='18',pricing_mode='INCLUSIVE'),None,units,'GST',money,rounded)
    assert inclusive['rate']==11800 and inclusive['base_amount']==20000 and inclusive['included_tax']==3600
    assert line_pricing(dict(rate='1.005'),None,units,'NON-GST',money,rounded)['base_amount']==202
    assert line_pricing(dict(unit_rate_decimal='1.005'),None,units,'NON-GST',money,rounded)['base_amount']==201
    assert rate_decimal('0.10000000000000000000000000000')==Decimal('0.1')
    assert rate_decimal('0e-1000000000').as_tuple().exponent==0
    assert line_pricing(dict(unit_rate_decimal='0e-1000000000'),None,units,'GST',money,rounded)['unit_rate_decimal']=='0'
    for value in ['NaN','Infinity','-1','0.0000000001','0.10000000000000000000000000001','0.'+'1'*101]:
        with pytest.raises(ValueError): line_pricing(dict(rate=value),None,units,'GST',money,rounded)


def test_service_units_do_not_create_physical_stock():
    product=dict(selling_price=10000,data=dict(kind='SERVICE',unit='HOUR',alternate_unit='DAY',alternate_factor='7.5'))
    units=line_units(dict(quantity='0.001',unit_choice='ALT'),product,qty)
    assert units['stock_quantity']==0 and return_stock_quantity(units,1)==0
    assert line_pricing({},product,units,'NON-GST',money,rounded)['base_amount']==75


def test_browser_default_rate_conversion_is_decimal_exact():
    import subprocess
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/'static/app.js').read_text(encoding='utf-8')
    helper=source[source.index('function convertedUnitRate('):source.index('\nif(dataElement)')]
    subprocess.run(['node','-e',helper+"\nconst assert=require('node:assert/strict');assert.equal(convertedUnitRate(29,'0.1'),'0.029');assert.equal(convertedUnitRate(10000,'10'),'1000');assert.equal(convertedUnitRate(1,'0.001'),'0.00001');assert.equal(convertedUnitRate(0,'1'),'0');"],check=True,capture_output=True,text=True)


def test_product_photo_is_bounded_and_metadata_removed():
    import io,base64
    from PIL import Image
    from werkzeug.datastructures import FileStorage
    from product_media import thumbnail
    source=io.BytesIO();Image.new('RGB',(500,300),'blue').save(source,format='JPEG',comment=b'private metadata')
    encoded=thumbnail(FileStorage(stream=io.BytesIO(source.getvalue()),filename='photo.jpg'))
    image=Image.open(io.BytesIO(base64.b64decode(encoded)))
    assert image.size==(320,192) and not image.getexif() and b'private metadata' not in base64.b64decode(encoded)
    for content in [b'<svg>untrusted</svg>',b'x'*(2*1024*1024+1)]:
        with pytest.raises(ValueError): thumbnail(FileStorage(stream=io.BytesIO(content),filename='photo.jpg'))


def test_upi_qr_preserves_the_last_paisa():
    from urllib.parse import urlsplit,parse_qs
    from sales_invoice_pdf import upi_qr
    drawing=upi_qr(dict(upi='test-merchant@upi',name='Test merchant'),8999999999910001)
    value=drawing.contents[0].value
    assert parse_qs(urlsplit(value).query)['am']==['89999999999100.01']
