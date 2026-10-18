from pathlib import Path
from html.parser import HTMLParser
from jinja2 import Environment, FileSystemLoader


class Options(HTMLParser):
    def __init__(self):
        super().__init__(); self.values=[]; self.selected=[]; self.groups=[]
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='option':
            self.values.append(attrs['value'])
            if 'selected' in attrs: self.selected.append(attrs['value'])
        if tag=='optgroup': self.groups.append(attrs['label'])


def options(selected):
    env=Environment(loader=FileSystemLoader(Path(__file__).resolve().parents[1]/'templates'),autoescape=True)
    parsed=Options();parsed.feed(env.get_template('indian_state_options.html').render(selected_state=selected));return parsed


def test_indian_states_are_complete_unique_and_keep_default():
    result=options('Tamil Nadu')
    assert len(result.values)==len(set(result.values))==36
    assert result.selected==['Tamil Nadu']
    assert result.groups==['States','Union territories']
    assert all(state in result.values for state in ['Arunachal Pradesh','Telangana','Ladakh','Delhi','Jammu and Kashmir','Dadra and Nagar Haveli and Daman and Diu'])


def test_legacy_state_is_preserved_on_edit():
    result=options('Tamil Nadu (Code 33)')
    assert len(result.values)==37
    assert result.selected==['Tamil Nadu (Code 33)']
