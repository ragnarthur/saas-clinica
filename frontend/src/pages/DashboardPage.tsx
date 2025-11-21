// src/pages/DashboardPage.tsx
import React, { useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import { useAuth } from "../auth/useAuth";
import "../styles/dashboard.css";

type AppointmentDTO = {
  id: string;
  start_time: string;
  end_time: string;
  status: string;
  patient_name: string;
  doctor_name: string;
  // novo: gênero do médico vindo do backend (ex: "M" / "F")
  doctor_gender?: "M" | "F" | null;
};

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
  doctor_for_secretary: {
    id: string;
    name: string;
    // novo: gênero também no /auth/me/
    gender?: "M" | "F" | null;
  } | null;
};

const dateTimeFormatter = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "short",
  timeStyle: "short",
});

function formatDateTime(value: string): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return dateTimeFormatter.format(d);
}

function getStatusLabel(status: string): string {
  switch (status) {
    case "CONFIRMED":
      return "Confirmado";
    case "REQUESTED":
      return "Solicitado";
    case "COMPLETED":
      return "Concluído";
    case "CANCELED_BY_PATIENT":
      return "Cancelado pelo paciente";
    case "CANCELED_BY_CLINIC":
      return "Cancelado pela clínica";
    default:
      return status;
  }
}

function getStatusClass(status: string): string {
  switch (status) {
    case "CONFIRMED":
      return "status-confirmed";
    case "REQUESTED":
      return "status-requested";
    case "COMPLETED":
      return "status-completed";
    case "CANCELED_BY_PATIENT":
    case "CANCELED_BY_CLINIC":
      return "status-canceled";
    default:
      return "status-requested";
  }
}

/**
 * Monta "Dr. Fulano" ou "Dra. Fulana" com base no gênero.
 * - Se o nome já vier com Dr/Dra, não duplica.
 * - Se o gênero não vier, devolve o nome puro.
 */
function formatDoctorName(
  name: string | null | undefined,
  gender?: "M" | "F" | null
): string {
  if (!name) return "";

  const normalized = name.trim();

  // se já tiver título, só retorna
  const hasTitle = /^Dr\.?\s|^Dra\.?\s/i.test(normalized);
  if (hasTitle) {
    return normalized;
  }

  let prefix: string | null = null;

  if (gender === "M") {
    prefix = "Dr.";
  } else if (gender === "F") {
    prefix = "Dra.";
  }

  // se não sabemos o gênero, não forçamos título
  if (!prefix) {
    return normalized;
  }

  return `${prefix} ${normalized}`;
}

const DashboardPage: React.FC = () => {
  const { logout } = useAuth();

  const [me, setMe] = useState<MeResponse | null>(null);
  const [appointments, setAppointments] = useState<AppointmentDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  useEffect(() => {
    let isActive = true;

    async function loadDashboardData() {
      try {
        setLoading(true);
        setError(null);

        // carrega /auth/me/ e /appointments/ em paralelo
        const [meData, appointmentsData] = await Promise.all([
          apiRequest<MeResponse>("/auth/me/", { method: "GET" }),
          apiRequest<AppointmentDTO[]>("/appointments/", { method: "GET" }),
        ]);

        if (!isActive) return;

        setMe(meData);
        setAppointments(appointmentsData);
      } catch (err: unknown) {
        console.error("[DASHBOARD LOAD ERROR]", err);
        if (!isActive) return;

        if (err instanceof Error) {
          setError(
            err.message ||
              "Não foi possível carregar o painel. Tente novamente."
          );
        } else {
          setError("Não foi possível carregar o painel. Tente novamente.");
        }
      } finally {
        if (isActive) {
          setLoading(false);
        }
      }
    }

    loadDashboardData();

    return () => {
      isActive = false;
    };
  }, []);

  async function handleChangeStatus(id: string, newStatus: string) {
    try {
      setUpdatingId(id);

      const updated = await apiRequest<AppointmentDTO>(`/appointments/${id}/`, {
        method: "PATCH",
        body: { status: newStatus },
      });

      setAppointments((prev) =>
        prev.map((appt) => (appt.id === id ? { ...appt, ...updated } : appt))
      );
    } catch (err: unknown) {
      console.error("[CHANGE STATUS ERROR]", err);
      const msg =
        err instanceof Error
          ? err.message
          : "Não foi possível atualizar o status. Tente novamente.";
      // depois dá pra trocar por toast bonitinho
      alert(msg);
    } finally {
      setUpdatingId(null);
    }
  }

  const totalAppointments = appointments.length;
  const confirmedCount = appointments.filter(
    (a) => a.status === "CONFIRMED"
  ).length;
  const requestedCount = appointments.filter(
    (a) => a.status === "REQUESTED"
  ).length;

  // ordena pelos mais próximos primeiro
  const sortedAppointments = appointments.slice().sort((a, b) =>
    a.start_time.localeCompare(b.start_time)
  );

  // strings de exibição do usuário / clínica / médico
  const displayName: string = me
    ? `${me.first_name || me.username}${
        me.last_name ? ` ${me.last_name}` : ""
      }`
    : "";

  const clinicName = me?.clinic?.name ?? null;

  const actingDoctorRaw =
    me?.role === "SECRETARY" && me.doctor_for_secretary
      ? me.doctor_for_secretary
      : null;

  const actingDoctorName = actingDoctorRaw
    ? formatDoctorName(actingDoctorRaw.name, actingDoctorRaw.gender)
    : null;

  return (
    <div className="dashboard-layout">
      <div className="dashboard-shell">
        {/* Header */}
        <header className="dashboard-header">
          <div className="dashboard-title-block">
            <h1 className="dashboard-title">Painel da Clínica</h1>
            <p className="dashboard-subtitle">
              Visão geral dos agendamentos do dia e próximos horários.
            </p>

            {me && (
              <p className="dashboard-subtitle dashboard-subtitle-secondary">
                Logado como <strong>{displayName}</strong>
                {clinicName && <> · {clinicName}</>}
                {actingDoctorName && (
                  <>
                    {" · Atuando com "}
                    <strong>{actingDoctorName}</strong>
                  </>
                )}
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
        <section className="dashboard-metrics" aria-label="Resumo da agenda">
          <article className="metric-card">
            <div className="metric-label">Agendamentos</div>
            <div className="metric-value">{totalAppointments}</div>
            <div className="metric-caption">Total carregado para a clínica</div>
          </article>

          <article className="metric-card">
            <div className="metric-label">Confirmados</div>
            <div className="metric-value">{confirmedCount}</div>
            <div className="metric-caption">
              Pacientes com horário já confirmado
            </div>
          </article>

          <article className="metric-card">
            <div className="metric-label">Solicitados</div>
            <div className="metric-value">{requestedCount}</div>
            <div className="metric-caption">
              Aguardando confirmação da secretaria
            </div>
          </article>
        </section>

        {/* Lista de agendamentos */}
        <section className="appointments-section">
          <div className="appointments-header">
            <h2 className="appointments-title">Próximos horários</h2>
            <p className="appointments-caption">
              Visualize rapidamente paciente, médico, horários e status de cada
              consulta.
            </p>
          </div>

          <div className="appointments-list" aria-label="Lista de agendamentos">
            {loading && (
              <div className="appointments-empty">Carregando agenda...</div>
            )}

            {!loading && error && (
              <div className="appointments-empty">{error}</div>
            )}

            {!loading && !error && sortedAppointments.length === 0 && (
              <div className="appointments-empty">
                Nenhum agendamento encontrado para esta clínica.
              </div>
            )}

            {!loading &&
              !error &&
              sortedAppointments.length > 0 && (
                <>
                  <div className="appointments-list-header">
                    <div>Paciente &amp; médico</div>
                    <div>Horários</div>
                    <div>Status &amp; ações</div>
                  </div>

                  {sortedAppointments.map((appt) => (
                    <div key={appt.id} className="appointment-row">
                      {/* Paciente + médico */}
                      <div className="appointment-cell">
                        <span className="appointment-label">Paciente</span>
                        <span className="appointment-value">
                          {appt.patient_name}
                        </span>
                        <span
                          className="appointment-label"
                          style={{ marginTop: "0.3rem" }}
                        >
                          Médico
                        </span>
                        <span className="appointment-value">
                          {formatDoctorName(appt.doctor_name, appt.doctor_gender)}
                        </span>
                      </div>

                      {/* Horários */}
                      <div className="appointment-cell">
                        <span className="appointment-label">Início</span>
                        <span className="appointment-value">
                          {formatDateTime(appt.start_time)}
                        </span>

                        <span
                          className="appointment-label"
                          style={{ marginTop: "0.3rem" }}
                        >
                          Fim
                        </span>
                        <span className="appointment-value">
                          {formatDateTime(appt.end_time)}
                        </span>
                      </div>

                      {/* Status + ações da secretária */}
                      <div className="appointment-cell">
                        <span className="appointment-label">Status</span>
                        <span
                          className={`appointment-status-pill ${getStatusClass(
                            appt.status
                          )}`}
                        >
                          {getStatusLabel(appt.status)}
                        </span>

                        {appt.status === "REQUESTED" && (
                          <div className="appointment-actions">
                            <button
                              type="button"
                              className="appointment-action-button confirm"
                              disabled={updatingId === appt.id}
                              onClick={() =>
                                handleChangeStatus(appt.id, "CONFIRMED")
                              }
                            >
                              Confirmar
                            </button>
                            <button
                              type="button"
                              className="appointment-action-button cancel"
                              disabled={updatingId === appt.id}
                              onClick={() =>
                                handleChangeStatus(
                                  appt.id,
                                  "CANCELED_BY_CLINIC"
                                )
                              }
                            >
                              Cancelar
                            </button>
                          </div>
                        )}

                        {appt.status === "CONFIRMED" && (
                          <div className="appointment-actions">
                            <button
                              type="button"
                              className="appointment-action-button complete"
                              disabled={updatingId === appt.id}
                              onClick={() =>
                                handleChangeStatus(appt.id, "COMPLETED")
                              }
                            >
                              Concluir
                            </button>
                            <button
                              type="button"
                              className="appointment-action-button cancel"
                              disabled={updatingId === appt.id}
                              onClick={() =>
                                handleChangeStatus(
                                  appt.id,
                                  "CANCELED_BY_CLINIC"
                                )
                              }
                            >
                              Cancelar
                            </button>
                          </div>
                        )}
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

export default DashboardPage;
