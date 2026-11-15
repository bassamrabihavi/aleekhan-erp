import { useEffect, useRef } from "react";

import { AuthProvider } from "./auth/AuthContext";
import { useAuth } from "./auth/context";
import { BootErrorScreen, LoginScreen, MfaEnrolmentScreen, MfaScreen, PasswordChangeScreen } from "./auth/AuthScreens";
import { AppShell } from "./components/AppShell";
import { PageErrorBoundary } from "./components/ErrorBoundary";
import { LoadingState } from "./components/States";
import { ChangesPage } from "./pages/ChangesPage";
import { CodeRulesPage } from "./pages/CodeRulesPage";
import { CustomersPage } from "./pages/CustomersPage";
import { DocumentsPage } from "./pages/DocumentsPage";
import { HomePage, MySessionsPage } from "./pages/HomePage";
import { OpsPage } from "./pages/OpsPage";
import { OrdersPage } from "./pages/OrdersPage";
import { OrgPage } from "./pages/OrgPage";
import { ParametersPage } from "./pages/ParametersPage";
import { ProductsPage } from "./pages/ProductsPage";
import { SecurityPage } from "./pages/SecurityPage";
import { SerialCenterPage } from "./pages/SerialCenterPage";
import { SystemStatusPage } from "./pages/SystemStatusPage";
import { useSystemStatus } from "./pages/useSystemStatus";
import { WorkPage } from "./pages/WorkPage";
import { useRoute } from "./lib/router";

/** PHASE_00 public smoke page (public probes only; no login needed). */
function StatusRoute() {
  const status = useSystemStatus();
  return <SystemStatusPage status={status} />;
}

const TITLES: Record<string, string> = {
  "/": "پیشخوان",
  "/work": "کارها و تأییدها",
  "/documents": "اسناد",
  "/org": "درخت سازمانی",
  "/security": "امنیت و کاربران",
  "/parameters": "پارامترها",
  "/ops": "سلامت سامانه و Job",
  "/me/sessions": "جلسه‌های من",
  "/status": "وضعیت سامانه",
  "/serials": "مرکز کنترل سریال",
  "/orders": "ثبت سفارش و کدگذاری",
  "/changes": "تغییرات سفارش",
  "/products": "ردیابی محصولات و استایل‌ها",
  "/customers": "مشتریان و برندها",
  "/code-rules": "قاعده کد ۱۴رقمی",
};

function Page({ route }: { route: string }) {
  const base = `/${route.split("/")[1] ?? ""}`;
  if (route === "/me/sessions") return <MySessionsPage />;
  switch (base) {
    case "/work":
      return <WorkPage />;
    case "/documents":
      return <DocumentsPage />;
    case "/org":
      return <OrgPage />;
    case "/security":
      return <SecurityPage />;
    case "/parameters":
      return <ParametersPage />;
    case "/ops":
      return <OpsPage />;
    case "/serials":
      return <SerialCenterPage />;
    case "/orders":
      return <OrdersPage />;
    case "/changes":
      return <ChangesPage />;
    case "/products":
      return <ProductsPage />;
    case "/customers":
      return <CustomersPage />;
    case "/code-rules":
      return <CodeRulesPage />;
    case "/":
      return <HomePage />;
    default:
      return (
        <div className="page" data-testid="page-not-found">
          <h1>صفحه پیدا نشد</h1>
          <p>
            <a href="#/">بازگشت به پیشخوان</a>
          </p>
        </div>
      );
  }
}

function Routed() {
  const route = useRoute();
  const { status } = useAuth();
  const mainRef = useRef(route);
  useEffect(() => {
    const base = `/${route.split("/")[1] ?? ""}`;
    document.title = `${TITLES[route] ?? TITLES[base] ?? "سامانه"} — سراجی سنتی عالیخان`;
    if (mainRef.current !== route) {
      mainRef.current = route;
      document.getElementById("main")?.focus(); // keyboard / screen reader users land on the new page
    }
  }, [route]);

  if (route === "/status") {
    return (
      <AppShell authenticated={status === "ready"}>
        <StatusRoute />
      </AppShell>
    );
  }
  let body;
  switch (status) {
    case "loading":
      body = <LoadingState label="در حال بررسی جلسه…" />;
      break;
    case "anonymous":
      body = <LoginScreen />;
      break;
    case "mfa_pending":
      body = <MfaScreen />;
      break;
    case "password_change":
      body = <PasswordChangeScreen />;
      break;
    case "mfa_enrolment":
      body = <MfaEnrolmentScreen />;
      break;
    case "boot_error":
      body = <BootErrorScreen />;
      break;
    default:
      body = (
        <PageErrorBoundary key={route}>
          <Page route={route} />
        </PageErrorBoundary>
      );
  }
  return <AppShell>{body}</AppShell>;
}

export function App() {
  return (
    <AuthProvider>
      <Routed />
    </AuthProvider>
  );
}
