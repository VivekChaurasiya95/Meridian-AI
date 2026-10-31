import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { AppShell } from "@/components/shell/AppShell";

const API_BASE =
  process.env.MERIDIAN_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8010";

/** Server-side session validation: a stale cookie cannot reach the app. */
async function sessionValid(next: string): Promise<boolean> {
  const cookieStore = await cookies();
  const token = cookieStore.get("meridian_session")?.value;
  if (!token) redirect(`/login?next=${encodeURIComponent(next)}`);
  try {
    const response = await fetch(`${API_BASE}/api/v1/me`, {
      headers: { Cookie: `meridian_session=${token}` },
      cache: "no-store",
    });
    return response.ok;
  } catch {
    return false;
  }
}

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  if (!(await sessionValid("/app"))) redirect("/login?next=%2Fapp");
  return <AppShell>{children}</AppShell>;
}
