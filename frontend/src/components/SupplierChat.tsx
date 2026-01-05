import React, { useState, useEffect, useRef } from 'react';
import './Chat.css';

const API_BASE_URL = 'http://localhost:8001';

interface Message {
  role: 'user' | 'assistant' | 'status';
  content: string;
  timestamp: string;
}

export const SupplierChat: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isWorking, setIsWorking] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  // Auto-scroll to bottom
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Load chat history on mount
  useEffect(() => {
    loadHistory();
  }, []);

  // Connect to SSE stream
  useEffect(() => {
    const eventSource = new EventSource(`${API_BASE_URL}/chat/supplier/stream`);
    eventSourceRef.current = eventSource;

    eventSource.onopen = () => {
      console.log('✅ Connected to supplier chat stream');
      setIsConnected(true);
    };

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'status') {
        const statusMsg: Message = {
          role: 'status',
          content: data.data,
          timestamp: new Date().toISOString()
        };
        setMessages((prev) => [...prev, statusMsg]);
      }
    };

    eventSource.onerror = () => {
      console.error('❌ SSE connection error');
      setIsConnected(false);
    };

    return () => {
      eventSource.close();
    };
  }, []);

  const loadHistory = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/chat/supplier/history`);
      const data = await response.json();
      setMessages(data.messages);
    } catch (error) {
      console.error('Failed to load chat history:', error);
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setInput('');
    setIsLoading(true);

    // Add user message optimistically
    const userMsg: Message = {
      role: 'user',
      content: userMessage,
      timestamp: new Date().toISOString()
    };
    setMessages((prev) => [...prev, userMsg]);

    // Add working status placeholder
    const statusMsg: Message = {
      role: 'status',
      content: `Acknowledged: "${userMessage}". Working on it...`,
      timestamp: new Date().toISOString()
    };
    setMessages((prev) => [...prev, statusMsg]);
    setIsWorking(true);

    try {
      const response = await fetch(`${API_BASE_URL}/chat/supplier`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: userMessage }),
      });
      
      if (response.ok) {
        const data = await response.json();
        // Add assistant message from HTTP response (SSE is backup)
        if (data.success && data.response) {
          const assistantMsg: Message = {
            role: 'assistant',
            content: data.response,
            timestamp: new Date().toISOString()
          };
          setMessages((prev) => {
            const filtered = prev.filter((msg, idx) => 
              !(idx === prev.length - 1 && msg.role === 'status')
            );
            return [...filtered, assistantMsg];
          });
        }
      }
    } catch (error) {
      console.error('Failed to send message:', error);
      setMessages((prev) => prev.filter((msg, idx) => 
        !(idx === prev.length - 1 && msg.role === 'status')
      ));
    } finally {
      setIsLoading(false);
      setIsWorking(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className="chat-container">
      <div className="chat-header">
        <div className="chat-title">
          <h2>Supplier Agent</h2>
        </div>
        <div className="chat-status">
          <span className={`status-indicator ${isConnected ? 'connected' : 'disconnected'}`} />
          {isConnected ? 'Connected' : 'Disconnected'}
        </div>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>Hi! I&apos;m your supplier agent.</p>
            <p>Tell me what products to sell, and I&apos;ll help you find buyers and create offers.</p>
            <div className="chat-suggestions">
              <button onClick={() => setInput('Sell the stuff on stock')}>
                Sell products from inventory
              </button>
              <button onClick={() => setInput('What products do I have in stock?')}>
                Show my inventory
              </button>
            </div>
          </div>
        )}

        {messages.map((msg, idx) => {
          const isStatus = msg.role === 'status';
          if (isStatus) {
            return (
              <div key={idx} className="status-line">
                <span className="status-dot">•</span>
                <span className="status-text">{msg.content}</span>
              </div>
            );
          }
          const messageClass = `message message-${msg.role}`;
          return (
          <div key={idx} className={`message ${messageClass}`}>
            <div className={`message-avatar ${msg.role === 'user' ? 'avatar-user' : 'avatar-assistant'}`}>
              {msg.role === 'user' ? 'U' : 'S'}
            </div>
            <div className="message-content">
              <div className="message-header">
                <span className="message-role">
                  {msg.role === 'user' ? 'You' : 'Supplier Agent'}
                </span>
                <span className="message-time">
                  {formatTimestamp(msg.timestamp)}
                </span>
              </div>
              <div className="message-text">
                {msg.content || ((isLoading || isWorking) && idx === messages.length - 1 && <span className="typing-indicator">●●●</span>)}
              </div>
            </div>
          </div>
        );})}

        <div ref={messagesEndRef} />
      </div>

      <div className="chat-input-container">
        <textarea
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Type your message... (Enter to send, Shift+Enter for new line)"
          disabled={isLoading}
          rows={2}
        />
        <button
          className="chat-send-button"
          onClick={sendMessage}
          disabled={!input.trim() || isLoading}
        >
          {isLoading ? '⏳' : '📤'} Send
        </button>
      </div>
    </div>
  );
};

