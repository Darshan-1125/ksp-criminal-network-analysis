import React, { createContext, useContext, useState, useEffect } from 'react';

const AuthContext = createContext(null);

const API_BASE_URL =
  import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('access_token') || '');
  const [refreshToken, setRefreshToken] = useState(() => localStorage.getItem('refresh_token') || '');
  const [user, setUser] = useState(() => {
    const savedUser = localStorage.getItem('user_data');
    return savedUser ? JSON.parse(savedUser) : null;
  });
  const [isInitializing, setIsInitializing] = useState(true);

  // Validate token on app mount
  useEffect(() => {
    const validateToken = async () => {
      const storedToken = localStorage.getItem('access_token');
      const storedRefresh = localStorage.getItem('refresh_token');
      if (!storedToken && !storedRefresh) {
        setIsInitializing(false);
        return;
      }

      try {
        const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
          method: 'GET',
          headers: {
            'Authorization': `Bearer ${storedToken}`
          }
        });

        if (res.ok) {
          const userData = await res.json();
          setUser(userData);
          localStorage.setItem('user_data', JSON.stringify(userData));
        } else if (storedRefresh) {
          // Attempt refresh on initial mount if access token expired
          const newAccess = await handleRefreshToken(storedRefresh);
          if (!newAccess) {
            logout();
          }
        } else {
          logout();
        }
      } catch (err) {
        console.error('Auth check error:', err);
      } finally {
        setIsInitializing(false);
      }
    };

    validateToken();
  }, []);

  const handleRefreshToken = async (existingRefresh = null) => {
    const rfToken = existingRefresh || refreshToken || localStorage.getItem('refresh_token');
    if (!rfToken) return null;

    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: rfToken })
      });

      if (!res.ok) {
        logout();
        return null;
      }

      const data = await res.json();
      const { access_token, refresh_token: newRfToken } = data;

      setToken(access_token);
      localStorage.setItem('access_token', access_token);

      if (newRfToken) {
        setRefreshToken(newRfToken);
        localStorage.setItem('refresh_token', newRfToken);
      }

      // Fetch user profile if missing
      const meRes = await fetch(`${API_BASE_URL}/api/auth/me`, {
        headers: { 'Authorization': `Bearer ${access_token}` }
      });
      if (meRes.ok) {
        const meData = await meRes.json();
        setUser(meData);
        localStorage.setItem('user_data', JSON.stringify(meData));
      }

      return access_token;
    } catch (err) {
      console.error('Failed to refresh token:', err);
      logout();
      return null;
    }
  };

  const login = async (username, password) => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });

      const data = await res.json();
      if (!res.ok) {
        return { success: false, error: data.detail || 'Login failed' };
      }

      const { access_token, refresh_token: rfToken, role, full_name } = data;
      const userData = { username, role, full_name };

      setToken(access_token);
      setRefreshToken(rfToken);
      setUser(userData);

      localStorage.setItem('access_token', access_token);
      localStorage.setItem('refresh_token', rfToken);
      localStorage.setItem('user_data', JSON.stringify(userData));

      return { success: true };
    } catch (err) {
      return { success: false, error: 'Could not connect to authentication server.' };
    }
  };

  const logout = () => {
    setToken('');
    setRefreshToken('');
    setUser(null);
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user_data');
  };

  // Centralized fetch wrapper attaching Bearer token & handling global 401s with token refresh
  const apiFetch = async (endpoint, options = {}) => {
    let currentToken = token || localStorage.getItem('access_token');
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (currentToken) {
      headers['Authorization'] = `Bearer ${currentToken}`;
    }

    const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;

    try {
      let response = await fetch(url, { ...options, headers });

      if (response.status === 401) {
        console.warn('Received 401 Unauthorized - attempting token refresh');
        const newToken = await handleRefreshToken();

        if (newToken) {
          headers['Authorization'] = `Bearer ${newToken}`;
          response = await fetch(url, { ...options, headers });
        } else {
          logout();
        }
      }

      return response;
    } catch (err) {
      console.error('API request failed:', err);
      throw err;
    }
  };

  return (
    <AuthContext.Provider value={{
      user,
      token,
      refreshToken,
      isInitializing,
      isAuthenticated: !!token && !!user,
      login,
      logout,
      apiFetch
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
