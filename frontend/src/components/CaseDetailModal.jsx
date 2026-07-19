import React, { useState, useEffect } from 'react';
import { X, Calendar, MapPin, ShieldAlert, Users, FileText, Activity } from 'lucide-react';

export default function CaseDetailModal({ caseId, onClose, language }) {
  const [caseData, setCaseData] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!caseId) return;

    const fetchCaseDetails = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const res = await fetch(`http://127.0.0.1:8000/api/cases/${caseId}`);
        if (!res.ok) {
          throw new Error('Failed to fetch case details');
        }
        const data = await res.json();
        setCaseData(data);
      } catch (err) {
        console.error('Error fetching case:', err);
        setError(language === 'kn' ? 'ಪ್ರಕರಣದ ವಿವರಗಳನ್ನು ಲೋಡ್ ಮಾಡಲು ಸಾಧ್ಯವಾಗುತ್ತಿಲ್ಲ.' : 'Failed to load case details.');
      } finally {
        setIsLoading(false);
      }
    };

    fetchCaseDetails();
  }, [caseId, language]);

  if (!caseId) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <div className="modal-title-group">
            <span className="modal-title">
              {isLoading ? (language === 'kn' ? 'ವಿವರಗಳನ್ನು ಲೋಡ್ ಮಾಡಲಾಗುತ್ತಿದೆ...' : 'Loading Details...') : `FIR: ${caseData?.fir_number || caseId}`}
            </span>
            <span className="modal-subtitle">
              {language === 'kn' ? 'ಕರ್ನಾಟಕ ಪೊಲೀಸ್ ದಾಖಲೆಗಳು' : 'Karnataka Police FIR Record'}
            </span>
          </div>
          <button className="modal-close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        {isLoading ? (
          <div className="modal-body" style={{ alignItems: 'center', justifyContent: 'center', minHeight: '200px' }}>
            <div className="loading-dots">
              <span></span>
              <span></span>
              <span></span>
            </div>
          </div>
        ) : error ? (
          <div className="modal-body" style={{ alignItems: 'center', justifyContent: 'center', minHeight: '200px', color: 'var(--color-accused)' }}>
            <ShieldAlert size={36} style={{ marginBottom: '12px' }} />
            <p>{error}</p>
          </div>
        ) : (
          <div className="modal-body">
            {/* Top row filters/metadata */}
            <div className="info-grid">
              <div className="info-item">
                <span className="info-label">{language === 'kn' ? 'ಅಪರಾಧದ ವಿಧ' : 'Crime Type'}</span>
                <span className="info-value" style={{ color: 'var(--accent-cyan)', fontWeight: 'bold' }}>
                  {caseData.crime_type}
                </span>
              </div>
              <div className="info-item">
                <span className="info-label">{language === 'kn' ? 'ತನಿಖೆಯ ಸ್ಥಿತಿ' : 'Investigation Status'}</span>
                <span className={`info-value status-badge ${caseData.status}`}>
                  {caseData.status === 'under_investigation' 
                    ? (language === 'kn' ? 'ತನಿಖೆಯಲ್ಲಿದೆ' : 'Under Investigation') 
                    : (language === 'kn' ? 'ಬಗೆಹರಿದಿದೆ' : 'Solved')}
                </span>
              </div>
              <div className="info-item">
                <span className="info-label">{language === 'kn' ? 'ಐಪಿಸಿ ಸೆಕ್ಷನ್ಗಳು' : 'IPC Sections'}</span>
                <span className="info-value">{caseData.ipc_sections || 'N/A'}</span>
              </div>
              <div className="info-item">
                <span className="info-label">{language === 'kn' ? 'ದಾಖಲಾದ ದಿನಾಂಕ' : 'Date Reported'}</span>
                <span className="info-value" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Calendar size={13} style={{ color: 'var(--text-secondary)' }} />
                  {caseData.date_reported}
                </span>
              </div>
              <div className="info-item">
                <span className="info-label">{language === 'kn' ? 'ಪೊಲೀಸ್ ಠಾಣೆ' : 'Police Station'}</span>
                <span className="info-value">{caseData.police_station || 'N/A'}</span>
              </div>
              <div className="info-item">
                <span className="info-label">{language === 'kn' ? 'ಜಿಲ್ಲೆ' : 'District'}</span>
                <span className="info-value">{caseData.district || 'N/A'}</span>
              </div>
            </div>

            {/* Modus Operandi */}
            <div className="modal-section">
              <span className="modal-section-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Activity size={14} />
                <span>{language === 'kn' ? 'ಕಾರ್ಯಾಚರಣೆಯ ವಿಧಾನ (MO)' : 'Modus Operandi (MO)'}</span>
              </span>
              <p className="modal-section-content" style={{ fontStyle: 'italic', color: 'var(--text-secondary)' }}>
                {caseData.mo_description || (language === 'kn' ? 'ಮಾಹಿತಿ ಲಭ್ಯವಿಲ್ಲ.' : 'No MO description specified.')}
              </p>
            </div>

            {/* Suspects & Victims */}
            <div className="info-grid">
              <div className="modal-section">
                <span className="modal-section-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Users size={14} style={{ color: 'var(--color-accused)' }} />
                  <span>{language === 'kn' ? 'ಆರೋಪಿಗಳು' : 'Accused / Suspects'}</span>
                </span>
                <div className="entity-list-modal">
                  {caseData.accused && caseData.accused.length > 0 ? (
                    caseData.accused.map((acc, idx) => (
                      <span key={idx} className="entity-modal-chip" style={{ borderColor: 'rgba(255, 94, 98, 0.2)', color: 'var(--color-accused)' }}>
                        {acc.name} (ID: {acc.id})
                      </span>
                    ))
                  ) : (
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      {language === 'kn' ? 'ಯಾರೂ ಇಲ್ಲ' : 'No accused specified'}
                    </span>
                  )}
                </div>
              </div>

              <div className="modal-section">
                <span className="modal-section-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Users size={14} style={{ color: 'var(--color-location)' }} />
                  <span>{language === 'kn' ? 'ಬಲಿಪಶುಗಳು' : 'Victims'}</span>
                </span>
                <div className="entity-list-modal">
                  {caseData.victims && caseData.victims.length > 0 ? (
                    caseData.victims.map((vic, idx) => (
                      <span key={idx} className="entity-modal-chip" style={{ borderColor: 'rgba(0, 242, 96, 0.2)', color: 'var(--color-location)' }}>
                        {vic.name} (ID: {vic.id})
                      </span>
                    ))
                  ) : (
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      {language === 'kn' ? 'ಯಾರೂ ಇಲ್ಲ' : 'No victims specified'}
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Incident Location */}
            <div className="modal-section">
              <span className="modal-section-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <MapPin size={14} />
                <span>{language === 'kn' ? 'ಘಟನೆಯ ಸ್ಥಳ' : 'Incident Location'}</span>
              </span>
              <div className="modal-section-content" style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <span>{caseData.location?.address || 'N/A'}</span>
                {caseData.location?.lat && (
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {language === 'kn' ? 'ಅಕ್ಷಾಂಶ / ರೇಖಾಂಶ' : 'Coordinates'}: {caseData.location.lat}, {caseData.location.lng}
                  </span>
                )}
              </div>
            </div>

            {/* Full Narrative Text */}
            <div className="modal-section">
              <span className="modal-section-title" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <FileText size={14} />
                <span>{language === 'kn' ? 'ಸಂಪೂರ್ಣ ವಿವರಣೆ' : 'Full Case Narrative'}</span>
              </span>
              <p className="modal-section-content" style={{ background: 'rgba(0,0,0,0.1)', padding: '12px', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.03)' }}>
                {caseData.narrative || (language === 'kn' ? 'ಯಾವುದೇ ವಿವರಣೆ ಲಭ್ಯವಿಲ್ಲ.' : 'No detailed narrative text available.')}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
