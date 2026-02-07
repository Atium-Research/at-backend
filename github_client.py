"""
GitHub App integration for creating and managing repositories.
Handles authentication and repository operations for the atium-research organization.
"""
import os
from typing import Optional
from github import Github, Auth


class GitHubClient:
    """Client for GitHub API operations using GitHub App authentication."""

    def __init__(
        self,
        app_id: Optional[str] = None,
        private_key: Optional[str] = None,
        installation_id: Optional[str] = None,
    ):
        """
        Initialize GitHub client with App credentials.

        Args:
            app_id: GitHub App ID (defaults to GITHUB_APP_ID env var)
            private_key: GitHub App private key (defaults to GITHUB_PRIVATE_KEY env var)
            installation_id: Installation ID (defaults to GITHUB_INSTALLATION_ID env var)
        """
        self.app_id = app_id or os.getenv("GITHUB_APP_ID")
        self.private_key = private_key or os.getenv("GITHUB_PRIVATE_KEY")
        self.installation_id = installation_id or os.getenv("GITHUB_INSTALLATION_ID")

        if not all([self.app_id, self.private_key, self.installation_id]):
            raise ValueError(
                "Missing GitHub App credentials. Ensure GITHUB_APP_ID, "
                "GITHUB_PRIVATE_KEY, and GITHUB_INSTALLATION_ID are set."
            )

        # Create auth once - PyGithub handles token refresh automatically
        # AppInstallationAuth takes (app_auth, installation_id) as parameters
        app_auth = Auth.AppAuth(self.app_id, self.private_key)
        self._auth = Auth.AppInstallationAuth(app_auth, int(self.installation_id))
        self._github_client = Github(auth=self._auth)

    def _get_client(self) -> Github:
        """Get the GitHub client."""
        return self._github_client

    def create_repository(
        self,
        repo_name: str,
        description: str = "",
        private: bool = False,
        auto_init: bool = False,
    ) -> str:
        """
        Create a new repository in the atium-research organization.

        Args:
            repo_name: Name of the repository
            description: Repository description
            private: Whether the repository should be private
            auto_init: Whether to initialize with a README

        Returns:
            The repository URL (e.g., https://github.com/atium-research/repo-name)

        Raises:
            Exception: If repository creation fails
        """
        client = self._get_client()

        try:
            # Get the organization
            org = client.get_organization("atium-research")

            # Create the repository
            repo = org.create_repo(
                name=repo_name,
                description=description,
                private=private,
                auto_init=auto_init,
                has_issues=True,
                has_wiki=False,
                has_projects=False,
            )

            return repo.html_url

        except Exception as e:
            if "name already exists" in str(e).lower():
                raise ValueError(f"Repository 'atium-research/{repo_name}' already exists")
            raise Exception(f"Failed to create repository: {str(e)}")

    def repository_exists(self, repo_name: str) -> bool:
        """
        Check if a repository exists in the atium-research organization.

        Args:
            repo_name: Name of the repository

        Returns:
            True if the repository exists, False otherwise
        """
        client = self._get_client()

        try:
            org = client.get_organization("atium-research")
            org.get_repo(repo_name)
            return True
        except:
            return False

    def get_clone_url(self, repo_name: str) -> str:
        """
        Get the HTTPS clone URL for a repository.

        Args:
            repo_name: Name of the repository

        Returns:
            The HTTPS clone URL
        """
        return f"https://github.com/atium-research/{repo_name}.git"
