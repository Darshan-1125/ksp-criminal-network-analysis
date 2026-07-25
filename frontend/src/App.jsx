import React, { useState, useEffect, useRef } from 'react';
import { jsPDF } from 'jspdf';
import { 
  ShieldAlert, 
  Network, 
  BarChart2, 
  HelpCircle,
  LogOut,
  UserCheck,
  ShieldCheck
} from 'lucide-react';

import { AuthProvider, useAuth } from './context/AuthContext';
import LoginPage from './components/LoginPage';
import ChatPanel from './components/ChatPanel';
import NetworkGraph from './components/NetworkGraph';
import TrendChart from './components/TrendChart';
import CaseDetailModal from './components/CaseDetailModal';
import AuditLogTable from './components/AuditLogTable';

function MainDashboard() {
  const { user, logout, apiFetch } = useAuth();
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingSession, setIsLoadingSession] = useState(false);
  const [language, setLanguage] = useState('en');

  const userRole = user?.role || 'investigator';
  const isPolicymaker = userRole === 'policymaker' || userRole === 'read_only';
  const isSupervisor = userRole === 'supervisor' || userRole === 'admin';

  // Tab states: 'network' | 'trend' | 'audit' | 'none'
  const [activeTab, setActiveTab] = useState(isPolicymaker ? 'trend' : 'none');
  const [visualPayload, setVisualPayload] = useState(null);
  const [selectedCaseId, setSelectedCaseId] = useState(null);

  // Resizable Panel States & Storage Persistence
  const bodyRef = useRef(null);
  const [chatWidth, setChatWidth] = useState(() => {
    const saved = localStorage.getItem('crime_gpt_chat_panel_width');
    return saved ? parseFloat(saved) : 38;
  });
  const [isResizing, setIsResizing] = useState(false);

  const handleResizeStart = (e) => {
    e.preventDefault();
    setIsResizing(true);
  };

  useEffect(() => {
    if (!isResizing) return;

    const handleMove = (e) => {
      if (!bodyRef.current) return;
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const rect = bodyRef.current.getBoundingClientRect();
      const relativeX = clientX - rect.left;
      
      const minChatPx = 280;
      const minVisualPx = 400;
      const totalWidth = rect.width;

      if (totalWidth <= 0) return;

      const minPercent = (minChatPx / totalWidth) * 100;
      const maxPercent = ((totalWidth - minVisualPx) / totalWidth) * 100;

      let newPercent = (relativeX / totalWidth) * 100;
      if (newPercent < minPercent) newPercent = minPercent;
      if (newPercent > maxPercent) newPercent = maxPercent;

      setChatWidth(newPercent);
    };

    const handleEnd = () => {
      setIsResizing(false);
      localStorage.setItem('crime_gpt_chat_panel_width', chatWidth.toString());
    };

    window.addEventListener('mousemove', handleMove);
    window.addEventListener('mouseup', handleEnd);
    window.addEventListener('touchmove', handleMove);
    window.addEventListener('touchend', handleEnd);

    return () => {
      window.removeEventListener('mousemove', handleMove);
      window.removeEventListener('mouseup', handleEnd);
      window.removeEventListener('touchmove', handleMove);
      window.removeEventListener('touchend', handleEnd);
    };
  }, [isResizing, chatWidth]);

  // Session Deletion Logic
  const handleDeleteSession = async (targetSessionId) => {
    if (!targetSessionId) return;

    const previousSessions = [...sessions];
    const updatedSessions = sessions.filter((s) => s.session_id !== targetSessionId);
    setSessions(updatedSessions);

    try {
      const res = await apiFetch(`/api/chat/sessions/${targetSessionId}`, {
        method: 'DELETE'
      });

      if (!res.ok) {
        throw new Error('Delete session API returned failure status');
      }

      if (targetSessionId === sessionId) {
        if (updatedSessions.length > 0) {
          await loadSessionMessages(updatedSessions[0].session_id);
        } else {
          await handleCreateNewSession();
        }
      }
      await fetchUserSessions();
    } catch (err) {
      console.error(`Failed to delete session ${targetSessionId}:`, err);
      setSessions(previousSessions);
      alert(language === 'kn' ? 'ಸಂಭಾಷಣೆಯನ್ನು ಅಳಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಪ್ರಯತ್ನಿಸಿ.' : 'Failed to delete session. Please try again.');
    }
  };

  // 1. Fetch user sessions from backend
  const fetchUserSessions = async () => {
    try {
      const res = await apiFetch('/api/chat/sessions');
      if (res.ok) {
        const data = await res.json();
        const sessionList = data.sessions || [];
        setSessions(sessionList);
        return sessionList;
      }
    } catch (err) {
      console.error('Failed to fetch user sessions:', err);
    }
    return [];
  };

  // 2. Load full message history & visual payload for a specific session ID
  const loadSessionMessages = async (targetSessionId) => {
    if (!targetSessionId) return;
    setIsLoadingSession(true);
    try {
      const res = await apiFetch(`/api/chat/sessions/${targetSessionId}/messages`);
      if (res.ok) {
        const data = await res.json();
        const loadedMsgs = data.messages || [];
        setMessages(loadedMsgs);
        setSessionId(targetSessionId);

        // Restore visual payload and tab from historical messages if present
        let restoredVisual = null;
        let restoredType = null;
        for (let i = loadedMsgs.length - 1; i >= 0; i--) {
          const m = loadedMsgs[i];
          if (m.visual_type && m.visual_type !== 'none' && m.visual_payload) {
            restoredVisual = m.visual_payload;
            restoredType = m.visual_type;
            break;
          }
        }
        if (restoredType && restoredVisual) {
          if (isPolicymaker && restoredType === 'network') {
            setActiveTab('trend');
          } else {
            setActiveTab(restoredType);
            setVisualPayload(restoredVisual);
          }
        } else {
          setVisualPayload(null);
        }
      }
    } catch (err) {
      console.error(`Failed to load session ${targetSessionId}:`, err);
    } finally {
      setIsLoadingSession(false);
    }
  };

  // 3. Create a brand-new chat session
  const handleCreateNewSession = async () => {
    setIsLoadingSession(true);
    try {
      const res = await apiFetch('/api/chat/session', { method: 'POST' });
      if (!res.ok) throw new Error('Failed to create session');
      const data = await res.json();
      const newId = data.session_id;
      setSessionId(newId);
      setMessages([]);
      setVisualPayload(null);
      setActiveTab(isPolicymaker ? 'trend' : 'none');
      await fetchUserSessions();
    } catch (err) {
      console.error('New session creation failed:', err);
    } finally {
      setIsLoadingSession(false);
    }
  };

  // 4. Select a session from history
  const handleSelectSession = async (targetSessionId) => {
    if (targetSessionId === sessionId) return;
    await loadSessionMessages(targetSessionId);
  };

  // 5. Initial hydration on mount / login
  useEffect(() => {
    const initUserChat = async () => {
      setIsLoadingSession(true);
      const userSessions = await fetchUserSessions();
      if (userSessions && userSessions.length > 0) {
        const latestSessionId = userSessions[0].session_id;
        await loadSessionMessages(latestSessionId);
      } else {
        await handleCreateNewSession();
      }
      setIsLoadingSession(false);
    };

    initUserChat();
  }, []);

  // 6. Message sending logic using centralized apiFetch
  const handleSendMessage = async (text) => {
    if (!sessionId || isLoading) return;

    const userMsg = {
      role: 'user',
      content: text,
      created_at: new Date().toISOString()
    };
    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const res = await apiFetch('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
          session_id: sessionId,
          message: text,
          language: language
        })
      });

      if (!res.ok) throw new Error('Failed to get chat response');
      const data = await res.json();

      const assistantMsg = {
        role: 'assistant',
        content: data.answer,
        citations: data.citations || [],
        total_count: data.total_count || 0,
        returned_count: data.returned_count || 0,
        shown_count: data.returned_count || 0,
        offset: data.offset || 0,
        limit: data.limit || 15,
        original_query: text,
        visual_type: data.visual_type,
        visual_payload: data.visual_payload,
        created_at: new Date().toISOString()
      };
      setMessages((prev) => [...prev, assistantMsg]);

      // Automatically switch to visualization tab if payload returned
      if (data.visual_type && data.visual_type !== 'none' && data.visual_payload) {
        setVisualPayload({ ...data.visual_payload });
        if (isPolicymaker && data.visual_type === 'network') {
          setActiveTab('trend');
        } else {
          setActiveTab(data.visual_type);
        }
      }

      // Refresh session list so preview snippet and message count stay updated
      fetchUserSessions();
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

  // Handle "Show N more" pagination request
  const handleShowMore = async (msg, msgIndex) => {
    if (!sessionId || isLoading) return;
    setIsLoading(true);

    const currentShown = msg.shown_count || msg.returned_count || 0;
    const nextOffset = currentShown;

    let queryText = msg.original_query;
    if (!queryText) {
      for (let i = msgIndex - 1; i >= 0; i--) {
        if (messages[i]?.role === 'user') {
          queryText = messages[i].content;
          break;
        }
      }
    }
    if (!queryText) queryText = '';

    try {
      const res = await apiFetch('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
          session_id: sessionId,
          message: queryText,
          language: language,
          offset: nextOffset
        })
      });

      if (!res.ok) throw new Error('Failed to fetch next batch of cases');
      const data = await res.json();

      setMessages((prev) => {
        const updated = [...prev];
        const target = { ...updated[msgIndex] };

        target.content = target.content + '\n\n' + data.answer;

        const existingCits = target.citations || [];
        const newCits = data.citations || [];
        const combinedCits = [...existingCits];
        newCits.forEach((c) => {
          if (!combinedCits.some((ec) => ec.fir_number === c.fir_number)) {
            combinedCits.push(c);
          }
        });

        const newReturned = data.returned_count || 0;
        target.citations = combinedCits;
        target.returned_count = newReturned;
        target.offset = nextOffset;
        target.shown_count = currentShown + newReturned;
        if (data.total_count) {
          target.total_count = data.total_count;
        }
        updated[msgIndex] = target;
        return updated;
      });
    } catch (err) {
      console.error('Error in handleShowMore:', err);
    } finally {
      setIsLoading(false);
    }
  };

// Helper to sanitize text for jsPDF standard Helvetica rendering
const sanitizeTextForPDF = (text) => {
  if (!text) return '';
  let result = text
    .replace(/💡/g, 'Tip: ')
    .replace(/⚠️/g, 'Warning: ')
    .replace(/ℹ️|ℹ/g, 'Info: ')
    .replace(/🔍/g, 'Search: ')
    .replace(/📌/g, 'Note: ')
    .replace(/✅/g, '[OK] ')
    .replace(/❌/g, '[X] ')
    .replace(/📊/g, '[Chart] ')
    .replace(/🚨/g, '[Alert] ')
    .replace(/👤/g, '[Person] ')
    .replace(/🏢/g, '[Station] ')
    .replace(/📅/g, '[Date] ')
    .replace(/📋/g, '[Record] ');

  // Strip any remaining high-codepoint Unicode emoji / symbol characters outside WinAnsi range
  result = result.replace(/[\u{1F000}-\u{1F9FF}]|[\u{1F300}-\u{1F5FF}]|[\u{1F600}-\u{1F64F}]|[\u{1F680}-\u{1F6FF}]|[\u{2600}-\u{27BF}]/gu, '');
  return result;
};

  // 3. Export session chat to PDF using jsPDF
  const handleExportPDF = () => {
    if (messages.length === 0) return;
    const doc = new jsPDF();

    // Top Header Block (Page 1)
    doc.setFillColor(10, 14, 23);
    doc.rect(0, 0, 210, 30, 'F');
    doc.setTextColor(0, 242, 254);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(16);
    doc.text('Karnataka Crime GPT', 15, 18);
    doc.setFontSize(9);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(156, 163, 175);
    doc.text(`Session Transcript: ${sessionId} | Role: ${userRole}`, 15, 25);

    let yOffset = 40;

    messages.forEach((msg) => {
      const isUser = msg.role === 'user';
      const roleText = isUser ? 'User' : 'GPT Assistant';
      const dateText = new Date(msg.created_at).toLocaleString();

      if (yOffset > 260) {
        doc.addPage();
        yOffset = 20;
      }

      // Role Header & Timestamp
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(10);
      // High-contrast colors for light page background: User = Deep Navy (#1B559B), Assistant = Deep Teal (#0F766E)
      doc.setTextColor(isUser ? 27 : 15, isUser ? 85 : 118, isUser ? 155 : 110);
      doc.text(`${roleText} (${dateText}):`, 15, yOffset);
      yOffset += 6;

      // Message Body Content
      const rawLines = msg.content.split('\n');

      rawLines.forEach((rawLine) => {
        const sanitizedLine = sanitizeTextForPDF(rawLine);
        const trimmed = sanitizedLine.trim();
        if (!trimmed) {
          yOffset += 3;
          return;
        }

        const isHeader = rawLine.startsWith('###') || rawLine.startsWith('##');
        const isFirHeader = /^\d+\.\s*\*\*FIR/i.test(trimmed) || trimmed.startsWith('**FIR');
        const isItalicTip = trimmed.startsWith('Tip:') || /^\s*[\*_]/.test(rawLine) || rawLine.includes('structured search filters');

        let cleanedText = sanitizedLine.replace(/^###\s*/, '').replace(/^##\s*/, '');
        cleanedText = cleanedText.replace(/\*\*/g, '').replace(/\*/g, '').replace(/_/g, '').replace(/\s+/g, ' ').trim();

        if (isHeader || isFirHeader) {
          doc.setFont('helvetica', 'bold');
          doc.setFontSize(10.5);
          doc.setTextColor(15, 23, 42); // Dark Navy #0F172A
        } else if (isItalicTip) {
          doc.setFont('helvetica', 'italic');
          doc.setFontSize(9.5);
          doc.setTextColor(71, 85, 105); // Slate Gray #475569
        } else {
          doc.setFont('helvetica', 'normal');
          doc.setFontSize(10);
          doc.setTextColor(30, 41, 59); // Dark Slate #1E293B
        }

        const textLines = doc.splitTextToSize(cleanedText, 180);
        textLines.forEach((line) => {
          if (yOffset > 270) {
            doc.addPage();
            yOffset = 20;
          }
          doc.text(line, 15, yOffset);
          yOffset += 5.2;
        });
      });

      // Citations Block
      if (!isPolicymaker && msg.citations && msg.citations.length > 0) {
        if (yOffset > 265) {
          doc.addPage();
          yOffset = 20;
        }

        // Subtle divider rule above citations
        doc.setDrawColor(226, 232, 240); // Light Slate #E2E8F0
        doc.setLineWidth(0.3);
        doc.line(15, yOffset, 195, yOffset);
        yOffset += 4;

        doc.setFont('helvetica', 'italic');
        doc.setFontSize(9);
        doc.setTextColor(71, 85, 105); // Dark Slate Gray #475569
        const citText = 'Citations: ' + msg.citations.map((c) => `FIR ${c.fir_number}`).join(', ');
        
        const citLines = doc.splitTextToSize(citText, 180);
        citLines.forEach((cline) => {
          if (yOffset > 270) {
            doc.addPage();
            yOffset = 20;
          }
          doc.text(cline, 15, yOffset);
          yOffset += 4.8;
        });
      }

      yOffset += 6;
    });

    // Stamp Page Numbers on Footers of all pages
    const totalPages = doc.getNumberOfPages();
    for (let i = 1; i <= totalPages; i++) {
      doc.setPage(i);
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(8);
      doc.setTextColor(148, 163, 184); // Slate Gray #94A3B8
      doc.text(
        `Karnataka Crime GPT - Confidential Audit Transcript | Page ${i} of ${totalPages}`,
        105,
        287,
        { align: 'center' }
      );
    }

    doc.save(`CrimeGPT-Transcript-${sessionId.slice(0, 8)}.pdf`);
  };

  const handleGraphNodeClick = (node) => {
    if (isPolicymaker) return; // Disable opening case details for policymaker
    if (node.type === 'case') {
      const caseId = node.id.replace('case_', '');
      setSelectedCaseId(caseId);
    } else if (node.type === 'accused') {
      const accusedId = node.id.replace('accused_', '');
      handleSendMessage(language === 'kn' 
        ? `ಆರೋಪಿ ID ${accusedId} ರ ಪ್ರಕರಣದ ವಿವರಗಳನ್ನು ತೋರಿಸಿ` 
        : `Show other cases for accused ID ${accusedId}`);
    }
  };

  return (
    <div className="app-container">
      {/* App Header with User Info and Logout */}
      <header className="app-header">
        <div className="header-title-container">
          <ShieldAlert className="header-logo" size={24} />
          <div>
            <h1 className="app-title">KARNATAKA CRIME GPT</h1>
            <p className="app-subtitle">Criminal Network & Trend Intelligence Dashboard</p>
          </div>
        </div>

        <div className="header-controls">
          <div className="user-badge-container">
            <span className={`role-tag role-${userRole}`}>
              <UserCheck size={14} />
              Logged in as: {userRole} ({user?.full_name || user?.username})
            </span>
            <button className="logout-btn" onClick={logout} title="Sign Out">
              <LogOut size={14} />
              <span>Logout</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Body Layout */}
      <div ref={bodyRef} className={`app-body ${isResizing ? 'is-resizing' : ''}`}>
        {/* Chat Panel - Left */}
        <div className="chat-side-wrapper" style={{ flex: `0 0 ${chatWidth}%`, width: `${chatWidth}%` }}>
          <ChatPanel
            messages={messages}
            onSendMessage={handleSendMessage}
            onShowMore={handleShowMore}
            isLoading={isLoading}
            language={language}
            setLanguage={setLanguage}
            onCitationClick={isPolicymaker ? undefined : setSelectedCaseId}
            onExportPDF={handleExportPDF}
            isPolicymaker={isPolicymaker}
            sessions={sessions}
            currentSessionId={sessionId}
            onSelectSession={handleSelectSession}
            onNewSession={handleCreateNewSession}
            onDeleteSession={handleDeleteSession}
            isLoadingSession={isLoadingSession}
          />
        </div>

        {/* Draggable Resize Divider */}
        <div
          className={`resize-divider ${isResizing ? 'active' : ''}`}
          onMouseDown={handleResizeStart}
          onTouchStart={handleResizeStart}
          title="Drag to resize panels"
        >
          <div className="resize-divider-bar" />
        </div>

        {/* Visualizations & Audit Panel - Right */}
        <div className="glass-panel visual-side">
          {/* Tabs header */}
          <div className="visual-tabs">
            {!isPolicymaker && (
              <button 
                className={`visual-tab-btn ${activeTab === 'network' ? 'active' : ''}`}
                onClick={() => setActiveTab('network')}
              >
                <Network size={16} />
                <span>{language === 'kn' ? 'ಸಂಬಂಧಗಳ ಜಾಲ' : 'Network Graph'}</span>
              </button>
            )}

            <button 
              className={`visual-tab-btn ${activeTab === 'trend' ? 'active' : ''}`}
              onClick={() => setActiveTab('trend')}
            >
              <BarChart2 size={16} />
              <span>{language === 'kn' ? 'ಅಪರಾಧ ಪ್ರವೃತ್ತಿ' : 'Crime Trends'}</span>
            </button>

            {isSupervisor && (
              <button 
                className={`visual-tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
                onClick={() => setActiveTab('audit')}
              >
                <ShieldCheck size={16} />
                <span>{language === 'kn' ? 'ಆಡಿಟ್ ಲಾಗ್ಗಳು' : 'Audit Logs'}</span>
              </button>
            )}
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
              </div>
            ) : activeTab === 'network' && !isPolicymaker ? (
              <NetworkGraph 
                data={visualPayload} 
                onNodeClick={handleGraphNodeClick} 
              />
            ) : activeTab === 'trend' ? (
              <TrendChart 
                payload={visualPayload} 
                language={language} 
              />
            ) : activeTab === 'audit' && isSupervisor ? (
              <AuditLogTable />
            ) : (
              <TrendChart payload={visualPayload} language={language} />
            )}
          </div>
        </div>
      </div>

      {/* Case Details Slide Overlay Modal (Suppressed for Policymakers) */}
      {!isPolicymaker && selectedCaseId && (
        <CaseDetailModal
          caseId={selectedCaseId}
          onClose={() => setSelectedCaseId(null)}
          language={language}
        />
      )}
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

function AppContent() {
  const { isAuthenticated, isInitializing } = useAuth();

  if (isInitializing) {
    return (
      <div className="login-screen-overlay">
        <div style={{ color: 'var(--accent-cyan)', fontSize: '16px', fontWeight: 600 }}>
          Authenticating session...
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginPage />;
  }

  return <MainDashboard />;
}
