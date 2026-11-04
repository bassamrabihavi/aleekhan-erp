import type { Tone } from "../lib/labels";

interface Props {
  tone: Tone;
  label: string;
  testId?: string;
}

/** Status pill. Colour is never the only signal: the label text always carries the meaning. */
export function StatusChip({ tone, label, testId }: Props) {
  return (
    <span className={`chip chip--${tone}`} data-testid={testId} data-tone={tone}>
      <span className="chip__dot" aria-hidden="true" />
      {label}
    </span>
  );
}
