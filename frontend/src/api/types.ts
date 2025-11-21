// src/api/types.ts
export type MeResponse = {
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
  } | null;
};
