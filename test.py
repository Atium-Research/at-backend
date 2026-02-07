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
You are a quantitative researcher building a research notebook to evaluate
a trading signal. Your goal is to quickly construct the signal, run a
backtest, and show the results. Keep it practical — get to the backtest
as fast as possible.

Key rules:
- Lag signals by at least 1 day to avoid lookahead bias.
- Cross-section normalize (z-score) signals within each date.
- Handle missing values by dropping them.

Notebook structure:
1. Brief hypothesis
2. Data loading & signal construction
3. Portfolio backtest & performance summary
4. Cumulative return plot
"""

# ---------------------------------------------------------------------------
# Prompt building blocks — separated by concern
# ---------------------------------------------------------------------------

BACKTEST_EXAMPLE = """\
## Reference Example

Follow this pattern exactly. The ONLY thing you should change is the signal
construction section — adapt it for the requested trading signal. Everything
else (imports, data loading, alpha conversion, backtest, performance summary)
stays the same.

If you need to understand a function or schema not shown here, you can inspect
the at-data-tools or at-research-tools packages at runtime, but do NOT
exhaustively explore them.

```python
from at_research_tools.constraints import FullyInvested, LongOnly
from at_research_tools.backtester import run_backtest
from at_research_tools.returns import generate_returns_from_weights, generate_cumulative_returns_from_weights
import at_data_tools as adt
import datetime as dt
import polars as pl

# Define backtest parameters
start = dt.date(2022, 7, 29)
end = dt.date(2025, 12, 31)
target_active_risk = 0.05  # 5% tracking error target

# Set up constraints
constraints = [
    FullyInvested(),  # Weights sum to 1
    LongOnly()        # No short positions
]

# Load market data
universe = adt.load_universe(start, end)
returns = adt.load_stock_returns(start, end)
idio_vol = adt.load_idio_vol(start, end)
factor_loadings = adt.load_factor_loadings(start, end)
factor_covariances = adt.load_factor_covariances(start, end)
benchmark_weights = adt.load_benchmark_weights(start, end)

# Combine data
data = (
    universe
    .join(returns, on=['date', 'ticker'], how='left')
    .join(idio_vol, on=['date', 'ticker'], how='left')
)

# === SIGNAL CONSTRUCTION (adapt this for the requested signal) ===
signals = (
    data
    .sort('ticker', 'date')
    .with_columns(
        pl.col('return')
        .log1p()
        .rolling_sum(230)  # ~1 year momentum
        .shift(21)          # 1-month lag
        .over('ticker')
        .alias('momentum')
    )
)

# Filter for valid data
filtered = (
    signals
    .filter(
        pl.col('momentum').is_not_null(),
        pl.col('idio_vol').is_not_null()
    )
)

# Standardize scores and convert to alphas
scores = (
    filtered
    .with_columns(
        pl.col('momentum')
        .sub(pl.col('momentum').mean())
        .truediv(pl.col('momentum').std())
        .over('date')
        .alias('score')
    )
)

alphas = (
    scores
    .with_columns(
        pl.lit(0.05)
        .mul('idio_vol')
        .mul('score')
        .alias('alpha')
    )
)
# === END SIGNAL CONSTRUCTION ===

# Run backtest
weights = run_backtest(
    alphas=alphas,
    factor_loadings=factor_loadings,
    factor_covariances=factor_covariances,
    idio_vol=idio_vol,
    benchmark_weights=benchmark_weights,
    constraints=constraints,
    target_active_risk=target_active_risk
)

# Calculate portfolio returns
forward_returns = adt.load_stock_forward_returns(start, end)
portfolio_returns = generate_returns_from_weights(weights, forward_returns)
cumulative_returns = generate_cumulative_returns_from_weights(weights, forward_returns)

# Analyze performance
summary = (
    portfolio_returns
    .select(
        pl.col('forward_return').mean().mul(252).alias('mean_return'),
        pl.col('forward_return').std().mul(pl.lit(252).sqrt()).alias('volatility')
    )
    .with_columns(
        pl.col('mean_return').truediv('volatility').alias('sharpe')
    )
)
print(summary)
```
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

Your goal is to construct this signal, run a backtest, and show the results.

{BACKTEST_EXAMPLE}

{NOTEBOOK_FORMAT}

{git_section}

## Execution Plan

Work through these phases in order:

**Phase 1 — Setup**
Clone and set up the repository. Use the reference example above as your
template — do NOT exhaustively explore the packages.

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
    repo_name = "at-research-reversal-2"

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
