"""Extraction and classification on real World Bank India procurement notices (tests/fixtures/real_notices)."""

from pathlib import Path

import pytest

from app.restructuring.classifier import classify
from app.restructuring.components import items_from_documents

FIX = Path(__file__).parent / "fixtures" / "real_notices"


def _items(notice_id: str, title: str | None = None) -> list[dict]:
    pages = [(f"DOC-{notice_id}", 1, (FIX / f"{notice_id}.txt").read_text())]
    items, _ = items_from_documents(pages, title=title)
    return items


def _texts(items: list[dict]) -> str:
    return "\n".join(i["text"] for i in items).lower()


def test_millet_plant_line_items_are_extracted():
    items = _items("OP00474853")
    texts = _texts(items)
    for expected in ("primary processing line for millets", "continuous milling line", "cold extrusion line",
                     "cookies making line", "flaking line", "vacuum packing machine", "band sealing machine",
                     "platform weighing scale"):
        assert expected in texts, expected
    assert any(i["source"] == "line_item" for i in items)


@pytest.mark.parametrize("notice_id,junk", [
    ("OP00474853", ["received financing", "project implementation unit"]),
    ("OP00471901", ["construction period", "mobile no", "e-mail", "ifsc"]),
])
def test_boilerplate_is_not_a_work_item(notice_id, junk):
    texts = _texts(_items(notice_id))
    for phrase in junk:
        assert phrase not in texts, phrase


def test_metro_contract_title_is_the_scope():
    texts = _texts(_items("OP00471901"))
    assert "construction of viaduct and elevated stations" in texts


def test_substation_name_of_work_is_found_and_electrical():
    items = _items("OP00464558")
    work = [i for i in items if "132 kv gis" in i["text"].lower()]
    assert work, "the quoted 'Detail of Work' must become a scope item"
    assert work[0]["capability"] == "electrical"


def test_tender_title_counts_as_scope_when_document_has_none():
    items, _ = items_from_documents([("D", 1, "Bids must be submitted online.")],
                                    title="Supply and installation of 33 kV switchgear panels")
    assert [i["source"] for i in items] == ["title"]


def test_food_processing_machinery_has_its_own_capability():
    preds = classify(["Primary Processing Line for Millets (Vibro-Grader cum Aspirator, Destoner, dehuller)",
                      "Vacuum Packing Machine", "Cookies Making Line (rotary rack oven)", "Continuous Milling Line (Chakki mill and Roller mill)"])
    assert [p[0] for p in preds] == ["industrial_machinery"] * 4
