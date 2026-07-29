// Wire-value → display-string helpers shared by the identity modules.
//
// The hub returns ISO timestamps and raw User-Agents; every screen in the
// handoff shows "26m ago" and "Windows · Chrome". That translation is
// presentation, not data, but it belongs here rather than in a component so
// `data/auth.ts` and `data/people.ts` produce the same strings.
//
// Deliberately NOT re-exported from `data/index.ts` — like `timing.ts`, this is
// scaffolding for the data layer, not public API.

/** Compact relative time. "active now" / "26m ago" / "3d ago" / a date. */
export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "never";
  const minutes = Math.round((Date.now() - then) / 60_000);
  if (minutes < 1) return "active now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days === 1) return "yesterday";
  if (days < 30) return `${days}d ago`;
  return new Date(then).toLocaleDateString();
}

/** Forward-looking counterpart. "in 30 days" / "in 4h" / "expired". */
export function relativeFuture(iso: string | null | undefined): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const minutes = Math.round((then - Date.now()) / 60_000);
  if (minutes <= 0) return "expired";
  if (minutes < 60) return `in ${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `in ${hours}h`;
  return `in ${Math.round(hours / 24)}d`;
}

/** "Windows · Chrome" from a raw User-Agent. Falls back to "Unknown device". */
export function describeUserAgent(userAgent: string): string {
  const ua = (userAgent || "").toLowerCase();
  if (!ua) return "Unknown device";

  let os = "";
  if (/windows/.test(ua)) os = "Windows";
  else if (/ipad/.test(ua)) os = "iPad";
  else if (/iphone|ipod/.test(ua)) os = "iPhone";
  else if (/mac os x|macintosh/.test(ua)) os = "macOS";
  else if (/android/.test(ua)) os = "Android";
  else if (/linux/.test(ua)) os = "Linux";

  let browser = "";
  if (/edg\//.test(ua)) browser = "Edge";
  else if (/opr\/|opera/.test(ua)) browser = "Opera";
  else if (/headlesschrome/.test(ua)) browser = "Headless Chrome";
  else if (/chrome|crios/.test(ua)) browser = "Chrome";
  else if (/firefox|fxios/.test(ua)) browser = "Firefox";
  else if (/safari/.test(ua)) browser = "Safari";

  if (os && browser) return `${os} · ${browser}`;
  return os || browser || "Unknown device";
}

/** "EK" from ("Emre", "Kaya"); falls back to the email's first letter. */
export function initialsFrom(
  firstName: string,
  lastName: string,
  email: string,
): string {
  const a = firstName.trim().charAt(0);
  const b = lastName.trim().charAt(0);
  const pair = `${a}${b}`.toUpperCase();
  if (pair) return pair;
  return email.trim().charAt(0).toUpperCase() || "?";
}

/** "Emre Kaya" from the name parts; falls back to the email's local part. */
export function displayNameFrom(
  firstName: string,
  lastName: string,
  email: string,
): string {
  const full = `${firstName.trim()} ${lastName.trim()}`.trim();
  return full || email.split("@")[0] || email;
}
