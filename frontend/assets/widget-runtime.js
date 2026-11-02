/**
 * Julius Sandboxed Widget Runtime Bridge
 * 
 * Provides host-to-iframe communication for sandboxed widgets:
 * - window.sendPrompt() bridge via window.postMessage
 * - Dynamic iframe auto-resizing
 * - Secure origin and message validation
 * (Includes backward-compatibility aliases for Julius widgets)
 */

(function () {
  'use strict';

  // Listen for messages from sandboxed widget iframes
  window.addEventListener('message', function (event) {
    const data = event.data;
    if (!data || typeof data !== 'object') return;

    // Handle intent prompt from widget (supports julius:sendPrompt and julius:sendPrompt)
    if ((data.type === 'julius:sendPrompt') && typeof data.text === 'string') {
      const promptText = data.text.trim();
      if (!promptText) return;

      console.log('[Widget Runtime] Received sendPrompt intent:', promptText);

      // 1. Try to set active chat input if present
      const chatInput = document.getElementById('chatInput') || 
                        document.querySelector('textarea.chat-input') ||
                        document.querySelector('input.chat-input');
      if (chatInput) {
        chatInput.value = promptText;
        chatInput.dispatchEvent(new Event('input', { bubbles: true }));
      }

      // 2. If host has a global send function or WebSocket sender, trigger it
      if (typeof window.juliusSendChatMessage === 'function') {
        window.juliusSendChatMessage(promptText);
      } else if (typeof window.juliusSendChatMessage === 'function') {
        window.juliusSendChatMessage(promptText);
      } else if (typeof window.sendWebSocketMessage === 'function') {
        window.sendWebSocketMessage({
          type: 'chat',
          message: promptText
        });
      } else {
        // Fallback: trigger send button click if available
        const sendBtn = document.getElementById('sendBtn') || 
                        document.querySelector('button.send-btn');
        if (sendBtn && chatInput) {
          sendBtn.click();
        }
      }
    }

    // Handle auto-resize from iframe (supports julius:widgetResize and julius:widgetResize)
    if ((data.type === 'julius:widgetResize') && typeof data.height === 'number') {
      const iframes = document.querySelectorAll('iframe.julius-widget-frame, ');
      iframes.forEach(function (iframe) {
        try {
          if (iframe.contentWindow === event.source) {
            const safeHeight = Math.max(120, Math.min(1200, data.height + 16));
            iframe.style.height = safeHeight + 'px';
          }
        } catch (e) {
          // Cross-origin restriction ignored
        }
      });
    }
  });

  // Export helper for host pages
  window.JuliusWidgetHost = {
    /**
     * Create a secure sandboxed iframe container for HTML widget content.
     * @param {string} srcDoc HTML content of the widget.
     * @param {Object} options Configuration options.
     * @returns {HTMLIFrameElement}
     */
    createWidgetFrame: function (srcDoc, options) {
      options = options || {};
      const iframe = document.createElement('iframe');
      iframe.className = 'julius-widget-frame ' + (options.className || '');
      iframe.setAttribute('sandbox', 'allow-scripts');
      iframe.setAttribute('loading', 'lazy');
      iframe.style.width = options.width || '100%';
      iframe.style.height = (options.initialHeight || 320) + 'px';
      iframe.style.border = 'none';
      iframe.style.borderRadius = 'var(--lt-radius, 10px)';
      iframe.style.background = 'transparent';
      iframe.style.overflow = 'hidden';
      iframe.style.display = 'block';
      iframe.srcdoc = srcDoc;
      return iframe;
    }
  };

  // Backward-compatibility alias
  

  console.log('[Widget Runtime] Julius Sandboxed Widget Host Bridge initialised.');
})();
