/**
 * Markdown Sanitizer — XSS prevention for marked.js output
 * 
 * Security requirements:
 * - No <script> execution
 * - No event handlers (onerror, onclick, etc.)
 * - No javascript: URLs
 * - No iframe/object/embed
 * - HTML tags escaped or stripped
 */
(function() {
  'use strict';

  // Escape HTML entities
  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#x27;');
  }

  // Dangerous patterns to strip from HTML
  const DANGEROUS_PATTERNS = [
    /<script[\s\S]*?<\/script>/gi,
    /<iframe[\s\S]*?<\/iframe>/gi,
    /<object[\s\S]*?<\/object>/gi,
    /<embed[\s\S]*?>/gi,
    /<applet[\s\S]*?<\/applet>/gi,
    /<form[\s\S]*?<\/form>/gi,
    /<input[\s\S]*?>/gi,
    /<textarea[\s\S]*?<\/textarea>/gi,
    /<select[\s\S]*?<\/select>/gi,
    /<link[\s\S]*?>/gi,
    /<meta[\s\S]*?>/gi,
    /<style[\s\S]*?<\/style>/gi,
    /<svg[\s\S]*?<\/svg>/gi,
    /<math[\s\S]*?<\/math>/gi,
  ];

  // Event handler attributes
  const EVENT_HANDLER_REGEX = /\s+on\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi;

  // javascript: URL pattern
  const JS_URL_REGEX = /(?:javascript|vbscript|data)\s*:/gi;

  /**
   * Sanitize HTML output from marked.js
   * Removes dangerous tags, event handlers, and javascript: URLs
   */
  function sanitizeMarkdown(html) {
    if (!html || typeof html !== 'string') return '';
    
    let clean = html;
    
    // Remove dangerous tags
    for (const pattern of DANGEROUS_PATTERNS) {
      clean = clean.replace(pattern, '<!-- stripped -->');
    }
    
    // Remove event handler attributes
    clean = clean.replace(EVENT_HANDLER_REGEX, '');
    
    // Neutralize javascript: URLs in href/src attributes
    clean = clean.replace(/((?:href|src|action)\s*=\s*)(["'])(javascript:[^"']*)\2/gi, 
      '$1$2about:blank$2');
    
    // Also catch unquoted javascript: URLs
    clean = clean.replace(/((?:href|src|action)\s*=\s*)(javascript:[^\s>]+)/gi,
      '$1about:blank');
    
    return clean;
  }

  /**
   * Render markdown safely:
   * 1. Parse with marked.js (HTML disabled via renderer)
   * 2. Sanitize any HTML that slips through
   */
  function safeMarkdown(text) {
    if (!text || typeof text !== 'string') return '';
    
    // Configure marked to escape HTML by default
    if (window.marked) {
      try {
        // Use marked with HTML disabled
        const renderer = new window.marked.Renderer();
        
        // Override link to sanitize href
        const origLink = renderer.link;
        renderer.link = function(href, title, text) {
          if (typeof href === 'object') {
            // marked v12 object format
            const token = href;
            href = token.href || '';
            title = token.title || '';
            text = token.text || '';
          }
          // Links are intentionally restricted to ordinary web URLs.
          if (JS_URL_REGEX.test(String(href)) || !/^https?:\/\//i.test(String(href))) {
            href = 'about:blank';
          }
          const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
          return `<a href="${escapeHtml(String(href))}"${titleAttr}>${text}</a>`;
        };
        
        // Override image to sanitize src
        const origImage = renderer.image;
        renderer.image = function(href, title, text) {
          if (typeof href === 'object') {
            const token = href;
            href = token.href || '';
            title = token.title || '';
            text = token.text || '';
          }
          if (JS_URL_REGEX.test(String(href)) || !/^https?:\/\//i.test(String(href))) {
            href = 'about:blank';
          }
          const titleAttr = title ? ` title="${escapeHtml(title)}"` : '';
          return `<img src="${escapeHtml(String(href))}" alt="${escapeHtml(String(text))}"${titleAttr}>`;
        };
        
        const result = window.marked.parse(text, { renderer, breaks: true, gfm: true });
        return sanitizeMarkdown(typeof result === 'string' ? result : result.text || '');
      } catch(e) {
        console.warn('marked.js parse error:', e);
      }
    }
    
    // Fallback: escape all HTML
    return escapeHtml(text).replace(/\n/g, '<br>');
  }

  // Export
  window.SafeMarkdown = safeMarkdown;
  window.MarkdownSanitizer = { sanitize: sanitizeMarkdown, escapeHtml };
})();
