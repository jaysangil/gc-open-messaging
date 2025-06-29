// static/scripts/view.js
function updateScroll() {
  const pane = document.getElementById('agent-assist');
  pane.scrollTop = pane.scrollHeight;
}

export default {
  addChatMessage(sender, message, purpose) {
    const container = document.createElement('div');
    container.className = `chat-message ${purpose}`;

    // Avatar
    const avatarUrl = purpose === 'agent'
      ? '/static/images/agent.jpg'
      : '/static/images/customer.jpg';
    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.style.backgroundImage = `url('${avatarUrl}')`;

    // Message body wrapper
    const body = document.createElement('div');
    body.className = 'message-body';

    // Bubble
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    bubble.textContent = message;

    // Timestamp
    const ts = document.createElement('span');
    ts.className = 'timestamp';
    ts.textContent = new Date().toLocaleTimeString([], {
      hour:   '2-digit',
      minute: '2-digit'
    });

    // Assemble
    body.appendChild(bubble);
    body.appendChild(ts);

    if (purpose === 'customer') {
      container.append(avatar, body);
    } else {
      container.append(body, avatar);
    }

    document.getElementById('agent-assist').appendChild(container);
    updateScroll();
  }
};
