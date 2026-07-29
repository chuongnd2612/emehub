# Example — project-bootstrap

## Input (what the user provides)

> "Index this repo for QA. It's our customer portal at `./portal`. We already have a
> Playwright project under `./portal/e2e`."

## What the skill does

1. Reads `portal/package.json` → detects React 18 + Vite frontend, .NET 8 API backend.
2. Reads `portal/e2e/playwright.config.ts` → Playwright 1.44, baseURL `http://localhost:5173`,
   HTML reporter, trace `on-first-retry`.
3. Scans `portal/e2e/pages/` → finds `LoginPage`, `DashboardPage`, `InvoiceListPage`.
4. Detects locator strategy: `getByTestId` used ~80% of the time, `getByRole` for buttons.
5. Reads `docs/domain.md` → extracts entities (Customer, Invoice, Payment) and roles (Admin, Agent, Viewer).

## Expected Output (excerpt of `knowledge.md`)

```md
## Automation Framework
- Tool: Playwright 1.44 (TypeScript)
- Existing Test Structure: portal/e2e/{pages,fixtures,tests}
- Config Files: portal/e2e/playwright.config.ts

## Locator Strategy
Priority: 1) data-testid  2) getByRole  3) CSS
Examples discovered:
page.getByTestId('invoice-row')
page.getByRole('button', { name: 'Pay now' })

## Existing Page Objects
| Page Object   | Purpose             | Key Methods                  | Used By              |
|---------------|---------------------|------------------------------|----------------------|
| LoginPage     | Auth entry          | login(user, pass)            | most specs           |
| InvoiceListPage | Browse invoices   | openInvoice(id), filterBy()  | invoice.spec.ts      |
```

And a synchronized `knowledge.json` with `"framework": "React", "automation": "Playwright",
"page_objects": [{ "name": "LoginPage", ... }]`.

## Note
`data-testid` was chosen as top priority **because the code already uses it**, not by default.
The skill records evidence, never invents conventions.
