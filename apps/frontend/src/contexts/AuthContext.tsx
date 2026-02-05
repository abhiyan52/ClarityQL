import { createContext, useContext, useState, useEffect, ReactNode } from "react";
import { User } from "@/types/auth";
import { login as apiLogin, register as apiRegister, getCurrentUser } from "@/api/auth";

interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const TOKEN_KEY = "clarityql_auth_token";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Load token from localStorage on mount
  useEffect(() => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    if (storedToken) {
      getCurrentUser(storedToken)
        .then((userData) => {
          setUser(userData);
          setToken(storedToken);
        })
        .catch(() => {
          // Token is invalid, clear it
          localStorage.removeItem(TOKEN_KEY);
        })
        .finally(() => {
          setIsLoading(false);
        });
    } else {
      setIsLoading(false);
    }
  }, []);

  const login = async (email: string, password: string) => {
    const response = await apiLogin({ email, password });
    const { access_token } = response;

    // Store token
    localStorage.setItem(TOKEN_KEY, access_token);
    setToken(access_token);

    // Fetch user info
    const userData = await getCurrentUser(access_token);
    setUser(userData);
  };

  const register = async (email: string, password: string) => {
    await apiRegister({ email, password });
    // Auto-login after registration
    await login(email, password);
  };

  const logout = () => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        isAuthenticated: !!user && !!token,
        login,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
