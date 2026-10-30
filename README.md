### ErpZeroZA

Run South African small-business books on ERPNext, and migrate off Xero.

A Frappe app for ERPNext v16. It sets ERPNext up as a simple SA bookkeeping system (VAT201,
SA tax invoices, a Books workspace, bank statement import and rules) and moves a company's
Xero history across, with a reconciliation that proves the numbers match to the cent, and has an
optional **showcase mode** for public demos.

**Barb the Bookkeeper**, an AI bookkeeper that drafts the VAT201 and explains the books, is a
separate, licensed add-on app from [2nth.ai](https://barb.2nth.app). ErpZeroZA works fully
without her; when she is installed she uses ErpZeroZA's VAT set-up, and showcase mode gives demo
guests a daily allowance of questions through her `barb_questions_left` hook.

Documentation: <https://doc.erpafrica.org/erpzeroza-docs.html>, and in `docs/`:
[VAT and the VAT201](docs/vat.md) · [Demo guests](docs/showcase.md).

### Modules

| Module | Holds |
|---|---|
| ZA Books | Chart of accounts template, VAT tax templates and VAT201, print formats, Books workspace, roles, management reports |
| Xero Migration | Xero connection (OAuth + CSV fallback), staging DocTypes, mapping review, loader, Migration Reconciliation report, archive |
| Bank | Statement import presets for SA banks, Bank Rule |
| Payroll Bridge | SimplePay accounting export → monthly payroll journal |
| Payments | Pay-now links (Paystack, Yoco) and settlement posting |
| Showcase | Showcase Settings, Showcase Lead: email sign-up for Demo Guests, guard rails, nightly clean-up |

Built so far: the lean profile (`lean.py`), SA VAT (`za_books/`) and showcase mode (`showcase/`). The other modules are placeholders for the work in the plan.

Demo data (the fictitious *Karoo Kettle Co.* and its fake Xero export) will be a separate
command, never run on install, so client sites stay clean.

### Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app erpnext --branch version-16   # if not already on the bench
bench get-app https://github.com/Starktail/csf_za --branch version-16
bench get-app https://github.com/erpafrica/erpzero-za --branch develop
bench --site <site> install-app erpnext csf_za erpzero_za
```

On Frappe Cloud: add this repo to the bench group (v16), deploy, then install the app on the site.

### Branches

- `develop`: day-to-day work; CI runs on every push.
- `version-16`: release branch the benches track, cut from `develop` with tags `v16.x.y`.

### Rules for this repo

- Everything a site needs is in the app: fixtures, patches and install hooks. Nothing is
  configured by hand on a site.
- No edits to `frappe` or `erpnext` core. Change behaviour through hooks and overrides only.
- Every pip dependency is declared in `pyproject.toml`; Frappe Cloud builds from it.

### Contributing

This app uses `pre-commit` for code formatting and linting:

```bash
cd apps/erpzero_za
pre-commit install
```

### CI

- CI: installs ERPNext, csf_za and this app on a fresh v16 site and runs the tests on every push to `develop`.
- Linters: Frappe Semgrep rules and pip-audit on every pull request.

### License

MIT
