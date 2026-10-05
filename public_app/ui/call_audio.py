"""Click-to-play browser speech; no audio asset, recorder, or external script."""
from __future__ import annotations

import json


def voice_document(text):
    """Escape script data, including closing tags, before entering the iframe."""
    if not isinstance(text, str) or len(text) > 4000:
        raise ValueError("Browser speech accepts a bounded plain-text message.")
    payload = json.dumps(text, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return """<!doctype html><html><head><meta charset="utf-8"><style>
      body { font: 13px system-ui, sans-serif; margin: 0; color: #516077; }
      .controls { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
      button, select { border: 1px solid #cbd5e1; border-radius: 8px; padding: 8px 10px;
        color: #16324f; background: #f8fafc; font: inherit; cursor: pointer; }
      button:first-child { background: #0d766d; border-color: #0d766d; color: white; }
      select { max-width: 220px; } p { margin: 8px 0 0; line-height: 1.45; }
    </style></head><body>
    <div class="controls"><button id="play" type="button">▶ Play lender voice</button>
      <button id="stop" type="button">Stop audio</button>
      <select id="voice" aria-label="Browser voice"></select></div>
    <p id="status" role="status">Optional browser audio. No telephone call or microphone recording.</p>
    <script>
    const message = """ + payload + """;
    const play = document.getElementById('play');
    const stop = document.getElementById('stop');
    const selector = document.getElementById('voice');
    const status = document.getElementById('status');
    const available = 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
    if (!available) {
      play.disabled = true; stop.disabled = true; selector.hidden = true;
      status.textContent = 'This browser does not support speech playback. Read the transcript below.';
    } else {
      let voices = [];
      function refreshVoices() {
        const selected = selector.value;
        voices = window.speechSynthesis.getVoices();
        selector.replaceChildren();
        const automatic = document.createElement('option');
        automatic.value = ''; automatic.textContent = 'Browser default voice'; selector.append(automatic);
        voices.filter(voice => voice.lang.toLowerCase().startsWith('en')).forEach(voice => {
          const item = document.createElement('option');
          item.value = voice.voiceURI; item.textContent = voice.name + ' (' + voice.lang + ')';
          selector.append(item);
        });
        selector.value = selected;
      }
      refreshVoices(); window.speechSynthesis.addEventListener('voiceschanged', refreshVoices);
      play.addEventListener('click', function () {
        window.speechSynthesis.cancel();
        const utterance = new SpeechSynthesisUtterance(message);
        const choice = voices.find(voice => voice.voiceURI === selector.value);
        if (choice) utterance.voice = choice;
        utterance.lang = choice ? choice.lang : 'en-IN'; utterance.rate = 0.95;
        utterance.onstart = () => { status.textContent = 'Playing browser voice. This is not a phone call.'; };
        utterance.onend = () => { status.textContent = 'Playback finished. Reply using the fictional borrower controls.'; };
        utterance.onerror = () => { status.textContent = 'Voice playback is unavailable. Read the transcript below.'; };
        window.speechSynthesis.speak(utterance);
      });
      stop.addEventListener('click', () => {
        window.speechSynthesis.cancel(); status.textContent = 'Audio stopped. Text conversation remains available.';
      });
      window.addEventListener('pagehide', () => window.speechSynthesis.cancel());
    }
    </script></body></html>"""


def render_browser_voice(text, key=None):
    """Render only plain lender text; speaking always requires a button click.

    Browser/OS speech voices are selected by the visitor. Voice assets are not
    distributed by this app. Production carrier/TTS providers require their
    own commercial terms and a separate deployment review.
    """
    import streamlit.components.v1 as components

    # components.html has no key argument; keep the public wrapper compatible
    # with the calling UI while the content itself identifies each message.
    del key
    components.html(voice_document(text), height=112, scrolling=False)
