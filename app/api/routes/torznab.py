from __future__ import annotations

import logging
from email.utils import format_datetime
from xml.etree.ElementTree import Element, SubElement, tostring

from fastapi import APIRouter, Depends, Query, Response

from app.api.deps import internet_archive_client
from app.catalog.internet_archive import InternetArchiveClient, InternetArchiveError, InternetArchiveRelease
from app.core.config import settings

logger = logging.getLogger("uvicorn.error")

router = APIRouter()

_TORZNAB_NS = "http://torznab.com/schemas/2015/feed"
_ATOM_NS = "http://www.w3.org/2005/Atom"
_AUDIO_CATEGORY = "3000"


@router.get("/internetarchive/api")
async def internet_archive_torznab(
    t: str = Query(default="caps"),
    q: str = Query(default=""),
    apikey: str = Query(default=""),
    client: InternetArchiveClient = Depends(internet_archive_client),
) -> Response:
    expected = settings.torznab_ia_api_key.strip()
    if expected and apikey != expected:
        return _xml_response(_error_xml(100, "Invalid API key"), status_code=401)

    if t == "caps":
        return _xml_response(_caps_xml())

    try:
        releases = await client.search(q)
    except InternetArchiveError as exc:
        # Return an empty (but successful) feed instead of an HTTP error so a
        # transient archive.org failure never trips Prowlarr's own indexer
        # circuit breaker — it just sees "no results this time".
        logger.warning("internet-archive-torznab: %s", exc)
        releases = []

    return _xml_response(_search_xml(releases))


def _xml_response(root: Element, *, status_code: int = 200) -> Response:
    body = b'<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(root, encoding="utf-8")
    return Response(content=body, media_type="application/xml", status_code=status_code)


def _caps_xml() -> Element:
    caps = Element("caps")
    server = SubElement(caps, "server")
    server.set("version", "1.0")
    server.set("title", "Internet Archive (proxied)")
    limits = SubElement(caps, "limits")
    limits.set("max", "100")
    limits.set("default", "100")

    searching = SubElement(caps, "searching")
    for tag, available in (
        ("search", "yes"),
        ("tv-search", "no"),
        ("movie-search", "no"),
        ("music-search", "yes"),
        ("book-search", "no"),
    ):
        node = SubElement(searching, tag)
        node.set("available", available)
        node.set("supportedParams", "q")

    categories = SubElement(caps, "categories")
    category = SubElement(categories, "category")
    category.set("id", _AUDIO_CATEGORY)
    category.set("name", "Audio")
    return caps


def _search_xml(releases: list[InternetArchiveRelease]) -> Element:
    rss = Element("rss")
    rss.set("version", "2.0")
    rss.set("xmlns:atom", _ATOM_NS)
    rss.set("xmlns:torznab", _TORZNAB_NS)
    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = "Internet Archive (proxied)"

    for release in releases:
        item = SubElement(channel, "item")
        SubElement(item, "title").text = release.title
        SubElement(item, "guid").text = release.torrent_url
        SubElement(item, "link").text = release.torrent_url
        SubElement(item, "pubDate").text = format_datetime(release.published_at)
        SubElement(item, "size").text = str(release.size_bytes)
        SubElement(item, "category").text = _AUDIO_CATEGORY

        enclosure = SubElement(item, "enclosure")
        enclosure.set("url", release.torrent_url)
        enclosure.set("length", str(release.size_bytes))
        enclosure.set("type", "application/x-bittorrent")

        for name, value in (
            ("category", _AUDIO_CATEGORY),
            ("size", str(release.size_bytes)),
            ("seeders", "1"),
            ("peers", "1"),
            ("minimumratio", "0"),
            ("minimumseedtime", "0"),
            ("downloadvolumefactor", "0"),
            ("uploadvolumefactor", "1"),
        ):
            attr = SubElement(item, "torznab:attr")
            attr.set("name", name)
            attr.set("value", value)

    return rss


def _error_xml(code: int, description: str) -> Element:
    error = Element("error")
    error.set("code", str(code))
    error.set("description", description)
    return error
