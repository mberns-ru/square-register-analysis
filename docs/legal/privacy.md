# Privacy Policy

**Effective October 29, 2026**

Databased ("we", "us") is a student-built sales analytics dashboard for small food and beverage businesses that use
Square. It's available at [squareanalysis.streamlit.app](https://squareanalysis.streamlit.app). This policy explains
what information the app handles, why, and the choices you have.

## The short version

- We collect only what's needed to give you an account and run the dashboard.
- Sales files you upload are processed in the app's memory and **not saved to our database**.
- We don't sell your information, show ads, or use tracking or advertising cookies.
- Each business's data is walled off from every other business's.

## What we collect

**Account information.** When you create an account we store your name, email address and business name. If you
sign up with an email and password, the password is stored only as a secure hash by our authentication provider
(Supabase); we never see it.

**Business membership.** We record which business you belong to and your role (owner, manager or viewer).

**Sales files you upload.** When you upload Square transaction and item exports, the app keeps only the columns it
needs to calculate sales, refunds, fees and item performance (amounts, dates and times, item names and categories,
dining option, staff name, refund reason, and Square's own transaction, payment, customer and deposit IDs). It
**discards** columns such as customer names, card brands and card digits as it reads each file. The processed data
is held in the app's server memory while you use it and is cleared when the app restarts. It is not currently
written to our database.

**Expenses and analyst questions.** Expenses you enter and questions you ask the AI analyst are kept for your
browser session only. You can download your expenses as a CSV file to keep them.

**Technical information.** Our hosting and authentication providers keep standard logs (such as IP address, browser
type and the time of each sign-in) to operate and secure their services.

## How we use it

We use your information to create and secure your account, show you your business's dashboard, keep each business's
data separate, and fix problems. We don't use it for advertising and we don't sell or rent it to anyone.

## AI features

If the app's operator has turned on the Claude-powered analyst, your question and the summary numbers the app
calculates to answer it are sent to Anthropic to generate the answer. If you upload a receipt to the expense
assistant, that image or PDF is sent to Anthropic to read it. Without that feature turned on, the analyst and the
expense assistant run entirely inside the app.

## Who processes your data

We rely on these providers, each under its own privacy terms:

- **Supabase**: database and sign-in (hosted in the United States, AWS us-east-1)
- **Streamlit Community Cloud** (Snowflake): hosts the app
- **Anthropic**: the optional AI features described above

We may also disclose information if the law requires it.

## Cookies

The app only uses the cookies Streamlit needs to work securely. We don't use analytics or advertising cookies. Streamlit Community Cloud may
collect its own usage statistics as described in its policies.

## Security

Connections to the app are encrypted (HTTPS). In the database, row-level security means each signed-in user can read
only the businesses they belong to, and people who aren't signed in can't read anything. No method of storing or
sending data is perfectly secure, so please use a strong password and keep your login to yourself.

## How long we keep it

We keep your account information while your account exists. If you ask us to delete your account, we delete your
profile, your business memberships and any businesses you own (with their data). Uploaded sales data isn't stored, so
there's nothing to delete there. Provider logs are kept according to those providers' retention policies.

## Your choices and rights

You can ask us to access, correct or delete your information. Depending on where you live, you may have additional
rights under laws such as the GDPR or CCPA. To make a request, open an issue at
[github.com/mberns-ru/square-register-analysis/issues](https://github.com/mberns-ru/square-register-analysis/issues)
titled "Privacy request". Please don't put personal details in the issue itself; we'll follow up privately.

## Children

Databased is a business tool for adults. It isn't directed to anyone under 18, and we don't knowingly collect
information from children.

## Changes to this policy

If we change this policy, for example when we start saving uploaded sales data to the database, we'll update it
here and change the effective date above. Significant changes will also be noted in the app.

## Contact

Questions about this policy: open an issue at
[github.com/mberns-ru/square-register-analysis/issues](https://github.com/mberns-ru/square-register-analysis/issues).
