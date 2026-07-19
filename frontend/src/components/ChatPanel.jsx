import React, { useState, useRef, useEffect } from 'react';
import { Send, Mic, MicOff, Globe, Download, Shield } from 'lucide-react';

export default function ChatPanel({
  messages,
  onSendMessage,
  isLoading,
  language,
  setLanguage,
  onCitationClick,
  onExportPDF
}) {
  const [input, setInput] = useState('');
  const [isRecording, setIsRecording] = useState(false);
  const messagesEndRef = useRef(null);
  const recognitionRef = useRef(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // Speech Recognition setup
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      const rec = new SpeechRecognition();
      rec.continuous = false;
      rec.interimResults = false;
      rec.lang = language === 'kn' ? 'kn-IN' : 'en-IN';

      rec.onstart = () => {
        setIsRecording(true);
      };

      rec.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        setInput((prev) => (prev + ' ' + transcript).trim());
        setIsRecording(false);
      };

      rec.onerror = (e) => {
        console.error('Speech recognition error', e);
        setIsRecording(false);
      };

      rec.onend = () => {
        setIsRecording(false);
      };

      recognitionRef.current = rec;
    }
  }, [language]);

  const toggleVoiceInput = () => {
    if (!recognitionRef.current) {
      alert(language === 'kn' ? 
        'ನಿಮ್ಮ ಬ್ರೌಸರ್ ಧ್ವನಿ ಇನ್‌ಪುಟ್ ಅನ್ನು ಬೆಂಬಲಿಸುವುದಿಲ್ಲ.' : 
        'Speech recognition is not supported in this browser.');
      return;
    }

    if (isRecording) {
      recognitionRef.current.stop();
    } else {
      recognitionRef.current.start();
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;
    onSendMessage(input.trim());
    setInput('');
  };

  // Helper to render markdown-like formatting (bold **text** and replacement of FIRs)
  const formatContent = (text, citations) => {
    if (!text) return '';
    
    // Convert bold text **text** -> <strong>text</strong>
    let formatted = text;
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    formatted = formatted.replace(/\n/g, '<br/>');

    // Parse text and make FIRs clickable if they match citation list
    if (citations && citations.length > 0) {
      citations.forEach((cit) => {
        const firNum = cit.fir_number;
        // Case insensitive replacement for case number with a link
        const regex = new RegExp(`(${firNum}|FIR\\s+${firNum})`, 'gi');
        formatted = formatted.replace(
          regex,
          `<span class="citation-chip" data-fir="${firNum}">$1</span>`
        );
      });
    }

    // Return HTML safely by catching clicks in the container
    return (
      <div 
        dangerouslySetInnerHTML={{ __html: formatted }} 
        onClick={(e) => {
          const chip = e.target.closest('.citation-chip');
          if (chip) {
            const fir = chip.getAttribute('data-fir');
            if (fir && onCitationClick) {
              onCitationClick(fir);
            }
          }
        }}
      />
    );
  };

  return (
    <div className="glass-panel chat-side">
      {/* Panel Header */}
      <div className="panel-header">
        <div className="panel-title">
          <Shield className="header-logo" size={18} />
          <span>{language === 'kn' ? 'ಕರ್ನಾಟಕ ಅಪರಾಧ ತನಿಖಾ ಸಹಾಯಕ' : 'Karnataka Crime GPT'}</span>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button 
            className={`lang-toggle-btn ${language === 'kn' ? 'active' : ''}`}
            onClick={() => setLanguage(language === 'en' ? 'kn' : 'en')}
          >
            <Globe size={14} />
            <span>{language === 'kn' ? 'English' : 'ಕನ್ನಡ'}</span>
          </button>
          {messages.length > 0 && (
            <button className="btn-secondary pdf-btn" onClick={onExportPDF} title="Export Chat to PDF">
              <Download size={14} />
              <span>PDF</span>
            </button>
          )}
        </div>
      </div>

      {/* Messages Window */}
      <div className="chat-messages-container">
        {messages.length === 0 ? (
          <div className="placeholder-view">
            <Shield size={40} className="placeholder-icon" />
            <h3>{language === 'kn' ? 'ಹಲೋ, ನಾನು ನಿಮ್ಮ ಅಪರಾಧ ತನಿಖಾ ಸಹಾಯಕ.' : 'Karnataka Crime GPT Assistant'}</h3>
            <p>
              {language === 'kn' 
                ? 'ಕರ್ನಾಟಕದ ಅಪರಾಧ ದಾಖಲೆಗಳು, ಪ್ರವೃತ್ತಿಗಳು ಮತ್ತು ಆರೋಪಿಗಳ ಸಂಬಂಧಗಳನ್ನು ವಿಶ್ಲೇಷಿಸಲು ನನಗೆ ಯಾವುದೇ ಪ್ರಶ್ನೆಯನ್ನು ಕೇಳಿ.'
                : 'Ask me any question to analyze FIR records, suspect networks, location connections, and monthly crime trends in Karnataka.'}
            </p>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div key={idx} className={`message-bubble ${msg.role}`}>
              <div className="msg-header">
                <span>{msg.role === 'user' ? (language === 'kn' ? 'ಬಳಕೆದಾರ' : 'User') : (language === 'kn' ? 'ಸಹಾಯಕ' : 'GPT Assistant')}</span>
                <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                  {new Date(msg.created_at || Date.now()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
              <div className="msg-content">
                {formatContent(msg.content, msg.citations)}
              </div>
              
              {/* Citations List Below Bubble if not highlighted inline */}
              {msg.role === 'assistant' && msg.citations && msg.citations.length > 0 && (
                <div className="citations-list">
                  {msg.citations.map((cit, cIdx) => (
                    <button
                      key={cIdx}
                      className="citation-chip"
                      onClick={() => onCitationClick(cit.fir_number)}
                      title={cit.snippet}
                    >
                      <span>FIR {cit.fir_number}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))
        )}

        {isLoading && (
          <div className="message-bubble assistant">
            <div className="msg-header">
              <span>{language === 'kn' ? 'ಸಹಾಯಕ' : 'GPT Assistant'}</span>
            </div>
            <div className="loading-dots">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Form */}
      <div className="chat-input-container">
        <form onSubmit={handleSubmit} className="chat-form">
          <input
            type="text"
            className="chat-input"
            placeholder={
              isLoading 
                ? (language === 'kn' ? 'ಲೋಡ್ ಆಗುತ್ತಿದೆ...' : 'Processing...') 
                : (language === 'kn' ? 'ಪ್ರಶ್ನೆಯನ್ನು ಇಲ್ಲಿ ಟೈಪ್ ಮಾಡಿ...' : 'Ask a question about FIRs, suspects, or trends...')
            }
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={isLoading}
          />
          <button
            type="button"
            className={`voice-btn ${isRecording ? 'recording' : ''}`}
            onClick={toggleVoiceInput}
            title={language === 'kn' ? 'ಧ್ವನಿ ಮೂಲಕ ಟೈಪ್ ಮಾಡಿ' : 'Voice Typing'}
            disabled={isLoading}
          >
            {isRecording ? <MicOff size={18} /> : <Mic size={18} />}
          </button>
          <button
            type="submit"
            className="send-btn"
            disabled={!input.trim() || isLoading}
          >
            <Send size={16} />
          </button>
        </form>
      </div>
    </div>
  );
}
