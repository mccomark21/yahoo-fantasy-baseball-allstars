/* The freshness stamp shared by all four views. The data refreshes daily via
   GitHub Actions, so what people actually want to know is "how fresh is this?"
   — answered best by relative phrasing (today / yesterday / 3 days ago) with
   the exact date kept one layer down (hover title + the machine `dateTime`).

   Sighted readers get the compact relative phrase; screen readers get one
   complete, unabbreviated sentence (the visible phrase is hidden from them to
   avoid a doubled, clipped reading). Static by design — the value is the same
   across leagues and changes only on reload, so it needs a clear accessible
   name, not a live region that would announce on every navigation. */

interface Freshness {
  /** Short phrase for sighted readers, e.g. "today", "3 days ago", "Jun 25, 2026". */
  compact: string;
  /** Exact local date+time for the hover tooltip. */
  title: string;
  /** One complete spoken sentence for assistive tech. */
  spoken: string;
}

const startOfDay = (d: Date) =>
  new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();

function describe(iso: string, now: Date): Freshness | null {
  const then = new Date(iso);
  if (Number.isNaN(then.getTime())) return null;

  const days = Math.round((startOfDay(now) - startOfDay(then)) / 86_400_000);

  const fullDate = then.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
  const shortDate = then.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
  const clock = then.toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
  });

  let compact: string;
  let when: string; // relative clause for the spoken sentence
  if (days <= 0) {
    compact = "today";
    when = `today, ${fullDate}`;
  } else if (days === 1) {
    compact = "yesterday";
    when = `yesterday, ${fullDate}`;
  } else if (days < 7) {
    compact = `${days} days ago`;
    when = `${days} days ago, on ${fullDate}`;
  } else {
    compact = shortDate;
    when = `on ${fullDate}`;
  }

  return {
    compact,
    title: `${fullDate} at ${clock}`,
    spoken: `Stats last updated ${when}.`,
  };
}

export default function UpdatedAt({ iso }: { iso: string }) {
  const info = describe(iso, new Date());
  if (!info) return null;

  return (
    <span className="updated-at">
      <span aria-hidden="true">
        Updated{" "}
        <time dateTime={iso} className="mono" title={info.title}>
          {info.compact}
        </time>
      </span>
      <span className="visually-hidden">{info.spoken}</span>
    </span>
  );
}
