from datetime import datetime
from hashlib import sha256
from json import JSONDecodeError, dump, load
from os import environ
from pathlib import Path
from sys import exit, stderr
from typing import Any, Optional, Union

from dateutil.relativedelta import relativedelta
from lxml.etree import ParseError
from lxml.etree import _Element as lxml_elem
from lxml.etree import _ElementTree as lxml_tree
from lxml.etree import parse as lxml_parse
from requests import RequestException, Response, post


class GitHubAPIError(Exception):
    """
    Custom exception for GitHub API errors.
    """

    pass


class CacheError(Exception):
    """
    Custom exception for cache handling errors.
    """

    pass


class StatProcessor:
    """
    Main class for fetching and processing GitHub statistics.
    """

    API_ENDPOINT: str = "https://api.github.com/graphql"
    CACHE_DIR = Path("cache")
    SVG_DIR = Path("assets")

    DOTS_LENGTHS: dict[str, int] = {
        "age_data_dots": 57,
        "star_data_dots": 58,
        "repo_data_dots": 58,
        "commit_data_dots": 56,
        "loc_data_dots": 50,
    }

    # Centralized GraphQL queries
    QUERIES: dict[str, str] = {
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

    def __init__(self, access_token: str, username: str, birthday: datetime) -> None:
        """
        Initialize all necessary data.
        """

        self.CACHE_DIR.mkdir(exist_ok=True)
        self.SVG_DIR.mkdir(exist_ok=True)

        self.access_token = access_token
        self.username = username
        self.birthday = birthday

        self.headers: dict[str, str] = {"authorization": f"token {access_token}"}
        self.user_id = self._get_user_id()

        self.cache_file: Path = (
            self.CACHE_DIR / f"{sha256(username.encode()).hexdigest()}.json"
        )

        self.stars = 0
        self.repos = 0
        self.commits = 0
        self.loc_total = 0
        self.loc_add = 0
        self.loc_del = 0

    def _get_user_id(self) -> str:
        """
        Fetch self.username's Github user ID.
        """

        query: str = self.QUERIES["user"]
        variables: dict[str, str] = {"login": self.username}
        data: dict = self._send_request(query, variables)

        return data["data"]["user"]["id"]

    def _calculate_age(self) -> str:
        """
        Calculate time since self.birthday.
        """

        diff = relativedelta(datetime.today(), self.birthday)
        return (
            f"{'🎂 ' if (diff.months == 0 and diff.days == 0) else ''}"
            f"{diff.years} year{'s' if diff.years != 1 else ''}, "
            f"{diff.months} month{'s' if diff.months != 1 else ''}, "
            f"{diff.days} day{'s' if diff.days != 1 else ''}"
        )

    def _send_request(self, query: str, variables: dict[str, str]) -> dict[str, Any]:
        """
        Make a GraphQL request and raise exceptions if necessary.
        """

        try:
            response: Response = post(
                self.API_ENDPOINT,
                json={"query": query, "variables": variables},
                headers=self.headers,
                timeout=10,
            )

            response.raise_for_status()
            return response.json()
        except RequestException as e:
            raise GitHubAPIError(f"Request failed: {str(e)}") from e

    def get_repos_or_stars(self, owner_affiliation: list[str], count_type: str) -> None:
        """
        Get repository count or total star count with pagination.
        """

        total = 0
        cursor: Optional[str] = None
        has_next_page = True

        while has_next_page:
            variables: dict[str, str] = {
                "owner_affiliation": owner_affiliation,
                "login": self.username,
                "cursor": cursor,
            }

            data = self._send_request(self.QUERIES["repos"], variables)
            repos = data["data"]["user"]["repositories"]

            if count_type == "repos":
                self.repos = repos["totalCount"]
                return
            elif count_type == "stars":
                total += sum(
                    edge["node"]["stargazers"]["totalCount"] for edge in repos["edges"]
                )

            page_info = repos["pageInfo"]
            has_next_page = page_info["hasNextPage"]
            cursor = page_info["endCursor"]

        self.stars = total

    def get_loc_data(self, owner_affiliation: list[str]) -> None:
        """
        Get lines of code data with caching.
        """

        edges: list[Any] = []
        cursor: Optional[str] = None
        has_next_page = True

        while has_next_page:
            variables: dict[str, str] = {
                "owner_affiliation": owner_affiliation,
                "login": self.username,
                "cursor": cursor,
            }

            data = self._send_request(self.QUERIES["loc_query"], variables)
            repos = data["data"]["user"]["repositories"]

            edges.extend(repos["edges"])

            page_info = repos["pageInfo"]
            has_next_page = page_info["hasNextPage"]
            cursor = page_info["endCursor"]

        # Process cache and save data
        self.loc_total, self.loc_add, self.loc_del = self._process_cache(edges)

    def _process_cache(self, edges: list[dict[str, Any]]) -> tuple[int, int, int]:
        """
        Process cache and compute LOC totals.
        """

        # Load existing cache
        try:
            with open(self.cache_file, "r") as f:
                cache: dict[str, dict[str, Union[int, str]]] = load(f)
        except (FileNotFoundError, JSONDecodeError):
            cache: dict[str, dict[str, Union[int, str]]] = {}

        loc_add = 0
        loc_del = 0

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
                # Empty repository
                current_commits = 0

            # Check if cache needs update
            if repo_hash not in cache or cache[repo_hash]["commits"] != current_commits:
                if current_commits > 0:
                    owner, name = repo_name.split("/")
                    additions, deletions = self._calculate_repo_loc(owner, name)
                else:
                    additions, deletions = 0, 0

                cache[repo_hash] = {
                    "name": repo_name,
                    "commits": current_commits,
                    "additions": additions,
                    "deletions": deletions,
                }

            # Update totals
            loc_add += cache[repo_hash]["additions"]
            loc_del += cache[repo_hash]["deletions"]

        # Save updated cache
        try:
            with open(self.cache_file, "w") as f:
                dump(cache, f, indent=4)
        except IOError as e:
            raise CacheError(f"Failed to write cache: {str(e)}") from e

        return (loc_add - loc_del, loc_add, loc_del)

    def _calculate_repo_loc(self, owner: str, repo_name: str) -> tuple[int, int]:
        """
        Calculate LOC for a single repository.
        """

        additions = 0
        deletions = 0
        cursor = None
        has_next = True

        while has_next:
            variables: dict[str, str] = {
                "owner": owner,
                "repo_name": repo_name,
                "cursor": cursor,
            }

            data = self._send_request(self.QUERIES["repo_history"], variables)

            # Handle empty repositories
            if data["data"]["repository"]["defaultBranchRef"] is None:
                break

            history = data["data"]["repository"]["defaultBranchRef"]["target"][
                "history"
            ]

            # Process commits
            for edge in history["edges"]:
                commit = edge["node"]
                if (
                    commit["author"]["user"]
                    and commit["author"]["user"]["id"] == self.user_id
                ):
                    additions += commit["additions"]
                    deletions += commit["deletions"]

            # Handle pagination
            page_info = history["pageInfo"]
            has_next = page_info["hasNextPage"]
            cursor = page_info["endCursor"]

        return additions, deletions

    def get_commit_count(self) -> None:
        """
        Get total commit count from cache.
        Depends on the cache being up-to-date,
        so this must be called *after* self.get_loc_data()!
        """

        try:
            with open(self.cache_file, "r") as f:
                cache: dict[str, dict[str, Union[int, str]]] = load(f)
            self.commits = sum(repo["commits"] for repo in cache.values())
        except (FileNotFoundError, JSONDecodeError, KeyError):
            self.commits = 0

    def update_svg(self, svg_name: str) -> None:
        """
        Update SVG file with the new data.
        """

        svg_path: Path = self.SVG_DIR / svg_name

        try:
            tree: lxml_tree = lxml_parse(svg_path)
            root: lxml_elem = tree.getroot()

            # Update elements
            self._update_svg_element(root, "age_data", self._calculate_age())
            self._update_svg_element(root, "star_data", self.stars)
            self._update_svg_element(root, "repo_data", self.repos)
            self._update_svg_element(root, "commit_data", self.commits)
            self._update_svg_element(root, "loc_total", self.loc_total)
            self._update_svg_element(root, "loc_add", self.loc_add)
            self._update_svg_element(root, "loc_del", self.loc_del)

            # Update file contents
            tree.write(svg_path, encoding="utf-8", xml_declaration=True)
        except (IOError, ParseError) as e:
            raise CacheError(f"SVG update failed: {str(e)}") from e

    def _update_svg_element(
        self, root: lxml_elem, element_id: str, value: Union[int, str]
    ) -> None:
        """
        Update single SVG element with value and dots.
        """

        # Format numeric values
        if isinstance(value, int):
            value_str = f"{value:,}"
        else:
            value_str = str(value)

        if element_id == "loc_add":
            value_str = f"+{value_str}"
        elif element_id == "loc_del":
            value_str = f"-{value_str}"

        # Update value element
        value_element = root.find(f".//*[@id='{element_id}']")
        if value_element is not None:
            value_element.text = value_str

        if element_id in ("loc_add", "loc_del"):
            return

        # Update dots element
        dots_id = f"{element_id}_dots"
        dots_element = root.find(f".//*[@id='{dots_id}']")

        if dots_element is not None:
            if element_id == "loc_total":
                num_dots = self.DOTS_LENGTHS[dots_id] - len(
                    f"{value_str} , {self.loc_add} , {self.loc_del}"
                )
            else:
                num_dots = self.DOTS_LENGTHS[dots_id] - len(value_str)

            dots_element.text = self._generate_dots(num_dots)

    def _generate_dots(self, dot_count: int, for_loc: bool = False) -> str:
        """
        Generate dots string for justification.
        """

        return f" {('.' * dot_count)} "


def main() -> None:
    """
    Fetch personal user data from Github's GraphQL4 API,
    and update the README's SVG image with the new data.
    """

    # try:
    # Define config
    access_token: str = environ["GH_TOKEN"]
    username: str = "jp-zuniga"
    birthday = datetime(2005, 7, 7)

    # Initialize stats processor
    stats = StatProcessor(username, access_token, birthday)

    # Fetch statistics
    stats.get_repos_or_stars(["OWNER"], "stars")
    stats.get_repos_or_stars(["OWNER"], "repos")
    stats.get_commit_count()
    stats.get_loc_data(["OWNER"])

    # Update SVG
    stats.update_svg("dark_mode.svg")

    # except KeyError as e:
    #     print(f"Missing environment variable: {str(e)}", file=stderr)
    #     exit(1)
    # except (GitHubAPIError, CacheError) as e:
    #     print(f"Error: {str(e)}", file=stderr)
    #     exit(1)


if __name__ == "__main__":
    main()
