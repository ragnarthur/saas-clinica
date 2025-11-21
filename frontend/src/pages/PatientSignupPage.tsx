// src/pages/PatientSignupPage.tsx
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiRequest } from "../api/client";
import { useAuth } from "../auth/useAuth";

type Clinic = {
  id: string;
  name: string;
  schema_name: string;
};

type LegalDoc = {
  id: string;
  doc_type: "TERMS" | "PRIVACY" | "CONSENT" | string;
  version: string;
  content: string;
};

type LegalDocsByType = {
  TERMS?: LegalDoc;
  PRIVACY?: LegalDoc;
  CONSENT?: LegalDoc;
};

type PatientRegisterPayload = {
  clinic_schema_name: string;
  full_name: string;
  cpf: string;
  phone: string;
  email: string;
  password: string;
  password_confirm: string;
  agree_terms: boolean;
  agree_privacy: boolean;
  agree_consent: boolean;
};

type PatientRegisterResponse = {
  access?: string;
  refresh?: string;
  message?: string;
};

const PatientSignupPage: React.FC = () => {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [clinics, setClinics] = useState<Clinic[]>([]);
  const [legalDocs, setLegalDocs] = useState<LegalDocsByType>({});
  const [loadingInitial, setLoadingInitial] = useState(true);

  const [form, setForm] = useState<PatientRegisterPayload>({
    clinic_schema_name: "",
    full_name: "",
    cpf: "",
    phone: "",
    email: "",
    password: "",
    password_confirm: "",
    agree_terms: false,
    agree_privacy: false,
    agree_consent: false,
  });

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [docToShow, setDocToShow] = useState<LegalDoc | null>(null);

  // ---------- carregamento inicial (clínicas + documentos legais) ----------

  useEffect(() => {
    async function loadInitial() {
      try {
        setLoadingInitial(true);
        setError(null);

        const [clinicsData, legalData] = await Promise.all([
          apiRequest<Clinic[]>("/clinics/active/"),
          apiRequest<LegalDoc[]>("/legal-documents/active/"),
        ]);

        setClinics(clinicsData);

        const docsByType: LegalDocsByType = {};
        for (const doc of legalData) {
          if (doc.doc_type === "TERMS") docsByType.TERMS = doc;
          if (doc.doc_type === "PRIVACY") docsByType.PRIVACY = doc;
          if (doc.doc_type === "CONSENT") docsByType.CONSENT = doc;
        }
        setLegalDocs(docsByType);

        // se tiver só uma clínica, já pré-seleciona
        if (clinicsData.length === 1) {
          setForm((prev) => ({
            ...prev,
            clinic_schema_name: clinicsData[0].schema_name,
          }));
        }
      } catch (err: unknown) {
        console.error("[SIGNUP] erro ao carregar dados iniciais:", err);
        if (err instanceof Error) {
          setError(err.message || "Erro ao carregar dados iniciais.");
        } else {
          setError("Erro ao carregar dados iniciais.");
        }
      } finally {
        setLoadingInitial(false);
      }
    }

    loadInitial();
  }, []);

  // ---------- handlers ----------

  function handleInputChange(
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) {
    const { name, value } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: value,
    }));
  }

  function handleCheckboxChange(e: React.ChangeEvent<HTMLInputElement>) {
    const { name, checked } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: checked,
    }));
  }

  function openDoc(type: "TERMS" | "PRIVACY" | "CONSENT") {
    const doc = legalDocs[type];
    if (doc) {
      setDocToShow(doc);
    }
  }

  function validateForm(): string | null {
    if (!form.clinic_schema_name) {
      return "Selecione a clínica em que deseja se cadastrar.";
    }
    if (!form.full_name.trim()) {
      return "Informe seu nome completo.";
    }
    if (!form.cpf.trim()) {
      return "Informe seu CPF.";
    }
    if (!form.phone.trim()) {
      return "Informe seu telefone.";
    }
    if (!form.email.trim()) {
      return "Informe seu e-mail.";
    }
    if (!form.password) {
      return "Defina uma senha.";
    }
    if (form.password.length < 6) {
      return "A senha deve ter pelo menos 6 caracteres.";
    }
    if (form.password !== form.password_confirm) {
      return "A confirmação de senha não confere.";
    }
    if (!form.agree_terms || !form.agree_privacy || !form.agree_consent) {
      return "Você precisa concordar com os Termos de Uso, Política de Privacidade e Termo de Consentimento para continuar.";
    }
    return null;
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSuccessMsg(null);

    const validationError = validateForm();
    if (validationError) {
      setError(validationError);
      return;
    }

    try {
      setSubmitting(true);

      const payload: PatientRegisterPayload = {
        clinic_schema_name: form.clinic_schema_name,
        full_name: form.full_name.trim(),
        cpf: form.cpf.trim(),
        phone: form.phone.trim(),
        email: form.email.trim(),
        password: form.password,
        password_confirm: form.password_confirm,
        agree_terms: form.agree_terms,
        agree_privacy: form.agree_privacy,
        agree_consent: form.agree_consent,
      };

      const data = await apiRequest<PatientRegisterResponse>(
        "/patients/register/",
        {
          method: "POST",
          body: payload,
        }
      );

      // se a API devolver token, já loga o paciente
      if (data.access) {
        login(data.access);
      }

      setSuccessMsg(
        data.message ||
          "Cadastro realizado com sucesso! Você já pode acessar o painel da clínica."
      );

      // redireciona depois de alguns segundos
      setTimeout(() => {
        navigate("/"); // ajusta se tiver rota específica de paciente
      }, 2000);
    } catch (err: unknown) {
      console.error("[SIGNUP] erro no cadastro:", err);
      if (err instanceof Error) {
        setError(err.message || "Não foi possível concluir o cadastro.");
      } else {
        setError("Não foi possível concluir o cadastro.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  // ---------- render ----------

  if (loadingInitial) {
    return (
      <div className="auth-layout">
        <div className="auth-card">
          <h1 className="auth-title">Criar conta na clínica</h1>
          <p>Carregando informações da clínica...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-layout patient-signup-page">
      <div className="auth-card patient-signup-card">
        <header className="auth-header">
          <h1 className="auth-title">Cadastro de paciente</h1>
          <p className="auth-subtitle">
            Crie sua conta na clínica e gerencie seus agendamentos em um só
            lugar.
          </p>
        </header>

        {error && <div className="alert alert-error">{error}</div>}
        {successMsg && <div className="alert alert-success">{successMsg}</div>}

        <form onSubmit={handleSubmit} className="auth-form">
          {/* Seção 1: Clínica */}
          <section className="form-section">
            <h2 className="form-section-title">1. Clínica</h2>
            <p className="form-section-subtitle">
              Escolha em qual clínica você quer se cadastrar.
            </p>

            <div className="form-row">
              <label htmlFor="clinic_schema_name" className="form-label">
                Clínica
              </label>
              <select
                id="clinic_schema_name"
                name="clinic_schema_name"
                value={form.clinic_schema_name}
                onChange={handleInputChange}
                className="form-input"
              >
                <option value="">Selecione...</option>
                {clinics.map((clinic) => (
                  <option
                    key={clinic.id}
                    value={clinic.schema_name}
                  >{clinic.name}</option>
                ))}
              </select>
            </div>
          </section>

          {/* Seção 2: Dados pessoais */}
          <section className="form-section">
            <h2 className="form-section-title">2. Dados pessoais</h2>

            <div className="form-row">
              <label htmlFor="full_name" className="form-label">
                Nome completo
              </label>
              <input
                id="full_name"
                name="full_name"
                type="text"
                className="form-input"
                value={form.full_name}
                onChange={handleInputChange}
                autoComplete="name"
              />
            </div>

            <div className="form-grid">
              <div className="form-row">
                <label htmlFor="cpf" className="form-label">
                  CPF
                </label>
                <input
                  id="cpf"
                  name="cpf"
                  type="text"
                  className="form-input"
                  value={form.cpf}
                  onChange={handleInputChange}
                  autoComplete="off"
                />
              </div>

              <div className="form-row">
                <label htmlFor="phone" className="form-label">
                  Telefone
                </label>
                <input
                  id="phone"
                  name="phone"
                  type="tel"
                  className="form-input"
                  value={form.phone}
                  onChange={handleInputChange}
                  autoComplete="tel"
                />
              </div>
            </div>

            <div className="form-row">
              <label htmlFor="email" className="form-label">
                E-mail
              </label>
              <input
                id="email"
                name="email"
                type="email"
                className="form-input"
                value={form.email}
                onChange={handleInputChange}
                autoComplete="email"
              />
            </div>

            <div className="form-grid">
              <div className="form-row">
                <label htmlFor="password" className="form-label">
                  Senha
                </label>
                <input
                  id="password"
                  name="password"
                  type="password"
                  className="form-input"
                  value={form.password}
                  onChange={handleInputChange}
                  autoComplete="new-password"
                />
              </div>

              <div className="form-row">
                <label htmlFor="password_confirm" className="form-label">
                  Confirmar senha
                </label>
                <input
                  id="password_confirm"
                  name="password_confirm"
                  type="password"
                  className="form-input"
                  value={form.password_confirm}
                  onChange={handleInputChange}
                  autoComplete="new-password"
                />
              </div>
            </div>
          </section>

          {/* Seção 3: LGPD */}
          <section className="form-section">
            <h2 className="form-section-title">3. LGPD e consentimento</h2>
            <p className="form-section-subtitle">
              Leia e concorde com os documentos abaixo para continuar utilizando
              a plataforma.
            </p>

            <div className="legal-doc-links">
              {legalDocs.TERMS && (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => openDoc("TERMS")}
                >
                  Ver Termos de Uso (v{legalDocs.TERMS.version})
                </button>
              )}
              {legalDocs.PRIVACY && (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => openDoc("PRIVACY")}
                >
                  Ver Política de Privacidade (v{legalDocs.PRIVACY.version})
                </button>
              )}
              {legalDocs.CONSENT && (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => openDoc("CONSENT")}
                >
                  Ver Termo de Consentimento (v{legalDocs.CONSENT.version})
                </button>
              )}
            </div>

            <div className="legal-checkbox-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  name="agree_terms"
                  checked={form.agree_terms}
                  onChange={handleCheckboxChange}
                />
                <span>
                  Li e concordo com os <strong>Termos de Uso</strong>.
                </span>
              </label>

              <label className="checkbox-label">
                <input
                  type="checkbox"
                  name="agree_privacy"
                  checked={form.agree_privacy}
                  onChange={handleCheckboxChange}
                />
                <span>
                  Li e concordo com a <strong>Política de Privacidade</strong>.
                </span>
              </label>

              <label className="checkbox-label">
                <input
                  type="checkbox"
                  name="agree_consent"
                  checked={form.agree_consent}
                  onChange={handleCheckboxChange}
                />
                <span>
                  Li e concordo com o{" "}
                  <strong>
                    Termo de Consentimento para Tratamento de Dados Pessoais e
                    de Saúde
                  </strong>
                  .
                </span>
              </label>
            </div>
          </section>

          <footer className="auth-footer">
            <button
              type="submit"
              className="primary-button"
              disabled={submitting}
            >
              {submitting ? "Criando conta..." : "Criar conta"}
            </button>

            <button
              type="button"
              className="ghost-button"
              onClick={() => navigate("/login")}
            >
              Já tenho conta
            </button>
          </footer>
        </form>
      </div>

      {/* Modal simples para mostrar os textos de LGPD */}
      {docToShow && (
        <div
          className="legal-modal-backdrop"
          onClick={() => setDocToShow(null)}
        >
          <div
            className="legal-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <header className="legal-modal-header">
              <h2>
                {docToShow.doc_type === "TERMS" && "Termos de Uso"}
                {docToShow.doc_type === "PRIVACY" && "Política de Privacidade"}
                {docToShow.doc_type === "CONSENT" &&
                  "Termo de Consentimento de Dados"}
              </h2>
              <span className="legal-modal-version">
                Versão {docToShow.version}
              </span>
            </header>
            <div className="legal-modal-content">
              <div style={{ whiteSpace: "pre-wrap" }}>
                {docToShow.content}
              </div>
            </div>
            <footer className="legal-modal-footer">
              <button
                type="button"
                className="primary-button"
                onClick={() => setDocToShow(null)}
              >
                Fechar
              </button>
            </footer>
          </div>
        </div>
      )}
    </div>
  );
};

export default PatientSignupPage;
