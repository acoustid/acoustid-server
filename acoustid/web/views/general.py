import datetime
import json
import logging
import os
from typing import Optional, Tuple

import markdown.util
import requests
from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    render_template_string,
    url_for,
)
from markdown import Markdown

from acoustid.utils import generate_demo_client_api_key
from acoustid.web import db

logger = logging.getLogger(__name__)

general_page = Blueprint("general", __name__)


@general_page.route("/favicon.ico")
def favicon_ico():
    return redirect(url_for("static", filename="favicon.ico"))


class MarkdownFlaskUrlProcessor(markdown.util.Processor):
    def run(self, root):
        stack = [root]
        while stack:
            element = stack.pop()
            if element.tag == "a":
                href = element.get("href")
                if href.startswith("flask:"):
                    element.set("href", url_for(href.split(":", 1)[1]))
            for child in element:
                stack.append(child)


def render_page(name, **context):
    path = os.path.join("pages", name)
    with current_app.open_resource(path, mode="rt") as file:
        text = file.read()
        text = render_template_string(text, **context)
        md = Markdown(extensions=["meta"])
        md.treeprocessors.register(MarkdownFlaskUrlProcessor(md), "flask_links", 50)
        html = md.convert(text)
        title = " ".join(md.Meta.get("title", []))
        return render_template("page.html", content=html, title=title)


def add_page_route(name, path=None):
    if path is None:
        path = "/" + name
    general_page.add_url_rule(path, name, lambda: render_page(name + ".md"))


add_page_route("index", "/")
add_page_route("contact")
add_page_route("database")
add_page_route("docs")
add_page_route("faq")
add_page_route("license")
add_page_route("server")
add_page_route("about")


@general_page.route("/webservice")
def webservice():
    return render_page(
        "webservice.md",
        client_api_key=generate_demo_client_api_key(current_app.config["SECRET_KEY"]),
    )


CHROMAPRINT_RELEASES_URL = (
    "https://api.github.com/repos/acoustid/chromaprint/releases?per_page=1"
)

CHROMAPRINT_RELEASE_CACHE_KEY = "chromaprint:latest_release"

# How long a cached release is served without asking GitHub again. Chromaprint
# is released rarely, so a long window costs almost nothing in staleness, while
# a short one costs a broken page: the call is unauthenticated, GitHub allows 60
# an hour per IP, and our egress shares a handful of addresses across every
# visitor.
CHROMAPRINT_RELEASE_TTL = datetime.timedelta(hours=12)

# How long a cached release is kept so it can still be served when GitHub will
# not answer. Past the TTL above we try to refresh, and fall back to this.
CHROMAPRINT_RELEASE_MAX_AGE = datetime.timedelta(days=30)

# The page renders fine without a release, so there is no reason to let an
# outbound call hold a worker for longer than a visitor would wait.
CHROMAPRINT_RELEASE_TIMEOUT = 5.0


def _read_cached_release():
    # type: () -> Optional[Tuple[Optional[dict], bool]]
    """The cached release and whether it is still fresh, or None if not cached.

    Redis here is sharded behind a proxy and does blip, so a failure to read the
    cache must look the same as a miss. Swapping a GitHub dependency for a Redis
    one would miss the point of caching this at all.
    """
    try:
        raw = db.get_redis().get(CHROMAPRINT_RELEASE_CACHE_KEY)
    except Exception:
        logger.warning("Failed to read the chromaprint release cache", exc_info=True)
        return None
    if not raw:
        return None
    try:
        cached = json.loads(raw)
        fetched_at = datetime.datetime.fromisoformat(cached["fetched_at"])
    except Exception:
        logger.warning("Ignoring an unreadable chromaprint release cache entry")
        return None
    age = datetime.datetime.now(datetime.timezone.utc) - fetched_at
    return cached.get("release"), age < CHROMAPRINT_RELEASE_TTL


def _write_cached_release(release):
    # type: (Optional[dict]) -> None
    value = json.dumps(
        {
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "release": release,
        }
    )
    try:
        db.get_redis().setex(
            CHROMAPRINT_RELEASE_CACHE_KEY,
            int(CHROMAPRINT_RELEASE_MAX_AGE.total_seconds()),
            value,
        )
    except Exception:
        logger.warning("Failed to write the chromaprint release cache", exc_info=True)


def _fetch_latest_chromaprint_release():
    # type: () -> Optional[dict]
    rv = requests.get(CHROMAPRINT_RELEASES_URL, timeout=CHROMAPRINT_RELEASE_TIMEOUT)
    rv.raise_for_status()
    releases = rv.json()
    if not releases:
        return None
    return releases[0]


def get_latest_chromaprint_release():
    # type: () -> Optional[dict]
    """The most recent Chromaprint release, or None if we cannot find out.

    Every path out of here that is not a fresh answer ends in the same place --
    returning what we have, or None -- because the version is an ornament on the
    page and GitHub being unreachable is not a reason to serve a 500 to someone
    who came to read the documentation.
    """
    cached = _read_cached_release()
    if cached is not None:
        release, is_fresh = cached
        if is_fresh:
            return release
    else:
        release = None

    try:
        release = _fetch_latest_chromaprint_release()
    except Exception:
        if cached is not None:
            logger.warning(
                "Failed to refresh the chromaprint release, serving a stale one",
                exc_info=True,
            )
            return release
        logger.warning("Failed to look up the chromaprint release", exc_info=True)
        return None

    _write_cached_release(release)
    return release


@general_page.route("/chromaprint")
def chromaprint():
    release = get_latest_chromaprint_release()
    return render_page("chromaprint.md", release=release)
