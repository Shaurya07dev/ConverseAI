import { auth } from "@/lib/auth/server";

// Signed-out visitors to the app pages are sent to sign in; marketing pages stay public
export default auth.middleware({ loginUrl: "/auth/sign-in" });

export const config = {
  matcher: ["/analysis/:path*", "/session/:path*"],
};
