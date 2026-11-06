"""Headless Streamlit tests (Streamlit AppTest) for the simple editor-friendly UI."""
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

import ui_config as C  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "app.py")
SAMPLE1 = "Sample story 1 (timestamps in blocks)"


def _at() -> AppTest:
    return AppTest.from_file(APP, default_timeout=60)


def _goto(at: AppTest, page: str):
    at.session_state["page_choice"] = page
    at.run()


def _text(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


def _loaded() -> AppTest:
    at = _at().run()
    assert not at.exception
    at.selectbox(key="sample_pick").set_value(SAMPLE1).run()
    at.button(key="run_btn").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state["res"] is not None
    return at


# ---------------------------------------------------------------- first page

def test_first_page_has_project_name_and_plain_description_and_no_technical_boxes():
    at = _at().run()
    assert not at.exception
    t = _text(at)
    assert C.APP_NAME in t and "ranks them from best to worst" in t
    assert at.session_state["page_choice"] == "Upload & Analyze"
    assert len(at.text_input) == 0                       # no Model / API key / Base URL / saved-run boxes
    assert len(at.number_input) == 0 and len(at.slider) == 0   # promo count and call budget are automatic
    for word in ("saved run", "Base URL", "Model", "budget", "heuristic", "None"):
        assert word not in t


def test_ai_dropdown_lists_rule_based_first_and_never_says_none():
    at = _at().run()
    opts = at.selectbox(key="ai_choice").options
    assert "Rule-based" in opts[0] and "Gemini" in opts[1]
    assert any("OpenAI" in o for o in opts) and any("Claude" in o for o in opts)
    assert not any("none" in o.lower() for o in opts)


def test_only_seven_pages_and_no_evaluation_page():
    at = _at().run()
    pages = at.radio(key="page_choice").options
    assert len(pages) == 7 and not any("Evaluation" in x for x in pages) and pages[1].endswith("Dashboard")


def test_run_without_files_or_sample_asks_politely():
    at = _at().run()
    at.button(key="run_btn").click().run()
    assert not at.exception
    assert any("Add your episodes first" in w.value for w in at.warning)
    assert "res" not in at.session_state or at.session_state["res"] is None


def test_sample_run_lands_on_dashboard_in_rule_based_mode():
    at = _loaded()
    assert at.session_state["page_choice"] == "Dashboard"
    res = at.session_state["res"]
    assert len(res.promos) >= 4 and res.report["mode"].startswith("rules-only")
    t = _text(at)
    assert "What's here" in t and "Rule-based" in t and "Top picks" in t


# ---------------------------------------------------------------- every page

def test_every_page_renders_and_opens_with_a_whats_here_line():
    at = _loaded()
    for name, _icon, intro in C.PAGES[1:]:
        _goto(at, name)
        assert not at.exception, f"{name}: {[e.value for e in at.exception]}"
        t = _text(at)
        assert "What's here" in t and intro.split(":")[0][:25] in t, name


def test_pages_before_a_run_show_a_friendly_empty_state():
    at = _at().run()
    for name in ("Dashboard", "Promo Discovery", "Export"):
        _goto(at, name)
        assert not at.exception
        assert "Nothing to show yet" in _text(at)


def test_promo_cards_use_plain_language():
    at = _loaded()
    _goto(at, "Promo Discovery")
    t = _text(at)
    assert "Opens with" in t and "Cuts on" in t and "Why it works" in t
    assert any(w in t for w in ("Strong pick", "Good pick", "Double-check"))
    assert "heuristic" not in t.lower() and "scores: " not in t


def test_promo_cards_have_no_keep_skip_buttons_but_review_page_does():
    at = _loaded()
    _goto(at, "Promo Discovery")
    keys = {b.key for b in at.button}
    assert not any(str(k).startswith(("keep_", "skip_")) for k in keys)
    _goto(at, "Editorial Review")
    assert "rv_ok" in {b.key for b in at.button}


def test_review_page_keep_then_export_has_the_decision():
    at = _loaded()
    _goto(at, "Editorial Review")
    at.button(key="rv_ok").click().run()
    assert not at.exception
    assert list(at.session_state["reviews"].values())[0]["status"] == "approved"
    _goto(at, "Export")
    assert not at.exception and len(at.get("download_button")) >= 2


def test_edit_to_10_seconds_is_rejected_with_clear_message():
    at = _loaded()
    _goto(at, "Editorial Review")
    pid = at.session_state["rev_pick"]
    p = next(p for p in at.session_state["res"].promos if p.promo_id == pid)
    at.number_input(key=f"ee_{pid}").set_value(p.segments[0].start + 10.0).run()
    at.button(key="edit_btn").click().run()
    assert any("below the 20s minimum" in e.value for e in at.error)
    assert "edit" not in at.session_state["reviews"].get(pid, {})


def test_valid_edit_is_accepted():
    at = _loaded()
    _goto(at, "Editorial Review")
    pid = at.session_state["rev_pick"]
    p = next(p for p in at.session_state["res"].promos if p.promo_id == pid)
    at.button(key="edit_btn").click().run()
    assert any("Edit accepted" in s.value for s in at.success)
    assert at.session_state["reviews"][pid]["edit"]["start"] == pytest.approx(p.segments[0].start)


# ---------------------------------------------------------------- AI choices and the key pop-up

def test_paid_ai_without_key_does_not_run_and_does_not_crash():
    at = _at().run()
    at.selectbox(key="sample_pick").set_value(SAMPLE1).run()
    at.selectbox(key="ai_choice").set_value("claude").run()
    assert not at.exception
    at.button(key="run_btn").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert "res" not in at.session_state or at.session_state["res"] is None      # nothing ran without a key


def test_gemini_without_any_key_does_not_run_and_does_not_crash(monkeypatch):
    monkeypatch.delenv("PROMOFORGE_API_KEY", raising=False)
    at = _at().run()
    at.selectbox(key="sample_pick").set_value(SAMPLE1).run()
    at.selectbox(key="ai_choice").set_value("gemini").run()
    at.button(key="run_btn").click().run()
    assert not at.exception
    assert "res" not in at.session_state or at.session_state["res"] is None


def test_selection_survives_visiting_another_page():
    at = _loaded()
    _goto(at, "Upload & Analyze")
    assert at.selectbox(key="ai_choice").value == "rules"


def test_free_limit_reached_shows_message_and_own_key_button():
    from promoforge.llm_provider import Settings
    from promoforge.pipeline import run_pipeline
    sample = Path(__file__).resolve().parent.parent / "sample_data" / "story_labelled"
    res = run_pipeline(input_path=sample, settings=Settings(provider="mock", model="mock-quota", rpm=6000), top_n=5)
    at = _at().run()
    at.session_state["res"] = res
    _goto(at, "Dashboard")
    assert not at.exception
    assert any("free AI limit is finished" in w.value for w in at.warning)
    assert at.button(key="dash_ownkey") is not None


def test_dashboard_tiles_show_checked_times():
    at = _loaded()
    assert "Times double-checked" in _text(at)
