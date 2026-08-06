// NO DESIGN WAS SUPPLIED FOR THIS SCREEN.
//
// The handoff has no account screen — the signed-in user appears only as the
// sidebar chip, which in the prototype just fires a toast. Structure is derived
// from QAgent's `app/src/screens/auth/Profile.tsx` (identity card, personal
// info, security, danger zone) and restyled onto EmeHub's tokens with the
// handoff's Settings-card shapes (`screens/Settings/SettingRow`), so it reads
// as part of the same product rather than a bolted-on form.
//
// Reached from the sidebar user chip: `/app/profile`. Sessions deliberately
// live on Authentication › Sessions rather than being duplicated here; the
// security card links across instead of forking the same table.
//
// Live against `GET|PATCH /auth/me`, `POST /auth/change-password` and
// `POST /auth/2fa/setup|enable|disable`.

import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

import {
  Button,
  GlassCard,
  Glyph,
  Icon,
  Input,
  Notice,
  Pill,
  Spinner,
  toast,
} from "@/components/ui";
import { Hairline, SettingRow } from "@/screens/Settings/SettingRow";
import { changePassword, updateMe } from "@/data";
import { ApiError } from "@/lib/api";
import { displayName, useAuth, userInitials, userRole } from "@/store/auth";
import { TwoFactorCard } from "./TwoFactorCard";

const reason = (error: unknown, fallback: string): string =>
  error instanceof ApiError ? error.message : fallback;

/** The hub hashes whatever it is given; this is the client-side floor. */
const MIN_LENGTH = 12;

export default function ProfileScreen() {
  const navigate = useNavigate();
  const user = useAuth((s) => s.user);
  const setUser = useAuth((s) => s.setUser);

  return (
    <div className="animate-fade-in-up flex max-w-[1080px] flex-col gap-[14px]">
      <GlassCard className="flex items-center gap-[14px] p-[22px]">
        <Glyph size={46} fill="accent" label={userInitials(user)} glow />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[18px] font-extrabold tracking-[-.02em] text-txt">
            {displayName(user) || "Your account"}
          </div>
          <div className="mt-[3px] truncate font-mono text-[12px] text-muted">
            {user?.email ?? "—"}
          </div>
        </div>
        {userRole(user) && (
          <Pill tone={userRole(user) === "Admin" ? "qagent" : "dagent"} size="sm">
            {userRole(user)}
          </Pill>
        )}
        {/* Navigate first; `/signed-out` performs the server logout on mount.
            Clearing the session here would flip `status` to "anon" and let
            RequireAuth redirect to /login before this navigation commits. */}
        <Button
          variant="ghost"
          icon={<Icon name="logout" size={15} strokeWidth={2.2} />}
          onClick={() => navigate("/signed-out")}
        >
          Sign out
        </Button>
      </GlassCard>

      <PersonalInfoCard
        firstName={user?.firstName ?? ""}
        lastName={user?.lastName ?? ""}
        onSaved={setUser}
      />

      <PasswordCard />

      <TwoFactorCard />
    </div>
  );
}

/* ── Personal info ───────────────────────────────────────────────────────── */

function PersonalInfoCard({
  firstName: initialFirst,
  lastName: initialLast,
  onSaved,
}: {
  firstName: string;
  lastName: string;
  onSaved: (user: Awaited<ReturnType<typeof updateMe>>) => void;
}) {
  const [firstName, setFirstName] = useState(initialFirst);
  const [lastName, setLastName] = useState(initialLast);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Resync when the store principal changes under us (bootstrap, refreshUser).
  useEffect(() => {
    setFirstName(initialFirst);
    setLastName(initialLast);
  }, [initialFirst, initialLast]);

  const dirty = firstName !== initialFirst || lastName !== initialLast;

  const save = async (e: FormEvent) => {
    e.preventDefault();
    if (saving || !dirty) return;
    setSaving(true);
    setError(null);
    try {
      onSaved(await updateMe({ firstName, lastName }));
      toast("Profile saved");
    } catch (err) {
      setError(reason(err, "The hub did not respond."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <GlassCard className="p-[22px]">
      <form onSubmit={save} className="flex flex-col gap-[14px]">
        <div className="text-[15px] font-extrabold tracking-[-.01em] text-txt">
          Personal information
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="FIRST NAME"
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            placeholder="Duna"
          />
          <Input
            label="LAST NAME"
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
            placeholder="Nguyen"
          />
        </div>

        {error && <Notice tone="danger">{error}</Notice>}

        <div className="flex items-center gap-3">
          <span className="text-[12px] text-faint">
            Your email is your sign-in identity and cannot be changed here.
          </span>
          <Button
            type="submit"
            variant="primary"
            className="ml-auto"
            disabled={saving || !dirty}
            icon={saving ? <Spinner size={14} speed="upload" /> : undefined}
          >
            {saving ? "Saving…" : "Save changes"}
          </Button>
        </div>
      </form>
    </GlassCard>
  );
}

/* ── Password ────────────────────────────────────────────────────────────── */

function PasswordCard() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (saving) return;
    if (next.length < MIN_LENGTH) {
      setError(`Use at least ${MIN_LENGTH} characters for the new password.`);
      return;
    }
    if (next !== confirm) {
      setError("The two new passwords do not match.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await changePassword({ currentPassword: current, newPassword: next });
      setCurrent("");
      setNext("");
      setConfirm("");
      // Kept: signing every other device out is a consequence the user has to
      // know about, not a restatement of "changed".
      toast(
        "Password changed",
        "ok",
        "Your other devices were signed out",
      );
    } catch (err) {
      setError(reason(err, "The hub did not respond."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <GlassCard className="p-[22px]">
      <form onSubmit={submit} className="flex flex-col gap-[14px]">
        <div className="text-[15px] font-extrabold tracking-[-.01em] text-txt">
          Password
        </div>

        <Input
          label="CURRENT PASSWORD"
          type="password"
          autoComplete="current-password"
          value={current}
          onChange={(e) => setCurrent(e.target.value)}
          placeholder="••••••••••••"
        />

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="NEW PASSWORD"
            type="password"
            autoComplete="new-password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            placeholder="••••••••••••"
          />
          <Input
            label="CONFIRM NEW PASSWORD"
            type="password"
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="••••••••••••"
          />
        </div>

        {error && <Notice tone="danger">{error}</Notice>}

        <Hairline />

        <SettingRow
          label="Changing your password signs out your other devices"
          description="This session stays signed in. Review the rest under Authentication › Sessions."
        >
          <Button
            type="submit"
            variant="primary"
            disabled={saving || !current || !next}
            icon={saving ? <Spinner size={14} speed="upload" /> : undefined}
          >
            {saving ? "Saving…" : "Change password"}
          </Button>
        </SettingRow>

        <Link
          to="/app/auth?tab=sessions"
          className="flex items-center gap-1.5 text-[12px] font-semibold text-ps-text hover:text-p"
        >
          Review active sessions
          <Icon name="arrowRight" size={13} strokeWidth={2.4} />
        </Link>
      </form>
    </GlassCard>
  );
}
