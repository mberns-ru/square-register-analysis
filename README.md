# Databased — Square Register sales dashboard

A browser dashboard for small cafes that reads monthly Square exports (transactions + items) and turns them
into sales, item, expense, refund, forecast and seasonality views, plus a plain-language AI analyst.

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the **Data** panel in the sidebar and select every CSV in your `transactions/` and `items/` folders.
Alternatively drop them into `data/transactions/` and `data/items/` and they load automatically
(`data/` is git-ignored so customer data never gets committed).

Optional: set `ANTHROPIC_API_KEY` (environment variable or `.streamlit/secrets.toml`) so Claude plans the AI
analyst's metric calls and reads receipt photos. Without it, a built-in rule-based planner and text parser are used.
`ANTHROPIC_MODEL` overrides the model (default `claude-sonnet-5-5`).

## Views

| Page | What it shows |
| --- | --- |
| Overview | Net sales, transactions and profit vs the prior period, a sales calendar, rolling-average trend vs last year, category mix, weekday and hourly patterns, dining option and payment method |
| Items | Every item with units, sales and estimated margin; flags items that sell well but earn little (cost % per category is editable) |
| Expenses | AI-assisted capture: describe a purchase or attach a receipt, review the drafted lines, confirm before anything posts. Each cost is Estimated, Confirmed or Document-backed |
| Refunds | Amount, count and rate; reasons; each refund linked back to its original payment |
| Forecast | Next 14–90 days of net sales with a backtested error band, expected transactions by weekday × daypart, and an item prep list |
| Seasonality | Year-over-year months, seasonal index, weekday × hour heatmap, daypart mix |
| AI analyst | Ask questions in plain language. Answers come only from approved metric functions (`core/metrics.py`), and every answer lists its calls and date range |
| Reports | Monthly P&L, CSV exports, a printable monthly report, and a data-quality summary of rejected / duplicate / voided rows |

## Layout

```
app.py              navigation, sidebar filters, data loading
core/theme.py       colors, CSS, Plotly template, card helpers
core/data.py        CSV ingestion, cleaning, daily aggregates
core/metrics.py     approved metric functions (the analyst's only data access)
core/analyst.py     question -> metric calls (Claude tool use or rule-based)
core/expenses.py    expense book, allocation by day, purchase drafting
views/*.py          one module per page
```
