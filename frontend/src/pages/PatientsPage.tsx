// src/pages/PatientsPage.tsx
import React, { useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import { useAuth } from "../auth/useAuth";
import "../styles/dashboard.css";

type MeResponse = {
  id: string;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: string;
  clinic: {
    id: string;
    name: string;
  } | null;
};

type PatientDTO = {
  id: string;
  full_name: string;
  cpf: string;
  phone: string;
  created_at: string;
};

const dateFormatter = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short",
});

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return dateFormatter.format(d);
}

const PatientsPage: React.FC = () => {
  const { logout } = useAuth();

  const [me, setMe] = useState<MeResponse | null>(null);
  const [patients, setPatients] = useState<PatientDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [form, setForm] = useState({
    full_name: "",
    cpf: "",
    phone: "",
  });
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let isActive = true;

    async function load() {
      try {
        setLoading(true);
        setError(null);

        const [meData, patientsData] = await Promise.all([
          apiRequest<MeResponse>("/auth/me/", { method: "GET" }),
          apiRequest<PatientDTO[]>("/patients/", { method: "GET" }),
        ]);

        if (!isActive) return;
        setMe(meData);
        setPatients(patientsData);
      } catch (err: unknown) {
        console.error("[PATIENTS LOAD ERROR]", err);
        if (!isActive) return;

        const msg =
          err instanceof Error
            ? err.message
            : "Não foi possível carregar os pacientes.";
        setError(msg);
      } finally {
        if (isActive) setLoading(false);
      }
    }

    load();

    return () => {
      isActive = false;
    };
  }, []);

  function handleInputChange(
    e: React.ChangeEvent<HTMLInputElement>
  ): void {
    const { name, value } = e.target;
    setForm((prev) => ({ ...prev, [name]: value }));
  }

  async function handleCreatePatient(e: React.FormEvent) {
    e.preventDefault();

    if (!form.full_name || !form.cpf || !form.phone) {
      alert("Preencha nome, CPF e telefone.");
      return;
    }

    try {
      setSaving(true);

      const payload = {
        full_name: form.full_name,
        cpf: form.cpf,
        phone: form.phone,
      };

      const newPatient = await apiRequest<PatientDTO>("/patients/", {
        method: "POST",
        body: payload,
      });

      setPatients((prev) => [newPatient, ...prev]);
      setForm({ full_name: "", cpf: "", phone: "" });
    } catch (err: unknown) {
      console.error("[PATIENT CREATE ERROR]", err);
      const msg =
        err instanceof Error
          ? err.message
          : "Não foi possível cadastrar o paciente.";
      alert(msg);
    } finally {
      setSaving(false);
    }
  }

  const displayName: string = me
    ? `${me.first_name || me.username}${
        me.last_name ? ` ${me.last_name}` : ""
      }`
    : "";

  const clinicName = me?.clinic?.name ?? null;

  return (
    <div className="dashboard-layout">
      <div className="dashboard-shell">
        {/* Header */}
        <header className="dashboard-header">
          <div className="dashboard-title-block">
            <h1 className="dashboard-title">Pacientes</h1>
            <p className="dashboard-subtitle">
              Cadastre e gerencie os pacientes da clínica.
            </p>

            {me && (
              <p className="dashboard-subtitle dashboard-subtitle-secondary">
                Logado como <strong>{displayName}</strong>
                {clinicName && <> · {clinicName}</>}
              </p>
            )}
          </div>

          <div className="dashboard-actions">
            <button
              type="button"
              className="secondary-button"
              onClick={logout}
            >
              Sair
            </button>
          </div>
        </header>

        {/* Métricas rápidas */}
        <section
          className="dashboard-metrics"
          aria-label="Resumo de pacientes"
        >
          <article className="metric-card">
            <div className="metric-label">Pacientes</div>
            <div className="metric-value">{patients.length}</div>
            <div className="metric-caption">
              Total de pacientes cadastrados na clínica
            </div>
          </article>
        </section>

        {/* Formulário de cadastro rápido */}
        <section className="appointments-section">
          <div className="appointments-header">
            <h2 className="appointments-title">Novo paciente</h2>
            <p className="appointments-caption">
              Informe dados básicos para criar um novo cadastro.
            </p>
          </div>

          <form className="appointment-row" onSubmit={handleCreatePatient}>
            <div className="appointment-cell">
              <span className="appointment-label">Nome completo</span>
              <input
                type="text"
                name="full_name"
                className="appointment-input"
                value={form.full_name}
                onChange={handleInputChange}
                placeholder="Nome completo"
              />
            </div>

            <div className="appointment-cell">
              <span className="appointment-label">CPF</span>
              <input
                type="text"
                name="cpf"
                className="appointment-input"
                value={form.cpf}
                onChange={handleInputChange}
                placeholder="000.000.000-00"
              />
            </div>

            <div className="appointment-cell">
              <span className="appointment-label">Telefone</span>
              <input
                type="text"
                name="phone"
                className="appointment-input"
                value={form.phone}
                onChange={handleInputChange}
                placeholder="(00) 00000-0000"
              />
              <div
                className="appointment-actions"
                style={{ marginTop: "0.75rem" }}
              >
                <button
                  type="submit"
                  className="appointment-action-button confirm"
                  disabled={saving}
                >
                  {saving ? "Salvando..." : "Cadastrar paciente"}
                </button>
              </div>
            </div>
          </form>
        </section>

        {/* Lista de pacientes */}
        <section className="appointments-section">
          <div className="appointments-header">
            <h2 className="appointments-title">Pacientes cadastrados</h2>
            <p className="appointments-caption">
              Lista de pacientes vinculados a esta clínica.
            </p>
          </div>

          <div className="appointments-list" aria-label="Lista de pacientes">
            {loading && (
              <div className="appointments-empty">Carregando pacientes...</div>
            )}

            {!loading && error && (
              <div className="appointments-empty">{error}</div>
            )}

            {!loading && !error && patients.length === 0 && (
              <div className="appointments-empty">
                Nenhum paciente cadastrado ainda.
              </div>
            )}

            {!loading && !error && patients.length > 0 && (
              <>
                <div className="appointments-list-header">
                  <div>Paciente</div>
                  <div>Contato</div>
                  <div>Cadastro</div>
                </div>

                {patients.map((p) => (
                  <div key={p.id} className="appointment-row">
                    <div className="appointment-cell">
                      <span className="appointment-label">Nome</span>
                      <span className="appointment-value">
                        {p.full_name}
                      </span>
                    </div>

                    <div className="appointment-cell">
                      <span className="appointment-label">CPF</span>
                      <span className="appointment-value">{p.cpf}</span>

                      <span
                        className="appointment-label"
                        style={{ marginTop: "0.3rem" }}
                      >
                        Telefone
                      </span>
                      <span className="appointment-value">{p.phone}</span>
                    </div>

                    <div className="appointment-cell">
                      <span className="appointment-label">Criado em</span>
                      <span className="appointment-value">
                        {formatDate(p.created_at)}
                      </span>
                    </div>
                  </div>
                ))}
              </>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};

export default PatientsPage;
