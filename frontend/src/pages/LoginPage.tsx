// src/pages/LoginPage.tsx
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiRequest } from "../api/client";
import { useAuth } from "../auth/useAuth";

type LoginResponse = {
  access: string;
  refresh?: string;
};

const LoginPage: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (!username || !password) {
      setError("Informe usuário/e-mail e senha.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const data = await apiRequest<LoginResponse>("/auth/login/", {
        method: "POST",
        body: { username, password },
        useAuth: false, // <- login sempre sem Authorization
      });

      // salva token no contexto + localStorage
      login(data.access);
      console.log("[LOGIN OK] token salvo.");

      navigate("/");
    } catch (err: unknown) {
      console.error("[LOGIN ERROR]", err);
      if (err instanceof Error) {
        setError(
          err.message ||
            "Não foi possível entrar. Verifique seus dados ou tente novamente."
        );
      } else {
        setError(
          "Não foi possível entrar. Verifique seus dados ou tente novamente."
        );
      }
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="auth-layout">
      <div className="auth-card">
        <header className="auth-header">
          <h1 className="auth-title">Login da Clínica</h1>
          <p className="auth-subtitle">
            Acesse o painel de agendamentos e gestão da sua clínica.
          </p>
        </header>

        {error && <div className="alert alert-error">{error}</div>}

        <form className="auth-form" onSubmit={handleSubmit}>
          <div className="form-row">
            <label htmlFor="username" className="form-label">
              Usuário ou e-mail
            </label>
            <input
              id="username"
              type="text"
              className="form-input"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
          </div>

          <div className="form-row">
            <label htmlFor="password" className="form-label">
              Senha
            </label>
            <input
              id="password"
              type="password"
              className="form-input"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>

          <button
            type="submit"
            className="primary-button"
            disabled={loading}
          >
            {loading ? "Entrando..." : "Entrar"}
          </button>
        </form>

        <footer className="auth-footer login-footer">
          <p className="auth-footer-text">
            Ainda não tem acesso?{" "}
            <button
              type="button"
              className="link-button"
              onClick={() => navigate("/cadastro-paciente")}
            >
              Faça seu cadastro
            </button>
          </p>
          <p className="auth-caption">
            SaaS Médico · Multi-clínica · LGPD Ready 🩺
          </p>
        </footer>
      </div>
    </div>
  );
};

export default LoginPage;
