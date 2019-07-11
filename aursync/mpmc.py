import asyncio
import contextlib
import logging
import traceback
import typing as ty

import aioredis
import jsonpickle

logger = logging.getLogger()
T_m = ty.TypeVar("T_m")


# Adapted from https://github.com/aio-libs/aioredis/issues/439

class MPMC:
    _TERMINATE = object()

    def __init__(self,
                 redis_conn: aioredis.Redis,
                 serializer: ty.Callable[[T_m], ty.Any] = jsonpickle.dumps,
                 deserializer: ty.Callable[[ty.Any], T_m] = jsonpickle.loads):

        self.redis_conn: aioredis.Redis = redis_conn
        self.serializer = serializer
        self.deserializer = deserializer
        self.channels: ty.Set[str] = set()
        self.channel_patterns: ty.Set[str] = set()
        self._lock = asyncio.Lock()
        self._mpsc = aioredis.pubsub.Receiver()
        self._reader_task: ty.Optional[asyncio.Future] = None
        self._registry: ty.Dict[
            aioredis.abc.AbcChannel,
            ty.Set[asyncio.Queue],
        ] = {}

    async def start(self) -> None:
        self._reader_task = asyncio.create_task(self.reader())

    async def stop(self) -> None:
        if not self._reader_task:
            raise RuntimeError(f'{type(self).__name__} is not running.')

        self._reader_task.cancel()
        f = asyncio.gather(*[
            subscription.put(self._TERMINATE)
            for subscriptions in self._registry.values()
            for subscription in subscriptions
        ])
        f.add_done_callback(lambda x: self.stop)
        # self._mpsc.stop()
        await f
        # self.redis_conn.close()

    async def reader(self):
        async for channel, produced in self._mpsc.iter():
            channel: aioredis.abc.AbcChannel
            data = produced[1] if channel.is_pattern else produced
            message = self.deserializer(data)
            # possible exception here?

            await asyncio.gather(*[
                sub.put(message)
                for sub in self._registry.get(channel, [])
            ])

    async def publish(self, channel: str, message: ty.Any):
        serialized = self.serializer(message)
        pub_res = await self.redis_conn.publish(channel, serialized)
        return pub_res

    @contextlib.asynccontextmanager
    async def _subscribe(self,
                         channel: str,
                         is_pattern: bool
                         ) -> ty.AsyncGenerator[asyncio.Queue, None]:

        sub_method = self.redis_conn.psubscribe if is_pattern else self.redis_conn.subscribe
        self.channel_patterns.add(channel) if is_pattern else self.channels.add(channel)

        async with self._lock:
            handler = self._mpsc.pattern if is_pattern else self._mpsc.channel
            registration = handler(channel)
            subscription: asyncio.Queue = asyncio.Queue()

            if registration not in self._registry:
                await sub_method(registration)
                self._registry[registration] = set()
            self._registry[registration].add(subscription)

        try:
            yield subscription
        except:
            print(traceback.format_exc())
        finally:
            async with self._lock:
                self._registry[registration].remove(subscription)
                if not self._registry[registration]:
                    await sub_method(registration)
                    del self._registry[registration]

    async def subscribe(self,
                        channel: str,
                        is_pattern: bool = False,
                        ) -> ty.AsyncGenerator[ty.Any, None]:
        async with self._subscribe(channel, is_pattern) as subscription:
            while True:
                value = await subscription.get()
                if value is self._TERMINATE:
                    break
                else:
                    yield value
