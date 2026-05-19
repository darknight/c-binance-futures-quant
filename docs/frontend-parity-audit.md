# Frontend Parity Audit

Date: 2026-05-17

Goal: decide when `legacy/react-front/` can be removed after the dashboard rewrite to `frontend/web-front/`.

## Summary

`frontend/web-front/` now covers the functional surface that is reachable from the current legacy frontend entrypoint:

- `legacy/react-front/src/App.js`
- `legacy/react-front/src/work/constainers/MySwitch.js`
- `legacy/react-front/src/work/constainers/Show.js`

The current legacy router maps only `/` to `Show`. Other files under `legacy/react-front/src/work/components/`, `reducers/`, `tradingview_extra_js/`, and related constants are historical or currently unreachable from the active route.

Do not delete `legacy/react-front/` until the "Needs owner decision" items below are explicitly accepted as deprecated or migrated.

## Covered Active Dashboard Features

| Legacy feature | Legacy source | New implementation | Status |
| --- | --- | --- | --- |
| KPI cards: total balance, position value, 24h commission, total profit, system status | `Show.js` `getQuantData()` and render cards | `frontend/web-front/src/components/KpiCards.tsx`, `/get_dashboard_summary`, `/get_profit_by_symbol` | Covered |
| Balance chart | `Show.js` `getPositionRecord()` | `BalanceChart.tsx`, `/get_position_record` | Covered |
| Position value chart | `Show.js` `getPositionRecord()` | `PositionValueChart.tsx`, `/get_position_record` | Covered |
| Chart range selector: participant change, 1 day, 7 days, 1 month, all | `Show.js` `HISTORY_TABLE_TYPE_ARR` | `BalanceChart.tsx`, `ChartRangeType`, `getRangeTimestamps()` | Covered |
| Day income chart: bar/line modes | `Show.js` `DAY_INCOME_TABLE_TYPE_ARR` | `DayIncomeChart.tsx`, `/get_day_income` | Covered |
| Big loss table | `Show.js` `bigLossTradesRecordColumns` | `BigLossTable.tsx`, `/get_big_loss_trades` | Covered |
| Big loss direction and price-rate fields | `Show.js` maps `direction`, `priceRate` | `BigLossTable.tsx`, `records.py` response fields | Covered |
| Profit history table: yesterday/week/month/all profit, BNB, commission | `Show.js` `historyTableColumns` | `HistoryTable.tsx`, `/get_profit_by_symbol` | Covered |
| Empty big-loss warning | `Show.js` warning alert | `BigLossTable.tsx` empty-state alert | Covered |
| Backend-driven dashboard data instead of CDN JSON | `Show.js` reads `CDN_BASE_URL` JSON | `frontend/web-front/src/api/dashboard.ts` calls FastAPI | Covered by design |

## Not Actively Routed In Legacy Frontend

These files are present under `legacy/react-front/`, but the active route only renders `Show`. Static references show these modules are not part of the current running legacy dashboard.

| Area | Files | Current assessment |
| --- | --- | --- |
| API key onboarding / risk instructions | `RealConfigPage.js` | Not routed by `MySwitch`; also depends on removed user/server-info concepts. |
| Hotkey editor | `HotKeyModal.js`, `constants/hotKey.js` | Not routed by `MySwitch`; represents old trading UI configuration, not dashboard display. |
| Runtime strategy/config modal | `OtherConfigModal.js`, `reducers/otherConfig.js` | Not routed by `MySwitch`; backend still has config APIs, but no active legacy route exposes this UI. |
| System modal | `SystemModal.js`, `reducers/setting.js` | Not routed by `MySwitch`. |
| TradingView charting | `tradingview_extra_js/*`, `pubilc/charting_library/*` | Not routed by `MySwitch`; old implementation reads CDN test JSON and global `TradingView`. |
| Upload/image components | `AliyunOSSUpload.js`, `UserAliyunOSSUpload.js`, `ChatImgUpload.js`, `ImgModal.js` | Not routed; tied to removed chat/user/OSS-era code. |
| Chat state | `reducers/chat.js` | Chat/visitor/user system has already been removed from backend and docs. |
| Old public server constants | `constants/serverURL.js` | Contains hardcoded legacy public hosts and websocket URLs; not used by active dashboard route. |

## Needs Owner Decision Before Deletion

To claim "100% of `legacy/react-front/` directory capability" rather than "100% of active dashboard route", decide the following:

1. API key onboarding page:
   - Migrate to `frontend/web-front`, or confirm it is obsolete because keys now live in `.env` as `BINANCE_API_ARR`.

2. Hotkey and trading UI configuration:
   - Migrate to `frontend/web-front`, or confirm it is obsolete because `frontend/web-front` is a dashboard only.

3. Runtime `state_config_obj` editor:
   - Migrate to `frontend/web-front`, or keep configuration edited via `user_config.json`/backend API without UI.

4. TradingView charting library:
   - Migrate to `frontend/web-front`, or confirm it is not part of the dashboard replacement scope.

5. Legacy upload/chat/image components:
   - Confirm deletion because user/chat/visitor and Aliyun OSS features were removed.

6. Legacy `CDN_BASE_URL` dashboard mode:
   - Confirm deletion because `frontend/web-front` intentionally reads FastAPI APIs instead of generated CDN JSON.

## Recommended Deletion Criteria

Delete `legacy/react-front/` only after all of these are true:

- `frontend/web-front` production build passes.
- Backend tests pass.
- The active dashboard parity list above remains covered.
- Each "Needs owner decision" item is marked either "migrate" with an issue/task or "deprecated".
- Main docs no longer advertise `legacy/react-front/` as runnable.
- `.env.example`, `settings.py`, `.dockerignore`, and Docker docs are cleaned of `QUANT_CDN_URL` / `react-front` runtime references in the same deletion commit.

## Verification Commands

```bash
uv run pytest tests/ -q
cd frontend/web-front
VITE_API_URL=http://localhost:8888 npm run build
```
