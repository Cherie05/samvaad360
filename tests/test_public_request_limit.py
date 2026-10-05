"""Request limits reject streamed public uploads before consuming the tail."""
import asyncio

from webhook.main import create_app


def test_oversized_chunked_offer_form_stops_reading_at_limit(service):
    app = create_app(service=service, token_map={})
    chunks = [b"x" * 1024, b"y" * 1025]
    consumed = []
    sent = []
    response_started = False

    async def receive():
        if response_started:
            return {"type": "http.disconnect"}
        index = len(consumed)
        if index >= len(chunks):
            raise AssertionError("The oversized request tail was consumed")
        consumed.append(index)
        return {"type": "http.request", "body": chunks[index], "more_body": True}

    async def send(message):
        nonlocal response_started
        sent.append(message)
        if message["type"] == "http.response.start":
            response_started = True

    scope = {
        "type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1", "method": "POST", "scheme": "http",
        "path": "/offer/example-token/respond", "raw_path": b"/offer/example-token/respond",
        "query_string": b"", "root_path": "",
        "headers": [(b"content-type", b"application/x-www-form-urlencoded")],
        "client": ("127.0.0.1", 1234), "server": ("testserver", 80),
    }
    asyncio.run(app(scope, receive, send))
    assert consumed == [0, 1]
    assert next(message for message in sent if message["type"] == "http.response.start")["status"] == 413
