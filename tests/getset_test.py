import pytest
import uuid
import aioredis
import aursync
import asyncio
import time
import typing as ty
import functools
import logging
logging.basicConfig()
log = logging.getLogger("aursync")

log.setLevel("DEBUG")

def makeEvilDict(n):
    return functools.reduce(lambda acc, x: {x: acc, x + ".alt": acc, x + ".alt2": acc}, ([{str(i): 0 for i in range(n)}] + [str(x) for x in range(n)]))


@pytest.mark.asyncio
async def test_dict_getset(event_loop):
    sync_client = aursync.Sync()
    await sync_client.init()
    test_dict = makeEvilDict(8)

    await sync_client.redis.aur_set_dict("test", test_dict)

    result_dict = await sync_client.redis.aur_get_dict("test")

    assert result_dict == test_dict

    await sync_client.stop()

