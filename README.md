# weight-tracker

Live body-weight trend chart, auto-updated daily via GitHub Actions from the Liftosaur MCP API.

- `fetch_weights.py` — pulls weight history from `https://www.liftosaur.com/mcp` (Bearer auth)
- `chart.py` — generates `chart.png` (seaborn style, dense-window trends, 1 lb/week target line)
- `.github/workflows/update.yml` — daily 02:30 UTC + manual dispatch
- Served via GitHub Pages

Setup: repo secret `LIFTOSAUR_TOKEN` = Liftosaur MCP API key (`lftsk_...`).
