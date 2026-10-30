# VAT in ErpZeroZA

How ErpZeroZA records South African VAT and prepares the VAT201 return, with the official source for
each rule. Written for the accountant or bookkeeper who signs off the set-up.

## Sources

Everything here follows these official documents. Where this guide and a source disagree, the source
wins. Tell us and we will fix the guide.

| Source | Used for |
|---|---|
| **Value-Added Tax Act 89 of 1991**: s7 (imposition, 15%), s11 (zero-rated supplies), s12 (exempt supplies), s20 (tax invoices), s21 (credit and debit notes) | What each tax template means, and what the invoice layouts must show |
| **SARS VAT 404 – Guide for Vendors**, Issue 15 (17 December 2024) | How supplies are classified; capital goods; imports |
| **SARS GEN-ELEC-04-G01 – Guide to completing the Value-Added Tax VAT201 Return**, revision 11 (effective 12 May 2025) | The VAT201 fields and how each is calculated |
| **Tax Administration Act 28 of 2011**, s29 | Keeping records for five years; why the Xero archive is kept in the system |

*Check the SARS website for a newer issue before relying on a version number here.*

## One VAT account, one template per VAT201 field

The company has a single VAT control account (`VAT`), as the standard South African chart and Xero
both have it. What decides where a transaction lands on the VAT201 is the **tax template** chosen on
the invoice. ErpZeroZA creates one template per field when a South African company is set up:

### Sales (output tax)

| Template | Rate | VAT201 field | Use it for |
|---|---|---|---|
| Standard rate 15% *(default)* | 15% | 1 (value incl. VAT) → 4 (VAT) | Ordinary taxable sales of goods and services |
| Capital goods sold 15% | 15% | 1A → 4A | Sale of the business's own capital goods or services |
| Zero-rated 0% | 0% | 2 | Zero-rated supplies other than exports, e.g. basic foodstuffs listed in s11 |
| Exports 0% | 0% | 2A | Goods exported, zero-rated under s11(1)(a) |
| Exempt | – | 3 | Exempt supplies and non-supplies under s12, e.g. residential rent |

### Purchases (input tax)

| Template | Rate | VAT201 field | Use it for |
|---|---|---|---|
| Standard rate 15% *(default)* | 15% | 15 | Goods and services bought locally, not capital |
| Capital goods 15% | 15% | 14 | Capital goods and services bought locally |
| Imports 15% | 15% | 15A | VAT paid to SARS on imported goods, not capital |
| Capital goods imported 15% | 15% | 14A | VAT paid on imported capital goods |
| No VAT | – | not on the return | Suppliers who are not VAT vendors, and costs with no VAT |

The templates are mapped to the VAT201 in **Value-added Tax Return Settings**, provided by the
open-source `csf_za` South African localisation, which ErpZeroZA builds on.

## Preparing the return

1. Open **Value-added Tax Return**, choose the company and the tax period dates, and save. The return
   is named after the company and the period's last month (CCYYMM), e.g. `Karoo Kettle Co-202610`.
2. Click **Get transactions for period**. Every invoice and journal that touched VAT in the period is
   listed with its VAT201 classification. Zero-rated, export and exempt sales are listed too, at
   their net value, even though they post nothing to the VAT account.
3. Classify anything left unclassified (usually journals), then submit. The return shows each
   VAT201 field and the VAT payable or refundable. Use those figures on eFiling.

The **🔍** button next to each field opens the transactions behind it.

## What ErpZeroZA fixes in csf_za's return

Three problems in the current `csf_za` version-16 release, fixed in ErpZeroZA and offered upstream:

- Zero-rated, export and exempt sales (fields 2, 2A and 3) were missing, because the return was built
  only from VAT account entries and these sales post none.
- Capital goods and zero-rated classifications (fields 1A, 2 and 2A) carried a trailing space that
  stopped the return from saving.
- Returns are named `{company}-{tax_period}`, but nothing set the tax period, so every return of a
  company got the same name. ErpZeroZA sets it from the period's last month.

Barb the Bookkeeper, the separate add-on from 2nth.ai, can prepare the draft return for you; a
person still checks and submits it.

Both are covered by `erpzero_za/tests/test_vat.py`, which posts one transaction per field and checks
every total on the return.
