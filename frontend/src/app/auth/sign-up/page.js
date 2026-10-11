import { Suspense } from "react";
import AuthForm from "@/components/AuthForm";

export const metadata = { title: "Create account — VaakSetu" };

export default function Page() {
  return (
    <Suspense>
      <AuthForm mode="sign-up" />
    </Suspense>
  );
}
