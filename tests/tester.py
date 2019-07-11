import pytest
import uuid
import aioredis
import aursync
import asyncio
# pytestmark = pytest.mark.asyncio
import time
import typing as ty

import logging

log = logging.getLogger("aursync")
log.setLevel("DEBUG")


def message():
    return uuid.uuid4().hex


@pytest.mark.asyncio
@pytest.mark.repeat(1)
async def test_long_async_handler(event_loop):
    pub = aursync.messager.Messager()
    await pub.init()
    sub = aursync.messager.Messager()
    await sub.init()
    messages_seen = []

    async def handle(message):
        await asyncio.sleep(2)
        messages_seen.append(message)
        return message

    await sub.subscribe(handle, "test", wait=True)

    await asyncio.sleep(2)
    messages_to_send = list(range(15))

    for t_mess in messages_to_send:
        await pub.publish(t_mess, "test")

    await asyncio.sleep(0.05)
    await pub.stop()
    await sub.stop()

    assert messages_seen == messages_to_send


@pytest.mark.asyncio
@pytest.mark.repeat(1)
async def test_multpub(event_loop):
    sub = await aursync.messager.Messager().init()

    pubs = [await aursync.messager.Messager(name=str(i)).init() for i in range(10)]

    messages_seen = set()
    messages_sent = set()

    async def handle(mess_in):
        await asyncio.sleep(2)
        messages_seen.add(mess_in)
        return mess_in

    await sub.subscribe(handle, "test")
    supertot = 0
    for i in range(100):
        log.info(f"it {i}")
        message_list = [message() for _ in range(len(pubs))]
        messages_sent.update(set(message_list))
        res = sum(aursync.messager._flatten(await asyncio.gather(*[pub.publish(mess, "test") for mess, pub in zip(message_list, pubs)])))
        supertot += res

    await asyncio.sleep(0.05)

    await asyncio.gather(*[pub.stop() for pub in pubs])
    await sub.stop()
    print(len(messages_seen))
    print(len(messages_sent))
    print(supertot)
    assert messages_seen == messages_sent

@pytest.mark.asyncio
@pytest.mark.repeat(1)
async def test_multsub(event_loop):
    import collections
    sub_count = 10
    pub_loop_count = 100
    subs = [await aursync.messager.Messager().init() for _ in range(sub_count)]

    pub = await aursync.messager.Messager().init()


    messages_seen = collections.deque()

    messages_sent = set()

    async def handle(mess_in):
        messages_seen.append(mess_in)
        return mess_in

    for sub in subs:
        await sub.subscribe(handle, "test")

    for _ in range(pub_loop_count):
        mess = message()
        messages_sent.add(mess)
        await pub.publish(mess, "test")

    await asyncio.sleep(0.05)

    await asyncio.gather(*[sub.stop() for sub in subs])

    await pub.stop()
    assert(len(messages_seen) == pub_loop_count*sub_count)

@pytest.mark.asyncio
@pytest.mark.repeat(1)
async def test_long_sync_handler(event_loop):
    pub = aursync.messager.Messager()
    await pub.init()
    sub = aursync.messager.Messager()
    await sub.init()
    messages_seen = []

    def handle(message):
        time.sleep(1)
        messages_seen.append(message)
        return message

    await sub.subscribe(handle, "test")

    messages_to_send = list(range(3))

    for t_mess in messages_to_send:
        await pub.publish(t_mess, "test")

    await asyncio.sleep(0.05)
    await pub.stop()
    await sub.stop()

    assert messages_seen == messages_to_send
