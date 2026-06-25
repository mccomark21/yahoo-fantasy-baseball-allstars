export default function BallIcon() {
  return (
    <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" className="ball-icon">
      <circle cx="12" cy="12" r="9.5" fill="var(--field-deep)" stroke="var(--crimson)" strokeWidth="1.6" />
      <path
        d="M7.5 4.2c2.4 2.6 2.4 13 0 15.6M16.5 4.2c-2.4 2.6-2.4 13 0 15.6"
        fill="none"
        stroke="var(--crimson)"
        strokeWidth="1.2"
        strokeLinecap="round"
      />
    </svg>
  );
}
