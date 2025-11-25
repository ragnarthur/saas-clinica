// src/pages/VerifyEmailPage.tsx
import React, { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { apiRequest } from "../api/client";
import { APP_NAME } from "../config/appConfig";

type Status = "idle" | "loading" | "success" | "error";

const VerifyEmailPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  // token vindo da query string ?token=...
  const token = searchParams.get("token");

  const [code, setCode] = useState("");
  const [status, setStatus] = useState<Status>(token ? "idle" : "error");
  const [message, setMessage] = useState<string>(
    token
      ? "Digite o código de 6 dígitos que enviamos para o seu e-mail."
      : "Link de verificação inválido. O token não foi encontrado na URL."
  );

  useEffect(() => {
    document.title = `Confirmação de e-mail · ${APP_NAME}`;
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();

    if (!token) {
      setStatus("error");
      setMessage("Token de verificação não encontrado. Use o link correto do e-mail.");
      return;
    }

    const trimmedCode = code.trim();

    if (!trimmedCode || trimmedCode.length !== 6) {
      setStatus("error");
      setMessage("Informe o código de 6 dígitos exatamente como recebido no e-mail.");
      return;
    }

    try {
      setStatus("loading");
      setMessage("Confirmando seu e-mail. Aguarde...");

      const data = await apiRequest<{ detail?: string }>("/auth/verify-email/", {
        method: "POST",
        body: { token, code: trimmedCode },
      });

      setStatus("success");
      setMessage(
        data.detail ||
          "E-mail verificado com sucesso! Agora você já pode fazer login na plataforma."
      );
    } catch (err: unknown) {
      console.error("[VERIFY EMAIL ERROR]", err);

      let errorMessage =
        "Não foi possível verificar o e-mail. Confira o código e tente novamente.";

      if (err instanceof Error && err.message) {
        errorMessage = err.message;
      }

      setStatus("error");
      setMessage(errorMessage);
    }
  }

  const alertClass =
    status === "success"
      ? "alert alert-success"
      : status === "error"
      ? "alert alert-error"
      : "alert";

  const isDisabled = status === "loading" || !token;

  return (
    <div className="auth-layout">
      <div className="auth-card">
        <header className="auth-header">
          <h1 className="auth-title">Confirmação de e-mail</h1>
          <p className="auth-subtitle">
            Para ativar seu acesso, informe o código de 6 dígitos enviado para o seu
            e-mail.
          </p>
        </header>

        <div className={alertClass}>{message}</div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="form-label" htmlFor="code">
            Código de verificação
          </label>
          <input
            id="code"
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={6}
            className="form-input otp-input"
            placeholder="000000"
            value={code}
            disabled={isDisabled}
            onChange={(e) => {
              // mantém apenas dígitos
              const value = e.target.value.replace(/\D/g, "");
              setCode(value);
            }}
          />

          <button
            type="submit"
            className="primary-button auth-submit"
            disabled={isDisabled}
          >
            {status === "loading" ? "Confirmando..." : "Confirmar e-mail"}
          </button>
        </form>

        <footer className="auth-footer">
          <button
            type="button"
            className="ghost-button"
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
