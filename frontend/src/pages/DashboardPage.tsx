// src/pages/DashboardPage.tsx
import React, { useEffect, useState } from "react";
import { apiRequest } from "../api/client";
import type { AppointmentDTO, MeDTO } from "../types";
import "../styles/dashboard.css";

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

/** Prefixa Dr./Dra. se o nome ainda não tiver título */
function formatDoctorName(
  name: string | null | undefined,
  gender?: "M" | "F" | null
): string {
  if (!name) return "";
  const normalized = name.trim();
  const hasTitle = /^Dr\.?\s|^Dra\.?\s/i.test(normalized);
  if (hasTitle) return normalized;

  if (gender === "M") return `Dr. ${normalized}`;
  if (gender === "F") return `Dra. ${normalized}`;
  return normalized;
}

const DashboardPage: React.FC = () => {
  const [me, setMe] = useState<MeDTO | null>(null);
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

        const [meData, appointmentsData] = await Promise.all([
          apiRequest<MeDTO>("/auth/me/", { method: "GET" }),
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

  const sortedAppointments = appointments
    .slice()
    .sort((a, b) => a.start_time.localeCompare(b.start_time));

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

  const subtitle = [
    displayName && `Logado como ${displayName}`,
    clinicName && `Clínica ${clinicName}`,
    actingDoctorName && `Atuando com ${actingDoctorName}`,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="dashboard-layout">
      <div className="dashboard-shell">
        {/* Cabeçalho da página (agora sem navbar) */}
        <header className="dashboard-header">
          <div className="dashboard-title-block">
            <h1 className="dashboard-title">Painel da Clínica</h1>
            <p className="dashboard-subtitle">
              Visão geral dos agendamentos do dia e próximos horários.
            </p>

            {subtitle && (
              <p className="dashboard-subtitle dashboard-subtitle-secondary">
                {subtitle}
              </p>
            )}
          </div>
        </header>

        {/* Métricas rápidas */}
        <section className="dashboard-metrics" aria-label="Resumo da agenda">
          <article className="metric-card">
            <div className="metric-label">Agendamentos</div>
            <div className="metric-value">{totalAppointments}</div>
            <div className="metric-caption">
              Total carregado para a clínica
            </div>
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
                          {formatDoctorName(
                            appt.doctor_name,
                            appt.doctor_gender
                          )}
                        </span>
                      </div>

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
