# AI X Growth Automation Bot

Automated daily AI news, real-data spec card, and screenshot bot built for X (Twitter) growth.

## What It Does
- **Twice-daily GitHub Actions schedule** (`~9:00 AM` & `~4:00 PM` US Pacific with natural jitter)
- **100% Real Data Sources**:
  - **Hugging Face Trending Models & Daily Papers** (parameters, 30d downloads, likes, license, arXiv IDs, GitHub repo links)
  - **GitHub Trending AI Repositories** (stars, forks, language, license, creation/push activity)
  - **Live Model Specs & Pricing Comparisons** via OpenRouter public catalog (context windows, max output tokens, input/output `$/1M` pricing, modality)
- **Zero AI-Generated Images**:
  - Renders crisp **dark-mode HTML-to-PNG spec cards** (`output/spec_card.png`) populated strictly from fetched API data
  - Captures **real Playwright webpage screenshots** (`output/live_shot.png`) of the source Hugging Face / GitHub / leaderboard page
- **Organic X Growth Strategy**:
  - Sharp AI builder/analyst voice via **Google Gemini** (`gemini-2.5-flash`) with zero hashtag spam or hype emojis
  - Mix of **280-char single posts** and **2–3 tweet mini-threads**
  - Posts screenshots natively on the main tweet and puts the source URL in an **auto-reply** to avoid X external-link reach penalties
  - Deduplicates topics over a 30-day cooldown in `data/history.json` and balances sources across runs

## Setup Guide

### 1. Get Your API Keys
1. **Google Gemini API Key** (free tier available):
   - Go to [Google AI Studio](https://aistudio.google.com/apikey) and create an API key.
2. **X (Twitter) Developer Portal Keys**:
   - Go to [developer.x.com](https://developer.x.com/) and open your Project & App.
   - Under **User authentication settings**, enable **OAuth 1.0a** with **Read and write** permissions.
   - Under **Keys and tokens**, generate/copy:
     - **API Key** (`X_API_KEY`)
     - **API Key Secret** (`X_API_SECRET`)
     - **Access Token** (`X_ACCESS_TOKEN`)
     - **Access Token Secret** (`X_ACCESS_TOKEN_SECRET`)
   - *(Note: Ensure your X Developer account has active posting credits/access enabled in the X Developer Console.)*

### 2. Add GitHub Repository Secrets
In your GitHub repo (`Settings -> Secrets and variables -> Actions -> New repository secret`), add:
- `GEMINI_API_KEY`
- `X_API_KEY`
- `X_API_SECRET`
- `X_ACCESS_TOKEN`
- `X_ACCESS_TOKEN_SECRET`

*(Optional)* Under **Variables** (`Actions -> Variables`), add `X_HANDLE` (without `@`) if you want your handle watermarked cleanly at the bottom-right of spec cards.

### 3. Test With a Dry Run First
1. Open the **Actions** tab in your GitHub repository.
2. Select **Daily AI X Growth Bot** -> **Run workflow**.
3. Keep **`dry_run: true`** and click **Run workflow**.
4. Inspect the workflow logs (exact tweets + char counts) and download the `post-screenshots-*` artifact to preview `spec_card.png` and `live_shot.png`.
5. Once satisfied, run again with `dry_run: false` or let the twice-daily schedule take over automatically!

## Local Development
```bash
uv sync
uv run playwright install chromium
cp .env.example .env
# Edit .env with your GEMINI_API_KEY (keep DRY_RUN=true to preview safely)
uv run python -m src.main
```

Run tests:
```bash
uv run pytest
```
