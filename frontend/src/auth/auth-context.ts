// src/auth/auth-context.ts
import { createContext } from "react";

export type AuthContextType = {
  token: string | null;
  login: (token: string) => void;
  logout: () => void;
  isAuthenticated: boolean;
};

// chave usada no localStorage
export const STORAGE_KEY = "saas_medico_access_token";

// Contexto em si (sem JSX, por isso este arquivo é .ts)
export const AuthContext = createContext<AuthContextType | undefined>(
  undefined
);
