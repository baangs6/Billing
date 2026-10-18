"""Exact selected-unit pricing and primary-unit stock quantities for document lines."""
from decimal import Decimal, InvalidOperation, localcontext


def rate_decimal(value):
    if len(str(value))>100: raise ValueError('Unit rates must contain at most 100 characters.')
    try: result=Decimal(str(value))
    except (InvalidOperation,TypeError): raise ValueError('Enter a valid unit rate.')
    if not result.is_finite() or not 0<=result<=1_000_000_000:
        raise ValueError('Unit rates support up to nine decimal places and must be non-negative.')
    if not result: return Decimal(0)
    digits=result.as_tuple().digits
    trailing=len(digits)-len(''.join(map(str,digits)).rstrip('0'))
    if result and -result.as_tuple().exponent-trailing>9:
        raise ValueError('Unit rates support up to nine decimal places and must be non-negative.')
    return result


def line_units(raw,product,quantity,original=None):
    data=product['data'] if product else {}
    choice=raw.get('unit_choice','PRIMARY')
    if choice not in ('PRIMARY','ALT'): raise ValueError('Choose a primary or alternate unit.')
    factor=Decimal(1)
    unit=str(data.get('unit') or raw.get('unit') or 'PCS').strip()
    if choice=='ALT':
        saved=original if original and original.get('product_id')==(product or {}).get('id') and original.get('unit_choice')=='ALT' else None
        unit=str(saved['unit'] if saved else data.get('alternate_unit') or '').strip()
        factor=rate_decimal(saved['unit_factor'] if saved else data.get('alternate_factor') or '0')
        if not unit or not 0<factor<=1_000_000: raise ValueError('Configure an alternate unit and conversion factor first.')
    if not unit or len(unit)>30: raise ValueError('Unit names must contain 1 to 30 characters.')
    displayed=quantity(raw.get('quantity'))
    primary=Decimal(displayed)*factor
    service=data.get('kind')=='SERVICE'
    if not service and (primary!=primary.to_integral_value() or not 0<primary<=100_000_000_000):
        raise ValueError('This quantity cannot be represented in primary units with three decimal places.')
    return dict(quantity=displayed,stock_quantity=0 if service else int(primary),unit=unit,primary_unit=data.get('unit') or unit,unit_choice=choice,unit_factor=format(factor,'f'),is_service=service)


def default_rate(product,tier='RETAIL',factor='1'):
    if tier not in ('RETAIL','WHOLESALE'): raise ValueError('Choose retail or wholesale pricing.')
    wholesale=product['data'].get('wholesale_price')
    amount=wholesale if tier=='WHOLESALE' and wholesale is not None else product['selling_price']
    return rate_decimal(Decimal(amount)/100*Decimal(str(factor)))


def line_pricing(raw,product,units,kind,money,rounded):
    data=product['data'] if product else {}
    mode=raw.get('pricing_mode',data.get('pricing_mode','EXCLUSIVE'))
    tier=raw.get('price_tier','RETAIL')
    if tier not in ('RETAIL','WHOLESALE'): raise ValueError('Choose retail or wholesale pricing.')
    if mode not in ('INCLUSIVE','EXCLUSIVE'): raise ValueError('Choose inclusive or exclusive prices.')
    if kind!='GST': mode='EXCLUSIVE'
    value=raw.get('unit_rate_decimal',raw.get('rate'))
    if value is None or value=='':
        if not product: raise ValueError('Enter an item rate.')
        value=default_rate(product,tier,units['unit_factor'])
    entered=rate_decimal(value)
    # Old callers round per-unit paise first; new unit/precision fields opt in to exact sub-paise rates.
    if 'unit_rate_decimal' not in raw and units['unit_choice']=='PRIMARY' and mode=='EXCLUSIVE': entered=Decimal(money(entered))/100
    with localcontext() as context:
        context.prec=40
        gross=rounded(entered*units['quantity']/10)
    rate=Decimal(str(raw.get('gst','0')))
    if not rate.is_finite() or not 0<=rate<=100: raise ValueError('Choose a valid GST rate.')
    result=dict(rate=money(entered),unit_rate_decimal=format(entered,'f'),base_amount=gross,pricing_mode=mode,price_tier=tier)
    if mode=='INCLUSIVE':
        base=rounded(Decimal(gross)*100/(100+rate))
        result.update(base_amount=base,included_tax=gross-base)
    return result


def primary_quantity(item):
    return item.get('stock_quantity',item['quantity'])


def rate_text(item):
    if 'unit_rate_decimal' not in item: return f"{item['rate']/100:,.2f}"
    value=rate_decimal(item['unit_rate_decimal'])
    return f'{value:,.9f}'.rstrip('0').rstrip('.')


def return_stock_quantity(item,returned_quantity):
    if not 0<returned_quantity<=item['quantity']: raise ValueError('Return quantity exceeds the original line.')
    stock=Decimal(primary_quantity(item))*returned_quantity/item['quantity']
    if stock!=stock.to_integral_value(): raise ValueError('Return quantity is below primary-unit stock precision.')
    return int(stock)


def product_options(raw,data,money):
    result=dict(data)
    for field,choices in [('kind',('STOCK','SERVICE')),('pricing_mode',('EXCLUSIVE','INCLUSIVE'))]:
        value=raw.get(field,result.get(field,choices[0]))
        if value not in choices: raise ValueError('Choose a valid product '+field.replace('_',' ')+'.')
        result[field]=value
    if 'wholesale_price' in raw: result['wholesale_price']=money(raw['wholesale_price']) if raw['wholesale_price'].strip() else None
    if 'alternate_unit' in raw:
        unit=raw['alternate_unit'].strip()
        if len(unit)>30 or unit and unit.casefold()==result.get('unit','').casefold(): raise ValueError('Choose a different alternate unit, up to 30 characters.')
        factor=rate_decimal(raw.get('alternate_factor') or '0')
        if unit and not 0<factor<=1_000_000: raise ValueError('Enter primary units per alternate unit, greater than zero and at most 1000000.')
        result.update(alternate_unit=unit,alternate_factor=format(factor if unit else Decimal(0),'f'))
    return result
