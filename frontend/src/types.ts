// src/types.ts

// Gênero básico usado em vários DTOs
export type Gender = "M" | "F";

// Papéis de usuário no sistema
export type UserRole =
  | "SAAS_ADMIN"
  | "CLINIC_OWNER"
  | "DOCTOR"
  | "SECRETARY"
  | "PATIENT";

// Clínica básica
export type ClinicDTO = {
  id: number;
  name: string;
};

// /auth/me/ -> médico vinculado à secretária
export type MeDoctorForSecretaryDTO = {
  id: number;
  name: string;
  gender?: Gender | null;
};

// /auth/me/
export type MeDTO = {
  id: number;
  username: string;
  email: string;
  first_name: string;
  last_name: string;
  role: UserRole;
  clinic: ClinicDTO | null;
  doctor_for_secretary: MeDoctorForSecretaryDTO | null;
};

// Status de agendamento
export type AppointmentStatus =
  | "REQUESTED"
  | "CONFIRMED"
  | "COMPLETED"
  | "CANCELED_BY_PATIENT"
  | "CANCELED_BY_CLINIC";

// /appointments/
export type AppointmentDTO = {
  id: string;
  start_time: string;
  end_time: string;
  status: AppointmentStatus;
  patient_name: string;
  doctor_name: string;
  doctor_gender?: Gender | null;
};

// /patients/
export type PatientDTO = {
  id: number;
  full_name: string;
  phone: string;
  email?: string | null;
};

// /staff/
export type StaffUserDTO = {
  id: number;
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  // CLINIC_OWNER | DOCTOR | SECRETARY
  role: Exclude<UserRole, "SAAS_ADMIN" | "PATIENT">;
  gender: Gender | null;
  crm?: string | null;
  specialty?: string | null;
};

// Documentos legais (consentimento / termos)
export type LegalDocType = "TERMS" | "PRIVACY" | "CONSENT";

export type LegalDocDTO = {
  id: number;
  version: string;
  doc_type: LegalDocType;
  content: string;
};
