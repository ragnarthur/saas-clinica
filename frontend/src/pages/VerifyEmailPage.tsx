// src/pages/VerifyEmailPage.tsx
import React, { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { apiRequest } from "../api/client";
import { APP_NAME } from "../config/appConfig";

const VerifyEmailPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  // token vindo da query string ?token=...
  const token = searchParams.get("token");

  // se não tiver token, já inicializa em erro
  const [status, setStatus] = useState<"loading" | "ok" | "error">(
    token ? "loading" : "error"
  );
  const [message, setMessage] = useState<string>(
    token
      ? "Confirmando seu cadastro. Aguarde..."
      : "Token de verificação não encontrado."
  );

  // título da aba
  useEffect(() => {
    document.title = `Confirmação de e-mail · ${APP_NAME}`;
  }, []);

  useEffect(() => {
    // sem token -> nada a fazer aqui, já está em erro pelo estado inicial
    if (!token) return;

    let isActive = true;

    async function verify() {
      try {
        const data = await apiRequest<{ detail?: string }>(
          "/auth/verify-email/",
          {
            method: "POST",
            body: { token },
          }
        );

        if (!isActive) return;

        setStatus("ok");
        setMessage(
          data.detail ||
            "E-mail verificado com sucesso! Agora você já pode fazer login."
        );
      } catch (err: unknown) {
        console.error("[VERIFY EMAIL ERROR]", err);

        if (!isActive) return;

        if (err instanceof Error) {
          setStatus("error");
          setMessage(
            err.message ||
              "Não foi possível verificar o e-mail. Tente novamente."
          );
        } else {
          setStatus("error");
          setMessage(
            "Não foi possível verificar o e-mail. Tente novamente."
          );
        }
      }
    }

    verify();

    // cleanup: evita setState depois do unmount
    return () => {
      isActive = false;
    };
  }, [token]);

  const alertClass =
    status === "ok"
      ? "alert alert-success"
      : status === "error"
      ? "alert alert-error"
      : "alert";

  return (
    <div className="auth-layout">
      <div className="auth-card">
        <header className="auth-header">
          <h1 className="auth-title">Confirmação de e-mail</h1>
        </header>

        <div className={alertClass}>{message}</div>

        <footer className="auth-footer">
          <button
            type="button"
            className="primary-button"
            onClick={() => navigate("/login")}
          >
            Ir para o login
          </button>
        </footer>
      </div>
    </div>
  );
};

export default VerifyEmailPage;
