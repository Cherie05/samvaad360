"""Representative extraction cases, including negation and speaker isolation."""

import pytest

from samvaad.signals import extract_signals


@pytest.mark.parametrize(
    "text,intent",
    [
        ("Borrower: I lost my job last week and cannot pay this month's EMI.", "financial hardship"),
        ("Borrower: Please provide the foreclosure statement. I want to transfer my balance.", "balance transfer or foreclosure"),
        ("Borrower: Do you have top-up options? I want to renovate my pharmacy.", "top-up or new loan interest"),
        ("Borrower: The service is terrible and your rate is too high.", "complaint about service or rate"),
        ("Borrower: I will pay the EMI on Friday.", "promise to pay"),
        ("Borrower: Please send my account statement.", "general query"),
        ("Borrower: Umm... I LOST my JOB!! uh cannot afford this month's EMI :(", "financial hardship"),
    ],
)
def test_representative_intents(text, intent):
    assert extract_signals(text)["intent"] == intent


@pytest.mark.parametrize(
    "text",
    [
        "Borrower: I have not lost my job. Please send my account statement.",
        "Borrower: I do not want to foreclose or transfer my balance. Just send a statement.",
        "Borrower: I am not interested in a top-up loan.",
    ],
)
def test_negated_signals_do_not_trigger_financial_actions(text):
    assert extract_signals(text)["intent"] == "general query"


def test_agent_speech_does_not_become_borrower_intent():
    text = "Agent: We help customers who lost their job and offer top-up loans.\nBorrower: Please send my account statement."
    signals = extract_signals(text)
    assert signals["intent"] == "general query"
    assert "lost their job" not in signals["evidence_text"]


def test_synthetic_agent_empathy_cannot_make_borrower_positive():
    text = "Agent: Thank you! We are happy to help and delighted to serve.\nBorrower: I am stressed and unhappy. I lost my job."
    signals = extract_signals(text)
    assert signals["intent"] == "financial hardship"
    sentiment = signals["sentiment"]
    assert sentiment < 0 if isinstance(sentiment, (int, float)) else sentiment.lower() == "negative"


def test_competitor_rate_extraction_keeps_numeric_evidence():
    signals = extract_signals(
        "Ananya: Brightline Bank offered to take over my loan at 10.75%. I am paying 14% with you."
    )
    assert signals["intent"] in ("balance transfer or foreclosure", "complaint about service or rate")
    assert "10.75" in str(signals["entities"])
    assert "Brightline" in str(signals["entities"])
