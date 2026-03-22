"""Tests for rate_limiter.py."""

import time


def test_token_bucket_basic():
    from src.core.rate_limiter import TokenBucketRateLimiter

    rl = TokenBucketRateLimiter(max_tokens=5, refill_period=60.0, name="test")
    # Should be able to acquire 5 tokens immediately
    for _ in range(5):
        assert rl.try_acquire() is True
    # 6th should fail (bucket empty)
    assert rl.try_acquire() is False


def test_token_bucket_refill():
    from src.core.rate_limiter import TokenBucketRateLimiter

    rl = TokenBucketRateLimiter(max_tokens=10, refill_period=1.0, name="test_refill")
    # Drain all tokens
    for _ in range(10):
        rl.try_acquire()
    assert rl.try_acquire() is False
    # Wait for refill (at 10 tokens / 1 sec, each token takes 0.1s)
    time.sleep(0.15)
    assert rl.try_acquire() is True


def test_acquire_blocking():
    from src.core.rate_limiter import TokenBucketRateLimiter

    rl = TokenBucketRateLimiter(max_tokens=2, refill_period=1.0, name="test_block")
    assert rl.acquire(timeout=1.0) is True
    assert rl.acquire(timeout=1.0) is True
    # 3rd acquire should block until refill, then succeed
    t0 = time.monotonic()
    assert rl.acquire(timeout=2.0) is True
    elapsed = time.monotonic() - t0
    assert elapsed > 0.1  # had to wait for refill


def test_acquire_timeout():
    from src.core.rate_limiter import TokenBucketRateLimiter

    rl = TokenBucketRateLimiter(max_tokens=1, refill_period=60.0, name="test_timeout")
    rl.try_acquire()  # drain
    # Should timeout quickly
    assert rl.acquire(timeout=0.2) is False


def test_available_tokens():
    from src.core.rate_limiter import TokenBucketRateLimiter

    rl = TokenBucketRateLimiter(max_tokens=10, refill_period=60.0, name="test_avail")
    assert rl.available_tokens == 10.0
    rl.try_acquire()
    assert rl.available_tokens < 10.0


def test_module_level_singletons():
    from src.core.rate_limiter import finnhub_limiter, anthropic_limiter

    assert finnhub_limiter.max_tokens == 55
    assert anthropic_limiter.max_tokens == 40
