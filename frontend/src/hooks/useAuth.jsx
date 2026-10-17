import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, onUnauthorized, setCsrfToken } from "../services/api.js";

const AuthContext = createContext(null);

// status: "loading" | "anonymous" | "mfa" | "authenticated"
export function AuthProvider({ children }) {
  const [state, setState] = useState({ status: "loading", user: null, notice: null });

  const applySession = useCallback((session, notice = null) => {
    setCsrfToken(session.csrf_token);
    if (session.authenticated) setState({ status: "authenticated", user: session.user, notice });
    else if (session.mfa_pending) setState({ status: "mfa", user: null, notice });
    else setState({ status: "anonymous", user: null, notice });
  }, []);

  const refresh = useCallback(async () => {
    try {
      applySession(await api("/auth/session"));
    } catch {
      setState({ status: "anonymous", user: null, notice: "Unable to contact the server." });
    }
  }, [applySession]);

  useEffect(() => {
    refresh();
    onUnauthorized(() => {
      setCsrfToken(null);
      setState({ status: "anonymous", user: null, notice: "Your session has ended. Please sign in again." });
    });
  }, [refresh]);

  const login = useCallback(
    async (username, password) => {
      const result = await api("/auth/login", { method: "POST", body: { username, password } });
      if (result.mfa_required) {
        setCsrfToken(result.csrf_token);
        setState({ status: "mfa", user: null, notice: null });
      } else {
        applySession(result);
      }
      return result;
    },
    [applySession],
  );

  const verifyMfa = useCallback(
    async (payload) => applySession(await api("/auth/mfa/verify", { method: "POST", body: payload })),
    [applySession],
  );

  const logout = useCallback(async () => {
    try {
      await api("/auth/logout", { method: "POST" });
    } finally {
      setCsrfToken(null);
      setState({ status: "anonymous", user: null, notice: "You have signed out." });
    }
  }, []);

  const value = useMemo(
    () => ({ ...state, login, verifyMfa, logout, refresh }),
    [state, login, verifyMfa, logout, refresh],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
