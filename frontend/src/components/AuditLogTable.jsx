import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { ShieldCheck, RefreshCw, ChevronLeft, ChevronRight } from 'lucide-react';

export default function AuditLogTable() {
  const { apiFetch } = useAuth();
  const [logs, setLogs] = useState([]);
  const [total, setTotal] = useState(0);
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchAuditLogs = async (currentOffset = offset) => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiFetch(`/api/audit-logs?limit=${limit}&offset=${currentOffset}`);
      if (!res.ok) {
        throw new Error(`Failed to fetch audit logs: ${res.status}`);
      }
      const data = await res.json();
      setLogs(data.results || []);
      setTotal(data.total || 0);
    } catch (err) {
      console.error(err);
      setError('Could not load audit logs. Ensure you have Supervisor permissions.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAuditLogs(offset);
  }, [offset]);

  const handlePrevPage = () => {
    if (offset >= limit) {
      setOffset(offset - limit);
    }
  };

  const handleNextPage = () => {
    if (offset + limit < total) {
      setOffset(offset + limit);
    }
  };

  return (
    <div className="audit-log-container glass-panel">
      <div className="audit-log-header">
        <div className="audit-title-group">
          <ShieldCheck size={22} className="audit-icon" />
          <h2>System Audit Logs</h2>
          <span className="audit-count-badge">{total} records</span>
        </div>
        <button 
          className="refresh-btn" 
          onClick={() => fetchAuditLogs(offset)}
          disabled={loading}
        >
          <RefreshCw size={16} className={loading ? 'spin' : ''} />
          <span>Refresh</span>
        </button>
      </div>

      {error ? (
        <div className="audit-error">{error}</div>
      ) : loading ? (
        <div className="audit-loading">Loading audit logs...</div>
      ) : (
        <>
          <div className="audit-table-wrapper">
            <table className="audit-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>User</th>
                  <th>Role</th>
                  <th>Method</th>
                  <th>Endpoint</th>
                  <th>Status</th>
                  <th>Query Content</th>
                  <th>Returned Entities</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {logs.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="no-data">No audit logs recorded yet.</td>
                  </tr>
                ) : (
                  logs.map((log) => (
                    <tr key={log.id}>
                      <td className="log-id">#{log.id}</td>
                      <td className="log-user">{log.username || 'Anonymous'}</td>
                      <td className="log-role">
                        <span className={`role-badge role-${log.role || 'unauth'}`}>
                          {log.role || 'none'}
                        </span>
                      </td>
                      <td className="log-method">
                        <span className={`method-badge method-${log.method}`}>
                          {log.method}
                        </span>
                      </td>
                      <td className="log-endpoint" title={log.endpoint}>{log.endpoint}</td>
                      <td>
                        <span className={`status-badge status-${log.status_code < 300 ? 'ok' : log.status_code < 500 ? 'warn' : 'err'}`}>
                          {log.status_code}
                        </span>
                      </td>
                      <td className="log-query" title={log.query_text || ''}>
                        {log.query_text ? (log.query_text.length > 30 ? log.query_text.slice(0, 30) + '...' : log.query_text) : '-'}
                      </td>
                      <td className="log-records">
                        {log.returned_records ? (
                          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            {log.returned_records.firs ? `${log.returned_records.firs.length} FIRs` : JSON.stringify(log.returned_records).slice(0, 25)}
                          </span>
                        ) : '-'}
                      </td>
                      <td className="log-time">
                        {log.created_at ? new Date(log.created_at).toLocaleString() : '-'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          <div className="audit-pagination">
            <span>
              Showing {logs.length > 0 ? offset + 1 : 0} - {Math.min(offset + limit, total)} of {total}
            </span>
            <div className="pagination-buttons">
              <button 
                onClick={handlePrevPage} 
                disabled={offset === 0 || loading}
                className="page-btn"
              >
                <ChevronLeft size={16} /> Prev
              </button>
              <button 
                onClick={handleNextPage} 
                disabled={offset + limit >= total || loading}
                className="page-btn"
              >
                Next <ChevronRight size={16} />
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
