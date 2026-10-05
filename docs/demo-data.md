# Synthetic data notes

All records are generated in `samvaad/fixtures.py` for local testing. Names, policy text, loan records, and conversation transcripts are fictional. Email addresses use the reserved `example.invalid` domain and phone numbers are masked placeholders. The seed contains 20 customers, 20 active personal loans, and one closed loan used to verify filtering. Dates are relative to the seeding time.

The three PRD journeys are Ravi C0001 (job-loss hardship), Ananya C0002 (foreclosure and competitor rate), and Imran C0003 (conditional top-up interest). Further records cover withdrawn consent, DND, missing income, a payment reminder, negated hardship, neutral requests, and agent speech that must not be mistaken for customer hardship.

Pasted interactions are local test inputs, stored in this workspace's SQLite database. Simulated outcomes use a separate channel and neutral signal values. They are not fabricated borrower utterances. Reset removes all added local inputs and outcomes and restores the seed.

This dataset is appropriate for a prototype demonstration. Its scores, policy caps, hardship terms, and top-up formula are illustrative and have not been validated as credit decision models.
