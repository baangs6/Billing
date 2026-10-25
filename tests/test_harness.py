from types import SimpleNamespace
import pytest
import test_app


def test_default_wsgi_import_uses_a_disposable_database():
    import app
    import conftest
    assert app.app.extensions['mongo'].name==conftest.BOOTSTRAP_DATABASE
    assert app.app.config['MONGODB_DATABASE'].startswith('ledger_test_bootstrap_')


def test_failed_database_setup_cleans_only_its_disposable_database(monkeypatch):
    removed=[];closed=[]
    def backend(uri,name):
        return SimpleNamespace(name=name,client=SimpleNamespace(drop_database=removed.append,close=lambda:closed.append(True)))
    def fail(backend): raise RuntimeError('Simulated setup failure')
    monkeypatch.setattr(test_app,'load_configuration',lambda:('unused-test-uri','unused'))
    monkeypatch.setattr(test_app,'MongoBackend',backend)
    monkeypatch.setattr(test_app,'initialize_saas',fail)
    with pytest.raises(RuntimeError,match='Simulated setup failure'):
        next(test_app.mongo_backend.__wrapped__(None))
    assert len(removed)==1 and removed[0].startswith('ledger_test_') and closed==[True]


@pytest.mark.parametrize('script',['admin_visual_review.py','proposal_visual_review.py','visual_review.py'])
def test_manual_qa_attempts_all_cleanup_after_failures(script):
    import ast
    from pathlib import Path
    source=ast.parse(Path(__file__).with_name(script).read_text(encoding='utf-8'))
    final=next(node.finalbody for node in source.body if isinstance(node,ast.Try))
    attempts=[]
    def fail(label):
        attempts.append(label);raise RuntimeError('Simulated '+label+' failure')
    class Fixture:
        def __next__(self): return fail('fixture')
    state=dict(generator=Fixture(),fixture=Fixture(),server=SimpleNamespace(close=lambda:fail('close'),task_dispatcher=SimpleNamespace(shutdown=lambda:attempts.append('shutdown'))),conftest=SimpleNamespace(pytest_sessionfinish=lambda *_:attempts.append('bootstrap')))
    with pytest.raises(RuntimeError): exec(compile(ast.Module(body=final,type_ignores=[]),script,'exec'),state)
    assert attempts[-2:]==['fixture','bootstrap']
    if script!='visual_review.py': assert attempts[:2]==['close','shutdown']


def test_imported_backend_aliases_use_the_canonical_session_store():
    store=object();requested=[]
    request=SimpleNamespace(getfixturevalue=lambda name:requested.append(name) or store)
    for _ in range(2):
        generator=test_app.mongo_backend.__wrapped__(request)
        assert next(generator) is store
        with pytest.raises(StopIteration): next(generator)
    assert requested==['shared_mongo_backend','shared_mongo_backend']
