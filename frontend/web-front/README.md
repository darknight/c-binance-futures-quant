# web-front

Active React dashboard for the Binance Futures quant framework.

## Stack

- React 19
- TypeScript
- Vite
- antd
- Zustand
- ECharts

This frontend replaces the deprecated `../../legacy/react-front/` app. The maintained data path is FastAPI (`web_server/`) instead of the old OSS JSON snapshot flow.

## Configuration

Set the backend API base URL with `VITE_API_URL`:

```bash
VITE_API_URL=http://localhost:8888 npm run dev
```

For local development, start the backend first from the repository root:

```bash
uv run python run_web_server.py
```

## Commands

Install dependencies:

```bash
npm install
```

Run the dev server:

```bash
VITE_API_URL=http://localhost:8888 npm run dev
```

Build for production:

```bash
VITE_API_URL=http://localhost:8888 npm run build
```

Lint:

```bash
npm run lint
```

Preview a production build:

```bash
npm run preview
```

## API Usage

The dashboard expects the FastAPI backend to expose:

- `/get_dashboard_summary`
- `/get_profit_by_symbol`
- legacy-compatible position, income, status, and record endpoints used by existing components

The backend currently calls Binance `exchangeInfo` during startup. Local development therefore needs outbound access to `https://fapi.binance.com`, unless that startup path is mocked or made optional in a later phase.

## Legacy Frontend

`../../legacy/react-front/` is kept as reference only. Do not add new dashboard features there.
