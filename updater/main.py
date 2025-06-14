import datetime
import hashlib
import os

import requests
from dateutil import relativedelta
from lxml import etree

BIRTHDAY = datetime.datetime(2005, 7, 7)
USER_NAME = os.environ["USER_NAME"]
HEADERS = {"authorization": "token " + os.environ["GH_TOKEN"]}


def calculate_age(birthday: datetime) -> str:
    """
    Returns the length of time since 'birthday' as a formatted string.
    """

    diff = relativedelta(datetime.today(), birthday)
    return (
        f"{'🎂 ' if diff.months == 0 and diff.days == 0 else ''}"
        + f"{diff.years} years"
        + f"{f', {diff.months}' if diff.months != 0 else ''}{' month' + 's' if diff.months != 1 else ''}"
        + f"{f', {diff.days}' if diff.days != 0 else ''}{' month' + 's' if diff.days != 1 else ''}"
    )


def simple_request(func_name, query, variables):
    """
    Returns a request, or raises an Exception if the response does not succeed.
    """

    request = requests.post(
        "https://api.github.com/graphql",
        json={"query": query, "variables": variables},
        headers=HEADERS,
    )

    if request.status_code == 200:
        return request
    raise Exception(func_name, " has failed with a", request.status_code, request.text)


def graph_commits(start_date, end_date):
    """
    Finds a user's total commit count.
    """

    query = """
    query($start_date: DateTime!, $end_date: DateTime!, $login: String!) {
        user(login: $login) {
            contributionsCollection(from: $start_date, to: $end_date) {
                contributionCalendar {
                    totalContributions
                }
            }
        }
    }"""

    variables = {"start_date": start_date, "end_date": end_date, "login": USER_NAME}
    request = simple_request(graph_commits.__name__, query, variables)
    return int(
        request.json()["data"]["user"]["contributionsCollection"]["contributionCalendar"][
            "totalContributions"
        ]
    )


def graph_repos_stars(count_type, owner_affiliation, cursor=None, add_loc=0, del_loc=0):
    """
    Find's a user's total repository, star, or lines of code count.
    """

    query = """
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
    }"""

    variables = {
        "owner_affiliation": owner_affiliation,
        "login": USER_NAME,
        "cursor": cursor,
    }

    request = simple_request(graph_repos_stars.__name__, query, variables)
    if request.status_code == 200:
        if count_type == "repos":
            return request.json()["data"]["user"]["repositories"]["totalCount"]
        elif count_type == "stars":
            return stars_counter(request.json()["data"]["user"]["repositories"]["edges"])


def recursive_loc(
    owner,
    repo_name,
    data,
    cache_comment,
    addition_total=0,
    deletion_total=0,
    my_commits=0,
    cursor=None,
):
    """
    Fetches 100 commits from a repository at a time.
    """

    query = """
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
                                        committedDate
                                    }
                                    author {
                                        user {
                                            id
                                        }
                                    }
                                    deletions
                                    additions
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
    }"""

    variables = {"repo_name": repo_name, "owner": owner, "cursor": cursor}

    # I cannot use simple_request(), because I want to save the file before raising Exception
    request = requests.post(
        "https://api.github.com/graphql",
        json={"query": query, "variables": variables},
        headers=HEADERS,
    )

    if request.status_code == 200:
        # Only count commits if repo isn't empty
        if request.json()["data"]["repository"]["defaultBranchRef"] is not None:
            return loc_counter_one_repo(
                owner,
                repo_name,
                data,
                cache_comment,
                request.json()["data"]["repository"]["defaultBranchRef"]["target"][
                    "history"
                ],
                addition_total,
                deletion_total,
                my_commits,
            )
        else:
            return 0

    # saves what is currently in the file before this program crashes
    force_close_file(data, cache_comment)
    if request.status_code == 403:
        raise Exception(
            "Too many requests in a short amount of time!\n"
            + "You've hit the non-documented anti-abuse limit!"
        )

    raise Exception(
        "recursive_loc() has failed with a",
        request.status_code,
        request.text,
    )


def loc_counter_one_repo(
    owner,
    repo_name,
    data,
    cache_comment,
    history,
    addition_total,
    deletion_total,
    my_commits,
):
    """
    Recursively call recursive_loc().
    Only adds the LOC value of commits authored by the user.
    """

    for node in history["edges"]:
        if node["node"]["author"]["user"] == OWNER_ID:
            my_commits += 1
            addition_total += node["node"]["additions"]
            deletion_total += node["node"]["deletions"]

    if history["edges"] == [] or not history["pageInfo"]["hasNextPage"]:
        return addition_total, deletion_total, my_commits
    else:
        return recursive_loc(
            owner,
            repo_name,
            data,
            cache_comment,
            addition_total,
            deletion_total,
            my_commits,
            history["pageInfo"]["endCursor"],
        )


def loc_query(
    owner_affiliation, comment_size=0, force_cache=False, cursor=None, edges=[]
):
    """
    Queries all the repositories the user has access to (with respect to owner_affiliation).
    Queries 60 repos at a time, since larger queries give a 502 timeout error,
    and smaller queries send too many requests and also give a 502 error.
    Returns the total number of lines of code in all repositories.
    """

    query = """
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
    }"""

    variables = {
        "owner_affiliation": owner_affiliation,
        "login": USER_NAME,
        "cursor": cursor,
    }

    request = simple_request(loc_query.__name__, query, variables)

    # If repository data has another page
    if request.json()["data"]["user"]["repositories"]["pageInfo"]["hasNextPage"]:
        # Add on to the LoC count
        edges += request.json()["data"]["user"]["repositories"]["edges"]
        return loc_query(
            owner_affiliation,
            comment_size,
            force_cache,
            request.json()["data"]["user"]["repositories"]["pageInfo"]["endCursor"],
            edges,
        )
    else:
        return cache_builder(
            edges + request.json()["data"]["user"]["repositories"]["edges"],
            comment_size,
            force_cache,
        )


def cache_builder(edges, comment_size, force_cache, loc_add=0, loc_del=0):
    """
    Checks each repository in edges to see if it has been updated since the last time it was cached
    If it has, run recursive_loc on that repository to update the LOC count
    """

    # Assume all repositories are cached
    cached = True

    # Create a unique filename for each user
    filename = "cache/" + hashlib.sha256(USER_NAME.encode("utf-8")).hexdigest() + ".txt"

    try:
        with open(filename, "r") as f:
            data = f.readlines()
    except FileNotFoundError:
        # create cache file if it doesn't exist
        data = []
        if comment_size > 0:
            for _ in range(comment_size):
                data.append(
                    "This line is a comment block. Write whatever you want here.\n"
                )
        with open(filename, "w") as f:
            f.writelines(data)

    # If the number of repos has changed, or force_cache is True
    if len(data) - comment_size != len(edges) or force_cache:
        cached = False
        flush_cache(edges, filename, comment_size)
        with open(filename, "r") as f:
            data = f.readlines()

    cache_comment = data[:comment_size]  # save the comment block
    data = data[comment_size:]  # remove those lines
    for index in range(len(edges)):
        repo_hash, commit_count, *__ = data[index].split()
        if (
            repo_hash
            == hashlib.sha256(
                edges[index]["node"]["nameWithOwner"].encode("utf-8")
            ).hexdigest()
        ):
            try:
                if (
                    int(commit_count)
                    != edges[index]["node"]["defaultBranchRef"]["target"]["history"][
                        "totalCount"
                    ]
                ):
                    # if commit count has changed, update loc for that repo
                    owner, repo_name = edges[index]["node"]["nameWithOwner"].split("/")
                    loc = recursive_loc(owner, repo_name, data, cache_comment)
                    data[index] = (
                        repo_hash
                        + " "
                        + str(
                            edges[index]["node"]["defaultBranchRef"]["target"]["history"][
                                "totalCount"
                            ]
                        )
                        + " "
                        + str(loc[2])
                        + " "
                        + str(loc[0])
                        + " "
                        + str(loc[1])
                        + "\n"
                    )
            except TypeError:  # If the repo is empty
                data[index] = repo_hash + " 0 0 0 0\n"
    with open(filename, "w") as f:
        f.writelines(cache_comment)
        f.writelines(data)
    for line in data:
        loc = line.split()
        loc_add += int(loc[3])
        loc_del += int(loc[4])
    return [loc_add, loc_del, loc_add - loc_del, cached]


def flush_cache(edges, filename, comment_size):
    """
    Wipes the cache file
    This is called when the number of repositories changes or when the file is first created
    """
    with open(filename, "r") as f:
        data = []
        if comment_size > 0:
            data = f.readlines()[:comment_size]  # only save the comment
    with open(filename, "w") as f:
        f.writelines(data)
        for node in edges:
            f.write(
                hashlib.sha256(node["node"]["nameWithOwner"].encode("utf-8")).hexdigest()
                + " 0 0 0 0\n"
            )


def force_close_file(data, cache_comment):
    """
    Forces the file to close, preserving whatever data was written to it
    This is needed because if this function is called, the program would've crashed before the file is properly saved and closed
    """
    filename = "cache/" + hashlib.sha256(USER_NAME.encode("utf-8")).hexdigest() + ".txt"
    with open(filename, "w") as f:
        f.writelines(cache_comment)
        f.writelines(data)
    print(
        "There was an error while writing to the cache file. The file,",
        filename,
        "has had the partial data saved and closed.",
    )


def stars_counter(data):
    """
    Count total stars in user's repositories.
    """

    return sum(node["node"]["stargazers"]["totalCount"] for node in data)


def svg_overwrite(
    filename,
    age_data,
    commit_data,
    star_data,
    repo_data,
    loc_data,
):
    """
    Parse SVG files and update elements with the newly retrieved Github data.
    """

    tree = etree.parse(filename)
    root = tree.getroot()
    justify_format(root, "commit_data", commit_data, 22)
    justify_format(root, "star_data", star_data, 14)
    justify_format(root, "repo_data", repo_data, 6)
    justify_format(root, "loc_data", loc_data[2], 9)
    justify_format(root, "loc_add", loc_data[0])
    justify_format(root, "loc_del", loc_data[1], 7)
    tree.write(filename, encoding="utf-8", xml_declaration=True)


def justify_format(root, element_id, new_text, length=0):
    """
    Updates and formats the text of the element,
    and modifes the amount of dots in the previous element,
    in order to justify the new text in the SVG.
    """

    if isinstance(new_text, int):
        new_text = f"{'{:,}'.format(new_text)}"
    new_text = str(new_text)

    find_and_replace(root, element_id, new_text)

    just_len = max(0, length - len(new_text))
    if just_len <= 2:
        dot_map = {0: "", 1: " ", 2: ". "}
        dot_string = dot_map[just_len]
    else:
        dot_string = " " + ("." * just_len) + " "

    find_and_replace(root, f"{element_id}_dots", dot_string)


def find_and_replace(root, element_id, new_text):
    """
    Finds the element in the SVG file and replaces its text with a new value
    """

    element = root.find(f".//*[@id='{element_id}']")
    if element is not None:
        element.text = new_text


def commit_counter(comment_size):
    """
    Counts up user's total commits, using the cache file created by cache_builder.
    """

    total_commits = 0

    # Use the same filename as cache_builder
    filename = "cache/" + hashlib.sha256(USER_NAME.encode("utf-8")).hexdigest() + ".txt"

    with open(filename, "r") as f:
        data = f.readlines()

    data = data[comment_size:]  # remove those lines
    for line in data:
        total_commits += int(line.split()[2])

    return total_commits


def user_getter(username):
    """
    Returns the account ID and creation time of the user
    """

    query = """
    query($login: String!){
        user(login: $login) {
            id
            createdAt
        }
    }"""

    variables = {"login": username}
    request = simple_request(user_getter.__name__, query, variables)
    return {"id": request.json()["data"]["user"]["id"]}, request.json()["data"]["user"][
        "createdAt"
    ]


def main():
    global OWNER_ID
    OWNER_ID, _ = user_getter(USER_NAME)

    age_data = calculate_age(BIRTHDAY)
    star_data = graph_repos_stars("stars", ["OWNER"])
    repo_data = graph_repos_stars("repos", ["OWNER"])
    commit_data = commit_counter(7)
    total_loc = loc_query(["OWNER"], 7)

    svg_overwrite(
        "dark_mode.svg",
        age_data,
        commit_data,
        star_data,
        repo_data,
        total_loc[:-1],
    )


if __name__ == "__main__":
    main()
