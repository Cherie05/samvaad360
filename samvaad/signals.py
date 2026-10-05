"""Transparent offline signal extraction; this is not a live LLM provider.

Only customer/borrower speech is considered when a transcript has speaker labels.
The rules are deliberately inspectable and conservatively handle common negation.
Snowflake Cortex will replace this provider after local acceptance checks.
"""
import hashlib
import re

VERSION = "local-rules-v1"
INTENTS = (
    "financial hardship", "balance transfer or foreclosure",
    "top-up or new loan interest", "complaint about service or rate",
    "promise to pay", "general query",
)


def borrower_text(text: str) -> str:
    # Turns may be separated by newlines or the PRD's em-dash notation.
    turns = re.split(r"\n|\s+[—–]\s+", text)
    speaker_pattern = re.compile(r"^\s*([\w .'-]{1,40}):\s*(.*)$")
    labelled = []
    found_agent = False
    for turn in turns:
        match = speaker_pattern.match(turn)
        if match:
            speaker, content = match.groups()
            if speaker.strip().lower() in {"agent", "bot", "samvaad", "officer", "support", "assistant"}:
                found_agent = True
            else:
                labelled.append(content)
        elif turn.strip():
            labelled.append(turn.strip())
    return " ".join(labelled).strip() if found_agent else text.strip()


def extract_signals(text: str) -> dict:
    evidence = borrower_text(text or "")
    low = evidence.lower()
    negated_hardship = bool(re.search(
        r"(?:did not|didn't|have not|haven't|not|never)\s+(?:lose|lost|laid off|been laid off|unemployed)", low
    ) or re.search(r"(?:no|not facing)\s+(?:financial )?hardship", low))
    hardship = (not negated_hardship and bool(re.search(
        r"laid off|lost (?:my |the )?job|job loss|unemployed|medical emergency|business slowdown|business loss|cannot afford|can't afford", low
    )))
    negated_transfer = bool(re.search(r"(?:not|no longer|don't|do not)\s+(?:want(?:ing)? to |planning to |intend to )?(?:transfer|foreclos|switch)", low))
    transfer = not negated_transfer and bool(re.search(r"foreclosure|balance transfer|take over my loan|switch lenders|why should i stay", low))
    negated_topup = bool(re.search(r"(?:not interested|no interest|don't need|do not need|no need).*?(?:top.?up|new loan)", low))
    topup = not negated_topup and bool(re.search(r"top[ -]?up|new loan|renovat|expand (?:my |the )?(?:shop|business)|education loan", low))
    complaint = bool(re.search(r"complaint|frustrat|unhappy|stressed|hurry|why should i stay|no update|any update|too high|poor service", low))
    promise = bool(re.search(r"i (?:will|can) pay|pay next week|promise to pay", low))
    intent = (INTENTS[0] if hardship else INTENTS[1] if transfer else INTENTS[2] if topup
              else INTENTS[3] if complaint else INTENTS[4] if promise else INTENTS[5])
    negative = len(re.findall(r"stressed|frustrat\w*|unhappy|hard|hurry|bounced|lost|laid off|why should i stay|poor", low))
    positive = len(re.findall(r"thank\w*|excellent|happy|helpful|great", low))
    sentiment = round(max(-1.0, min(1.0, 0.20 * positive - 0.24 * negative)), 2)
    competitor = re.search(r"\b(Brightline Bank|Northstar Finance)\b", evidence, re.I)
    rates = re.findall(r"(?<!\d)(\d{1,2}(?:\.\d{1,2})?)\s*%", evidence)
    offered_rate = float(rates[0]) if competitor and rates else None
    if offered_rate is not None and not 1 <= offered_rate <= 40:
        offered_rate = None
    reason = ("job loss" if hardship and re.search(r"laid off|lost.*job|job loss|unemployed", low)
              else "medical emergency" if hardship and "medical" in low
              else "business loss" if hardship and "business" in low else None)
    return {
        "intent": intent, "sentiment": sentiment,
        "entities": {"hardship_reason": reason, "competitor": competitor.group(1) if competitor else None,
                     "offered_rate": offered_rate, "life_event": "renovation" if "renovat" in low else None},
        "evidence_text": evidence, "source_hash": hashlib.sha256((text or "").encode()).hexdigest(),
        "extraction_version": VERSION, "provider": "local deterministic rules",
    }
