import React from 'react';
import { Plus, MessageSquare, Clock, X, ChevronRight, History, Trash2 } from 'lucide-react';

export default function SessionHistory({
  sessions = [],
  currentSessionId,
  onSelectSession,
  onNewSession,
  onDeleteSession,
  isLoadingSession,
  language = 'en',
  onClose
}) {
  const formatDate = (isoString) => {
    if (!isoString) return '';
    const date = new Date(isoString);
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();

    if (isToday) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  const handleDelete = (e, targetSessionId) => {
    e.stopPropagation();
    const confirmMsg = language === 'kn'
      ? 'ಈ ಸಂಭಾಷಣೆಯನ್ನು ಅಳಿಸಬೇಕೇ? ಇದನ್ನು ಹಿಂತಿರುಗಿಸಲು ಸಾಧ್ಯವಿಲ್ಲ.'
      : 'Delete this session? This action cannot be undone.';
    if (window.confirm(confirmMsg)) {
      if (onDeleteSession) {
        onDeleteSession(targetSessionId);
      }
    }
  };

  return (
    <div className="session-history-drawer">
      <div className="session-history-header">
        <div className="session-history-title">
          <History size={16} className="header-logo" />
          <span>{language === 'kn' ? 'ಹಿಂದಿನ ಸಂಭಾಷಣೆಗಳು' : 'Chat History'}</span>
        </div>
        {onClose && (
          <button className="icon-btn-close" onClick={onClose} title="Close History">
            <X size={16} />
          </button>
        )}
      </div>

      <div className="session-history-actions">
        <button 
          className="btn-new-chat" 
          onClick={onNewSession}
          disabled={isLoadingSession}
        >
          <Plus size={16} />
          <span>{language === 'kn' ? 'ಹೊಸ ಸಂಭಾಷಣೆ' : 'New Conversation'}</span>
        </button>
      </div>

      <div className="session-list-container">
        {sessions.length === 0 ? (
          <div className="empty-history">
            <MessageSquare size={32} className="placeholder-icon" />
            <p>{language === 'kn' ? 'ಯಾವುದೇ ಹಿಂದಿನ ಸಂಭಾಷಣೆಗಳಿಲ್ಲ' : 'No previous chat sessions found.'}</p>
          </div>
        ) : (
          sessions.map((session) => {
            const isActive = session.session_id === currentSessionId;
            return (
              <div
                key={session.session_id}
                className={`session-item ${isActive ? 'active' : ''}`}
                onClick={() => onSelectSession(session.session_id)}
              >
                <div className="session-item-content">
                  <div className="session-preview" title={session.preview}>
                    {session.preview || (language === 'kn' ? 'ಹೊಸ ಸಂಭಾಷಣೆ' : 'New Conversation')}
                  </div>
                  <div className="session-meta">
                    <span className="session-time">
                      <Clock size={11} />
                      {formatDate(session.created_at)}
                    </span>
                    <span className="session-badge">
                      {session.message_count} {language === 'kn' ? 'ಸಂದೇಶಗಳು' : 'msgs'}
                    </span>
                  </div>
                </div>
                <div className="session-item-actions">
                  <button
                    className="session-delete-btn"
                    title={language === 'kn' ? 'ಸಂಭಾಷಣೆಯನ್ನು ಅಳಿಸಿ' : 'Delete session'}
                    onClick={(e) => handleDelete(e, session.session_id)}
                  >
                    <Trash2 size={14} />
                  </button>
                  <ChevronRight size={14} className="session-arrow" />
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
