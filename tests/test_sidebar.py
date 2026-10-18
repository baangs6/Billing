from pathlib import Path
import re
from jinja2 import Environment, FileSystemLoader


def render(nav, active):
    environment = Environment(loader=FileSystemLoader(Path(__file__).resolve().parents[1] / 'templates'), autoescape=True)
    environment.globals['url_for'] = lambda endpoint: '/' + endpoint
    return environment.get_template('sidebar.html').render(nav=[(endpoint, endpoint, '') for endpoint in nav], active_section=active)


def test_sidebar_keeps_every_link_once_and_opens_current_category():
    endpoints = ['dashboard','billing','proposals','invoices','sales_returns_page','service_reminders_page','customers','suppliers_page','purchases_page','products','inventory','payments','finance_page','reports','settings_page','company_users','company_roles','subscription_page']
    html = render(endpoints, 'finance_page')
    assert sorted(re.findall(r'href="/([^" ]+)"', html)) == sorted(endpoints)
    assert len(re.findall(r'<details', html)) == 5
    assert len(re.findall(r'<details[^>]*\bopen', html)) == 1
    assert re.search(r'<details[^>]*open[^>]*>\s*<summary>Money', html)


def test_sidebar_only_groups_authorized_links_and_hides_empty_groups():
    html = render(['subscription_page'], 'subscription_page')
    assert re.findall(r'href="/([^" ]+)"', html) == ['subscription_page']
    assert len(re.findall(r'<details', html)) == 1
    assert '<summary>Administration' in html
    assert '<summary>Sales' not in html
