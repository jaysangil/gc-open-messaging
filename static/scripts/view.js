// static/scripts/view.js
/**
 * Helper to scroll to bottom of the chat pane.
 */
function updateScroll() {
  const pane = document.getElementById('agent-assist');
  pane.scrollTop = pane.scrollHeight;
}

export default {
  /**
   * Append a chat bubble.
   * @param {String} sender  — display name
   * @param {String} message — the text to show
   * @param {String} purpose — CSS class (e.g. 'agent' or 'customer')
   */
  addChatMessage(sender, message, purpose) {
    const container = document.createElement('div');
    container.className = `chat-message ${purpose}`;

    const p = document.createElement('p');
    p.textContent = `${sender}: ${message}`;

    container.appendChild(p);
    document.getElementById('agent-assist').appendChild(container);
    updateScroll();
  }
};
