import { createNeonAuth } from "@neondatabase/auth/next/server";

// Neon Auth (managed Better Auth): sessions live in cookies on this app's origin
export const auth = createNeonAuth({
  baseUrl: process.env.NEON_AUTH_BASE_URL,
  cookies: { secret: process.env.NEON_AUTH_COOKIE_SECRET },
});
