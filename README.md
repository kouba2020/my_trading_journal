# Trading Journal MVP

A first Streamlit MVP for a Tradervue-style trading journal.

## Features

- Upload broker executions CSV
- Clean executions
- Reconstruct round-trip trades using average-cost logic
- Show key metrics: net P&L, win rate, profit factor, expectancy, max drawdown
- Equity curve
- Daily P&L
- Reports by symbol, side, and entry hour
- Export reconstructed trades

## Expected CSV columns

Required:

- `Symbol`
- `Action` with values `Buy` or `Sell`
- `Fill qty`
- `Fill price`
- `Exec time`

Optional:

- `Account`
- `Total value`
- `Time placed`

## Run locally

```bash
cd trading_journal_mvp
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

## Notes

This version uses average-cost trade reconstruction. Later versions can add FIFO/LIFO modes, fees per execution, screenshots, setups, tags, MFE/MAE, and AI coaching.
