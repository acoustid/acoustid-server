import json
from typing import List, Dict, Optional, Any
from redis import Redis


class CacheBackend(object):

    def __init__(self):
        pass

    def get(self, key):
        # type: (str) -> Optional[str]
        return None

    def get_multi(self, keys):
        # type: (List[str]) -> Dict[str, str]
        results = {}
        for key in keys:
            value = self.get(key)
            if value is not None:
                results[key] = value
        return results

    def set(self, key, value, ttl):
        # type: (str, str, Optional[int]) -> None
        pass

    def set_multi(self, items, ttl):
        # type: (Dict[str, str], Optional[int]) -> None
        for key, value in items.items():
            self.set(key, value, ttl)

    def delete(self, key):
        # type: (str) -> None
        pass

    def delete_multi(self, keys):
        # type: (List[str]) -> None
        for key in keys:
            self.delete(key)


class Cache(object):

    def __init__(self, backend, prefix=None, ttl=None):
        # type: (CacheBackend, Optional[str], Optional[int]) -> None
        self.backend = backend
        self.prefix = prefix
        self.ttl = ttl

    def _dumps_value(self, value):
        # type: (Any) -> str
        return json.dumps(value)

    def _loads_value(self, data):
        # type: (Optional[str]) -> Any
        if data is None:
            return None
        return json.loads(data)

    def _add_prefix(self, key):
        if self.prefix is not None:
            return self.prefix + key
        return key

    def _strip_prefix(self, key):
        if self.prefix is not None:
            return key[len(self.prefix):]
        return key

    def get(self, key):
        # type: (str) -> Any
        value = self.backend.get(self._add_prefix(key))
        return self._loads_value(value)

    def get_multi(self, keys):
        # type: (List[str]) -> Dict[str, Any]
        results = self.backend.get_multi([self._add_prefix(k) for k in keys])
        return dict((self._strip_prefix(key), self._loads_value(value)) for (key, value) in results.items())

    def set(self, key, value):
        # type: (str, Any) -> None
        self.backend.set(self._add_prefix(key), self._dumps_value(value), self.ttl)

    def set_multi(self, items):
        # type: (Dict[str, Any]) -> None
        data_items = dict((self._add_prefix(key), self._dumps_value(value)) for (key, value) in items.items())
        self.backend.set_multi(data_items, self.ttl)

    def delete(self, key):
        # type: (str) -> None
        self.backend.delete(self._add_prefix(key))

    def delete_multi(self, keys):
        # type: (List[str]) -> None
        self.backend.delete_multi([self._add_prefix(key) for key in keys])


class RedisCacheBackend(CacheBackend):

    def __init__(self, redis):
        # type: (Redis) -> None
        self.redis = redis

    def get(self, key):
        # type: (str) -> Optional[str]
        return self.redis.get(key)

    def get_multi(self, keys):
        # type: (List[str]) -> Dict[str, str]
        values = self.redis.mget(keys)
        return dict((key, value) for (key, value) in zip(keys, values) if value is not None)

    def set(self, key, value, ttl):
        # type: (str, str, Optional[int]) -> None
        if ttl is None:
            self.redis.set(key, value)
        else:
            self.redis.setex(key, ttl, value)

    def delete(self, key):
        # type: (str) -> None
        self.redis.delete(key)
