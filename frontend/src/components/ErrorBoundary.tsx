// Page-level error boundary (02.5): an unexpected render error shows a Persian error state with a reload action
// instead of an empty page. Keyed by route in App.tsx, so navigating elsewhere resets it.
import { Component, type ErrorInfo, type ReactNode } from "react";

interface State {
  failed: boolean;
}

export class PageErrorBoundary extends Component<{ children: ReactNode }, State> {
  override state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  override componentDidCatch(error: unknown, info: ErrorInfo): void {
    // console only (no data values are logged by the UI); the dev server shows it for diagnosis
    console.error("page render error", error, info.componentStack);
  }

  override render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <div className="state state--error" data-testid="state-render-error" role="alert">
        <p className="state__title">نمایش این صفحه با خطا روبه‌رو شد.</p>
        <p className="state__message">داده‌ای نمایش داده نمی‌شود تا اشتباه دیده نشود. صفحه را دوباره بارگذاری کنید.</p>
        <button type="button" className="btn btn--secondary" onClick={() => { window.location.reload(); }}>
          بارگذاری دوباره
        </button>
      </div>
    );
  }
}
