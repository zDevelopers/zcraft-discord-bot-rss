#!/usr/bin/env python3

import json
import os
import random
import time
import xml.etree.ElementTree as ET

from datetime import datetime
from html.parser import HTMLParser
from urllib import request
from urllib.error import HTTPError


ROOT = "https://forum.zcraft.fr"
FLUX = [
    # (link, with catchphrase)
    ("/rss/t/actualites-de-zcraft/discussions?sort=newest", False),
    # ("/rss/discussions?sort=newest", True)
]
CATCH_PHRASES = [
    # Articles
    [],

    # Topics
    [
        "Un nouveau sujet est en ligne",
        "Oyez, oyez ! un nouveau sujet est en ligne",
        "À vos souris, un nouveau sujet est en ligne",
        "Hey, un sujet vient de paraître ! Ça pourrait peut être t’intéresser ?",
    ],
]

# One url per line for each feed, in the same order
WEBHOOK_URLS = open("webhook_url.txt").read().strip().split("\n")

HORO_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), "horodatage.json")


def get_items_from_url(url, force=False):
    print(url)
    page = request.urlopen(url).read()
    root = ET.fromstring(page)

    lastBuildList = {}
    with open(HORO_PATH, "r") as f:
        lastBuildList = json.load(f)

    date_min = lastBuildList.get(url, 0)
    lastBuildDate = next(root.iter("pubDate")).text
    lastBuildDate = datetime.strptime(lastBuildDate, "%a, %d %b %Y %H:%M:%S %z")
    lastBuildDate = int(lastBuildDate.timestamp())
    if not force:
        if lastBuildDate <= date_min:
            print("RSS is not new")
            return []
    else:
        print("forcing refresh")

    items = []
    for item in root.iter("item"):
        temp = {}
        temp["title"] = item.find("title").text
        temp["link"] = (
            item.find("link").text if item.find("link") else item.find("guid").text
        )
        temp["description"] = item.find("description").text
        temp["guid"] = item.find("guid").text
        temp["pubDate"] = datetime.strptime(
            item.find("pubDate").text, "%a, %d %b %Y %H:%M:%S %z"
        )  # Tue, 15 Jan 2019 00:09:15 +0100

        creator = item.find(r"{http://purl.org/dc/elements/1.1/}creator")
        if creator:
            temp["creator"] = creator.text

        pubDate = int(temp["pubDate"].timestamp())
        if force or pubDate > date_min:
            items.append(temp)

    with open(HORO_PATH, "w") as f:
        lastBuildList[url] = lastBuildDate
        json.dump(lastBuildList, f)

    return items


def truncate(content, length=256, suffix="…"):
    return content[:length].rsplit(" ", 1)[0] + suffix


def post_item_to_discord(item, catch_phrase, webhook_url):
    if catch_phrase:
        content = f":small_blue_diamond: {catch_phrase}"
    else:
        content = f":small_blue_diamond: **{item['title']}**\n"
        if 'creator' in item:
            content += f"_Par {item['creator']}_"

    payload = {
        "content": content,
        "embeds": [
            {
                "title": item["title"],
                "description": truncate(strip_tags(item["description"])),
                "url": item["link"],
                "color": 0x3f9718,  # zcraft green
                "thumbnail": {
                  "url": "https://i.zcraft.fr/9781931573048863.png"
                },
                "footer": {
                  "text": "Actualités de Zcraft" if not catch_phrase else "Forum de Zcraft"
                },
                "timestamp": item["pubDate"].isoformat(),
            }
        ],
    }

    if "creator" in item:
        payload["embeds"][0]["author"] = {"name": item["creator"]}

    headers = {
        "Content-Type": "application/json",
        "user-agent": "Mozilla/5.0 (X11; U; Linux i686) Gecko/20071127 Firefox/2.0.0.11",
    }
    req = request.Request(
        url=webhook_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        r = request.urlopen(req)
        print(r.status)
        print(r.reason)
        print(r.headers)
    except HTTPError as e:
        print("ERROR")
        print(e.reason)
        print(e.hdrs)
        print(e.file.read())


# HTML strip from Django (<3)
class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.reset()
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def handle_entityref(self, name):
        self.fed.append('&%s;' % name)

    def handle_charref(self, name):
        self.fed.append('&#%s;' % name)

    def get_data(self):
        return ''.join(self.fed)


def _strip_once(value):
    """
    Internal tag stripping utility used by strip_tags.
    """
    s = MLStripper()
    s.feed(value)
    s.close()
    return s.get_data()


def strip_tags(value):
    """Return the given HTML with all tags stripped."""
    # Note: in typical case this loop executes _strip_once once. Loop condition
    # is redundant, but helps to reduce number of executions of _strip_once.
    value = str(value)
    while '<' in value and '>' in value:
        new_value = _strip_once(value)
        if value.count('<') == new_value.count('<'):
            # _strip_once wasn't able to detect more tags.
            break
        value = new_value
    return value


if __name__ == "__main__":
    # We only publish each link once, so articles already published in the news
    # channel are not published to the main channel too.
    published_links = []

    for idx, (f, has_catchphrase) in enumerate(FLUX):
        items = get_items_from_url(ROOT + f)
        for item in items:
            if item["guid"] not in published_links:
                post_item_to_discord(
                    item, random.choice(CATCH_PHRASES[idx]) if has_catchphrase else None, WEBHOOK_URLS[idx]
                )
                published_links.append(item["guid"])
                time.sleep(2)  # Lazy workaround to not break the rate limit
