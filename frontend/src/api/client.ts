// src/api/client.ts

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api";

type RequestOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  /**
   * useAuth = true -> envia Authorization: Bearer <token>
   * useAuth = false -> chamada pública (sem header de auth)
   */
  useAuth?: boolean;
};

type ApiErrorShape = {
  detail?: string;
};

function getAccessToken(): string | null {
  const keysToTry = ["access_token", "token", "authToken", "access"];

  for (const key of keysToTry) {
    const value = localStorage.getItem(key);
    if (value) {
      if (key !== "access_token") {
        console.log(`[API] usando token da chave legada "${key}".`);
      } else {
        console.log("[API] usando token da chave access_token.");
      }
      return value;
    }
  }

  console.log("[API] nenhum token encontrado no localStorage.");
  return null;
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {}
): Promise<T> {
  const { method = "GET", body, useAuth = true } = options;

  const headers: HeadersInit = {
    "Content-Type": "application/json",
  };

  const token = useAuth ? getAccessToken() : null;

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  const text = await response.text();
  let data: unknown = null;

  if (text) {
    try {
      data = JSON.parse(text) as unknown;
    } catch {
      // resposta não JSON, segue sem quebrar
      console.warn("[API] resposta não JSON recebida de", path);
    }
  }

  const errorData = (data ?? null) as ApiErrorShape | null;

  if (!response.ok) {
    // 401 - não autenticado / token inválido
    if (response.status === 401) {
      throw new Error(
        errorData?.detail ??
          "Sessão expirada ou não autorizada. Faça login novamente."
      );
    }

    // 403 - sem permissão
    if (response.status === 403) {
      throw new Error(errorData?.detail ?? "Acesso negado.");
    }

    // qualquer erro que veio com detail
    if (errorData?.detail) {
      throw new Error(errorData.detail);
    }

    // 5xx - erro de servidor / backend off
    if (response.status >= 500) {
      throw new Error(
        "Não foi possível conectar ao servidor. Verifique se o backend está rodando."
      );
    }

    // fallback genérico
    throw new Error("Falha na requisição. Tente novamente.");
  }

  return data as T;
}
