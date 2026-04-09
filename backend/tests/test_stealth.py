import pytest

from app.scraper.stealth import (
    USER_AGENTS,
    ProxyPool,
    get_random_delay,
    get_random_user_agent,
)


class TestUserAgent:
    """Test user agent rotation functionality."""

    def test_get_random_user_agent_returns_string(self):
        """Test that get_random_user_agent returns a string."""
        ua = get_random_user_agent()
        assert isinstance(ua, str)
        assert len(ua) > 0

    def test_get_random_user_agent_returns_valid_ua(self):
        """Test that get_random_user_agent returns a valid UA from the list."""
        ua = get_random_user_agent()
        assert ua in USER_AGENTS

    def test_get_random_user_agent_varies(self):
        """Test that get_random_user_agent returns different values."""
        uas = [get_random_user_agent() for _ in range(50)]
        # Check that we got at least 2 different UAs in 50 tries
        # (statistically very likely with 12 choices)
        assert len(set(uas)) > 1

    def test_user_agents_list_has_12_items(self):
        """Test that USER_AGENTS list contains 12 items."""
        assert len(USER_AGENTS) == 12


class TestRandomDelay:
    """Test random delay functionality."""

    def test_get_random_delay_in_range(self):
        """Test that get_random_delay returns values in the specified range."""
        min_s, max_s = 1.0, 3.0
        delays = [get_random_delay(min_s, max_s) for _ in range(100)]

        for delay in delays:
            assert isinstance(delay, float)
            assert min_s <= delay <= max_s

    def test_get_random_delay_custom_range(self):
        """Test get_random_delay with custom range."""
        min_s, max_s = 0.5, 2.0
        delays = [get_random_delay(min_s, max_s) for _ in range(50)]

        for delay in delays:
            assert min_s <= delay <= max_s

    def test_get_random_delay_varies(self):
        """Test that get_random_delay returns different values."""
        delays = [get_random_delay() for _ in range(50)]
        # Check that we got different values (floating point comparison)
        unique_delays = len(set(delays))
        assert unique_delays > 1


class TestProxyPool:
    """Test proxy pool functionality."""

    def test_proxy_pool_next_round_robin(self):
        """Test that next() rotates through proxies in round-robin order."""
        proxies = ["proxy1", "proxy2", "proxy3"]
        pool = ProxyPool(proxies)

        # Check round-robin cycling
        assert pool.next() == "proxy1"
        assert pool.next() == "proxy2"
        assert pool.next() == "proxy3"
        assert pool.next() == "proxy1"  # Back to start
        assert pool.next() == "proxy2"

    def test_proxy_pool_random(self):
        """Test that random() returns a proxy from the pool."""
        proxies = ["proxy1", "proxy2", "proxy3"]
        pool = ProxyPool(proxies)

        # Get several random proxies
        random_proxies = [pool.random() for _ in range(50)]

        # All should be in the original list
        for proxy in random_proxies:
            assert proxy in proxies

        # Should get at least 2 different proxies in 50 tries
        assert len(set(random_proxies)) > 1

    def test_proxy_pool_empty_next(self):
        """Test that next() returns None for empty pool."""
        pool = ProxyPool([])
        assert pool.next() is None

    def test_proxy_pool_empty_random(self):
        """Test that random() returns None for empty pool."""
        pool = ProxyPool([])
        assert pool.random() is None

    def test_proxy_pool_single_proxy(self):
        """Test proxy pool with a single proxy."""
        pool = ProxyPool(["only_proxy"])

        assert pool.next() == "only_proxy"
        assert pool.next() == "only_proxy"
        assert pool.random() == "only_proxy"
