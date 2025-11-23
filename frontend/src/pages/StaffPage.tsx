// src/pages/StaffPage.tsx
import React, { useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import type { StaffUserDTO, Gender } from "../types";
import "../styles/dashboard.css";

// gênero usado no formulário ("" = não informar)
type FormGender = "" | Gender;

type CreateDoctorForm = {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
  crm: string;
  specialty: string;
  gender: FormGender;
};

type CreateDoctorPayload = {
  email: string;
  username: string;
  password: string;
  first_name: string;
  last_name: string;
  role: "DOCTOR";
  crm: string;
  specialty: string;
  gender?: Gender | null;
};

const initialForm: CreateDoctorForm = {
  email: "",
  password: "",
  first_name: "",
  last_name: "",
  crm: "",
  specialty: "",
  gender: "",
};

function getRoleLabel(role: StaffUserDTO["role"]): string {
  switch (role) {
    case "DOCTOR":
      return "Médico(a)";
    case "SECRETARY":
      return "Secretária(o)";
    case "CLINIC_OWNER":
      return "Administrador(a) da clínica";
    default:
      return role;
  }
}

const StaffPage: React.FC = () => {
  const [staff, setStaff] = useState<StaffUserDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<CreateDoctorForm>(initialForm);

  // ------- carregar staff da API --------
  useEffect(() => {
    let isActive = true;

    async function loadStaff() {
      try {
        setLoading(true);
        setError(null);

        const data = await apiRequest<StaffUserDTO[]>("/staff/", {
          method: "GET",
        });

        if (!isActive) return;
        setStaff(data);
      } catch (err: unknown) {
        console.error("[STAFF LOAD ERROR]", err);
        if (!isActive) return;

        const msg =
          err instanceof Error
            ? err.message || "Não foi possível carregar o time."
            : "Não foi possível carregar o time.";

        setError(msg);
      } finally {
        if (isActive) setLoading(false);
      }
    }

    loadStaff();
    return () => {
      isActive = false;
    };
  }, []);

  // ------- handlers de formulário --------
  function handleInputChange(
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) {
    const { name, value } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: value,
    }));
  }

  async function handleCreateDoctor(e: React.FormEvent) {
    e.preventDefault();

    if (!form.email || !form.password || !form.first_name) {
      alert("Preencha pelo menos e-mail, senha e nome.");
      return;
    }

    try {
      setSaving(true);
      setError(null);

      const payload: CreateDoctorPayload = {
        email: form.email,
        username: form.email,
        password: form.password,
        first_name: form.first_name,
        last_name: form.last_name,
        role: "DOCTOR",
        crm: form.crm,
        specialty: form.specialty,
      };

      // Só manda gender se for M ou F
      if (form.gender === "M" || form.gender === "F") {
        payload.gender = form.gender;
      }

      const newDoctor = await apiRequest<StaffUserDTO>("/staff/", {
        method: "POST",
        body: payload,
      });

      setStaff((prev) => [newDoctor, ...prev]);
      setForm(initialForm);
    } catch (err: unknown) {
      console.error("[CREATE DOCTOR ERROR]", err);
      const msg =
        err instanceof Error
          ? err.message || "Não foi possível criar o médico. Tente novamente."
          : "Não foi possível criar o médico. Tente novamente.";
      setError(msg);
      alert(msg);
    } finally {
      setSaving(false);
    }
  }

  // ------- render --------
  return (
    <div className="dashboard-layout">
      <div className="dashboard-shell">
        {/* Header */}
        <header className="dashboard-header">
          <div className="dashboard-title-block">
            <h1 className="dashboard-title">Equipe da Clínica</h1>
            <p className="dashboard-subtitle">
              Gerencie médicos e funcionários vinculados a esta clínica.
            </p>
          </div>
        </header>

        {/* Métricas */}
        <section className="dashboard-metrics" aria-label="Resumo da equipe">
          <article className="metric-card">
            <div className="metric-label">Total de usuários</div>
            <div className="metric-value">{staff.length}</div>
          </article>

          <article className="metric-card">
            <div className="metric-label">Médicos</div>
            <div className="metric-value">
              {staff.filter((s) => s.role === "DOCTOR").length}
            </div>
          </article>

          <article className="metric-card">
            <div className="metric-label">Secretárias</div>
            <div className="metric-value">
              {staff.filter((s) => s.role === "SECRETARY").length}
            </div>
          </article>
        </section>

        {/* Form de novo médico */}
        <section className="appointments-section">
          <div className="appointments-header">
            <h2 className="appointments-title">Cadastrar novo médico</h2>
            <p className="appointments-caption">
              O médico criado já aparecerá na agenda e poderá acessar o sistema.
            </p>
          </div>

          <form className="appointments-list" onSubmit={handleCreateDoctor}>
            <div className="appointment-row">
              <div className="appointment-cell">
                <span className="appointment-label">E-mail (login)</span>
                <input
                  type="email"
                  name="email"
                  className="appointment-input"
                  placeholder="dr@exemplo.com"
                  value={form.email}
                  onChange={handleInputChange}
                  required
                />

                <span
                  className="appointment-label"
                  style={{ marginTop: "0.5rem" }}
                >
                  Senha
                </span>
                <input
                  type="password"
                  name="password"
                  className="appointment-input"
                  placeholder="Senha temporária"
                  value={form.password}
                  onChange={handleInputChange}
                  required
                />
              </div>

              <div className="appointment-cell">
                <span className="appointment-label">Nome</span>
                <input
                  type="text"
                  name="first_name"
                  className="appointment-input"
                  placeholder="Nome"
                  value={form.first_name}
                  onChange={handleInputChange}
                  required
                />

                <span
                  className="appointment-label"
                  style={{ marginTop: "0.5rem" }}
                >
                  Sobrenome
                </span>
                <input
                  type="text"
                  name="last_name"
                  className="appointment-input"
                  placeholder="Sobrenome"
                  value={form.last_name}
                  onChange={handleInputChange}
                />
              </div>

              <div className="appointment-cell">
                <span className="appointment-label">CRM</span>
                <input
                  type="text"
                  name="crm"
                  className="appointment-input"
                  placeholder="CRM"
                  value={form.crm}
                  onChange={handleInputChange}
                />

                <span
                  className="appointment-label"
                  style={{ marginTop: "0.5rem" }}
                >
                  Especialidade
                </span>
                <input
                  type="text"
                  name="specialty"
                  className="appointment-input"
                  placeholder="Especialidade (ex: Clínico Geral)"
                  value={form.specialty}
                  onChange={handleInputChange}
                />
              </div>

              <div className="appointment-cell">
                <span className="appointment-label">Tratamento</span>
                <select
                  name="gender"
                  className="appointment-input"
                  value={form.gender || ""} // <- aqui some o erro
                  onChange={handleInputChange}
                >
                  <option value="">Não informar</option>
                  <option value="M">Masculino (Dr.)</option>
                  <option value="F">Feminino (Dra.)</option>
                </select>

                <span
                  className="appointment-label"
                  style={{ marginTop: "0.5rem" }}
                >
                  &nbsp;
                </span>
                <button
                  type="submit"
                  className="appointment-action-button confirm"
                  disabled={saving}
                >
                  {saving ? "Salvando..." : "Criar médico"}
                </button>
              </div>
            </div>

            {error && (
              <div className="appointments-empty" style={{ marginTop: "1rem" }}>
                {error}
              </div>
            )}
          </form>
        </section>

        {/* Lista de staff */}
        <section className="appointments-section" style={{ marginTop: "2rem" }}>
          <div className="appointments-header">
            <h2 className="appointments-title">Equipe atual</h2>
            <p className="appointments-caption">
              Lista de médicos, secretárias e administradores desta clínica.
            </p>
          </div>

          <div className="appointments-list">
            {loading && (
              <div className="appointments-empty">Carregando equipe...</div>
            )}

            {!loading && staff.length === 0 && (
              <div className="appointments-empty">
                Nenhum usuário cadastrado ainda.
              </div>
            )}

            {!loading &&
              staff.length > 0 && (
                <>
                  <div className="appointments-list-header">
                    <div>Nome</div>
                    <div>E-mail</div>
                    <div>Função</div>
                  </div>

                  {staff.map((user) => (
                    <div key={user.id} className="appointment-row">
                      <div className="appointment-cell">
                        <span className="appointment-label">Nome</span>
                        <span className="appointment-value">
                          {user.first_name} {user.last_name}
                        </span>
                      </div>
                      <div className="appointment-cell">
                        <span className="appointment-label">E-mail</span>
                        <span className="appointment-value">{user.email}</span>
                      </div>
                      <div className="appointment-cell">
                        <span className="appointment-label">Função</span>
                        <span className="appointment-value">
                          {getRoleLabel(user.role)}
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

export default StaffPage;
