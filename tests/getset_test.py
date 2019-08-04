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
    return functools.reduce(lambda acc, x: {x: acc}, ([{str(i) + "→": "0" for i in range(n)}] + [str(x) for x in range(n)]))


@pytest.mark.asyncio
async def test_dict_getset(event_loop):
    sync_client = aursync.Sync()
    await sync_client.init()

    test_dict = makeEvilDict(5)

    print(test_dict)

    await sync_client.redis.aur_set_dict("test", test_dict)

    result_dict = await sync_client.redis.aur_get_dict("test")
    print(result_dict)
    await sync_client.stop()

    assert result_dict == test_dict

@pytest.mark.asyncio
async def test_proxy_get(event_loop):
    sync_client = await aursync.Sync().init()

# @pytest.mark.asyncio
# async def test_dict_getset_list(event_loop):
#     sync_client = aursync.Sync()
#     await sync_client.init()
#     test_dict = {"→": {"b": {"c": ["d1", "d2", "d3", "d4"]},
#                        "e": [{"f1": "f2"}, {"f3": "f4"}, {"f5": "f6", "f7":"f8", "f9":{"g1":"g2"}}],
#                        "h": [{"i1": ["j1","j2","j3"]}, {"i2": "i3"}, {"i4": "i5"}]}}
#
#     print(test_dict)
#
#     await sync_client.redis.aur_set_dict("test", test_dict)
#
#     result_dict = await sync_client.redis.aur_get_dict("test")
#     print(result_dict)
#     await sync_client.stop()
#
#     assert result_dict == test_dict
