import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
import os
import sys

import requests
from dateutil.relativedelta import relativedelta
from lxml import etree


class GitHubAPIError(Exception):
    """Custom exception for GitHub API errors"""

    pass


class CacheError(Exception):
    """Custom exception for cache handling errors"""

    pass


class GitHubStats:
    """Main class for fetching and processing GitHub statistics"""

    GRAPHQL_ENDPOINT = "https://api.github.com/graphql"
    CACHE_DIR = Path("cache")
    SVG_DIR = Path("assets")

    # Centralized GraphQL queries
    QUERIES = {
        "user": """
            query($login: String!){
                user(login: $login) {
                    id
                    createdAt
                }
            }
        """,
        "repos": """
            query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
                user(login: $login) {
                    repositories(first: 100, after: $cursor, ownerAffiliations: $owner_affiliation) {
                        totalCount
                        edges {
                            node {
                                ... on Repository {
                                    nameWithOwner
                                    stargazers {
                                        totalCount
                                    }
                                }
                            }
                        }
                        pageInfo {
                            endCursor
                            hasNextPage
                        }
                    }
                }
            }
        """,
        "repo_history": """
            query ($repo_name: String!, $owner: String!, $cursor: String) {
                repository(name: $repo_name, owner: $owner) {
                    defaultBranchRef {
                        target {
                            ... on Commit {
                                history(first: 100, after: $cursor) {
                                    totalCount
                                    edges {
                                        node {
                                            ... on Commit {
                                                author {
                                                    user {
                                                        id
                                                    }
                                                }
                                                deletions
                                                additions
                                            }
                                        }
                                    }
                                    pageInfo {
                                        endCursor
                                        hasNextPage
                                    }
                                }
                            }
                        }
                    }
                }
            }
        """,
        "loc_query": """
            query ($owner_affiliation: [RepositoryAffiliation], $login: String!, $cursor: String) {
                user(login: $login) {
                    repositories(first: 60, after: $cursor, ownerAffiliations: $owner_affiliation) {
                        edges {
                            node {
                                ... on Repository {
                                    nameWithOwner
                                    defaultBranchRef {
                                        target {
                                            ... on Commit {
                                                history {
                                                    totalCount
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        pageInfo {
                            endCursor
                            hasNextPage
                        }
                    }
                }
            }
        """,
    }

    def __init__(self, username: str, access_token: str, birthday: datetime):
        self.username = username
        self.access_token = access_token
        self.birthday = birthday
        self.user_id = None
        self.cache_file = self.CACHE_DIR / f"{sha256(username.encode()).hexdigest()}.json"
        self.headers = {"authorization": f"token {access_token}"}
        self.CACHE_DIR.mkdir(exist_ok=True)
        self.SVG_DIR.mkdir(exist_ok=True)

    def initialize(self):
        """Initialize user data and cache"""
        self.user_id = self.get_user_id()

    def get_user_id(self) -> str:
        """Get GitHub user ID"""
        query = self.QUERIES["user"]
        variables = {"login": self.username}
        data = self.simple_request(query, variables)
        return data["data"]["user"]["id"]

    def simple_request(self, query: str, variables: dict) -> dict:
        """Make GraphQL request with error handling"""
        try:
            response = requests.post(
                self.GRAPHQL_ENDPOINT,
                json={"query": query, "variables": variables},
                headers=self.headers,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise GitHubAPIError(f"Request failed: {str(e)}") from e

    def calculate_age(self) -> str:
        """Calculate age since birthday"""
        diff = relativedelta(datetime.today(), self.birthday)
        return (
            f"{diff.years} year{'s' if diff.years != 1 else ''}, "
            f"{diff.months} month{'s' if diff.months != 1 else ''}, "
            f"{diff.days} day{'s' if diff.days != 1 else ''}"
            f"{' 🎂' if (diff.months == 0 and diff.days == 0) else ''}"
        )

    def get_repos(self, owner_affiliation: list, count_type: str) -> int:
        """Get repository count or star count with pagination"""
        total = 0
        cursor = None
        has_next_page = True

        while has_next_page:
            variables = {
                "owner_affiliation": owner_affiliation,
                "login": self.username,
                "cursor": cursor,
            }
            data = self.simple_request(self.QUERIES["repos"], variables)
            repos = data["data"]["user"]["repositories"]

            if count_type == "repos":
                return repos["totalCount"]
            elif count_type == "stars":
                total += sum(
                    edge["node"]["stargazers"]["totalCount"] for edge in repos["edges"]
                )

            page_info = repos["pageInfo"]
            has_next_page = page_info["hasNextPage"]
            cursor = page_info["endCursor"]

        return total

    def get_loc_data(self, owner_affiliation: list) -> list:
        """Get lines of code data with caching"""
        # Get all repository edges
        edges = []
        cursor = None
        has_next_page = True

        while has_next_page:
            variables = {
                "owner_affiliation": owner_affiliation,
                "login": self.username,
                "cursor": cursor,
            }
            data = self.simple_request(self.QUERIES["loc_query"], variables)
            repos = data["data"]["user"]["repositories"]
            edges.extend(repos["edges"])
            page_info = repos["pageInfo"]
            has_next_page = page_info["hasNextPage"]
            cursor = page_info["endCursor"]

        # Process cache
        return self.process_cache(edges)

    def process_cache(self, edges: list) -> list:
        """Process cache and compute LOC totals"""
        # Load existing cache
        try:
            with open(self.cache_file, "r") as f:
                cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            cache = {}

        loc_add = 0
        loc_del = 0
        cached = True

        # Process each repository
        for edge in edges:
            repo = edge["node"]
            repo_name = repo["nameWithOwner"]
            repo_hash = sha256(repo_name.encode()).hexdigest()

            # Get current commit count
            try:
                current_commits = repo["defaultBranchRef"]["target"]["history"][
                    "totalCount"
                ]
            except TypeError:
                current_commits = 0  # Empty repository

            # Check if cache needs update
            if repo_hash not in cache or cache[repo_hash]["commits"] != current_commits:
                cached = False
                if current_commits > 0:
                    owner, name = repo_name.split("/")
                    additions, deletions, _ = self.calculate_repo_loc(owner, name)
                else:
                    additions, deletions = 0, 0

                cache[repo_hash] = {
                    "name": repo_name,
                    "commits": current_commits,
                    "additions": additions,
                    "deletions": deletions,
                }

            # Add to totals
            loc_add += cache[repo_hash]["additions"]
            loc_del += cache[repo_hash]["deletions"]

        # Save updated cache
        try:
            with open(self.cache_file, "w") as f:
                json.dump(cache, f, indent=2)
        except IOError as e:
            raise CacheError(f"Failed to write cache: {str(e)}") from e

        return [loc_add, loc_del, loc_add - loc_del, cached]

    def calculate_repo_loc(self, owner: str, repo_name: str) -> tuple:
        """Calculate LOC for a single repository"""
        additions = 0
        deletions = 0
        commit_count = 0
        cursor = None
        has_next = True

        while has_next:
            variables = {"owner": owner, "repo_name": repo_name, "cursor": cursor}
            data = self.simple_request(self.QUERIES["repo_history"], variables)

            # Handle empty repositories
            if data["data"]["repository"]["defaultBranchRef"] is None:
                break

            history = data["data"]["repository"]["defaultBranchRef"]["target"]["history"]

            # Process commits
            for edge in history["edges"]:
                commit = edge["node"]
                if (
                    commit["author"]["user"]
                    and commit["author"]["user"]["id"] == self.user_id
                ):
                    commit_count += 1
                    additions += commit["additions"]
                    deletions += commit["deletions"]

            # Handle pagination
            page_info = history["pageInfo"]
            has_next = page_info["hasNextPage"]
            cursor = page_info["endCursor"]

        return additions, deletions, commit_count

    def get_commit_count(self) -> int:
        """Get total commit count from cache"""
        try:
            with open(self.cache_file, "r") as f:
                cache = json.load(f)
            return sum(repo["commits"] for repo in cache.values())
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return 0

    def update_svg(
        self,
        svg_name: str,
        age: str,
        commits: int,
        stars: int,
        repos: int,
        loc_data: list,
    ):
        """Update SVG file with new statistics"""
        svg_path = self.SVG_DIR / svg_name

        try:
            tree = etree.parse(svg_path)
            root = tree.getroot()

            # Update elements
            self.update_svg_element(root, "commit_data", commits, 22)
            self.update_svg_element(root, "star_data", stars, 14)
            self.update_svg_element(root, "repo_data", repos, 6)
            self.update_svg_element(root, "loc_data", loc_data[2], 9)
            self.update_svg_element(root, "loc_add", loc_data[0])
            self.update_svg_element(root, "loc_del", loc_data[1], 7)

            # Write back to file
            tree.write(svg_path, encoding="utf-8", xml_declaration=True)
        except (IOError, etree.ParseError) as e:
            raise CacheError(f"SVG update failed: {str(e)}") from e

    def update_svg_element(self, root, element_id: str, value: int, dots_length: int = 0):
        """Update single SVG element with value and dots"""
        # Format numeric values
        if isinstance(value, int):
            value_str = f"{value:,}"
        else:
            value_str = str(value)

        # Update value element
        value_element = root.find(f".//*[@id='{element_id}']")
        if value_element is not None:
            value_element.text = value_str

        # Update dots element if needed
        if dots_length > 0:
            dots_id = f"{element_id}_dots"
            dots_element = root.find(f".//*[@id='{dots_id}']")
            if dots_element is not None:
                num_dots = max(0, dots_length - len(value_str))
                dots_element.text = self.generate_dots(num_dots)

    def generate_dots(self, count: int) -> str:
        """Generate dot string for justification"""
        if count <= 2:
            return {0: "", 1: " ", 2: ". "}.get(count, "")
        return " " + ("." * count) + " "


def main():
    """Main execution function"""
    try:
        # Load configuration from environment
        username = os.environ["USER_NAME"]
        access_token = os.environ["GH_TOKEN"]
        birthday = datetime(2005, 7, 7)

        # Initialize stats processor
        stats = GitHubStats(username, access_token, birthday)
        stats.initialize()

        # Fetch statistics
        age = stats.calculate_age()
        loc_data = stats.get_loc_data(["OWNER"])
        commits = stats.get_commit_count()
        stars = stats.get_repos(["OWNER"], "stars")
        repos = stats.get_repos(["OWNER"], "repos")

        # Update SVG
        stats.update_svg("dark_mode.svg", age, commits, stars, repos, loc_data[:3])

    except KeyError as e:
        print(f"Missing environment variable: {str(e)}", file=sys.stderr)
        sys.exit(1)
    except (GitHubAPIError, CacheError) as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
