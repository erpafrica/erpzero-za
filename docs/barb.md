# Barb the Bookkeeper

Barb is an AI bookkeeper inside ERPNext. Ask her for this period's VAT201, who owes you money, or why
a figure is what it is. She looks it up with your permissions, shows her working with links to the
documents behind each figure, and leaves drafts for a person to check and submit.

Her panel and tools are in this app (`erpzero_za/barb/`). Her reasoning is a service from 2nth.ai at
`https://barb.2nth.app`, switched on per site with a key.

## Switching her on

1. Get a Barb key for the site from 2nth.ai.
2. **Barb Settings**: tick **Enabled**, Barb URL `https://barb.2nth.app`, paste the key, save.
3. Reload the desk: **Ask Barb** appears at the bottom right of every page.

## What she can and can't do

| She can | She cannot |
|---|---|
| Look up invoices, payments, journals, customers, suppliers, items, accounts and VAT returns | Submit, cancel or delete anything |
| Run the trial balance, P&L, balance sheet, cash flow, general ledger, registers, gross profit, age analyses | Pay, send email or file with SARS |
| Prepare or refresh a draft VAT201 for a period (`vat_return`) | Reach users, roles, settings or anything outside the books |
| Read the document open on screen | See anything the person asking can't |

The tools are in `erpzero_za/barb/tools.py`. Each runs as the signed-in user through ERPNext's own
permission checks, limited to the books doctypes and reports listed there.

## How a question is answered

1. The panel calls `erpzero_za.barb.api.ask`, which records a **Barb Log** and queues a background job.
2. The job sends the conversation to Barb's service. She replies with an answer, or with tools to run.
3. The site runs those tools as the user and sends back only the results; repeat (at most 10 steps).
4. The answer reaches the panel over realtime, and the log records tools, model, steps and tokens.

Barb's service holds no password to the site and keeps nothing between questions.

## Barb Log

One entry per question: who asked, the open document, the tools run, the answer, the model and the
tokens. Users read their own entries; Accounts Managers and System Managers read all.

## Limits

Barb is not a registered tax practitioner. On a judgement call she explains the rule, cites the
source (see [vat.md](vat.md)) and suggests confirming with the accountant. Demo guests get a daily
question allowance ([showcase.md](showcase.md)).
