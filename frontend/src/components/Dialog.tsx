// Accessible modal: role="dialog" + aria-modal, labelled by its title, focus moved inside on open, Tab kept
// inside, Escape closes, focus returned to the opener on close.
import { useEffect, useId, useRef, type ReactNode } from "react";

interface Props {
  title: string;
  onClose: () => void;
  children: ReactNode;
  testId?: string;
  /** Escape / backdrop close disabled (e.g. while a one-time password is shown). */
  closeOnEscape?: boolean;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

export function Dialog({ title, onClose, children, testId, closeOnEscape = true }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();

  useEffect(() => {
    const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const box = ref.current;
    const first = box?.querySelector<HTMLElement>(FOCUSABLE);
    (first ?? box)?.focus();
    return () => {
      opener?.focus();
    };
  }, []);

  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const box = ref.current;
    if (!box) return;
    const handler = (e: KeyboardEvent): void => {
      onKeyDown(e, box, closeOnEscape, () => {
        onCloseRef.current();
      });
    };
    box.addEventListener("keydown", handler);
    return () => {
      box.removeEventListener("keydown", handler);
    };
  }, [closeOnEscape]);

  return (
    <div className="dialog-backdrop">
      <div
        ref={ref}
        className="dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        data-testid={testId}
      >
        <h2 id={titleId} className="dialog__title">
          {title}
        </h2>
        {children}
      </div>
    </div>
  );
}

function onKeyDown(e: KeyboardEvent, box: HTMLElement, closeOnEscape: boolean, close: () => void): void {
  if (e.key === "Escape" && closeOnEscape) {
    e.stopPropagation();
    close();
    return;
  }
  if (e.key !== "Tab") return;
  const items = Array.from(box.querySelectorAll<HTMLElement>(FOCUSABLE));
  if (items.length === 0) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last?.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first?.focus();
  }
}
