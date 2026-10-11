"use client";

import { authClient } from "@/lib/auth/client";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

// Short-lived JWT the FastAPI backend verifies against Neon's JWKS
export async function authToken() {
  const { data } = await authClient.token();
  return data?.token || "";
}

// fetch() against the backend's /api with the signed-in user's token attached
export async function apiFetch(path, options = {}) {
  const token = await authToken();
  const headers = { ...options.headers, ...(token && { Authorization: `Bearer ${token}` }) };
  return fetch(`${API_URL}/api${path}`, { ...options, headers });
}
