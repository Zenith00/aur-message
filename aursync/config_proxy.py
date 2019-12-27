from aursync.sync import Sync

class _ConfigProxy:

    def __init__(self, sync: Sync, key_root):
        self.key_root: str = key_root
        self.hm_key = ""
        self.sync = sync

    def _verify_redis(self) -> None:
        if not self.sync.ready:
            raise RuntimeError("Sync redis not ready!")
        if not self.sync.redis:
            raise RuntimeError("<???>: Sync is ready but redis is None")
        if self.sync.redis.closed:
            raise RuntimeError("Sync redis is closed!")

    def __setitem__(self, k: flattener.FlatKey, v: str) -> None:
        self._verify_redis()
        self.compose_key(k)

        assert self.sync.redis is not None  # dummy for Mypy
        self.sync.redis.hmset(self.key_root, self.hm_key, v)

    def compose_key(self, k) -> None:
        sep: flattener.FlatContainerType
        sep = list if isinstance(k, int) else dict
        self.hm_key = flattener.compose_keys(self.hm_key, k, sep)

    def __delitem__(self, k: flattener.FlatKey) -> None:
        self._verify_redis()
        self.compose_key(k)

        assert self.sync.redis is not None  # dummy for Mypy
        self.sync.redis.hdel(self.key_root, self.hm_key)

    def __getitem__(self, k: flattener.FlatKey) -> _ConfigProxy:
        self._verify_redis()
        self.compose_key(k)

        assert self.sync.redis is not None  # dummy for  Mypy
        return self

    def __str__(self) -> str:
        assert self.sync.redis is not None  # dummy for  Mypy
        return self.sync.redis.hmget(self.key_root, self.hm_key)