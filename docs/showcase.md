# Demo guests (showcase mode)

Lets visitors try a demo company safely: they sign up with their email, get a one-time sign-in link,
and can open anything and draft documents, but not submit, cancel, delete or send. Off by default;
switch it on only on a demo site.

## Before switching it on

- A default outgoing **Email Account** (sign-in links and lead emails are sent through it).
- The demo company, with the data you want people to see.

## Showcase Settings

| Setting | Default | What it does |
|---|---|---|
| Enabled | off | Opens `erpzero_za.showcase.guests.signup` and creates the Demo Guest role; switches on email-link login |
| Demo company | | Guests get a User Permission for this company only |
| Barb questions per guest per day | 20 | Given to Barb (if installed) through the `barb_questions_left` hook |
| Days a guest account stays open | 7 | Signing up again re-opens it |
| Sign-in link valid for (minutes) | 60 | Each link works once |
| Send leads to | | Each sign-up is emailed here, reply-to the lead |
| Marketing consent text | | Shown on the form; consent is recorded only when ticked |

## The sign-up form

POST to `/api/method/erpzero_za.showcase.guests.signup` with `full_name`, `email`, `company_name`,
`consent` (0/1) and an empty `website` field (a honeypot). Five sign-ups an hour per IP address. The
answer is always the same, so the form can't be used to find out who has an account, and an
existing (non-guest) user's account is never touched.

## Guard rails

Guests hold Accounts User, Sales User and Purchase User (so every screen works) plus **Demo Guest**,
which blocks, on every doctype: submit, cancel, deleting anything but their own drafts, and outgoing
email (`showcase/guests.py`, wired in `hooks.py`). Administrator is never treated as a guest.

## Every night

`guests.nightly` (daily scheduler) deletes drafts and records guests created (VAT returns, invoices,
quotations, orders, journals, payments, customers, suppliers, items, addresses, contacts, to-dos,
files) and switches off guests whose period has ended. Each sign-up is kept as a **Showcase Lead**.
