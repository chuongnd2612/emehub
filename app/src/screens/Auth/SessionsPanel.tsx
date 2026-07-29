// Handoff § 7 › Sessions — "sessions table with revoke".
//
// Live against `GET /auth/sessions`, `DELETE /auth/sessions/{id}` and
// `POST /auth/sessions/revoke-others`.
//
// Two deliberate departures from the prototype, both forced by the payload:
//   • The LOCATION column is gone. `SessionOut` has no geo field and the hub
//     does no IP lookup, so the prototype's "Istanbul, TR" has no source. Its
//     width goes to an EXPIRES column, which the payload does have.
//   • Revoke is a real request, so it can fail. The prototype filters the row
//     out optimistically with no undo; here the row goes only once the hub
//     confirms, and a failure toasts the reason instead of lying.

import { useCallback, useEffect, useState } from "react";

import {
  Button,
  ErrorState,
  LoadingState,
  Pill,
  Table,
  TableCell,
  TableEmpty,
  TableRow,
  toast,
} from "@/components/ui";
import {
  getSessions,
  revokeOtherSessions,
  revokeSession,
  type Session,
} from "@/data";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/cn";

const COLUMNS = "14px minmax(0,2fr) 150px 130px 120px 110px";

const reason = (error: unknown, fallback: string): string =>
  error instanceof ApiError ? error.message : fallback;

export function SessionsPanel() {
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [revokingOthers, setRevokingOthers] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      setSessions(await getSessions());
    } catch (err) {
      setSessions(null);
      setError(reason(err, "The hub did not respond."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const revoke = async (session: Session) => {
    setBusyId(session.id);
    try {
      await revokeSession(session.id);
      setSessions((prev) => prev?.filter((s) => s.id !== session.id) ?? null);
      toast("Session revoked", "That device has been signed out of EmeHub", "ok");
    } catch (err) {
      toast(
        "Could not revoke that session",
        reason(err, "The hub did not respond."),
        "warn",
      );
    } finally {
      setBusyId(null);
    }
  };

  const revokeOthers = async () => {
    setRevokingOthers(true);
    try {
      await revokeOtherSessions();
      setSessions((prev) => prev?.filter((s) => s.current) ?? null);
      toast(
        "Other sessions revoked",
        "Every device except this one has been signed out",
        "ok",
      );
    } catch (err) {
      toast(
        "Could not revoke those sessions",
        reason(err, "The hub did not respond."),
        "warn",
      );
    } finally {
      setRevokingOthers(false);
    }
  };

  if (error) {
    return (
      <Table>
        <ErrorState
          title="Could not load your sessions"
          detail={error}
          onRetry={() => void load()}
        />
      </Table>
    );
  }

  if (sessions === null) {
    return (
      <Table>
        <LoadingState label="Loading sessions…" />
      </Table>
    );
  }

  const others = sessions.filter((s) => !s.current).length;

  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex items-center gap-3">
        <span className="text-[12.5px] font-semibold text-muted">
          {sessions.length === 1
            ? "1 active session"
            : `${sessions.length} active sessions`}
          {others > 0 && ` · ${others} on other devices`}
        </span>
        <Button
          variant="destructive"
          size="sm"
          className="ml-auto"
          disabled={others === 0 || revokingOthers}
          onClick={() => void revokeOthers()}
        >
          {revokingOthers ? "Revoking…" : "Sign out other devices"}
        </Button>
      </div>

      <Table>
        <TableRow columns={COLUMNS} header>
          <span />
          <span>DEVICE</span>
          <span>IP ADDRESS</span>
          <span>LAST SEEN</span>
          <span>EXPIRES</span>
          <span className="text-right">ACTION</span>
        </TableRow>

        {sessions.length === 0 ? (
          <TableEmpty
            icon="shield"
            message="No active sessions on this workspace"
          />
        ) : (
          sessions.map((s) => (
            <TableRow key={s.id} columns={COLUMNS}>
              <TableCell>
                <span
                  className={cn(
                    "size-2 shrink-0 rounded-full",
                    s.current
                      ? "animate-pulse-dot bg-ok shadow-[0_0_8px_var(--ok)]"
                      : "bg-bd2",
                  )}
                />
              </TableCell>
              <TableCell
                className="text-[13px] font-bold text-txt2"
                title={s.userAgent}
              >
                {s.device}
              </TableCell>
              <TableCell mono className="text-muted">
                {s.ip}
              </TableCell>
              <TableCell className="text-[12px] text-muted">{s.when}</TableCell>
              <TableCell className="text-[12px] text-label">
                {s.expires || "—"}
              </TableCell>
              <TableCell align="end">
                {s.current ? (
                  <Pill tone="ok" size="sm">
                    This device
                  </Pill>
                ) : (
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={busyId === s.id}
                    onClick={() => void revoke(s)}
                  >
                    {busyId === s.id ? "Revoking…" : "Revoke"}
                  </Button>
                )}
              </TableCell>
            </TableRow>
          ))
        )}
      </Table>
    </div>
  );
}
