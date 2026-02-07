"""
Research Project Agent: Creates marimo notebooks for any research topic.
Repositories are created under the atium-research GitHub organization.

Run: uv run python test.py
"""
import asyncio
import sys
from pathlib import Path

from agent import AgentSession
from github_client import GitHubClient

# Load .env so child processes (agent bash commands) inherit these vars
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# ---------------------------------------------------------------------------
# System prompt: establishes deep quantitative research expertise
# ---------------------------------------------------------------------------

QUANT_RESEARCH_SYSTEM_PROMPT = """\
You are a senior quantitative researcher at a systematic equity fund.
You build rigorous, publication-quality research notebooks that evaluate
trading signals. You think like a skeptic: every signal is guilty until
proven innocent. Your research is reproducible, statistically grounded,
and always accounts for real-world trading frictions.

Core principles you follow:
- NEVER look ahead: always lag signals appropriately to avoid lookahead bias.
- ALWAYS cross-section normalize: z-score signals within each date before use.
- ALWAYS check data quality first: coverage, missing values, outliers.
- ALWAYS evaluate signal strength BEFORE running a backtest. IC analysis,
  quintile spreads, and decay analysis come first — they are cheaper and more
  informative than a full portfolio backtest.
- ALWAYS include out-of-sample or time-split validation to check for overfitting.
- ALWAYS consider transaction costs — a signal that requires 200% annual turnover
  is very different from one at 50%.
- Present results honestly. If a signal is weak, say so.

When constructing a research notebook you follow this structure:
1. Hypothesis & motivation — why should this signal predict returns?
2. Data loading & quality checks
3. Signal construction with clear documentation of every parameter choice
4. Signal properties (distribution, coverage, autocorrelation, turnover)
5. Predictive power analysis (IC, rank IC, quintile/decile analysis)
6. Signal decay analysis
7. Portfolio backtest with proper risk model
8. Performance attribution and robustness checks
9. Conclusions & limitations
"""

# ---------------------------------------------------------------------------
# Prompt building blocks — separated by concern
# ---------------------------------------------------------------------------

API_REFERENCE = """\
## Available Packages

### at-data-tools (import as adt) — Data Access Layer
Always use these dates for all data loading:
  start = datetime.date(2022, 7, 29)
  end = datetime.date(2025, 12, 31)

Functions (all take start_date, end_date as datetime.date objects, return polars DataFrames):
- load_stock_prices, load_stock_returns, load_etf_prices
- load_alphas(start, end, signal_names), load_signals(start, end, signal_names)
- load_betas, load_factor_loadings, load_factor_covariances
- load_idio_vol, load_benchmark_weights, load_universe
- load_calendar, load_stock_forward_returns
- Schema inspection: get_stock_prices_schema(), get_alphas_schema(), etc.

All data has 'date' and 'ticker' columns. Dates are datetime.date objects.
Use .join() on ['date', 'ticker'] to combine datasets.
Factor loadings have a 'factor' column. Factor covariances have 'factor_1', 'factor_2', 'covariance'.

### at-research-tools (import as art) — Backtesting & Portfolio Optimization
- art.run_backtest(alphas, factor_loadings, factor_covariances, idio_vol,
    benchmark_weights, constraints=[], target_active_risk=0.05)
  Returns portfolio weights DataFrame.
- Constraints: from at_research_tools.constraints import FullyInvested, LongOnly
- Returns: from at_research_tools.returns import generate_returns_from_weights,
    generate_cumulative_returns_from_weights

### Exploring the API (only when needed)
The reference above should be sufficient for most tasks. If you encounter
unexpected column names, missing fields, or need details not covered above,
you can inspect packages at runtime:
- python -c "import at_data_tools as adt; help(adt.<function_name>)"
- python -c "import at_data_tools as adt; print(adt.get_<dataset>_schema())"
Do NOT exhaustively explore every function — only look up what you actually need.
"""

SIGNAL_EVALUATION_FRAMEWORK = """\
## Signal Evaluation Framework

Follow these steps IN ORDER. Do not skip to backtesting before completing
the signal analysis — understanding signal properties first is essential.

### Step 1: Signal Construction
- Define the signal clearly. Document every parameter (lookback window, lag, etc.)
- Apply proper lag to avoid lookahead bias (minimum 1 day; typically 21 days
  for monthly rebalancing signals)
- Cross-section normalize: for each date, z-score the signal (subtract mean,
  divide by std) so that it is comparable across time
- Handle missing values explicitly (document how many are dropped and why)

### Step 2: Signal Properties
- **Coverage**: What fraction of the universe has a valid signal on each date?
  Plot coverage over time. Flag if coverage < 70%.
- **Distribution**: Show histogram of signal values (after z-scoring). Check for
  extreme outliers. Consider winsorizing at +/- 3 sigma.
- **Autocorrelation**: Compute rank autocorrelation of the signal (correlation of
  today's cross-section ranks with tomorrow's). High autocorrelation (>0.95)
  means low turnover but potentially stale information.
- **Sector exposure**: Check whether the signal is just a disguised sector bet
  by computing the average signal per sector. If so, consider sector-neutralizing.

### Step 3: Predictive Power — Information Coefficient (IC) Analysis
This is the MOST IMPORTANT step. Compute:
- **IC (Information Coefficient)**: Pearson correlation between the signal and
  subsequent forward returns, computed cross-sectionally each period. Report
  the time-series mean, std, and t-statistic of the IC series.
- **Rank IC**: Spearman rank correlation (more robust to outliers). Same stats.
- **IC_IR**: Mean IC / Std IC. This is the signal-level information ratio.
  Values > 0.05 are interesting; > 0.1 is strong.
- **Rolling IC**: Plot 12-month rolling average IC to check stability over time.
  A signal that only works in one regime is less valuable.
- **IC by sector**: Does the signal predict returns uniformly across sectors
  or only in certain industries?

### Step 4: Quintile Analysis
- Each period, sort stocks into 5 groups (quintiles) by signal strength
- Compute the average forward return for each quintile
- Key metrics:
  * **Long-short spread**: Mean return of Q5 (highest signal) minus Q1 (lowest)
  * **Monotonicity**: Returns should increase (or decrease) smoothly from Q1→Q5.
    A non-monotonic pattern suggests the signal is noisy.
  * **Hit rate**: What fraction of periods does the long-short spread have the
    correct sign?
- Visualize: bar chart of average returns by quintile, cumulative long-short
  return over time

### Step 5: Signal Decay
- Compute IC at different forward horizons (1 day, 5 days, 21 days, 63 days)
- Plot IC vs. horizon. This shows how quickly the signal's predictive power fades.
- A signal with fast decay needs frequent rebalancing (higher costs).
- A signal that peaks at a longer horizon may be more capacity-friendly.

### Step 6: Portfolio Backtest
Only AFTER the above analysis confirms the signal has merit:
- Use art.run_backtest() with proper risk model inputs
- Constraints: FullyInvested() and LongOnly() unless otherwise specified
- Reasonable target_active_risk (0.02-0.05 range)
- Calculate:
  * Annualized return, annualized volatility
  * Sharpe ratio (return / volatility)
  * Information ratio (active return / tracking error)
  * Maximum drawdown (peak-to-trough)
  * Turnover (average daily weight changes, annualized)
  * Cumulative return plot vs. benchmark
- Split into in-sample (first 2/3) and out-of-sample (last 1/3) periods.
  Report metrics for both.

### Step 7: Robustness Checks
- **Parameter sensitivity**: Vary key signal parameters (e.g., lookback ±50%)
  and show that results don't collapse. A signal that only works for exactly
  one parameter setting is likely overfit.
- **Subperiod analysis**: Report metrics for each calendar year separately.
- **Drawdown analysis**: Identify the worst drawdown period and discuss what
  market conditions drove it.
"""

NOTEBOOK_FORMAT = """\
## Marimo Notebook Format

Create the notebook as 'research.py' using marimo's app structure.

### Script Metadata (top of file)
```python
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "marimo",
#   "numpy",
#   "polars",
#   "altair",
#   "great_tables",
#   "scipy",
#   "at-data-tools>=0.1.8",
#   "at-research-tools>=0.1.2",
# ]
# ///
```

### Environment Setup Cell (required first)
```python
@app.cell
def setup_environment():
    import os
    from pathlib import Path
    env_file = Path.home() / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, value = line.strip().split('=', 1)
                    os.environ[key] = value
    return
```

### Cell Rules
- Use @app.cell decorator for each section
- The LAST EXPRESSION in a cell is displayed (not a return statement)
- `return var,` assigns a variable for other cells but does NOT display it
- For display-only cells: make the expression the last line (no return)
- For data cells: use `return var1, var2,` syntax
- Use `def _(...)` for display-only cells, named functions for data cells
- Use marimo UI elements (mo.ui.slider, mo.ui.dropdown) for interactive parameters
- Use mo.vstack(), mo.hstack(), mo.md() for layout
- Ensure all variable names are unique across cells (marimo requirement)

### Visualizations
- Use Altair for all charts
- Include: cumulative return plots, IC time series, quintile bar charts,
  drawdown plots, signal distribution histograms, coverage over time
- Label axes clearly, include titles
"""

GIT_WORKFLOW = """\
## Repository Setup & Publishing

1. Create directory '{repo_name}', cd into it
2. git init && git config user.name "Research Agent" && git config user.email "agent@example.com"
3. Create the marimo notebook (research.py)
4. Validate: uvx marimo check research.py
5. Test execution: uvx marimo export html research.py -o test.html --sandbox
   - Check for MarimoExceptionRaisedError in output
   - Fix any errors, re-validate
6. Export PDF: uvx marimo export pdf research.py -o research.pdf --sandbox
7. Clean up: rm -f test.html
8. git add . && git commit -m "Add research project: {topic}"
9. git remote add origin {clone_url}
10. git branch -M main && git push -u origin main
"""


class ResearchProjectAgent:
    def __init__(self):
        self.agent = AgentSession(system_prompt=QUANT_RESEARCH_SYSTEM_PROMPT)
        self.github = GitHubClient()

    async def create_research_project(self, topic: str, repo_name: str = None) -> None:
        """
        Create a complete research project evaluating a trading signal
        in a marimo notebook.

        Args:
            topic: The trading signal / research topic to evaluate
            repo_name: Optional custom repository name (auto-generated if not provided)
        """

        if repo_name is None:
            repo_name = self._sanitize_repo_name(topic)

        # Create GitHub repository
        print(f"Creating GitHub repository: atium-research/{repo_name}")
        try:
            if self.github.repository_exists(repo_name):
                print(f"Repository already exists, using existing repo")
                repo_url = f"https://github.com/atium-research/{repo_name}"
            else:
                repo_url = self.github.create_repository(
                    repo_name=repo_name,
                    description=f"Research project: {topic}",
                    private=False,
                    auto_init=False,
                )
                print(f"Repository created: {repo_url}")
        except Exception as e:
            print(f"Failed to create repository: {e}")
            return

        clone_url = self.github.get_clone_url(repo_name)

        # Build the research prompt from composable sections
        prompt = self._build_research_prompt(
            topic=topic,
            repo_name=repo_name,
            repo_url=repo_url,
            clone_url=clone_url,
        )

        self.agent.send_message(prompt)

        async for msg in self.agent.get_output_stream():
            if msg is None:
                break
            await self._handle_message(msg)

    def _build_research_prompt(
        self, topic: str, repo_name: str, repo_url: str, clone_url: str
    ) -> str:
        """Compose the research prompt from structured building blocks."""

        git_section = GIT_WORKFLOW.format(
            repo_name=repo_name,
            topic=topic,
            clone_url=clone_url,
        )

        return f"""\
# Research Task: {topic}

Evaluate the following trading signal with full quantitative rigor:

**SIGNAL:** {topic}

Your goal is to determine whether this signal has genuine predictive power
for future stock returns, quantify its strength, and assess its practical
viability as a trading strategy.

{API_REFERENCE}

{SIGNAL_EVALUATION_FRAMEWORK}

{NOTEBOOK_FORMAT}

{git_section}

## Execution Plan

Work through these phases in order:

**Phase 1 — Setup**
Clone and set up the repository. The API Reference above already documents
the available functions, their signatures, and column schemas — use it as
your primary reference. Do NOT exhaustively explore the packages upfront.
Only inspect a function or schema at runtime if you hit a specific issue
(e.g., unexpected column names or unclear return types).

**Phase 2 — Build the Notebook**
Create the marimo notebook following the Signal Evaluation Framework above.
Every section of the framework should be a clearly labeled section in the
notebook with explanatory markdown cells.

**Phase 3 — Validate & Fix**
Run marimo check and export to HTML. Fix any errors. Iterate until clean.

**Phase 4 — Export & Publish**
Export to PDF, commit, and push to GitHub.

The repository has been created at: {repo_url}
Environment variables for at-data-tools (AWS credentials, etc.) are already
configured in the current process — do not check, create, or modify any .env files.

Begin now. Start with Phase 1."""

    async def _handle_message(self, msg: dict) -> None:
        """Handle and display different message types."""
        msg_type = msg.get("type")

        if msg_type == "assistant_message":
            content = msg['content']
            print(f"\nClaude: {content}")

        elif msg_type == "tool_use":
            tool_name = msg['toolName']
            tool_input = msg['toolInput']

            print(f"\nTool: {tool_name}")

            if tool_name == "Bash":
                cmd = tool_input.get('command', '')
                print(f"   $ {cmd}")
            elif tool_name in ["Write", "Edit"]:
                path = tool_input.get('path', '')
                print(f"   File: {path}")
            elif tool_name == "Read":
                path = tool_input.get('path', '')
                print(f"   Reading: {path}")

        elif msg_type == "result":
            if msg['success']:
                print(f"\nCompleted successfully")
                if msg.get('cost'):
                    print(f"   Cost: ${msg['cost']:.4f}")
                if msg.get('duration_ms'):
                    print(f"   Duration: {msg['duration_ms']}ms")
            else:
                print(f"\nTask failed")

        elif msg_type == "error":
            print(f"\nError: {msg['error']}")

    def _sanitize_repo_name(self, topic: str) -> str:
        """Convert research topic to a valid directory name."""
        name = topic.lower()[:50]
        name = ''.join(c if c.isalnum() else '-' for c in name)
        name = '-'.join(filter(None, name.split('-')))
        return name or "research-project"


async def main() -> None:
    topic = "Short Term Reversal"
    repo_name = "at-research-reversal-1"

    print(f"\n{'='*60}")
    print(f"Creating Research Project")
    print(f"{'='*60}")
    print(f"Topic: {topic}")
    if repo_name:
        print(f"Repository: {repo_name}")
    print(f"GitHub org: atium-research (https://github.com/atium-research/{repo_name})")
    print(f"{'='*60}\n")

    agent = ResearchProjectAgent()
    await agent.create_research_project(topic, repo_name)

    print(f"\n{'='*60}")
    print(f"Research project creation complete!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
