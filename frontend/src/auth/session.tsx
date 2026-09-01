import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { api, jsonBody, type User } from "../api/client";

interface SessionContextValue {
  user: User | null;
  loading: boolean;
  refresh: () => Promise<void>;
  login: (identifier: string, password: string) => Promise<User>;
  register: (payload: Record<string, string>) => Promise<User>;
  logout: () => Promise<void>;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      setUser(await api<User>("/auth/me"));
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => void refresh(), [refresh]);

  const value = useMemo<SessionContextValue>(
    () => ({
      user,
      loading,
      refresh,
      login: async (identifier, password) => {
        const current = await api<User>("/auth/login", {
          method: "POST",
          body: jsonBody({ identifier, password }),
        });
        setUser(current);
        return current;
      },
      register: async (payload) =>
        api<User>("/auth/register", { method: "POST", body: jsonBody(payload) }),
      logout: async () => {
        await api<void>("/auth/logout", { method: "POST" });
        setUser(null);
      },
    }),
    [loading, refresh, user],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession must be used inside SessionProvider");
  return context;
}
