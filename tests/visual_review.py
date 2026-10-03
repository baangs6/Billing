"""Render a PDF using disposable Atlas test records; never uses live business data."""
import sys
import importlib.util
from pathlib import Path
import pymupdf
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
spec=importlib.util.spec_from_file_location('test_app',Path(__file__).with_name('test_app.py'))
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
fixture=module.mongo_backend.__wrapped__(); backend=next(fixture)
try:
    client,post,_=module.workspace.__wrapped__(backend)
    post('/billing',module.payload())
    post('/payments',dict(invoice='1',amount='100',date='2026-10-02',method='UPI',reference='QA-001'))
    pdf=client.get('/invoices/1/pdf').data
    root=Path('tmp/review'); root.mkdir(parents=True,exist_ok=True)
    (root/'invoice.pdf').write_bytes(pdf)
    doc=pymupdf.open(stream=pdf,filetype='pdf')
    for n,page in enumerate(doc): page.get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(root/f'invoice-{n+1}.png')
    print('MongoDB PDF rendered. Pages:',len(doc))
finally:
    try: next(fixture)
    except StopIteration: pass
