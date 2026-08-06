// Handoff § 7 › API keys — "API keys table with reveal/copy".
//
// SECURITY (CLAUDE.md › "Never log or return a secret"): the data layer only
// ever carries the visible PREFIX of a key. Rows render masked by default and
// the remainder is only materialised behind an explicit Reveal.
//
// STILL A STUB. The hub has no API-key resource at all — no list, no create, no
// revoke (verified against `/api/openapi.json`). These rows are the design's
// fixtures and the panel says so, because rendering them unlabelled would be
// presenting invented keys as real ones.

import { useEffect, useState } from "react";
import {
  Button,
  Icon,
  Notice,
  Table,
  TableCell,
  TableEmpty,
  TableRow,
  toast,
} from "@/components/ui";
import { getApiKeys, type ApiKey } from "@/data";
import { useUi } from "@/store/ui";

const COLUMNS =
  "minmax(0,1.2fr) minmax(0,1.4fr) minmax(0,1.2fr) 110px 100px 170px";

/**
 * The prototype's demo remainder. The real `GET /api/auth/api-keys` never
 * returns it — a revealed key will come from a dedicated reveal endpoint.
 */
const DEMO_REMAINDER = "a91Xc4Rt7Qm2";

const mask = (prefix: string) => `${prefix}_••••••••••`;
const full = (prefix: string) => `${prefix}_${DEMO_REMAINDER}`;

export function ApiKeysPanel() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [revealed, setRevealed] = useState<string | null>(null);
  const setModal = useUi((s) => s.setModal);

  useEffect(() => {
    let live = true;
    void getApiKeys().then((rows) => live && setKeys(rows));
    return () => {
      live = false;
    };
  }, []);

  const copy = (key: ApiKey) => {
    void navigator.clipboard?.writeText(full(key.prefix));
    toast("Key copied");
  };

  return (
    <div className="flex flex-col gap-3.5">
      <Notice tone="warn">
        Preview data. The hub does not issue API keys yet, so none of these are
        real and Create key is not wired to anything. Use a signed-in session
        for machine access until the endpoint lands.
      </Notice>

      <div className="flex items-center gap-3">
        <span className="text-[12.5px] font-semibold text-muted">
          {keys.length} active keys · rotate every 90 days
        </span>
        <Button
          variant="primary"
          className="ml-auto"
          icon={<Icon name="plus" size={15} strokeWidth={2.6} />}
          onClick={() => setModal("apiKey")}
        >
          Create key
        </Button>
      </div>

      <Table>
        {keys.length === 0 ? (
          <TableEmpty
            icon="key"
            message="No API keys yet — create one for headless CI runners"
            action={
              <Button variant="primary" onClick={() => setModal("apiKey")}>
                Create key
              </Button>
            }
          />
        ) : (
          keys.map((k) => {
            const isRevealed = revealed === k.id;
            return (
              <TableRow key={k.id} columns={COLUMNS}>
                <TableCell className="text-[13px] font-bold text-txt2">
                  {k.name}
                </TableCell>
                <TableCell mono className="tracking-[.02em] text-ps-text">
                  {isRevealed ? full(k.prefix) : mask(k.prefix)}
                </TableCell>
                <TableCell className="text-[12px] text-muted">
                  {k.scope}
                </TableCell>
                <TableCell className="text-[12px] text-muted">
                  {k.used}
                </TableCell>
                <TableCell className="text-[12px] text-label">
                  {k.created}
                </TableCell>
                <TableCell align="end" className="gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setRevealed(isRevealed ? null : k.id)}
                    icon={
                      <Icon
                        name={isRevealed ? "eyeOff" : "eye"}
                        size={13}
                        strokeWidth={2.2}
                      />
                    }
                  >
                    {isRevealed ? "Hide" : "Reveal"}
                  </Button>
                  <Button
                    variant="tinted"
                    size="sm"
                    onClick={() => copy(k)}
                    icon={<Icon name="copy" size={13} strokeWidth={2.2} />}
                  >
                    Copy
                  </Button>
                </TableCell>
              </TableRow>
            );
          })
        )}
      </Table>
    </div>
  );
}
