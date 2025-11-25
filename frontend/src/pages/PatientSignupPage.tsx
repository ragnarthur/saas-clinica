// src/pages/PatientSignupPage.tsx
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiRequest } from "../api/client";
import { APP_NAME } from "../config/appConfig";

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

type Sex = "M" | "F" | "N";

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
  sex?: Sex;
  birth_date?: string | null;
};

type PatientRegisterResponse = {
  user_id: string;
  patient_id: string;
  email: string;
  full_name: string;
  clinic_id: string;
  detail: string;
  access?: string;
  refresh?: string;
};

type DocTypeKey = "TERMS" | "PRIVACY" | "CONSENT";

type PasswordStrength = "empty" | "weak" | "medium" | "strong";

/* --------------------------------
   Máscaras (CPF, Telefone, Nasc.)
----------------------------------- */

function maskCPF(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 11);
  const part1 = digits.slice(0, 3);
  const part2 = digits.slice(3, 6);
  const part3 = digits.slice(6, 9);
  const part4 = digits.slice(9, 11);

  let result = "";
  if (part1) result = part1;
  if (part2) result += "." + part2;
  if (part3) result += "." + part3;
  if (part4) result += "-" + part4;
  return result;
}

function maskCellPhone(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 11);
  const ddd = digits.slice(0, 2);
  const nine = digits.slice(2, 3);
  const part1 = digits.slice(3, 7);
  const part2 = digits.slice(7, 11);

  let result = "";
  if (ddd) {
    result = `(${ddd}`;
    if (ddd.length === 2) result += ") ";
  }
  if (nine) result += nine + " ";
  if (part1) result += part1;
  if (part2) result += "-" + part2;
  return result;
}

function maskBirthDate(value: string): string {
  const digits = value.replace(/\D/g, "").slice(0, 8);
  const d = digits.slice(0, 2);
  const m = digits.slice(2, 4);
  const y = digits.slice(4, 8);

  let result = "";
  if (d) result = d;
  if (m) result += "/" + m;
  if (y) result += "/" + y;
  return result;
}

// dd/mm/aaaa -> yyyy-mm-dd
function parseBirthDateToISO(value: string): string | null {
  const digits = value.replace(/\D/g, "");
  if (digits.length !== 8) return null;
  const d = digits.slice(0, 2);
  const m = digits.slice(2, 4);
  const y = digits.slice(4, 8);
  return `${y}-${m}-${d}`;
}

/* --------------------------------
   Força da senha
----------------------------------- */

function evaluatePasswordStrength(password: string): PasswordStrength {
  if (!password) return "empty";

  let score = 0;
  if (password.length >= 8) score++;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score++;
  if (/\d/.test(password)) score++;
  if (/[^A-Za-z0-9]/.test(password)) score++;

  if (score <= 1) return "weak";
  if (score <= 3) return "medium";
  return "strong";
}

function getPasswordStrengthMeta(strength: PasswordStrength) {
  switch (strength) {
    case "weak":
      return { label: "Fraca", percent: 33, color: "#ff4d4f" };
    case "medium":
      return { label: "Média", percent: 66, color: "#faad14" };
    case "strong":
      return { label: "Forte", percent: 100, color: "#52c41a" };
    default:
      return { label: "—", percent: 0, color: "transparent" };
  }
}

/* --------------------------------
   Componente
----------------------------------- */

const PatientSignupPage: React.FC = () => {
  const navigate = useNavigate();

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

  const [birthDate, setBirthDate] = useState<string>("");
  const [sex, setSex] = useState<"" | Sex>("");

  const [passwordStrength, setPasswordStrength] =
    useState<PasswordStrength>("empty");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const [docToShow, setDocToShow] = useState<LegalDoc | null>(null);

  // título da aba
  useEffect(() => {
    document.title = `Cadastro de paciente · ${APP_NAME}`;
  }, []);

  /* --------------------------------
     Carregamento inicial
  ----------------------------------- */
  useEffect(() => {
    async function loadInitial() {
      try {
        setLoadingInitial(true);
        setError(null);

        const [clinicsData, legalData] = await Promise.all([
          apiRequest<Clinic[]>("/clinics/active/", { useAuth: false }),
          apiRequest<LegalDoc[]>("/legal-documents/active/", {
            useAuth: false,
          }),
        ]);

        setClinics(clinicsData);

        const docsByType: LegalDocsByType = {};
        for (const doc of legalData) {
          if (doc.doc_type === "TERMS") docsByType.TERMS = doc;
          if (doc.doc_type === "PRIVACY") docsByType.PRIVACY = doc;
          if (doc.doc_type === "CONSENT") docsByType.CONSENT = doc;
        }
        setLegalDocs(docsByType);

        if (clinicsData.length === 1) {
          setForm((prev) => ({
            ...prev,
            clinic_schema_name: clinicsData[0].schema_name,
          }));
        }
      } catch (err: unknown) {
        console.error("[SIGNUP] erro ao carregar dados iniciais:", err);
        setError("Erro ao carregar dados iniciais.");
      } finally {
        setLoadingInitial(false);
      }
    }

    loadInitial();
  }, []);

  /* --------------------------------
     Helpers de formulário
  ----------------------------------- */

  function handleInputChange(
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) {
    const { name } = e.target;
    let value = e.target.value;

    if (name === "cpf") value = maskCPF(value);
    if (name === "phone") value = maskCellPhone(value);

    if (name === "password") {
      setPasswordStrength(evaluatePasswordStrength(value));
    }

    setForm((prev) => ({ ...prev, [name]: value }));
  }

  function handleBirthDateChange(e: React.ChangeEvent<HTMLInputElement>) {
    setBirthDate(maskBirthDate(e.target.value));
  }

  function handleSexChange(e: React.ChangeEvent<HTMLSelectElement>) {
    setSex(e.target.value as "" | Sex);
  }

  function openDoc(type: DocTypeKey) {
    const doc = legalDocs[type];
    if (doc) setDocToShow(doc);
  }

  function closeDoc() {
    setDocToShow(null);
  }

  function handleModalToggle(type: DocTypeKey, checked: boolean) {
    setForm((prev) => {
      if (type === "TERMS") return { ...prev, agree_terms: checked };
      if (type === "PRIVACY") return { ...prev, agree_privacy: checked };
      if (type === "CONSENT") return { ...prev, agree_consent: checked };
      return prev;
    });
  }

  /* --------------------------------
     Validação
  ----------------------------------- */

  function validateForm(): string | null {
    if (!form.clinic_schema_name) return "Selecione a clínica.";
    if (!form.full_name.trim()) return "Informe seu nome completo.";
    if (!form.cpf.trim()) return "Informe seu CPF.";
    if (!form.phone.trim()) return "Informe seu celular.";
    if (!form.email.trim()) return "Informe seu e-mail.";

    if (!form.password) return "Defina uma senha.";
    if (form.password.length < 8)
      return "A senha deve ter pelo menos 8 caracteres.";
    if (form.password !== form.password_confirm)
      return "A confirmação de senha não confere.";

    const strength = evaluatePasswordStrength(form.password);
    if (strength === "weak") {
      return "A senha está fraca. Use letras, números e símbolos.";
    }

    if (!form.agree_terms || !form.agree_privacy || !form.agree_consent) {
      return "Você precisa concordar com todos os documentos de LGPD antes de continuar.";
    }

    return null;
  }

  const strengthMeta = getPasswordStrengthMeta(passwordStrength);

  /* --------------------------------
     Submit
  ----------------------------------- */

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

      const birthDateISO = parseBirthDateToISO(birthDate);

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

      if (sex !== "") {
        payload.sex = sex as Sex;
      }
      if (birthDateISO) {
        payload.birth_date = birthDateISO;
      }

      const data = await apiRequest<PatientRegisterResponse>(
        "/patients/register/",
        {
          method: "POST",
          body: payload,
          useAuth: false, // endpoint público
        }
      );

      setSuccessMsg(
        data.detail ||
          "Cadastro recebido! Enviamos um e-mail com link e código para confirmar seu acesso."
      );
    } catch (err) {
      console.error("[SIGNUP] erro no cadastro:", err);
      if (err instanceof Error && err.message) {
        setError(err.message);
      } else {
        setError("Não foi possível concluir o cadastro.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  /* --------------------------------
     Helpers de render (modal)
  ----------------------------------- */

  const currentDocType = docToShow?.doc_type as DocTypeKey | undefined;

  const currentAgree =
    currentDocType === "TERMS"
      ? form.agree_terms
      : currentDocType === "PRIVACY"
      ? form.agree_privacy
      : currentDocType === "CONSENT"
      ? form.agree_consent
      : false;

  /* --------------------------------
     Render
  ----------------------------------- */

  if (loadingInitial) {
    return (
      <div className="auth-layout">
        <div className="auth-card">
          <h1 className="auth-title">Cadastro de paciente</h1>
          <p>Carregando informações da clínica...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-layout patient-signup-page">
      <div className="auth-card patient-signup-card">
        {/* Header */}
        <header className="auth-header">
          <h1 className="auth-title">Cadastro de paciente</h1>
          <p className="auth-subtitle">
            Crie sua conta em uma clínica parceira do {APP_NAME}. Após o
            cadastro, você receberá um e-mail com link e código para confirmar
            seu acesso.
          </p>
        </header>

        {error && <div className="alert alert-error">{error}</div>}
        {successMsg && <div className="alert alert-success">{successMsg}</div>}

        {/* FORM */}
        <form onSubmit={handleSubmit} className="auth-form">
          {/* 1. Clínica */}
          <section className="form-section">
            <h2 className="form-section-title">1. Clínica</h2>
            <p className="form-section-subtitle">
              Escolha a clínica em que deseja se cadastrar.
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
                  <option key={clinic.id} value={clinic.schema_name}>
                    {clinic.name}
                  </option>
                ))}
              </select>
            </div>
          </section>

          {/* 2. Dados pessoais */}
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
                  placeholder="000.000.000-00"
                  value={form.cpf}
                  onChange={handleInputChange}
                  autoComplete="off"
                />
              </div>

              <div className="form-row">
                <label htmlFor="phone" className="form-label">
                  Celular
                </label>
                <input
                  id="phone"
                  name="phone"
                  type="tel"
                  className="form-input"
                  placeholder="(34) 9 9999-9999"
                  value={form.phone}
                  onChange={handleInputChange}
                  autoComplete="tel"
                />
              </div>
            </div>

            <div className="form-grid">
              <div className="form-row">
                <label htmlFor="birth_date" className="form-label">
                  Data de nascimento
                </label>
                <input
                  id="birth_date"
                  name="birth_date"
                  type="text"
                  className="form-input"
                  placeholder="dd/mm/aaaa"
                  value={birthDate}
                  onChange={handleBirthDateChange}
                  autoComplete="bday"
                />
              </div>

              <div className="form-row">
                <label htmlFor="sex" className="form-label">
                  Sexo
                </label>
                <select
                  id="sex"
                  name="sex"
                  className="form-input"
                  value={sex}
                  onChange={handleSexChange}
                >
                  <option value="">Selecione...</option>
                  <option value="M">Masculino</option>
                  <option value="F">Feminino</option>
                  <option value="N">Prefiro não informar</option>
                </select>
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

            {/* Força da senha */}
            <div className="password-strength-container">
              <div className="password-strength-header">
                <span className="password-strength-label">
                  Força da senha: <strong>{strengthMeta.label}</strong>
                </span>
              </div>
              <div className="password-strength-meter">
                <div
                  className="password-strength-meter-fill"
                  style={{
                    width: `${strengthMeta.percent}%`,
                    backgroundColor: strengthMeta.color,
                  }}
                />
              </div>
              <ul className="password-requirements">
                <li>Pelo menos 8 caracteres</li>
                <li>Letras maiúsculas e minúsculas</li>
                <li>Pelo menos um número</li>
                <li>Pelo menos um símbolo (ex: !, @, #, $)</li>
              </ul>
            </div>
          </section>

          {/* 3. LGPD – status + leitura em modal */}
          <section className="form-section">
            <h2 className="form-section-title">3. LGPD e consentimento</h2>
            <p className="form-section-subtitle">
              Abra cada documento em tela cheia, leia com atenção e depois
              registre o aceite.
            </p>

            {/* Termos de Uso */}
            {legalDocs.TERMS && (
              <div className="lgpd-doc-block">
                <header className="lgpd-doc-header">
                  <div className="lgpd-doc-left">
                    <div className="lgpd-doc-title">Termos de Uso</div>
                  </div>
                  <div className="lgpd-doc-right">
                    <span
                      className={
                        form.agree_terms
                          ? "lgpd-status lgpd-status-accepted"
                          : "lgpd-status lgpd-status-pending"
                      }
                    >
                      {form.agree_terms ? "Aceito" : "Pendente"}
                    </span>
                    <span className="lgpd-doc-version">
                      Versão {legalDocs.TERMS.version}
                    </span>
                  </div>
                </header>

                <button
                  type="button"
                  className="primary-button primary-button-neutral lgpd-open-button"
                  onClick={() => openDoc("TERMS")}
                >
                  Ler Termos de Uso
                </button>
              </div>
            )}

            {/* Política de Privacidade */}
            {legalDocs.PRIVACY && (
              <div className="lgpd-doc-block">
                <header className="lgpd-doc-header">
                  <div className="lgpd-doc-left">
                    <div className="lgpd-doc-title">
                      Política de Privacidade
                    </div>
                  </div>
                  <div className="lgpd-doc-right">
                    <span
                      className={
                        form.agree_privacy
                          ? "lgpd-status lgpd-status-accepted"
                          : "lgpd-status lgpd-status-pending"
                      }
                    >
                      {form.agree_privacy ? "Aceito" : "Pendente"}
                    </span>
                    <span className="lgpd-doc-version">
                      Versão {legalDocs.PRIVACY.version}
                    </span>
                  </div>
                </header>

                <button
                  type="button"
                  className="primary-button primary-button-neutral lgpd-open-button"
                  onClick={() => openDoc("PRIVACY")}
                >
                  Ler Política de Privacidade
                </button>
              </div>
            )}

            {/* Termo de Consentimento */}
            {legalDocs.CONSENT && (
              <div className="lgpd-doc-block">
                <header className="lgpd-doc-header">
                  <div className="lgpd-doc-left">
                    <div className="lgpd-doc-title">
                      Termo de Consentimento Médico
                    </div>
                  </div>
                  <div className="lgpd-doc-right">
                    <span
                      className={
                        form.agree_consent
                          ? "lgpd-status lgpd-status-accepted"
                          : "lgpd-status lgpd-status-pending"
                      }
                    >
                      {form.agree_consent ? "Aceito" : "Pendente"}
                    </span>
                    <span className="lgpd-doc-version">
                      Versão {legalDocs.CONSENT.version}
                    </span>
                  </div>
                </header>

                <button
                  type="button"
                  className="primary-button primary-button-neutral lgpd-open-button"
                  onClick={() => openDoc("CONSENT")}
                >
                  Ler Termo de Consentimento
                </button>
              </div>
            )}
          </section>

          {/* Footer */}
          <footer className="auth-footer">
            <button
              type="submit"
              className="primary-button primary-button-cta"
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

      {/* MODAL LGPD FULLSCREEN */}
      {docToShow && (
        <div className="legal-modal-backdrop" onClick={closeDoc}>
          <div className="legal-modal" onClick={(e) => e.stopPropagation()}>
            <header className="legal-modal-header">
              <h2>
                {docToShow.doc_type === "TERMS" && "Termos de Uso"}
                {docToShow.doc_type === "PRIVACY" &&
                  "Política de Privacidade"}
                {docToShow.doc_type === "CONSENT" &&
                  "Termo de Consentimento Médico"}
              </h2>
              <span className="legal-modal-version">
                Versão {docToShow.version}
              </span>
            </header>

            <div className="legal-modal-content-wrapper">
              <div
                className="legal-modal-content"
                dangerouslySetInnerHTML={{ __html: docToShow.content }}
              />
            </div>

            <footer className="legal-modal-footer">
              {currentDocType && (
                <div className="legal-modal-accept">
                  <label className="toggle-wrapper toggle-wrapper-modal">
                    <input
                      type="checkbox"
                      className="toggle-input"
                      checked={currentAgree}
                      onChange={(e) =>
                        handleModalToggle(currentDocType, e.target.checked)
                      }
                    />
                    <span className="toggle-slider" />
                    <span className="toggle-label">
                      {currentDocType === "TERMS" &&
                        "Li e concordo com os Termos de Uso."}
                      {currentDocType === "PRIVACY" &&
                        "Li e concordo com a Política de Privacidade."}
                      {currentDocType === "CONSENT" &&
                        "Li e concordo com o Termo de Consentimento para Tratamento de Dados Pessoais e de Saúde."}
                    </span>
                  </label>
                  <p className="legal-modal-accept-hint">
                    Este registro ficará vinculado à sua conta para fins de
                    auditoria e conformidade com a LGPD.
                  </p>
                </div>
              )}

              <button
                type="button"
                className="primary-button primary-button-neutral legal-modal-close-btn"
                onClick={closeDoc}
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
