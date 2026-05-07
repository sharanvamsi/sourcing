'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { api } from '@/lib/api';
import { useRouter } from 'next/navigation';

interface User {
  email: string;
  name: string;
  team_name: string;
  role: string;
  is_admin: boolean;
  membership?: string;
  blacklist_exempt?: boolean;
}

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  creditsUsed: number;
  teamCredits: number;
  basketCount: number;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [creditsUsed, setCreditsUsed] = useState(0);
  const [teamCredits, setTeamCredits] = useState(0);
  const [basketCount, setBasketCount] = useState(0);
  const router = useRouter();

  const refreshUser = async () => {
    try {
      const data = await api.getMe();
      setUser(data.user);
      setCreditsUsed(data.credits_used);
      setTeamCredits(data.team_credits);
      setBasketCount(data.basket_count);
    } catch {
      setUser(null);
      api.logout();
    }
  };

  useEffect(() => {
    const token = api.getToken();
    if (token) {
      refreshUser().finally(() => setIsLoading(false));
    } else {
      setIsLoading(false);
    }
  }, []);

  const login = async (email: string, password: string) => {
    const data = await api.login(email, password);
    setUser(data.user);
    await refreshUser();
    router.push('/dashboard');
  };

  const logout = () => {
    api.logout();
    setUser(null);
    setCreditsUsed(0);
    setTeamCredits(0);
    setBasketCount(0);
    router.push('/login');
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        creditsUsed,
        teamCredits,
        basketCount,
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
