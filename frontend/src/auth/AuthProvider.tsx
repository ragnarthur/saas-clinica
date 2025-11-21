// src/auth/AuthProvider.tsx
import React, {
  createContext,
  useEffect,
  useState,
  type PropsWithChildren,
} from "react";

export type AuthContextType = {
  token: string | null;
  isAuthenticated: boolean;
  login: (token: string) => void;
  logout: () => void;
};

// Essa linha não é um componente, então o react-refresh reclama.
// Desabilitamos a regra só aqui porque é um contexto estático e seguro.
/* eslint-disable-next-line react-refresh/only-export-components */
export const AuthContext = createContext<AuthContextType | undefined>(
  undefined
);

export const AuthProvider: React.FC<PropsWithChildren> = ({ children }) => {
  // carrega token salvo (se houver)
  const [token, setToken] = useState<string | null>(() => {
    const stored = localStorage.getItem("access_token");
    if (stored) {
      console.log("[AUTH] access_token carregado do localStorage.");
      return stored;
    }

    // fallback para chaves antigas
    const legacy =
      localStorage.getItem("token") ||
      localStorage.getItem("authToken") ||
      localStorage.getItem("access");
    if (legacy) {
      console.log("[AUTH] token legado encontrado, migrando para access_token.");
      localStorage.setItem("access_token", legacy);
      return legacy;
    }

    return null;
  });

  useEffect(() => {
    if (token) {
      localStorage.setItem("access_token", token);
      console.log("[AUTH] access_token salvo no localStorage.");
    } else {
      localStorage.removeItem("access_token");
      console.log("[AUTH] access_token removido do localStorage.");
    }
  }, [token]);

  const login = (newToken: string) => {
    console.log("[AUTH] login() chamado, token recebido.");
    setToken(newToken);
  };

  const logout = () => {
    console.log("[AUTH] logout() chamado, limpando token.");
    setToken(null);
  };

  const isAuthenticated = !!token;

  return (
    <AuthContext.Provider value={{ token, isAuthenticated, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};
