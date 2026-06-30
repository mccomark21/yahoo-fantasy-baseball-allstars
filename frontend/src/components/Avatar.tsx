import { useState } from "react";

/* A compact player avatar: headshot when we have one, monogram fallback
   otherwise, with an optional position badge. Used in the Positional Races
   identity column; the same visual language as the diamond's player cards. */

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase() || "—";
}

interface Props {
  name: string;
  src?: string;
  badge?: string;
}

export default function Avatar({ name, src, badge }: Props) {
  const [failed, setFailed] = useState(false);
  return (
    <span className="avatar">
      {src && !failed ? (
        <img
          src={src}
          alt=""
          loading="lazy"
          decoding="async"
          onError={() => setFailed(true)}
        />
      ) : (
        <span className="avatar__initials" aria-hidden="true">
          {initials(name)}
        </span>
      )}
      {badge && <span className="avatar__badge">{badge}</span>}
    </span>
  );
}
