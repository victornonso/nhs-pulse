"""Bounded analytical cache, keyed by the database publication generation."""

import asyncio
import copy
import json
import time
from collections import OrderedDict
from .database import fetch
from .analytics import workspace

entries = OrderedDict()
locks = {}


async def published_workspace(conn, screen, parameters):
    generation = (
        await fetch(
            conn,
            "SELECT coalesce(sum(generation),0) generation FROM ops.mart_publication",
        )
    )[0]["generation"]
    key = (screen, json.dumps(parameters, sort_keys=True, default=str), generation)
    ttl = 10 if screen == "operations" else 60
    slot = locks.setdefault(key, [asyncio.Lock(), 0])
    slot[1] += 1
    try:
        async with slot[0]:
            return await _load(conn, screen, parameters, key, ttl)
    finally:
        slot[1] -= 1
        if slot[1] == 0:
            locks.pop(key, None)


async def _load(conn, screen, parameters, key, ttl):
    cached = entries.get(key)
    if cached and time.monotonic() - cached[0] < ttl:
        entries.move_to_end(key)
        return copy.deepcopy(cached[1])
    result = await workspace(conn, screen, parameters)
    entries[key] = (time.monotonic(), result)
    while len(entries) > 64:
        entries.popitem(last=False)
    # Private visitor history is added by the router only after this copy.
    return copy.deepcopy(result)
