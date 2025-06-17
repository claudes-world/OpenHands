"""Rate limiting middleware for multi-user support."""

import time
from typing import Any, Optional

import redis.asyncio as redis
from fastapi import Request, status
from fastapi.responses import JSONResponse

from features.multiuser.config.multi_user_config import MultiUserConfig


class RateLimiter:
    """Redis-based rate limiter for multi-user API endpoints."""

    def __init__(
        self, config: MultiUserConfig, redis_client: Optional[redis.Redis] = None
    ):
        self.config = config
        self.redis_client = redis_client
        self._fallback_store: dict[str, dict[str, Any]] = {}

    async def _get_redis_client(self) -> Optional[redis.Redis]:
        """Get Redis client for rate limiting storage."""
        if self.redis_client:
            return self.redis_client

        # Try to create Redis client if not provided
        try:
            client = redis.from_url('redis://localhost:6379', decode_responses=True)
            await client.ping()
            return client
        except Exception:
            # Fall back to in-memory storage
            return None

    async def is_rate_limited(
        self, user_id: str, endpoint: str = 'default'
    ) -> tuple[bool, dict[str, Any]]:
        """Check if user is rate limited for the given endpoint.

        Returns:
            tuple: (is_limited, rate_limit_info)
        """
        redis_client = await self._get_redis_client()

        # Define rate limits
        per_minute_limit = self.config.rate_limit_per_minute
        per_hour_limit = self.config.rate_limit_per_hour

        current_time = int(time.time())
        minute_window = current_time // 60
        hour_window = current_time // 3600

        minute_key = f'rate_limit:{user_id}:{endpoint}:minute:{minute_window}'
        hour_key = f'rate_limit:{user_id}:{endpoint}:hour:{hour_window}'

        if redis_client:
            # Use Redis for distributed rate limiting
            try:
                # Check and increment counters atomically
                pipe = redis_client.pipeline()

                # Minute window
                pipe.get(minute_key)
                pipe.incr(minute_key)
                pipe.expire(minute_key, 60)

                # Hour window
                pipe.get(hour_key)
                pipe.incr(hour_key)
                pipe.expire(hour_key, 3600)

                results = await pipe.execute()

                minute_count = int(results[1]) if results[1] else 1
                hour_count = int(results[4]) if results[4] else 1

                minute_exceeded = minute_count > per_minute_limit
                hour_exceeded = hour_count > per_hour_limit

                is_limited = minute_exceeded or hour_exceeded

                rate_limit_info = {
                    'minute_count': minute_count,
                    'minute_limit': per_minute_limit,
                    'minute_reset': (minute_window + 1) * 60,
                    'hour_count': hour_count,
                    'hour_limit': per_hour_limit,
                    'hour_reset': (hour_window + 1) * 3600,
                    'retry_after': min(
                        60 - (current_time % 60) if minute_exceeded else float('inf'),
                        3600 - (current_time % 3600) if hour_exceeded else float('inf'),
                    ),
                }

                return is_limited, rate_limit_info

            except Exception:
                # Fall through to in-memory implementation
                pass

        # Fallback to in-memory rate limiting
        return await self._in_memory_rate_limit(
            user_id, endpoint, per_minute_limit, per_hour_limit, current_time
        )

    async def _in_memory_rate_limit(
        self,
        user_id: str,
        endpoint: str,
        per_minute_limit: int,
        per_hour_limit: int,
        current_time: int,
    ) -> tuple[bool, dict[str, Any]]:
        """In-memory rate limiting fallback."""
        minute_window = current_time // 60
        hour_window = current_time // 3600

        key = f'{user_id}:{endpoint}'

        if key not in self._fallback_store:
            self._fallback_store[key] = {
                'minute_window': minute_window,
                'minute_count': 0,
                'hour_window': hour_window,
                'hour_count': 0,
            }

        user_data = self._fallback_store[key]

        # Reset counters if window changed
        if user_data['minute_window'] != minute_window:
            user_data['minute_window'] = minute_window
            user_data['minute_count'] = 0

        if user_data['hour_window'] != hour_window:
            user_data['hour_window'] = hour_window
            user_data['hour_count'] = 0

        # Increment counters
        user_data['minute_count'] += 1
        user_data['hour_count'] += 1

        minute_exceeded = user_data['minute_count'] > per_minute_limit
        hour_exceeded = user_data['hour_count'] > per_hour_limit

        is_limited = minute_exceeded or hour_exceeded

        rate_limit_info = {
            'minute_count': user_data['minute_count'],
            'minute_limit': per_minute_limit,
            'minute_reset': (minute_window + 1) * 60,
            'hour_count': user_data['hour_count'],
            'hour_limit': per_hour_limit,
            'hour_reset': (hour_window + 1) * 3600,
            'retry_after': min(
                60 - (current_time % 60) if minute_exceeded else float('inf'),
                3600 - (current_time % 3600) if hour_exceeded else float('inf'),
            ),
        }

        return is_limited, rate_limit_info

    async def cleanup_expired_keys(self):
        """Clean up expired in-memory rate limit data."""
        current_time = int(time.time())
        current_hour = current_time // 3600

        expired_keys = []
        for key, data in self._fallback_store.items():
            # Remove data older than 2 hours
            if data.get('hour_window', 0) < current_hour - 2:
                expired_keys.append(key)

        for key in expired_keys:
            del self._fallback_store[key]


class RateLimitMiddleware:
    """FastAPI middleware for rate limiting."""

    def __init__(
        self, config: MultiUserConfig, redis_client: Optional[redis.Redis] = None
    ):
        self.rate_limiter = RateLimiter(config, redis_client)
        self.config = config

    async def __call__(self, request: Request, call_next):
        """Process request with rate limiting."""
        # Skip rate limiting if not enabled
        if not self.config.enabled:
            return await call_next(request)

        # Extract user ID from request (this assumes JWT auth is already processed)
        user_id = getattr(request.state, 'user_id', None)

        if not user_id:
            # No user ID - skip rate limiting for unauthenticated requests
            return await call_next(request)

        # Determine endpoint for rate limiting
        endpoint = f'{request.method}:{request.url.path}'

        # Check rate limit
        is_limited, rate_info = await self.rate_limiter.is_rate_limited(
            user_id, endpoint
        )

        if is_limited:
            # Return rate limit exceeded response
            retry_after = int(rate_info.get('retry_after', 60))

            headers = {
                'X-RateLimit-Limit-Minute': str(rate_info['minute_limit']),
                'X-RateLimit-Remaining-Minute': str(
                    max(0, rate_info['minute_limit'] - rate_info['minute_count'])
                ),
                'X-RateLimit-Reset-Minute': str(rate_info['minute_reset']),
                'X-RateLimit-Limit-Hour': str(rate_info['hour_limit']),
                'X-RateLimit-Remaining-Hour': str(
                    max(0, rate_info['hour_limit'] - rate_info['hour_count'])
                ),
                'X-RateLimit-Reset-Hour': str(rate_info['hour_reset']),
                'Retry-After': str(retry_after),
            }

            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                headers=headers,
                content={
                    'detail': 'Rate limit exceeded',
                    'retry_after': retry_after,
                    'limits': {
                        'minute': {
                            'limit': rate_info['minute_limit'],
                            'remaining': max(
                                0, rate_info['minute_limit'] - rate_info['minute_count']
                            ),
                            'reset': rate_info['minute_reset'],
                        },
                        'hour': {
                            'limit': rate_info['hour_limit'],
                            'remaining': max(
                                0, rate_info['hour_limit'] - rate_info['hour_count']
                            ),
                            'reset': rate_info['hour_reset'],
                        },
                    },
                },
            )

        # Process request normally
        response = await call_next(request)

        # Add rate limit headers to response
        response.headers['X-RateLimit-Limit-Minute'] = str(rate_info['minute_limit'])
        response.headers['X-RateLimit-Remaining-Minute'] = str(
            max(0, rate_info['minute_limit'] - rate_info['minute_count'])
        )
        response.headers['X-RateLimit-Reset-Minute'] = str(rate_info['minute_reset'])
        response.headers['X-RateLimit-Limit-Hour'] = str(rate_info['hour_limit'])
        response.headers['X-RateLimit-Remaining-Hour'] = str(
            max(0, rate_info['hour_limit'] - rate_info['hour_count'])
        )
        response.headers['X-RateLimit-Reset-Hour'] = str(rate_info['hour_reset'])

        return response
