"""
Caching decorators for function and API response caching
"""
import functools
import hashlib
import inspect
import json
import logging
from typing import Any, Callable, Dict, Optional, Tuple, Type, Union

from fastapi import Depends, Request
from fastapi.encoders import jsonable_encoder

from src.cache.backends.base import CacheBackend
from src.cache.backends.factory import get_cache_backend
from src.cache.dependencies import get_cache
from src.core.config import settings
from src.core.exceptions import CacheError


logger = logging.getLogger(__name__)


def _get_cache_key(
    prefix: str,
    func_name: str,
    args_dict: Dict[str, Any]
) -> str:
    """
    Generate a cache key from function name and arguments
    """
    # Create a deterministic string representation of args and kwargs
    args_str = json.dumps(args_dict, sort_keys=True, default=str)
    
    # Create a hash of the arguments to keep key length reasonable
    args_hash = hashlib.md5(args_str.encode()).hexdigest()
    
    # Combine function name and args hash into a key
    return f"{prefix}:{func_name}:{args_hash}"


def cached(
    ttl: int = None,
    key_prefix: str = "cache",
    key_builder: Callable = None,
    exclude_keys: Tuple[str, ...] = (
        "self",
        "cls",
        "request",
        "db",
        "cache",
        "redis",
    ),
):
    """
    Decorator for caching function return values in Redis
    
    Args:
        ttl: Time to live in seconds. Defaults to settings.CACHE_TTL_SECONDS.
        key_prefix: Prefix for the cache key to namespace keys
        key_builder: Custom function to build the cache key
        exclude_keys: Parameter names to exclude from key generation
    """    
    def decorator(func):
        # Get function signature for parameter names
        sig = inspect.signature(func)
        func_name = func.__qualname__
        
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Allow callers to pass explicit cache or redis keyword arguments
            cache_backend = kwargs.pop("cache", None)
            if cache_backend is None:
                cache_backend = kwargs.pop("redis", None)
            if cache_backend is None:
                # Use the singleton cache backend
                cache_backend = get_cache_backend()

            # Build a dictionary of all arguments with their parameter names
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            arg_dict = {k: v for k, v in bound_args.arguments.items()
                        if k not in exclude_keys and not isinstance(v, (CacheBackend, Request))}

            # Generate the cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                cache_key = _get_cache_key(key_prefix, func_name, arg_dict)

            cached_value = None
            try:
                cached_value = await cache_backend.get(cache_key)
            except Exception as cache_exc:
                logger.error(f"Cache error during get: {cache_exc}")

            if cached_value is not None:
                logger.debug(f"Cache hit for key: {cache_key}")
                return json.loads(cached_value)

            logger.debug(f"Cache miss for key: {cache_key}")
            result = await func(*args, **kwargs)

            actual_ttl = ttl if ttl is not None else settings.CACHE_TTL_SECONDS
            try:
                serialized = json.dumps(jsonable_encoder(result))
                await cache_backend.set(cache_key, serialized, ex=actual_ttl)
            except Exception as cache_exc:
                logger.error(f"Cache error during set: {cache_exc}")

            return result
                    
        return wrapper
    return decorator


def invalidate_cache(
    key_pattern: str
):
    """
    Decorator for invalidating cache keys matching a pattern
    
    Args:
        key_pattern: Key pattern to match for invalidation (e.g., "user:*")
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # Get cache backend
            cache_backend = get_cache_backend()
            
            # Call the original function first
            result = await func(*args, **kwargs)
            
            # Invalidate matching cache keys
            try:
                # Scan for keys matching the pattern
                cursor = "0"
                deleted_count = 0
                
                while cursor:
                    cursor, keys = await cache_backend.scan(
                        cursor=cursor, 
                        match=key_pattern,
                        count=100
                    )
                    
                    if keys:
                        deleted_count += await cache_backend.delete(*keys)
                        logger.debug(f"Invalidated {len(keys)} cache keys")
                    
                    # Stop if we've completed the scan
                    if cursor == "0":
                        break
                
                logger.info(f"Invalidated {deleted_count} cache keys matching '{key_pattern}'")
            except Exception as e:
                logger.error(f"Cache invalidation error: {str(e)}")
                
            return result
        
        return wrapper
    
    return decorator
