import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { ShieldAlert, LogIn, Lock, User, AlertCircle } from 'lucide-react';

export default function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError('Please enter both username and password.');
      return;
    }

    setError('');
    setLoading(true);

    const res = await login(username, password);
    setLoading(false);

    if (!res.success) {
      setError(res.error || 'Invalid username or password');
    }
  };

  const handleQuickFill = (demoUser, demoPass) => {
    setUsername(demoUser);
    setPassword(demoPass);
    setError('');
  };

  return (
    <div className="login-screen-overlay">
      <div className="glass-panel login-card">
        {/* Header Branding */}
        <div className="login-header">
          <div className="login-logo-badge">
            <ShieldAlert size={36} className="login-logo" />
          </div>
          <h1 className="login-title">KARNATAKA CRIME GPT</h1>
          <p className="login-subtitle">Role-Based Intelligence Dashboard</p>
        </div>

        {/* Inline Error Message */}
        {error && (
          <div className="login-error-banner">
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        )}

        {/* Credentials Form */}
        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label htmlFor="username">Username</label>
            <div className="input-with-icon">
              <User size={18} className="input-icon" />
              <input
                id="username"
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter your username"
                autoComplete="username"
                required
              />
            </div>
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <div className="input-with-icon">
              <Lock size={18} className="input-icon" />
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your password"
                autoComplete="current-password"
                required
              />
            </div>
          </div>

          <button type="submit" className="login-submit-btn" disabled={loading}>
            {loading ? (
              <span className="btn-spinner">Authenticating...</span>
            ) : (
              <>
                <LogIn size={18} />
                <span>Sign In</span>
              </>
            )}
          </button>
        </form>

        {/* Demo Accounts Quick Fill Options */}
        <div className="demo-accounts-section">
          <p className="demo-accounts-label">Demo Quick Access Accounts:</p>
          <div className="demo-buttons-grid">
            <button
              type="button"
              className="demo-chip chip-investigator"
              onClick={() => handleQuickFill('investigator1', 'investigator_pass123')}
            >
              Investigator
            </button>
            <button
              type="button"
              className="demo-chip chip-analyst"
              onClick={() => handleQuickFill('analyst1', 'analyst_pass123')}
            >
              Analyst
            </button>
            <button
              type="button"
              className="demo-chip chip-supervisor"
              onClick={() => handleQuickFill('supervisor1', 'supervisor_pass123')}
            >
              Supervisor
            </button>
            <button
              type="button"
              className="demo-chip chip-policymaker"
              onClick={() => handleQuickFill('policymaker1', 'policymaker_pass123')}
            >
              Policymaker
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
