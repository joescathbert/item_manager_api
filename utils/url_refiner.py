from typing import List
from urllib.parse import urlparse
from utils.domain_urls import REDDIT_DOMAINS, TWITTER_DOMAINS

def refine_twitter_url(raw_url: str) -> str:
    """
    Normalize Twitter/X URLs to https://twitter.com/<username>/status/<id>.
    Raises ValueError if format is invalid.
    """
    parsed = urlparse(raw_url.strip())

    path_parts: List[str] = parsed.path.strip("/").split("/")
    if len(path_parts) < 3 or path_parts[1] != "status":
        raise ValueError("URL must be in the format /<username>/status/<id>")

    post_host_name: str = path_parts[0]
    status_id: str = path_parts[2]

    if not status_id.isdigit():
        raise ValueError("Status ID must be numeric.")

    twitter_url = f"https://twitter.com/{post_host_name}/status/{status_id}"

    return {'url': twitter_url, 'post_host': 'user', 'post_host_name': post_host_name, 'url_site_name': 'twitter'}

def refine_reddit_url(raw_url: str) -> str:
    """
    Normalize Reddit URLs to https://www.reddit.com/r/<subreddit>/comments/<post_id>.
    Raises ValueError if format is invalid.
    """
    parsed = urlparse(raw_url.strip())

    path_parts: List[str] = parsed.path.strip("/").split("/")
    # Expected: ["r", "<subreddit>", "comments", "<post_id>", ...]
    if len(path_parts) < 4 or path_parts[0] not in ["r", "user"] or path_parts[2] != "comments":
        raise ValueError("URL must be in the format /r/<subreddit>/comments/<post_id> or /user/<username>/comments/<post_id>")

    post_host: str = path_parts[0]
    post_host_name: str = path_parts[1]
    post_id: str = path_parts[3]

    # Reddit post IDs are alphanumeric
    if not post_id.isalnum():
        raise ValueError("Post ID must be alphanumeric.")

    reddit_url = f"https://www.reddit.com/{post_host}/{post_host_name}/comments/{post_id}"

    return {'url': reddit_url, 'post_host': post_host, 'post_host_name': post_host_name, 'url_site_name': 'reddit'}

def refine_url(raw_url: str) -> str:
    """
    Dispatches to the correct refiner based on domain.
    """
    parsed = urlparse(raw_url.strip())
    domain = parsed.netloc.lower()

    if domain in TWITTER_DOMAINS:
        return refine_twitter_url(raw_url)
    elif domain in REDDIT_DOMAINS:
        return refine_reddit_url(raw_url)
    else:
        raise ValueError("Unsupported domain. Only Twitter/X and Reddit are allowed.")
