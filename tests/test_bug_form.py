"""The bug report form asks for every option the setup page can turn on or off."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORM = (ROOT / ".github/ISSUE_TEMPLATE/bug_report.yml").read_text()
PAGE = (ROOT / "web/index.html").read_text()


def block(block_id):
    # the form's body item with this id, up to the next item
    m = re.search(rf"^  - type: \w+\n    id: {block_id}\n(.*?)(?=^  - type:|\Z)", FORM, re.M | re.S)
    assert m, f"no {block_id} block in bug_report.yml"
    return m.group(0)


def test_every_page_option_is_a_checkbox():
    page = set(re.findall(r'data-(?:dsp|option)="(HX_\w+)"', PAGE))
    assert page, "no feature options found in web/index.html"
    enabled = block("enabled")
    assert "type: checkboxes" in enabled
    form = set(re.findall(r"- label: .*\((HX_\w+)\)", enabled))
    assert form == page


def test_nam_slots_match_the_page():
    page = re.findall(r'name="slots" value="(\d)"', PAGE)
    form = re.findall(r'^        - "(\w+)"$', block("nam-slots"), re.M)
    assert form == page + ["Off"]
