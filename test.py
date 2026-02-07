"""
Research Project Agent: Creates marimo notebooks for any research topic.
Repositories are created under the atium-research GitHub organization.

Run: uv run python test.py
"""
import asyncio
import sys
from agent import AgentSession
from github_client import GitHubClient

class ResearchProjectAgent:
    def __init__(self):
        self.agent = AgentSession()
        self.github = GitHubClient()
    
    async def create_research_project(self, topic: str, repo_name: str = None) -> None:
        """
        Create a complete research project in a marimo notebook.

        Args:
            topic: The research topic/question to explore
            repo_name: Optional custom repository name (auto-generated if not provided)
        """

        # Auto-generate repo name from topic if not provided
        if repo_name is None:
            repo_name = self._sanitize_repo_name(topic)

        # Create GitHub repository first
        print(f"🔧 Creating GitHub repository: atium-research/{repo_name}")
        try:
            if self.github.repository_exists(repo_name):
                print(f"⚠️  Repository already exists, using existing repo")
                repo_url = f"https://github.com/atium-research/{repo_name}"
            else:
                repo_url = self.github.create_repository(
                    repo_name=repo_name,
                    description=f"Research project: {topic}",
                    private=False,
                    auto_init=False,
                )
                print(f"✅ Repository created: {repo_url}")
        except Exception as e:
            print(f"❌ Failed to create repository: {e}")
            return

        clone_url = self.github.get_clone_url(repo_name)

        prompt = f"""Create a complete research project for the following topic as a marimo notebook:

TOPIC: {topic}

Complete these steps in order:

1. SETUP REPOSITORY
   - Create directory: '{repo_name}'
   - Change into that directory
   - Run: git init
   - Run: git config user.name "Research Agent" && git config user.email "agent@example.com"

2. CREATE MARIMO NOTEBOOK
   - Create a file called 'research.py' as a marimo notebook
   - At the VERY TOP of the file, include inline script metadata (PEP 723) specifying ALL dependencies:
     ```python
     # /// script
     # requires-python = ">=3.11"
     # dependencies = [
     #   "marimo",
     #   "numpy",
     #   "polars",
     #   "altair",
     #   "great_tables",
     #   # ... add any other packages needed
     # ]
     # ///
     ```
   - Structure the notebook with these sections:
     * Title and introduction explaining the research question
     * Data loading/generation section
     * Exploratory data analysis with visualizations
     * Main analysis/modeling section
     * Results and interpretation
     * Conclusions
   - Use marimo's @app.cell decorator for each section
   - Include markdown cells (using mo.md()) for explanations
   - Make it interactive where appropriate using marimo UI elements
   - Write high-quality, well-commented code

3. EXPORT TO PDF
   - Run: uvx marimo export pdf research.py -o research.pdf
   - Note: uvx will automatically install dependencies from the script metadata

4. FIX ANY ERRORS
   - If any command fails, diagnose the issue
   - Update the script metadata if dependencies are missing
   - Retry failed steps
   - Verify all files were created successfully

5. COMMIT AND PUSH TO GITHUB
   - Run: git add .
   - Run: git commit -m "Add research project: {topic}"
   - Run: git remote add origin {clone_url}
   - Run: git branch -M main
   - Run: git push -u origin main

IMPORTANT NOTES:
- Verify each step completes before moving to next
- If errors occur, attempt to fix them automatically
- Include actual data analysis code, not placeholders
- Make the notebook publication-ready
- Use uvx to run marimo commands - it handles dependency isolation automatically
- Never install dependencies manually - declare them in the script metadata
- The GitHub repository has already been created at: {repo_url}
- At the end, confirm the repository is accessible at: {repo_url}

Begin now and work through each step systematically."""

        self.agent.send_message(prompt)
        
        # Stream and display output
        async for msg in self.agent.get_output_stream():
            if msg is None:
                break
            
            await self._handle_message(msg)
    
    async def _handle_message(self, msg: dict) -> None:
        """Handle and display different message types."""
        msg_type = msg.get("type")
        
        if msg_type == "assistant_message":
            content = msg['content']
            print(f"\n🤖 Claude: {content}")
        
        elif msg_type == "tool_use":
            tool_name = msg['toolName']
            tool_input = msg['toolInput']
            
            print(f"\n🔧 Tool: {tool_name}")
            
            # Display relevant parts of input based on tool
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
                print(f"\n✅ Completed successfully")
                if msg.get('cost'):
                    print(f"   Cost: ${msg['cost']:.4f}")
                if msg.get('duration_ms'):
                    print(f"   Duration: {msg['duration_ms']}ms")
            else:
                print(f"\n❌ Task failed")
        
        elif msg_type == "error":
            print(f"\n⚠️  Error: {msg['error']}")
    
    def _sanitize_repo_name(self, topic: str) -> str:
        """Convert research topic to a valid directory name."""
        # Take first 50 chars, lowercase, replace spaces/special chars with hyphens
        name = topic.lower()[:50]
        name = ''.join(c if c.isalnum() else '-' for c in name)
        name = '-'.join(filter(None, name.split('-')))  # Remove consecutive hyphens
        return name or "research-project"


async def main() -> None:
    topic = "Linear regression analysis"
    repo_name = "linear-regression-demo"
    
    print(f"\n{'='*60}")
    print(f"🔬 Creating Research Project")
    print(f"{'='*60}")
    print(f"Topic: {topic}")
    if repo_name:
        print(f"Repository: {repo_name}")
    print(f"GitHub org: atium-research (https://github.com/atium-research/{repo_name})")
    print(f"{'='*60}\n")
    
    agent = ResearchProjectAgent()
    await agent.create_research_project(topic, repo_name)
    
    print(f"\n{'='*60}")
    print(f"✨ Research project creation complete!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())