from test_app import mongo_backend,workspace
from saas import Platform

def test_public_home_and_protected_company_routes(workspace):
    owner=workspace[0];guest=owner.application.test_client()
    for route in ('/','/home'):
        response=guest.get(route)
        assert response.status_code==200
        assert b'Customer login' in response.data and b'Beautifully in balance.' in response.data
        assert b'href="/login"' in response.data and b'href="/register"' in response.data
        assert b'Acme Electronics' not in response.data and b'owner@example.com' not in response.data
        assert b'Illustrative product preview' in response.data
    for route in ('/billing','/invoices','/customers','/products','/proposals','/subscription'):
        assert guest.get(route).headers['Location']=='/login'
    assert b'Business overview' in owner.get('/').data
    assert b'Beautifully in balance.' in owner.get('/home').data

def test_home_live_plans_registration_policy_and_plan_selection(workspace):
    owner,post,backend=workspace;platform=Platform(backend)
    plan=backend.database.plans.find_one({'active':True})
    platform.transaction(lambda ms,store:backend.database.plans.update_one({'id':plan['id']},{'$set':{'name':'Growth','monthly_price':49900}},session=ms))
    guest=owner.application.test_client();response=guest.get('/home')
    assert b'Growth' in response.data and '₹499.00'.encode() in response.data
    registration=guest.get('/register',query_string={'plan_id':plan['id']})
    assert f'value="{plan["id"]}" selected'.encode() in registration.data
    platform.transaction(lambda ms,store:backend.database.platform_settings.update_one({'_id':'policy'},{'$set':{'registration_open':False}},session=ms))
    response=guest.get('/home')
    assert b'href="/register' not in response.data
    assert b'New registrations are currently closed' in response.data
    assert b'href="/login"' in response.data
