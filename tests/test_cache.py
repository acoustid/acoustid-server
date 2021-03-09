# Copyright (C) 2011 Lukas Lalinsky
# Distributed under the MIT license, see the LICENSE file for details.

import uuid

from nose.tools import assert_equal
from tests import with_script_context

from acoustid.script import ScriptContext
from acoustid.cache import Cache, RedisCacheBackend


@with_script_context
def test_redis_cache(ctx):
    # type: (ScriptContext) -> None
    prefix = '{}:'.format(uuid.uuid1())
    cache = Cache(RedisCacheBackend(ctx.redis), prefix=prefix, ttl=60)

    assert_equal(cache.get('foo'), None)
    assert_equal(cache.get_multi(['foo', 'bar']), {})

    cache.set('foo', '1')
    assert_equal(cache.get('foo'), '1')
    assert_equal(cache.get_multi(['foo', 'bar']), {'foo': '1'})

    cache.set_multi({'bar': '2'})
    assert_equal(cache.get('bar'), '2')
    assert_equal(cache.get_multi(['foo', 'bar']), {'foo': '1', 'bar': '2'})

    cache.delete('foo')
    assert_equal(cache.get('foo'), None)
    assert_equal(cache.get_multi(['foo', 'bar']), {'bar': '2'})

    cache.delete_multi(['bar'])
    assert_equal(cache.get('bar'), None)
    assert_equal(cache.get_multi(['foo', 'bar']), {})


@with_script_context
def test_redis_cache_with_prefix(ctx):
    # type: (ScriptContext) -> None
    prefix = '{}:'.format(uuid.uuid1())
    cache = Cache(RedisCacheBackend(ctx.redis), prefix=prefix, ttl=60)

    prefixed_cache = cache.with_prefix('x:')

    assert_equal(prefixed_cache.get('foo'), None)
    assert_equal(prefixed_cache.get_multi(['foo', 'bar']), {})

    prefixed_cache.set('foo', '1')
    assert_equal(cache.get('x:foo'), '1')
    assert_equal(prefixed_cache.get('foo'), '1')
    assert_equal(prefixed_cache.get_multi(['foo', 'bar']), {'foo': '1'})

    prefixed_cache.set_multi({'bar': '2'})
    assert_equal(cache.get('x:bar'), '2')
    assert_equal(prefixed_cache.get('bar'), '2')
    assert_equal(prefixed_cache.get_multi(['foo', 'bar']), {'foo': '1', 'bar': '2'})

    prefixed_cache.delete('foo')
    assert_equal(cache.get('x:foo'), None)
    assert_equal(prefixed_cache.get('foo'), None)
    assert_equal(prefixed_cache.get_multi(['foo', 'bar']), {'bar': '2'})

    prefixed_cache.delete_multi(['bar'])
    assert_equal(cache.get('x:bar'), None)
    assert_equal(prefixed_cache.get('bar'), None)
    assert_equal(prefixed_cache.get_multi(['foo', 'bar']), {})
