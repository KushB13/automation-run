# AI X Growth Automation Bot

100% free (`$0/month`) automated AI news, real-data spec card, and screenshot bot built for organic X (Twitter) follower growth.

## What It Does
- **Twice-daily GitHub Actions schedule** (`~9:00 AM` & `~4:00 PM` US Pacific with natural random jitter)
- **5 Real-Time AI Data Sources (`$0`, no paid news APIs)**:
  - **Breaking AI News & Lab Announcements (`ai_news`)**: OpenAI News, Google AI Blog, Hugging Face Blog, Simon Willison AI, TechCrunch AI, VentureBeat AI, MIT Tech Review AI, and Google News AI breaking feed
  - **Hugging Face Trending Models & Daily Papers** (parameters, 30d downloads, likes, license, arXiv IDs, GitHub repo links)
  - **GitHub Trending AI Repositories** (stars, forks, language, license, creation/push activity)
  - **Live Model Specs & Pricing Comparisons** via OpenRouter public catalog (context windows, max output tokens, input/output `$/1M` pricing, modality)
- **Feed-Style Matching (`data/style_examples.json`)**:
  - Uses an **Adaptive AI Curator + Builder** voice steered by example X posts in `data/style_examples.json`
  - Paste 2–10 favorite AI posts from your own X feed into `data/style_examples.json` anytime to tune the exact hook cadence and formatting while keeping content 100% original and grounded
- **Smart Visuals (Zero AI-Generated Images)**:
  - Renders crisp **dark-mode HTML-to-PNG News / Spec Cards** (`output/spec_card.png`) populated strictly from fetched data
  - Captures **real Playwright webpage screenshots** (`output/live_shot.png`) and automatically skips cookie-walled, CAPTCHA-gated, or blocked pages
- **100% Free Tier Friendly (`$0/month`)**:
  - **X API v2 Free Tier**: Write-only OAuth 1.0a (`<= 500` posts/month; 2 runs/day stays well below the limit with zero paid `$200/mo` read endpoints)
  - **Google AI Studio Free Tier**: Compact `gemini-2.5-flash` prompts (`<= 280` chars/tweet) with an automatic zero-cost deterministic fallback if unconfigured or rate-limited
  - **GitHub Actions Free Tier**: `uv` and Playwright browser caching keep scheduled runs fast and minimal

## Setup Guide

### 1. Get Your Free API Keys
1. **Google Gemini API Key** (Free tier, no billing required):
   - Go to [Google AI Studio](https://aistudio.google.com/apikey) and create an API key.
2. **X (Twitter) Developer Portal Keys** (Free tier):
   - Go to [developer.x.com](https://developer.x.com/) and open your Project & App.
   - Under **User authentication settings**, enable **OAuth 1.0a** with **Read and write** permissions.
   - Under **Keys and tokens**, generate/copy:
     - **API Key** (`X_API_KEY`)
     - **API Key Secret** (`X_API_SECRET`)
     - **Access Token** (`X_ACCESS_TOKEN`)
     - **Access Token Secret** (`X_ACCESS_TOKEN_SECRET`)

### 2. Add GitHub Repository Secrets & Handle
In your GitHub repo (`Settings -> Secrets and variables -> Actions -> New repository secret`), add:
- `GEMINI_API_KEY`
- `X_API_KEY`
- `X_API_SECRET`
- `X_ACCESS_TOKEN`
- `X_ACCESS_TOKEN_SECRET`

*(Optional)* Under **Variables** (`Actions -> Variables`), add `X_HANDLE` (without `@`) to watermark your handle cleanly at the bottom-right of rendered cards.

### 3. Customize Your Feed Style (Optional)
Edit [`data/style_examples.json`](data/style_examples.json) and paste 2–10 favorite AI posts from your X feed under `"examples"`. The bot adapts its pacing, hooks, and structure to match your feed while writing strictly about fresh live updates.

### 4. Test With a Dry Run First
1. Open the **Actions** tab in your GitHub repository.
2. Select **Daily AI X Growth Bot** -> **Run workflow**.
3. Keep **`dry_run: true`** and click **Run workflow**.
4. Inspect the workflow logs (exact tweets + char counts) and download the `post-screenshots-*` artifact to preview `spec_card.png` and `live_shot.png`.
5. Once satisfied, run again with `dry_run: false` or let the twice-daily schedule post automatically!

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
