# Deploying to the always-on Mac (Phase 8)

Follow these steps once. Commands go in the Terminal app on the always-on Mac. Anything that asks for a password or code is yours to type; never paste it into a chat.

## 1. Mac settings

1. **Stay signed in after restarts:** System Settings → Users & Groups → *Automatically log in as* → your user.
   The schedule runs inside your login session. If FileVault is on, macOS won't auto-login; then sign in once after any restart.
2. **Never sleep, and restart after a power cut:** System Settings → Energy (or Battery → Options). Turn on *Prevent automatic sleeping when the display is off* and *Start up automatically after a power failure*. The same thing from Terminal:

   ```bash
   sudo pmset -a sleep 0 autorestart 1
   ```

## 2. Tools

```bash
xcode-select --install
```

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

- **GitHub CLI:** `brew install gh` if you have Homebrew, otherwise download it from cli.github.com.
- **Claude Code:** install it the same way you did on your main Mac.

## 3. Get the code and sign in

```bash
gh auth login
```

```bash
gh repo clone Stanliu23/trading-agent ~/trading-agent && cd ~/trading-agent && uv sync --python 3.12 --extra analyst
```

```bash
claude auth login
```

## 4. Your private settings (never in the repo)

1. Copy `config.local.yaml` from your main Mac into `~/trading-agent/` (AirDrop works). It holds your email addresses.
2. Add one line to it with the trial's start date, usually the day you finish this guide:

   ```yaml
   shadow_start: "2026-11-23"
   ```

3. Save the Gmail **app password** (the 16 lowercase letters) in this Mac's Keychain:

   ```bash
   cd ~/trading-agent && uv run tradeagent set-secret gmail_app_password
   uv run tradeagent set-secret alpaca_paper_key        # paper test: the PAPER key from alpaca.markets
   uv run tradeagent set-secret alpaca_paper_secret
   uv run tradeagent paper-check                        # shows the paper account; places nothing
   # strategy experiments (SPEC 2f): one more Alpaca paper account each, $1,000, with its own keys
   uv run tradeagent set-secret alpaca_exp_mom_key
   uv run tradeagent set-secret alpaca_exp_mom_secret
   uv run tradeagent set-secret alpaca_exp_lowv_key
   uv run tradeagent set-secret alpaca_exp_lowv_secret
   uv run tradeagent exp-check                          # shows both accounts, flags keys saved in the wrong slot; places nothing
   uv run tradeagent set-secret schwab_app_key          # Schwab app "Trade bot": Client ID
   uv run tradeagent set-secret schwab_app_secret       # Schwab app "Trade bot": Client Secret
   uv run tradeagent schwab-login                       # log in, tick your account, paste the 127.0.0.1 address within ~30 s
   ```

   Keychains are per Mac, so these are saved again here even though your main Mac has them.
   Before starting the schedule, check Alpaca still shows only the starting cash and no positions: the first
   scheduled run records that balance as the test's start, and the first orders go in at 08:00 ET on the next trading day.

## 5. Build local data and check everything

```bash
cd ~/trading-agent && uv run tradeagent init-db && uv run tradeagent backtest-setups && uv run tradeagent doctor
```

- **Expected result:** 0 failing.
- **Fine to leave as "still to do":** the Finnhub key (off), the always-on power settings if you skipped them, and the 15-minute schedule (the next step).

Optional preview, which writes files only and sends nothing:

```bash
uv run tradeagent run close --dry-run --start 2026-06-01
```

## 6. Turn on the 15-minute schedule

```bash
cd ~/trading-agent && mkdir -p logs && uv run tradeagent launchd-plist > ~/Library/LaunchAgents/com.tradeagent.tick.plist && launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.tradeagent.tick.plist
```

Check it's running (`doctor` should now show the schedule as OK):

```bash
uv run tradeagent doctor | grep schedule && tail -5 logs/tick.log
```

## Day to day

- **Get an update:**

  ```bash
  cd ~/trading-agent && git pull && uv sync --extra analyst
  ```

  The next 15-minute run picks it up.
- **Pause everything:**

  ```bash
  launchctl bootout gui/$(id -u)/com.tradeagent.tick
  ```

  Run the `bootstrap` line from step 6 to resume.
- **Errors** go to `logs/errors.log`, and every run is logged in the database. The daily digest's System line shows today's runs and errors.
- **If the Claude login expires,** emails still go out with template wording. Run `claude auth login` again.
