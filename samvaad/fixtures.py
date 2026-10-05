"""Seeded fictional customers. Contacts are reserved example addresses."""
from datetime import datetime, timedelta, timezone


def generate_fixture(count: int = 20, reference: datetime | None = None) -> dict:
    reference = reference or datetime.now(timezone.utc)
    count = max(10, min(int(count), 2000))
    customers, loans, payments, interactions = [], [], [], []
    heroes = [
        ("Ravi Kumar", "Pune", "SALARIED", 85000, "EN", 600000, 14.5, 16546, 22, 9),
        ("Ananya Iyer", "Bengaluru", "SALARIED", 160000, "EN", 1000000, 14., 23268, 30, 0),
        ("Imran Shaikh", "Hyderabad", "SELF_EMPLOYED", 120000, "HI", 300000, 13., 10108, 18, 0),
    ]
    for number in range(1, count + 1):
        cid = f"C{number:04d}"
        if number <= 3:
            name, city, segment, income, language, principal, rate, emi, months, dpd = heroes[number - 1]
        else:
            name = {4: "Neha Rao", 5: "Dev Shah", 6: "Asha Menon", 7: "Kabir Bose",
                    8: "Maya Sen", 9: "Priya Das", 10: "Vikram Roy"}.get(number, f"Demo Borrower {number:02d}")
            city, segment, income, language = ["Pune", "Bengaluru", "Hyderabad", "Chennai"][number % 4], "SALARIED", 70000 + number * 1000, "EN"
            principal, rate, emi, months, dpd = 300000, 12., 10000, 18, 7 if number == 7 else 0
        customers.append({"customer_id": cid, "full_name": name, "city": city, "segment": segment,
                          "monthly_income": 0 if number == 6 else income, "preferred_language": language,
                          "phone": "******0000", "email": f"{cid.lower()}@example.invalid",
                          "consent_calls": number != 4, "consent_marketing": number != 1,
                          "dnd": number == 5})
        loan_id = f"L-{cid}"
        loans.append({"loan_id": loan_id, "customer_id": cid, "product": "PERSONAL", "principal": principal,
                      "outstanding": round(principal * .61), "interest_rate": rate, "emi": emi,
                      "relationship_months": months, "current_dpd": dpd, "status": "ACTIVE",
                      "disbursed_on": (reference - timedelta(days=months * 30)).date().isoformat()})
        for period in range(min(months, 24)):
            latest = period == min(months, 24) - 1
            due = reference - timedelta(days=9 if latest else (min(months, 24) - period - 1) * 30 + 9)
            bounced = latest and dpd > 0
            payments.append({"payment_id": f"P-{cid}-{period:02d}", "loan_id": loan_id,
                             "due_date": due.date().isoformat(), "paid_date": None if bounced else due.date().isoformat(),
                             "amount_due": emi, "amount_paid": 0 if bounced else emi,
                             "status": "BOUNCED" if bounced else "PAID"})
        if number > 3:
            text = {
                4: "Please share a foreclosure statement. Brightline Bank offered 10.75%.",
                5: "I am planning a balance transfer. Why should I stay?",
                6: "Do you have a top-up for my shop renovation?",
                7: "I will pay next week. Please send me a reminder.",
                8: "I did not lose my job. I do not need a top-up. Please share my statement.",
                9: "Please share my account statement. Thank you.",
                10: "Agent: If you lost your job we have support options.\nCustomer: I only need an address update.",
            }.get(number, "Please share my account statement and payment schedule.")
            interactions.append({"interaction_id": f"I-{cid}-01", "customer_id": cid,
                                 "channel": "CHAT", "ts": (reference - timedelta(days=5)).isoformat(), "text": text})
    hero_turns = [
        ("I-C0001-07", "C0001", "CALL_IN", 12, "Agent: Thank you for calling DemoLend Finance.\nRavi: I was laid off last week. I have never missed an EMI before. This month will be very hard and I am stressed. Can an officer discuss support options?"),
        ("I-C0001-08", "C0001", "CHAT", 3, "Ravi: Any update on my support request? My EMI bounced and I don't want this to hurt my credit score."),
        ("I-C0002-04", "C0002", "EMAIL", 10, "Subject: Foreclosure statement request. Please share the foreclosure statement for my personal loan, including prepayment charges. Regards, Ananya."),
        ("I-C0002-05", "C0002", "CHAT", 5, "Ananya: Brightline Bank has offered to take over my loan at 10.75%. I pay 14% with you and have never missed a payment. Why should I stay? Please hurry, I need to decide this week."),
        ("I-C0003-03", "C0003", "CHAT", 20, "Imran: Namaste. I plan to renovate my pharmacy and home. My current loan is running fine. Do you have any top-up options, and what documents would you need?"),
    ]
    for iid, cid, channel, days, text in hero_turns:
        interactions.append({"interaction_id": iid, "customer_id": cid, "channel": channel,
                             "ts": (reference - timedelta(days=days)).isoformat(), "text": text})
    # A closed loan must never inflate current obligations or current tenure.
    loans.append({"loan_id": "L-C0003-CLOSED", "customer_id": "C0003", "product": "TWO_WHEELER",
                  "principal": 100000, "outstanding": 0, "interest_rate": 20., "emi": 0,
                  "relationship_months": 40, "current_dpd": 0, "status": "CLOSED",
                  "disbursed_on": (reference - timedelta(days=40 * 30)).date().isoformat()})
    return {"customers": customers, "loans": loans, "payments": payments, "interactions": interactions}
