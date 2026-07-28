// Handoff § 7 › Sessions — "sessions table with revoke".

import { useEffect, useState } from "react";
import {
  Button,
  Pill,
  Table,
  TableCell,
  TableEmpty,
  TableRow,
  toast,
} from "@/components/ui";
import { getSessions, type Session } from "@/data";
import { cn } from "@/lib/cn";

const COLUMNS = "14px minmax(0,2fr) minmax(0,1fr) 130px 120px 110px";

export function SessionsPanel() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [revoked, setRevoked] = useState<string[]>([]);

  useEffect(() => {
    let live = true;
    void getSessions().then((rows) => live && setSessions(rows));
    return () => {
      live = false;
    };
  }, []);

  const revoke = (id: string) => {
    setRevoked((prev) => [...prev, id]);
    toast(
      "Session revoked",
      "That device has been signed out of EmeHub",
      "ok",
    );
  };

  const rows = sessions.filter((s) => !revoked.includes(s.id));

  return (
    <Table>
      {rows.length === 0 ? (
        <TableEmpty
          icon="shield"
          message="No active sessions on this workspace"
        />
      ) : (
        rows.map((s) => (
          <TableRow key={s.id} columns={COLUMNS}>
            <TableCell>
              <span
                className={cn(
                  "size-2 shrink-0 rounded-full",
                  s.current ? "animate-pulse-dot bg-ok" : "bg-bd2",
                )}
              />
            </TableCell>
            <TableCell className="text-[13px] font-bold text-txt2">
              {s.device}
            </TableCell>
            <TableCell className="text-[12px] text-txt4">{s.where}</TableCell>
            <TableCell mono className="text-muted">
              {s.ip}
            </TableCell>
            <TableCell className="text-[12px] text-muted">{s.when}</TableCell>
            <TableCell align="end">
              {s.current ? (
                <Pill tone="ok" size="sm">
                  This device
                </Pill>
              ) : (
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => revoke(s.id)}
                >
                  Revoke
                </Button>
              )}
            </TableCell>
          </TableRow>
        ))
      )}
    </Table>
  );
}
