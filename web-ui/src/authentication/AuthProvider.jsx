import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getProfile, refreshTokens, logout as apiLogout } from "../services/authService";
import * as tokenStorage from "../utils/tokenStorage";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [authenticated, setAuthenticated] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    let mounted = true;

    async function init() {
      const tokens = tokenStorage.getTokens();
      if (!tokens?.access_token) {
        setLoading(false);
        return;
      }
      try {
        const res = await getProfile(tokens.access_token);
        if (mounted) {
          setProfile(res.profile);
          setAuthenticated(true);
        }
      } catch (err) {
        // try refresh
        try {
          const refreshed = await refreshTokens(tokens.refresh_token);
          tokenStorage.saveTokens(refreshed);
          const res2 = await getProfile(refreshed.access_token);
          if (mounted) {
            setProfile(res2.profile);
            setAuthenticated(true);
          }
        } catch (err2) {
          tokenStorage.clearTokens();
          setAuthenticated(false);
        }
      } finally {
        if (mounted) setLoading(false);
      }
    }

    init();
    return () => (mounted = false);
  }, [navigate]);

  const value = useMemo(
    () => ({ profile, setProfile, authenticated, setAuthenticated, loading }),
    [profile, authenticated, loading]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
