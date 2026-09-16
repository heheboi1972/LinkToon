"use client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import { api, ApiError, post, setTokenGetter } from "@/lib/api";
import type { Profile, PublicConfig, Session } from "@/lib/types";

interface AuthValue {
  user: Profile | null;
  loading: boolean;
  error: Error | null;
  config: PublicConfig | null;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, name: string) => Promise<boolean>;
  signOut: () => Promise<void>;
}
const AuthContext = createContext<AuthValue | null>(null);
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("Auth provider missing");
  return context;
}

function AuthProvider({
  children,
  queryClient,
}: {
  children: React.ReactNode;
  queryClient: QueryClient;
}) {
  const [user, setUser] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [config, setConfig] = useState<PublicConfig | null>(null);
  const [supabase, setSupabase] = useState<SupabaseClient | null>(null);
  const acceptLocal = useCallback(
    (session: Session) => {
      localStorage.setItem("linktoon-session", session.access_token);
      setTokenGetter(async () => localStorage.getItem("linktoon-session"));
      queryClient.clear();
      setUser(session.user);
    },
    [queryClient],
  );

  useEffect(() => {
    let alive = true;
    let unsubscribe: (() => void) | undefined;
    async function boot() {
      try {
        const configuration = await api<PublicConfig>("/config");
        if (!alive) return;
        setConfig(configuration);
        if (configuration.auth_mode === "supabase") {
          const client = createClient(
            configuration.supabase_url,
            configuration.supabase_anon_key,
          );
          setSupabase(client);
          setTokenGetter(
            async () =>
              (await client.auth.getSession()).data.session?.access_token ||
              null,
          );
          const { data: listener } = client.auth.onAuthStateChange((event) => {
            if (event === "SIGNED_OUT") {
              setUser(null);
              queryClient.clear();
            }
            if (event === "SIGNED_IN") {
              setTimeout(() => {
                void api<Profile>("/auth/me")
                  .then((profile) => {
                    if (alive) setUser(profile);
                  })
                  .catch(() => undefined);
              }, 0);
            }
          });
          unsubscribe = () => listener.subscription.unsubscribe();
          if (!(await client.auth.getSession()).data.session) return;
        } else {
          setTokenGetter(async () => localStorage.getItem("linktoon-session"));
          if (!localStorage.getItem("linktoon-session")) return;
        }
        const profile = await api<Profile>("/auth/me").catch((err: Error) => {
          if (err instanceof ApiError && err.status === 401) {
            localStorage.removeItem("linktoon-session");
            return null;
          }
          throw err;
        });
        if (alive) setUser(profile);
      } catch (err) {
        if (alive) setError(err as Error);
      } finally {
        if (alive) setLoading(false);
      }
    }
    void boot();
    return () => {
      alive = false;
      unsubscribe?.();
    };
  }, [queryClient]);

  async function signIn(email: string, password: string) {
    if (supabase) {
      const { error } = await supabase.auth.signInWithPassword({
        email,
        password,
      });
      if (error) throw error;
      queryClient.clear();
      setUser(await api<Profile>("/auth/me"));
    } else acceptLocal(await post<Session>("/auth/login", { email, password }));
  }
  async function signUp(email: string, password: string, name: string) {
    if (supabase) {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: { display_name: name },
          emailRedirectTo: `${location.origin}/login`,
        },
      });
      if (error) throw error;
      if (!data.session) return false;
      queryClient.clear();
      setUser(await api<Profile>("/auth/me"));
    } else
      acceptLocal(
        await post<Session>("/auth/signup", {
          email,
          password,
          display_name: name,
        }),
      );
    return true;
  }
  async function signOut() {
    if (supabase) {
      const { error } = await supabase.auth.signOut();
      if (error) throw error;
    }
    localStorage.removeItem("linktoon-session");
    queryClient.clear();
    setUser(null);
  }
  return (
    <AuthContext.Provider
      value={{ user, loading, error, config, signIn, signUp, signOut }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: (count, error) =>
              !(
                error instanceof ApiError &&
                [401, 403, 404].includes(error.status)
              ) && count < 1,
          },
        },
      }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider queryClient={queryClient}>{children}</AuthProvider>
    </QueryClientProvider>
  );
}
