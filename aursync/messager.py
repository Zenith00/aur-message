from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import operator
import typing as ty
import warnings
import contextlib
import time
import operator
import aioredis
import jsonpickle
from aioredis import Redis

from aursync.mpmc import MPMC

log = logging.getLogger("aursync")

_FLAG_FIRST = object()

_DICT_FLATTEN_SEP = "⸱"  # u"\u2E31"


def _flatten_dict(d, join=lambda l, r: l + _DICT_FLATTEN_SEP + r, lift=lambda x: x):
    results = []

    def visit(subdict, res, partialKey):
        for k, v in subdict.items():
            newKey = lift(k) if partialKey == _FLAG_FIRST else join(join(partialKey, _DICT_FLATTEN_SEP), lift(k))
            if isinstance(v, ty.Mapping):
                visit(v, res, newKey)
            else:
                res.append((newKey, v))

    visit(d, results, _FLAG_FIRST)
    return results


def _inflate(d):
    items = dict()
    for k, v in d.items():
        keys = k.split(_DICT_FLATTEN_SEP)
        sub_items = items
        for ki in keys[:-1]:
            try:
                sub_items = sub_items[ki]
            except KeyError:
                sub_items[ki] = dict()
                sub_items = sub_items[ki]

        sub_items[keys[-1]] = v

    return items


def _listify_arg(listy: ty.Optional[ty.Union[str, ty.Iterable[str]]]
) -> ty.Iterable:
    if listy is None:
        return []
    list_like__types = list, tuple, set
    if isinstance(listy, list_like__types):
        return listy
    return [listy]


def _flatten(li, list_types=(list, tuple)):
    li_type = type(li)
    li = list(li)
    i = 0
    while i < len(li):
        while isinstance(li[i], list_types):
            if not li[i]:
                li.pop(i)
                i -= 1
                break
            else:
                li[i:i + 1] = li[i]
        i += 1
    return li_type(li)


def _parameterize(deco_to_enhance):
    """
    @_parameterize
    def parameterized_deco(func, *deco_args, **deco_kwargs):
    """

    def deco_factory(*args, **kwargs):
        # Factory for decorators that accept a function retaining original arguments
        def deco_wrapper(func):
            # Return result of original deco (a normal deco'd function)
            return deco_to_enhance(func, *args, **kwargs)

        return deco_wrapper

    return deco_factory


@_parameterize
def _link_args(func, *arg_tups):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        func_binding = inspect.signature(func).bind(*args, **kwargs).arguments
        for arg_tup in arg_tups:
            if functools.reduce(operator.xor, [arg in func_binding for arg in arg_tup]):
                raise ValueError(f"{' and '.join(arg_tup)} must all be defined or undefined")

        func(*args, **kwargs)

    return wrapper


def _timegate(coro: ty.Awaitable, gate=0.01
) -> ty.Awaitable:
    async def wrap():
        res = await asyncio.gather(coro, asyncio.sleep(gate))
        return res[0]

    return wrap()


T_m = ty.TypeVar("T_m")


class ConfigProxy:
    pass


class Messager:
    redis: ty.Optional[Redis]
    _mpmc: ty.Optional[MPMC]
    _receiver: ty.Optional[aioredis.pubsub.Receiver]
    _init = False

    @_link_args(("serializer", "deserializer"))
    def __init__(
            self,
            name="Anon",
            redis: aioredis.ConnectionsPool = None,
            serializer: ty.Callable[[T_m], ty.Any] = jsonpickle.dumps,
            deserializer: ty.Callable[[ty.Any], T_m] = jsonpickle.loads):
        self.name = name
        self._serializer = serializer
        self._deserializer = deserializer
        self._waiting_handler_ct = 0
        self._waiting_handlers_done = asyncio.Event()
        self.redis = redis
        self._receiver = None

    async def init(self) -> Messager:
        if self._init:
            warnings.warn(f"[{self.name} already init'd, ignoring", RuntimeWarning)
            return self
        self._init = True

        if self.redis is None:
            self.redis: aioredis.Redis = await aioredis.create_redis_pool('redis://localhost', maxsize=5)
            warnings.warn(f"[{self.name} no redis provided, creating pool", RuntimeWarning)

        self._mpmc: MPMC = MPMC(redis_conn=self.redis,
                                serializer=self._serializer,
                                deserializer=self._deserializer)

        self._waiting_handler_ct = 0
        self._waiting_handlers_done.clear()
        await self._mpmc.start()
        await asyncio.sleep(0.1)

        return self

    async def stop(self):
        log.info(f"[{self.name}] Stopping Messager")
        await self._mpmc.stop()

        if self._waiting_handler_ct != 0:
            log.debug(f"[{self.name}] Waiting for {self._waiting_handler_ct} handles to clear")
            log.debug(f"handler is {self._waiting_handlers_done.is_set()}")
            await self._waiting_handlers_done.wait()
            log.debug(f"handler is {self._waiting_handlers_done.is_set()}")
        self.redis.close()
        await self.redis.wait_closed()

    async def _handle(
            self,
            handler_func: ty.Callable[[T_m], ty.Any],
            channel: str,
            is_pattern: bool = False
    ) -> None:

        is_coro = inspect.iscoroutinefunction(handler_func)

        log.info(
            f"[{self.name}][handler] "
            f"Registering {'async' if is_coro else ''} handler {handler_func.__name__} "
            f"for {'channel pattern' if is_pattern else 'channel'} {channel}")

        async for message in self._mpmc.subscribe(channel, is_pattern=is_pattern):
            if is_coro:
                self._waiting_handler_ct += 1
                log.debug(f"[{self.name}][handler] Handle count: {self._waiting_handler_ct}")
                self._waiting_handlers_done.clear()

                # Callback for handler_funcs that tracks number of ongoing handler_funcs
                def track_live_handlers(_):
                    log.debug(f"[{self.name}][handler] Callback firing, decreasing count to {self._waiting_handler_ct}")
                    self._waiting_handler_ct -= 1
                    if self._waiting_handler_ct == 0:
                        log.debug(f"[{self.name}][handler] Handle count at 0, setting done")
                        self._waiting_handlers_done.set()

                asyncio.create_task(handler_func(message)).add_done_callback(track_live_handlers)
            else:
                handler_func(message)

    def subscribe(
            self,
            handler_func: ty.Callable[[T_m], ty.Any],
            channels: ty.Union[str, ty.List[str]] = None,
            channel_patterns: ty.Union[str, ty.List[str]] = None,
            wait=True
    ) -> ty.Union[ty.Awaitable, None]:
        """
        Usage:
            (async) def handle(message):
                do_something(message)

            (await) Messager().subscribe(handle, "test")
        :param handler_func: Called with message when matching channel received
        :param channels: Channels to accept for handler_func
        :param channel_patterns: Channel patterns to accept for handler_func
        :param wait: Return a sleep of 100ms for subscription to process
        :return: 100 ms asyncio.sleep to ensure proper handler registration if wait, otherwise none
        """
        channels = _listify_arg(channels)
        channel_patterns = _listify_arg(channel_patterns)
        log.info(f"[{self.name}][subscribe] "
                 f"Subscribing to channels [{','.join(channels)}], "
                 f"channel patterns [{','.join(channel_patterns)}] with func {handler_func.__name__}")

        for t_channel in channels:
            asyncio.create_task(self._handle(handler_func=handler_func, channel=t_channel, is_pattern=False))
        for t_channel_pattern in channel_patterns:
            asyncio.create_task(self._handle(handler_func=handler_func, channel=t_channel_pattern, is_pattern=True))
        if wait:
            return asyncio.sleep(0.1)

    def publish(
            self,
            message: T_m,
            channels: ty.Union[str, ty.List[str]] = None,
            wait: bool = True,
            callback: ty.Optional[ty.Callable[[T_m], ty.Any]] = None
    ) -> ty.Union[ty.Awaitable, ty.Tuple]:
        channels = _listify_arg(channels)
        if wait and callback is not None:
            raise ValueError("Callback provided for awaiting publish")
        pub_coros = [self._mpmc.publish(t_channel, message) for t_channel in channels]
        if wait:
            return _timegate(asyncio.gather(*pub_coros), gate=0.005)
        else:
            if callback:
                for t_coro in pub_coros:
                    asyncio.create_task(t_coro).add_done_callback(lambda x: callback(x.result()))

    @contextlib.asynccontextmanager
    async def acquire_conn(self
    ) -> ty.ContextManager[aioredis.ConnectionsPool]:
        conn: aioredis.RedisConnection = await self.redis.acquire()
        try:
            yield conn
        finally:
            await conn.close()

    def get(self,
            keys=ty.Union[str, ty.Iterable[str]]
    ) -> ty.Union[str, ty.List[str]]:
        if isinstance(keys, ty.Iterable):
            keys = list(keys)
            return self.redis.mget(*keys)
        return self.redis.get(keys)

    def set(self,
            keyval_pairs=ty.Union[ty.Tuple[str, str],
                                  ty.Iterable[ty.Tuple[str, str]],
                                  ty.Dict[str, str]]
    ) -> None:

        if isinstance(keyval_pairs, ty.Iterable):
            keyval_pairs = list(keyval_pairs)
            return self.redis.mset(*keyval_pairs)
        if isinstance(keyval_pairs, ty.Dict):
            keyval_pairs = keyval_pairs.values()
            return self.redis.mset(*keyval_pairs)
        if isinstance(keyval_pairs, ty.Tuple):
            return self.redis.set(*keyval_pairs)

    def set_dict(self, key: str, d: dict):
        flattened_dict = _flatten_dict(d)
        return self.redis.hmset_dict(key, flattened_dict)

    def get_dict(self, key, fields=None):
        if fields:
            flattened_dict = self.redis.hmget(key, fields[0], *fields[1:])
        else:
            flattened_dict = self.redis.hgetall(key)
        return _inflate(flattened_dict)
