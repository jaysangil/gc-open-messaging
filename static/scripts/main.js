// static/scripts/main.js
import view from './view.js';

/**
 * A fresh conversation ID per page load.
 * Uses crypto.randomUUID() if available, otherwise a simple fallback.
 */
const sessionId = (crypto && crypto.randomUUID)
  ? crypto.randomUUID()
  : (() => {
      // fallback UUID v4 generator
      return ([1e7]+-1e3+-4e3+-8e3+-1e11)
        .replace(/[018]/g, c =>
          (c ^ crypto.getRandomValues(new Uint8Array(1))[0] & 15 >> c / 4)
            .toString(16)
        );
    })();

/**
 * Fetch & render any new messages.
 */
function refreshTranscript() {
  fetch('/transcript')
    .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
    .then(msgs => {
      msgs.forEach(m =>
        view.addChatMessage(m.sender, m.message, m.purpose)
      );
    })
    .catch(err => console.error('Transcript error:', err));
}

/**
 * Send the chat message, then refreshTranscript().
 */
function sendChat() {
  const ta   = document.getElementById('message-textarea');
  const text = ta.value.trim();
  if (!text) return;

  fetch('/messageToGenesys', {
    method:  'POST',
    headers: {'Content-Type': 'application/json'},
    body:    JSON.stringify({
      id:        sessionId,    // use the browser-generated session ID
      nickname:  'Takuya',
      idType:    'email',
      firstName: 'Takuya',
      lastName:  'Sangil',
      message:   text
    })
  })
  .then(r => {
    if (!r.ok) throw new Error(r.statusText);
    ta.value = '';
    refreshTranscript();
  })
  .catch(err => console.error('Send error:', err));
}

// Only use the form’s submit event:
document.getElementById('chat-form')
        .addEventListener('submit', e => { e.preventDefault(); sendChat(); });

// On page load: fetch existing messages, then start polling
window.addEventListener('DOMContentLoaded', () => {
  refreshTranscript();
  setInterval(refreshTranscript, 2000);
});
