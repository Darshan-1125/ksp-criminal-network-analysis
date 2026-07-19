import React, { useState, useEffect } from 'react';
import { jsPDF } from 'jspdf';
import { 
  ShieldAlert, 
  Network, 
  BarChart2, 
  HelpCircle,
  FileText,
  Activity,
  UserCheck
} from 'lucide-react';
import ChatPanel from './components/ChatPanel';
import NetworkGraph from './components/NetworkGraph';
import TrendChart from './components/TrendChart';
import CaseDetailModal from './components/CaseDetailModal';

export default function App() {
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [language, setLanguage] = useState('en');
  
  // Tab states: 'network' | 'trend' | 'none'
  const [activeTab, setActiveTab] = useState('none');
  const [visualPayload, setVisualPayload] = useState(null);
  
  // Case detail modal state
  const [selectedCaseId, setSelectedCaseId] = useState(null);

  // 1. Initialize chat session on load
  useEffect(() => {
    const initSession = async () => {
      try {
        const res = await fetch('http://127.0.0.1:8000/api/chat/session', {
          method: 'POST'
        });
        if (!res.ok) throw new Error('Failed to create session');
        const data = await res.json();
        setSessionId(data.session_id);
      } catch (err) {
        console.error('Session initialization failed:', err);
        // Fallback session ID to prevent breaking UI
        setSessionId('session-local-fallback');
      }
    };
    initSession();
  }, []);

  // 2. Message sending logic
  const handleSendMessage = async (text) => {
    if (!sessionId || isLoading) return;

    // Append user message immediately
    const userMsg = {
      role: 'user',
      content: text,
      created_at: new Date().toISOString()
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const res = await fetch('http://127.0.0.1:8000/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          message: text,
          language: language
        })
      });

      if (!res.ok) throw new Error('Failed to get chat response');
      const data = await res.json();

      // Append assistant message
      const assistantMsg = {
        role: 'assistant',
        content: data.answer,
        citations: data.citations || [],
        created_at: new Date().toISOString()
      };
      setMessages((prev) => [...prev, assistantMsg]);

      // Automatically switch to visualization tab if payload is returned
      if (data.visual_type !== 'none' && data.visual_payload) {
        setActiveTab(data.visual_type);
        setVisualPayload(data.visual_payload);
      }
    } catch (err) {
      console.error('Error posting message:', err);
      const errorMsg = {
        role: 'assistant',
        content: language === 'kn'
          ? 'ದಿನಚರಿ ಲೋಡ್ ಮಾಡಲು ಸಾಧ್ಯವಾಗಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೊಮ್ಮೆ ಪ್ರಯತ್ನಿಸಿ.'
          : 'Could not connect to the assistant server. Please check your connection and try again.',
        citations: [],
        created_at: new Date().toISOString()
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setIsLoading(false);
    }
  };

  // 3. Export session chat to PDF using jsPDF
  const handleExportPDF = () => {
    if (messages.length === 0) return;
    const doc = new jsPDF();

    // Title / Header Styling
    doc.setFillColor(10, 14, 23);
    doc.rect(0, 0, 210, 30, 'F');
    doc.setTextColor(0, 242, 254);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(16);
    doc.text('Karnataka Crime GPT', 15, 18);
    doc.setFontSize(9);
    doc.setTextColor(156, 163, 175);
    doc.text(`Session Transcript: ${sessionId}`, 15, 25);

    let yOffset = 40;

    messages.forEach((msg) => {
      const isUser = msg.role === 'user';
      const roleText = isUser ? 'User' : 'GPT Assistant';
      const dateText = new Date(msg.created_at).toLocaleString();

      // Page limit check
      if (yOffset > 260) {
        doc.addPage();
        yOffset = 20;
      }

      // Role Header
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(10);
      doc.setTextColor(isUser ? 79 : 0, isUser ? 172 : 198, isUser ? 254 : 255);
      doc.text(`${roleText} (${dateText}):`, 15, yOffset);
      yOffset += 5;

      // Message Body
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(10.5);
      doc.setTextColor(240, 240, 240); // Close to white for dark backgrounds
      
      // Clean markdown tags for pdf readability
      const cleanContent = msg.content.replace(/\*\*/g, '');
      const textLines = doc.splitTextToSize(cleanContent, 180);

      textLines.forEach((line) => {
        if (yOffset > 275) {
          doc.addPage();
          yOffset = 20;
        }
        doc.text(line, 15, yOffset);
        yOffset += 5.5;
      });

      // Render citations list if assistant has them
      if (msg.citations && msg.citations.length > 0) {
        doc.setFont('helvetica', 'italic');
        doc.setFontSize(9);
        doc.setTextColor(156, 163, 175);
        const citText = 'Citations: ' + msg.citations.map((c) => `FIR ${c.fir_number}`).join(', ');
        
        if (yOffset > 275) {
          doc.addPage();
          yOffset = 20;
        }
        doc.text(citText, 15, yOffset);
        yOffset += 6;
      }

      yOffset += 6; // Extra space between message blocks
    });

    // Save to disk
    doc.save(`CrimeGPT-Transcript-${sessionId.slice(0, 8)}.pdf`);
  };

  // 4. Handle double clicking a node in the graph
  const handleGraphNodeClick = (node) => {
    if (node.type === 'case') {
      // Split node ID 'case_12' to get original ID/FIR
      const caseId = node.id.replace('case_', '');
      setSelectedCaseId(caseId);
    } else if (node.type === 'accused') {
      const accusedId = node.id.replace('accused_', '');
      // High-light connection or search accomplishments
      handleSendMessage(language === 'kn' 
        ? `ಆರೋಪಿ ID ${accusedId} ರ ಪ್ರಕರಣದ ವಿವರಗಳನ್ನು ತೋರಿಸಿ` 
        : `Show other cases for accused ID ${accusedId}`);
    }
  };

  return (
    <div className="app-container">
      {/* App Header */}
      <header className="app-header">
        <div className="header-title-container">
          <ShieldAlert className="header-logo" size={24} />
          <div>
            <h1 className="app-title">KARNATAKA CRIME GPT</h1>
            <p className="app-subtitle">Criminal Network & Trend Intelligence Dashboard</p>
          </div>
        </div>
      </header>

      {/* Main Body Layout */}
      <div className="app-body">
        {/* Chat Panel - Left 35-40% */}
        <ChatPanel
          messages={messages}
          onSendMessage={handleSendMessage}
          isLoading={isLoading}
          language={language}
          setLanguage={setLanguage}
          onCitationClick={setSelectedCaseId}
          onExportPDF={handleExportPDF}
        />

        {/* Visualizations Panel - Right 60-65% */}
        <div className="glass-panel visual-side">
          {/* Tabs header */}
          <div className="visual-tabs">
            <button 
              className={`visual-tab-btn ${activeTab === 'network' ? 'active' : ''}`}
              onClick={() => setActiveTab('network')}
            >
              <Network size={16} />
              <span>{language === 'kn' ? 'ಸಂಬಂಧಗಳ ಜಾಲ' : 'Network Graph'}</span>
            </button>
            <button 
              className={`visual-tab-btn ${activeTab === 'trend' ? 'active' : ''}`}
              onClick={() => setActiveTab('trend')}
            >
              <BarChart2 size={16} />
              <span>{language === 'kn' ? 'ಅಪರಾಧ ಪ್ರವೃತ್ತಿ' : 'Crime Trends'}</span>
            </button>
          </div>

          {/* Tab contents */}
          <div className="visual-content-container">
            {activeTab === 'none' ? (
              <div className="placeholder-view">
                <HelpCircle size={48} className="placeholder-icon" />
                <h3>{language === 'kn' ? 'ವಿಶುಲೈಸೇಶನ್ ವಿಂಡೋ' : 'Interactive Visualization Panel'}</h3>
                <p>
                  {language === 'kn' 
                    ? 'ನೆಟ್‌ವರ್ಕ್ ಆಕೃತಿಗಳು ಮತ್ತು ಅಪರಾಧ ಪ್ರವೃತ್ತಿಗಳ ಚಾರ್ಟ್‌ಗಳು ಸ್ವಯಂಚಾಲಿತವಾಗಿ ಇಲ್ಲಿ ಪ್ರದರ್ಶನಗೊಳ್ಳುತ್ತವೆ.'
                    : 'Interactive network graphs, accomplice chains, and crime trends will automatically render here based on your conversation queries.'}
                </p>
                
                {/* Visual Quick tips */}
                <div style={{ marginTop: '24px', display: 'flex', flexDirection: 'column', gap: '12px', textAlign: 'left', maxWidth: '380px', fontSize: '13px', background: 'rgba(255,255,255,0.02)', padding: '16px', borderRadius: '12px', border: '1px solid var(--border-glass)' }}>
                  <div style={{ display: 'flex', gap: '10px' }}>
                    <Network size={16} style={{ color: 'var(--color-accused)', flexShrink: 0, marginTop: '2px' }} />
                    <span><strong>Accomplices:</strong> Try "Show network for Shankar" or "Who are the links for accused Ravi Kumar?"</span>
                  </div>
                  <div style={{ display: 'flex', gap: '10px' }}>
                    <BarChart2 size={16} style={{ color: 'var(--accent-cyan)', flexShrink: 0, marginTop: '2px' }} />
                    <span><strong>Analytics:</strong> Try "Show crime types in Mysuru" or "Show monthly theft trend".</span>
                  </div>
                </div>
              </div>
            ) : activeTab === 'network' ? (
              <NetworkGraph 
                data={visualPayload} 
                onNodeClick={handleGraphNodeClick} 
              />
            ) : (
              <TrendChart 
                payload={visualPayload} 
                language={language} 
              />
            )}
          </div>
        </div>
      </div>

      {/* Case Details Slide Overlay Modal */}
      {selectedCaseId && (
        <CaseDetailModal
          caseId={selectedCaseId}
          onClose={() => setSelectedCaseId(null)}
          language={language}
        />
      )}
    </div>
  );
}
