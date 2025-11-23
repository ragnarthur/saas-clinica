// src/pages/ConsentPage.tsx
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiRequest } from "../api/client";
import "../styles/dashboard.css";
import { APP_NAME } from "../config/appConfig";

type LegalDocDTO = {
  id: number;
  doc_type: "TERMS" | "PRIVACY" | "CONSENT" | string;
  version: string;
  content: string;
};

const docTypeLabel: Record<string, string> = {
  TERMS: "Termos de Uso",
  PRIVACY: "Política de Privacidade",
  CONSENT: "Termo de Consentimento Médico",
};

const ConsentPage: React.FC = () => {
  const navigate = useNavigate();

  const [docs, setDocs] = useState<LegalDocDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // título da aba (opcional, mas deixa mais redondo)
  useEffect(() => {
    document.title = `Consentimentos · ${APP_NAME}`;
  }, []);

  useEffect(() => {
    let isActive = true;

    async function loadDocs() {
      try {
        setLoading(true);
        setError(null);

        const data = await apiRequest<LegalDocDTO[]>("/consent/active-docs/", {
          method: "GET",
        });

        if (!isActive) return;
        setDocs(data);
      } catch (err: unknown) {
        console.error("[CONSENT LOAD ERROR]", err);
        if (!isActive) return;

        if (err instanceof Error) {
          setError(
            err.message ||
              "Não foi possível carregar os documentos de consentimento."
          );
        } else {
          setError("Não foi possível carregar os documentos de consentimento.");
        }
      } finally {
        if (isActive) setLoading(false);
      }
    }

    loadDocs();
    return () => {
      isActive = false;
    };
  }, []);

  async function handleAccept() {
    try {
      setSaving(true);
      setError(null);
      setSuccess(null);

      await apiRequest("/consent/accept/", { method: "POST" });

      setSuccess("Consentimentos registrados com sucesso.");
      // manda o usuário de volta pro painel
      setTimeout(() => {
        navigate("/", { replace: true });
      }, 600);
    } catch (err: unknown) {
      console.error("[CONSENT ACCEPT ERROR]", err);
      if (err instanceof Error) {
        setError(
          err.message || "Não foi possível registrar os consentimentos."
        );
      } else {
        setError("Não foi possível registrar os consentimentos.");
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="dashboard-layout">
      <div className="dashboard-shell">
        <header className="dashboard-header">
          <div className="dashboard-title-block">
            <h1 className="dashboard-title">Atualização de consentimento</h1>
            <p className="dashboard-subtitle">
              Para continuar usando o sistema, é necessário revisar e aceitar
              os documentos abaixo.
            </p>
          </div>
        </header>

        <section className="appointments-section">
          <div className="appointments-header">
            <h2 className="appointments-title">Documentos legais ativos</h2>
            <p className="appointments-caption">
              Estes textos são definidos pela clínica e pela equipe do{" "}
              {APP_NAME}, seguindo as exigências da LGPD.
            </p>
          </div>

          {loading && (
            <div className="appointments-empty">Carregando documentos...</div>
          )}

          {!loading && error && (
            <div className="appointments-empty">{error}</div>
          )}

          {!loading && !error && docs.length === 0 && (
            <div className="appointments-empty">
              Nenhum documento ativo encontrado.
            </div>
          )}

          {!loading && !error && docs.length > 0 && (
            <>
              <div className="appointments-list">
                {docs.map((doc) => (
                  <article key={doc.id} className="appointment-row">
                    <div className="appointment-cell">
                      <span className="appointment-label">Tipo</span>
                      <span className="appointment-value">
                        {docTypeLabel[doc.doc_type] ?? doc.doc_type}
                      </span>
                      <span
                        className="appointment-label"
                        style={{ marginTop: "0.3rem" }}
                      >
                        Versão
                      </span>
                      <span className="appointment-value">{doc.version}</span>
                    </div>

                    <div className="appointment-cell">
                      <span className="appointment-label">Conteúdo</span>
                      <div
                        className="appointment-value"
                        style={{
                          marginTop: "0.5rem",
                          maxHeight: "260px",
                          overflow: "auto",
                          paddingRight: "0.5rem",
                        }}
                        // Conteúdo vem em HTML/Markdown já convertido
                        dangerouslySetInnerHTML={{ __html: doc.content }}
                      />
                    </div>
                  </article>
                ))}
              </div>

              <div
                className="appointment-actions"
                style={{ marginTop: "1.5rem" }}
              >
                {success && (
                  <div className="appointments-empty">{success}</div>
                )}
                {error && !loading && (
                  <div className="appointments-empty">{error}</div>
                )}

                <button
                  type="button"
                  className="appointment-action-button confirm"
                  disabled={saving}
                  onClick={handleAccept}
                >
                  {saving ? "Salvando..." : "Aceitar e continuar"}
                </button>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
};

export default ConsentPage;
