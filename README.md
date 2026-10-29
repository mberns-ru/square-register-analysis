# Databased: Square Register Sales Analytics

A browser dashboard that helps small food and beverage businesses understand their sales without needing a
statistics background. Upload the monthly CSV exports from a Square register and Databased turns them into
sales trends, item performance, refunds, expenses and profit, forecasts and seasonal patterns. An AI analyst
answers questions like *"Why was August slow?"* in plain language.

Built by **Advait Ashtikar, Madeline Berns and Andy Chen**.

![Overview](docs/screenshots/overview.png)

## Why

Small businesses fail at high rates, and owners rarely have the time or training to analyze their own sales
data. Tracking sales, expenses and profit in one place usually takes several tools. Square is widely used:
62% of U.S. food and beverage sellers with $500k+ in annual payment volume use a Square Register. So reading
Square's own exports directly means the owner has one source and no setup.

## Features

| Page | What it does |
| --- | --- |
| **Overview** | Net sales, transactions and estimated profit vs the prior period; a sales calendar with best and slowest days; rolling-average trend vs the same days last year; category mix, weekday and hourly patterns; dining option and payment method |
| **Items** | Every item with units, sales and estimated margin. Flags items that sell well but earn little. Cost % per category is editable |
| **Expenses** | AI-assisted capture: describe a purchase (*"6 gallons of milk and two bags of flour, about $140"*) or attach a receipt. Databased drafts the line items, reuses prices from past invoices and flags gaps. Nothing posts until you confirm. Each cost is tagged Estimated, Confirmed or Document-backed |
| **Refunds** | Amount, count and refund rate; reasons; when refunds happen; each refund linked to its original payment |
| **Forecast** | Next 14–90 days of net sales with a backtested error band, expected transactions by weekday and daypart for staffing, and an item prep list |
| **Seasonality** | Year-over-year monthly sales, a seasonal index, a weekday × hour heatmap and the daypart mix by month |
| **AI analyst** | Ask questions in plain language. Answers use only approved metric functions, and every answer shows the calls it made and the date range |
| **Reports** | Monthly profit and loss, CSV exports, a printable monthly report, and a data-quality summary |

<table>
<tr><td><img src="docs/screenshots/analyst.png" alt="AI analyst"></td><td><img src="docs/screenshots/expenses.png" alt="Expense capture"></td></tr>
<tr><td align="center">AI analyst</td><td align="center">AI-assisted expense capture</td></tr>
<tr><td><img src="docs/screenshots/items.png" alt="Items"></td><td><img src="docs/screenshots/forecast.png" alt="Forecast"></td></tr>
<tr><td align="center">Item performance</td><td align="center">Forecast</td></tr>
</table>

## Getting started

Requires Python 3.10+.

```bash
git clone https://github.com/mberns-ru/square-register-analysis.git
cd square-register-analysis
pip install -r requirements.txt
streamlit run app.py
```

The app opens at <http://localhost:8501>.

### Load your data

1. In the Square Dashboard, export **Transactions** and **Item sales** as CSV, one file per month.
2. Either open the **Data** panel in the app's sidebar and select every file (Ctrl/Cmd+A in the file dialog),
   or put them in these folders and they load automatically on start:

   ```
   data/transactions/transactions-2026-08-01-2026-09-01.csv
   data/items/items-2026-08-01-2026-09-01.csv
   ```

`data/` is git-ignored, so customer data never gets committed. Uploading the same month twice is safe because
duplicates are dropped.

### Optional: turn on Claude

Without an API key, the AI analyst uses a built-in rule-based planner and expense capture uses a text parser.
To have Claude plan the analyst's metric calls and read receipt photos, set an Anthropic API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# optional, defaults to claude-sonnet-5-5
export ANTHROPIC_MODEL=claude-sonnet-5-5
```

or add `ANTHROPIC_API_KEY = "sk-ant-..."` to `.streamlit/secrets.toml` (also git-ignored).

## How it works

### The data

Square exports two kinds of monthly CSV, linked by **Transaction ID**:

- **Transactions**: one row per payment or refund, with sales, tax, tip and fees.
- **Items**: one row per item sold.

Refunds point back to their original payment through **Payment ID**. Most transactions have no customer
attached, cash sales have no deposit, and item and category names aren't perfectly consistent, so the app
treats those fields as plain attributes.

### Ingestion

Upload → parse → normalize → load. Only the columns the app uses are kept, money strings like `-$3.00` are
parsed, voided transactions are excluded and duplicate payments are dropped. Rejected rows are counted on the
**Reports → Data quality** card rather than silently dropped.

### Analytics

- Daily aggregates are computed once per set of files and shared across pages.
- Rolling averages use a selectable window (3–90 days).
- Recurring expenses (monthly, weekly, yearly) are spread evenly across days; one-time costs land on their date.
  Profit = net sales − processing fees − allocated expenses.
- Refunds are netted against sales.
- **Forecast** blends two estimates: each weekday's median over the last 8 weeks scaled by a seasonal month
  index, and the same weekday last year scaled by recent year-over-year growth. The error band comes from
  backtesting on the most recent weeks.

### AI guardrails

The analyst can only read data through the named, read-only functions in [`core/metrics.py`](core/metrics.py)
(`metric_total`, `metric_by`, `compare_periods`, `top_items`, `item_movers`, `anomalies`,
`refunds_by_reason`, `best_worst_days`). It never writes free-form SQL or estimates figures, every answer
lists the calls and date range behind it, and each question is logged.

## Project structure

```
app.py              navigation, sidebar filters, data loading
core/
  theme.py          colors, CSS, Plotly template, card helpers
  data.py           CSV ingestion, cleaning, daily aggregates
  metrics.py        approved metric functions (the analyst's only data access)
  analyst.py        question → metric calls (Claude tool use or rule-based)
  expenses.py       expense book, allocation by day, purchase drafting
views/              one module per page
assets/             logo
docs/screenshots/   images used in this README
```

## Limitations

- Square exports have no cost data, so item margins use an estimated cost % per category (30% by default).
- Daily sales are noisy, so the forecast's typical daily miss is about 25%. It doesn't yet account for holidays,
  local events, weather or academic calendars.
- Expenses live in the browser session. Download them as CSV from the Expenses page and load them back next time.

## Roadmap

- Live Square API connection instead of CSV upload
- Demand forecasting with local events and weather
- Ingredient costing for real item-level margins
- Loss and waste detection from expected vs actual usage
- Multi-location and multi-business support
- Benchmarking against similar cafes

## Data

Developed with real sales data from Friends Cafe in New Brunswick, NJ (January 2023 – August 2026). That data is
not included in this repository.
