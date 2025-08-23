"""
Performance benchmarks for redisthon components.
"""

import pytest
import time
from unittest.mock import Mock, patch

from redisthon.client import RedisClient
from redisthon import RedisSession


class TestSerializationPerformance:
    """Test serialization performance metrics."""

    @pytest.fixture
    def sample_data(self):
        """Sample data for performance testing."""
        return {
            'session_name': 'performance_test',
            'dc_id': 2,
            'server_address': 'test.telegram.org',
            'port': 443,
            'auth_key': 'base64_encoded_auth_key_data',
            'entities': list(range(100)),  # Simulate entity cache
            'metadata': {
                'version': '0.1.0',
                'timestamp': time.time(),
                'features': ['connection_pooling', 'hash_storage', 'ttl_support']
            }
        }

    def test_msgpack_serialization_speed(self, sample_data):
        """Measure msgpack serialization performance."""
        with patch('redis.Redis'):
            client = RedisClient()

        iterations = 1000
        start_time = time.perf_counter()

        for _ in range(iterations):
            serialized = client.serialize(sample_data)
            deserialized = client.deserialize(serialized)

        duration = time.perf_counter() - start_time
        ops_per_second = iterations / duration

        # Performance should be reasonable
        assert ops_per_second > 1000, f"Serialization too slow: {ops_per_second:.0f} ops/sec"
        assert duration < 5.0, f"Total time too long: {duration:.3f}s"

        # Verify data integrity
        assert deserialized == sample_data

    def test_serialization_data_size(self, sample_data):
        """Measure serialized data size efficiency."""
        with patch('redis.Redis'):
            client = RedisClient()

        serialized = client.serialize(sample_data)

        # Serialized data should be reasonably compact
        assert len(serialized) < 2000, f"Serialized data too large: {len(serialized)} bytes"
        assert len(serialized) > 0, "Serialized data is empty"


class TestRedisOperationsPerformance:
    """Test Redis operations performance."""

    @pytest.fixture
    def mock_client_with_timing(self):
        """Create mock client that tracks operation timing."""
        with patch('redis.Redis') as mock_redis_class:
            mock_redis_instance = Mock()

            # Add timing to mock operations
            def timed_operation(operation_name):
                def wrapper(*args, **kwargs):
                    time.sleep(0.001)  # Simulate small delay
                    return b'test_data' if 'get' in operation_name else None
                return wrapper

            mock_redis_instance.set = timed_operation('set')
            mock_redis_instance.get = timed_operation('get')
            mock_redis_instance.hset = timed_operation('hset')
            mock_redis_instance.hget = timed_operation('hget')
            mock_redis_instance.ping.return_value = True

            mock_redis_class.return_value = mock_redis_instance

            client = RedisClient()
            return client

    def test_basic_operations_speed(self, mock_client_with_timing):
        """Test speed of basic Redis operations."""
        client = mock_client_with_timing
        test_data = {'key': 'value', 'number': 12345}

        iterations = 100
        start_time = time.perf_counter()

        for i in range(iterations):
            key = f'test_key_{i}'
            client.set_key(key, test_data)
            retrieved = client.get_key(key)

        duration = time.perf_counter() - start_time
        ops_per_second = (iterations * 2) / duration  # 2 ops per iteration

        # Should handle reasonable throughput
        assert ops_per_second > 100, f"Operations too slow: {ops_per_second:.0f} ops/sec"

    def test_hash_operations_speed(self, mock_client_with_timing):
        """Test speed of hash operations."""
        client = mock_client_with_timing
        test_data = {'entity_id': 123456, 'access_hash': 789012}

        iterations = 100
        start_time = time.perf_counter()

        for i in range(iterations):
            field = f'entity_{i}'
            client.hash_set('entities', field, test_data)
            retrieved = client.hash_get('entities', field)

        duration = time.perf_counter() - start_time
        ops_per_second = (iterations * 2) / duration

        # Hash operations should be efficient
        assert ops_per_second > 100, f"Hash operations too slow: {ops_per_second:.0f} ops/sec"


class TestSessionPerformance:
    """Test session operations performance."""

    @pytest.fixture
    def fast_mock_client(self):
        """Create optimized mock client for session testing."""
        mock_client = Mock(spec=RedisClient)
        mock_client.ping.return_value = True
        mock_client.serialize.side_effect = lambda x: str(x).encode()
        mock_client.deserialize.side_effect = lambda x: eval(x.decode()) if isinstance(x, bytes) else x
        mock_client.get_key.return_value = None
        mock_client.set_key.return_value = None
        mock_client.hash_get.return_value = None
        mock_client.hash_set.return_value = None
        mock_client.key_exists.return_value = False
        mock_client.hash_len.return_value = 0
        return mock_client

    def test_session_creation_speed(self, fast_mock_client):
        """Test session creation performance."""
        iterations = 100
        start_time = time.perf_counter()

        sessions = []
        for i in range(iterations):
            session = RedisSession(f'test_session_{i}', redis_client=fast_mock_client)
            sessions.append(session)

        duration = time.perf_counter() - start_time
        creations_per_second = iterations / duration

        # Session creation should be fast
        assert creations_per_second > 50, f"Session creation too slow: {creations_per_second:.0f}/sec"
        assert duration < 10.0, f"Total creation time too long: {duration:.3f}s"

    def test_session_save_load_speed(self, fast_mock_client):
        """Test session save/load performance."""
        session = RedisSession('perf_test', redis_client=fast_mock_client)

        iterations = 50
        start_time = time.perf_counter()

        for i in range(iterations):
            # Simulate setting DC info and saving
            session.set_dc(2, f'server_{i}.telegram.org', 443)

            # Simulate loading (get health info triggers some operations)
            health = session.get_health_info()
            stats = session.get_statistics()

        duration = time.perf_counter() - start_time
        operations_per_second = (iterations * 4) / duration  # 4 ops per iteration

        # Session operations should be reasonably fast
        assert operations_per_second > 20, f"Session ops too slow: {operations_per_second:.0f}/sec"


class TestMemoryUsage:
    """Test memory efficiency of redisthon components."""

    def test_session_memory_efficiency(self):
        """Test that sessions use __slots__ for memory efficiency."""
        # Check that RedisSession uses __slots__
        assert hasattr(RedisSession, '__slots__'), "RedisSession should use __slots__ for memory efficiency"

        # Check RedisClient uses __slots__
        assert hasattr(RedisClient, '__slots__'), "RedisClient should use __slots__ for memory efficiency"

    def test_multiple_sessions_memory(self, fast_mock_client):
        """Test memory usage with multiple sessions."""
        sessions = []

        # Create multiple sessions
        for i in range(10):
            session = RedisSession(f'session_{i}', redis_client=fast_mock_client)
            session.set_dc(i + 1, f'server_{i}.telegram.org', 443)
            sessions.append(session)

        # Verify all sessions are functional
        for session in sessions:
            assert session.dc_id is not None
            health = session.get_health_info()
            assert health['session_name'].startswith('session_')


class TestScalability:
    """Test scalability characteristics."""

    def test_concurrent_session_operations(self, fast_mock_client):
        """Test handling multiple concurrent-like operations."""
        session = RedisSession('scalability_test', redis_client=fast_mock_client)

        # Simulate concurrent-like workload
        operations = []
        start_time = time.perf_counter()

        # Mix of different operations
        for i in range(20):
            session.set_dc(2, 'test.telegram.org', 443)
            health = session.get_health_info()
            stats = session.get_statistics()
            operations.extend(['set_dc', 'health_info', 'statistics'])

        duration = time.perf_counter() - start_time

        # Should handle mixed workload efficiently
        assert len(operations) == 60  # 3 ops × 20 iterations
        assert duration < 2.0, f"Mixed workload took too long: {duration:.3f}s"

    def test_large_entity_cache_performance(self, fast_mock_client):
        """Test performance with large entity cache simulation."""
        session = RedisSession('large_cache_test', redis_client=fast_mock_client)

        # Simulate looking up entities in large cache
        entity_lookups = 1000
        start_time = time.perf_counter()

        for entity_id in range(entity_lookups):
            result = session.get_entity_rows_by_id(entity_id)
            # Result will be empty since we're using mock, but operation completes

        duration = time.perf_counter() - start_time
        lookups_per_second = entity_lookups / duration

        # Entity lookups should be fast (O(1) with Redis Hash)
        assert lookups_per_second > 500, f"Entity lookups too slow: {lookups_per_second:.0f}/sec"


@pytest.mark.benchmark
class TestBenchmarkSuite:
    """Comprehensive benchmark suite for redisthon."""

    def test_end_to_end_performance(self, fast_mock_client):
        """End-to-end performance test simulating real usage."""
        # Create session
        session = RedisSession('e2e_test', redis_client=fast_mock_client)

        start_time = time.perf_counter()

        # Typical Telethon session usage pattern
        session.set_dc(2, 'test.telegram.org', 443)

        # Simulate entity processing (would be called by Telethon)
        for entity_id in range(10):
            # Simulate cached entity data
            session._client.hash_set.return_value = None

        # Simulate entity lookups
        for entity_id in range(10):
            session.get_entity_rows_by_id(entity_id)

        # Get session info
        health = session.get_health_info()
        stats = session.get_statistics()

        duration = time.perf_counter() - start_time

        # End-to-end should complete quickly
        assert duration < 1.0, f"End-to-end test took too long: {duration:.3f}s"
        assert health['connection_healthy'] is True
        assert 'session_name' in stats

        # Clean up
        session.close()

    def test_serialization_metrics(self):
        """Test serialization performance metrics."""
        with patch('redis.Redis'):
            client = RedisClient()

        # Test data preparation
        test_data = {'key': f'value_{i}' for i in range(100)}

        # Measure serialization performance
        start_time = time.perf_counter()
        serialized = client.serialize(test_data)
        serialization_time = time.perf_counter() - start_time

        # Measure deserialization performance
        start_time = time.perf_counter()
        deserialized = client.deserialize(serialized)
        deserialization_time = time.perf_counter() - start_time

        # Collect metrics
        metrics = {
            'data_size_original': len(str(test_data)),
            'data_size_serialized': len(serialized),
            'compression_ratio': len(str(test_data)) / len(serialized),
            'serialization_time_ms': serialization_time * 1000,
            'deserialization_time_ms': deserialization_time * 1000,
        }

        # Verify metrics are reasonable
        assert metrics['compression_ratio'] > 0.5, "Compression ratio should be meaningful"
        assert metrics['serialization_time_ms'] < 100, "Serialization should be fast"
        assert metrics['deserialization_time_ms'] < 100, "Deserialization should be fast"
        assert deserialized == test_data, "Data integrity should be maintained"
