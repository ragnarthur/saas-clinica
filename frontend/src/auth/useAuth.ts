// src/auth/useAuth.ts
import { useContext } from "react";
import { AuthContext, type AuthContextType } from "./AuthProvider";

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth deve ser usado dentro de um AuthProvider");
  }
  return ctx;
}
