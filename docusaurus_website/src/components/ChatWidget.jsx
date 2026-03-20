import React, { useState, useEffect, useRef } from "react";
import "../../src/css/chat.css";

// Set this to your Render.com backend URL after deployment
const BACKEND_URL =
  process.env.NODE_ENV === "production"
    ? "https://physical-ai-book-api.onrender.com"
    : "http://localhost:8002";

const WELCOME_MSG = {
  role: "bot",
  text: "Hi! I'm Robo 🤖 — your Physical AI textbook assistant. Ask me anything from the book, or highlight text on a page and ask a question about it!",
};

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([WELCOME_MSG]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedText, setSelectedText] = useState("");
  const bottomRef = useRef(null);
  const inputRef = useRef(null);

  // Capture highlighted text anywhere on the page
  useEffect(() => {
    const handleSelection = () => {
      const sel = window.getSelection()?.toString().trim();
      if (sel && sel.length > 10) {
        setSelectedText(sel.slice(0, 400)); // cap at 400 chars
      }
    };
    document.addEventListener("mouseup", handleSelection);
    return () => document.removeEventListener("mouseup", handleSelection);
  }, []);

  // Auto-scroll to latest message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  // Focus input when panel opens
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  const sendMessage = async () => {
    const question = input.trim();
    if (!question || loading) return;

    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${BACKEND_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, selected_text: selectedText }),
      });

      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      const data = await res.json();
      setMessages((prev) => [...prev, { role: "bot", text: data.answer }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "bot",
          text: "Sorry, I couldn't reach the server. Make sure the backend is running.",
        },
      ]);
    } finally {
      setLoading(false);
      setSelectedText("");
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  return (
    <>
      {/* Floating toggle button */}
      <button
        className="chat-toggle-btn"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "Close chat" : "Open Robo chat assistant"}
        title="Ask Robo"
      >
        {open ? "✕" : "🤖"}
      </button>

      {/* Chat panel */}
      {open && (
        <div className="chat-panel" role="dialog" aria-label="Robo chat assistant">
          {/* Header */}
          <div className="chat-header">
            <div className="chat-avatar">R</div>
            <div className="chat-header-title">
              Robo
              <div style={{ fontSize: 11, fontWeight: 400, opacity: 0.85 }}>
                Physical AI Book Assistant
              </div>
            </div>
            <button
              className="chat-close-btn"
              onClick={() => setOpen(false)}
              aria-label="Close chat"
            >
              ✕
            </button>
          </div>

          {/* Selected text context banner */}
          {selectedText && (
            <div className="chat-context-banner">
              <span>📌 Context: "{selectedText.slice(0, 60)}…"</span>
              <button onClick={() => setSelectedText("")} aria-label="Clear context">
                ✕
              </button>
            </div>
          )}

          {/* Messages */}
          <div className="chat-messages">
            {messages.map((msg, i) => (
              <div key={i} className={`chat-message ${msg.role}`}>
                {msg.text}
              </div>
            ))}
            {loading && (
              <div className="chat-message bot loading">Robo is thinking…</div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <div className="chat-input-row">
            <textarea
              ref={inputRef}
              className="chat-input"
              rows={1}
              placeholder="Ask a question about the book…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
            />
            <button
              className="chat-send-btn"
              onClick={sendMessage}
              disabled={loading || !input.trim()}
              aria-label="Send message"
            >
              ➤
            </button>
          </div>
        </div>
      )}
    </>
  );
}
