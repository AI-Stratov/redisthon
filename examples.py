"""
Usage examples for redisthon - Redis/Dragonfly session storage for Telethon.

Shows usage patterns with the modular architecture.
"""

import asyncio
import logging
from typing import Optional

from telethon import TelegramClient
from redisthon import RedisSession, RedisClient
from redisthon.exceptions import ConnectionError, SessionError

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def basic_usage_example():
    """Basic usage with automatic configuration."""
    try:
        # Simple usage with defaults - Redis on localhost:6379
        with RedisSession('my_telegram_session') as session:
            client = TelegramClient(session, api_id=123456, api_hash='your_api_hash')

            async with client:
                me = await client.get_me()
                logger.info(f'Connected as {me.username}')

                # Session automatically persists to Redis
                logger.info(f'Session DC: {session.dc_id}')

        logger.info('Session closed automatically')

    except SessionError as e:
        logger.error(f'Session error: {e.message}')
    except Exception as e:
        logger.error(f'Unexpected error: {e}')


async def advanced_configuration_example():
    """Advanced configuration with custom Redis settings."""
    try:
        # Production configuration
        session = RedisSession(
            session_name='production_session',
            host='redis.company.com',
            port=6379,
            password='secure_password',
            username='app_user',
            max_connections=100,
            socket_keepalive=True,
            connection_timeout=10,
            ttl_seconds=86400 * 7,  # 1 week TTL
            save_entities=True,
        )

        # Check connection health before using
        health = session.get_health_info()
        if not health['connection_healthy']:
            raise ConnectionError(f"Redis connection failed: {health.get('error')}")

        with session:
            client = TelegramClient(session, api_id=123456, api_hash='your_api_hash')

            async with client:
                me = await client.get_me()
                logger.info(f'Session for {me.username}')

                # Get statistics
                stats = session.get_statistics()
                logger.info(f"Cached entities: {stats['entities_count']}")
                logger.info(f"Cached files: {stats['sent_files_count']}")

    except Exception as e:
        logger.error(f'Advanced configuration failed: {e}')


async def dragonfly_example():
    """Example with Dragonfly."""
    try:
        # Dragonfly configuration
        session = RedisSession(
            session_name='dragonfly_session',
            host='localhost',
            port=6380,  # Common Dragonfly port
            is_dragonfly=True,
            max_connections=200,  # Dragonfly handles more connections
            ttl_seconds=0,  # No TTL for persistent storage
        )

        with session:
            # Verify we're using Dragonfly
            health = session.get_health_info()
            server_info = health.get('server_info', {})
            logger.info(f"Using Dragonfly: {server_info.get('is_dragonfly', False)}")

            client = TelegramClient(session, api_id=123456, api_hash='your_api_hash')

            async with client:
                dialogs = await client.get_dialogs(limit=1000)
                logger.info(f'Loaded {len(dialogs)} dialogs with Dragonfly')

    except Exception as e:
        logger.error(f'Dragonfly example failed: {e}')


def custom_redis_client_example():
    """Example with custom Redis client configuration."""
    try:
        # Create custom Redis client with specific settings
        redis_client = RedisClient(
            host='localhost',
            port=6379,
            max_connections=50,
            socket_keepalive=True,
            socket_keepalive_options={
                'TCP_KEEPIDLE': 600,
                'TCP_KEEPINTVL': 60,
                'TCP_KEEPCNT': 3
            },
            connection_timeout=5,
        )

        # Test connection
        if not redis_client.ping():
            logger.error("Redis client connection failed")
            return

        # Use custom client with session
        with RedisSession('custom_client_session', redis_client=redis_client) as session:
            # Get client information
            client_info = redis_client.get_client_info()
            logger.info(f"Client config: {client_info}")

            server_info = redis_client.get_info()
            logger.info(f"Server version: {server_info.get('redis_version')}")

            # Use session normally
            health = session.get_health_info()
            logger.info(f"Session health: {health['connection_healthy']}")

    except Exception as e:
        logger.error(f'Custom client example failed: {e}')


async def error_handling_example():
    """Error handling patterns."""
    session: Optional[RedisSession] = None

    try:
        # Attempt to create session with error handling
        session = RedisSession(
            'error_handling_test',
            host='localhost',
            port=6379,
            connection_timeout=3,
        )

        # Pre-flight checks
        health = session.get_health_info()
        if not health['connection_healthy']:
            error_msg = health.get('error', 'Unknown connection error')
            raise ConnectionError(f"Pre-flight check failed: {error_msg}")

        logger.info("Session created and validated successfully")

        with session:
            try:
                client = TelegramClient(session, api_id=123456, api_hash='your_api_hash')

                async with client:
                    me = await client.get_me()
                    logger.info(f'Connected as {me.username}')

            except Exception as telethon_error:
                logger.error(f'Telethon operation failed: {telethon_error}')
                # Session data is still preserved in Redis

    except ConnectionError as e:
        logger.error(f'Redis connection error: {e.message}')
        if e.details:
            logger.error(f'Connection details: {e.details}')
    except SessionError as e:
        logger.error(f'Session error: {e.message}')
    except Exception as e:
        logger.error(f'Unexpected error: {e}')
    finally:
        if session:
            try:
                session.close()
                logger.info("Session closed gracefully")
            except Exception as cleanup_error:
                logger.warning(f'Cleanup error: {cleanup_error}')


def monitoring_example():
    """Example of monitoring and observability."""
    try:
        session = RedisSession('monitoring_test')

        # Collect metrics
        health = session.get_health_info()
        stats = session.get_statistics()

        # Server health metrics
        server_info = health.get('server_info', {})
        logger.info("=== Server Health ===")
        logger.info(f"Connection: {'✓' if health['connection_healthy'] else '✗'}")
        logger.info(f"Redis version: {server_info.get('redis_version', 'unknown')}")
        logger.info(f"Connected clients: {server_info.get('connected_clients', 0)}")
        logger.info(f"Memory usage: {server_info.get('used_memory_human', 'unknown')}")
        logger.info(f"Serializer: {server_info.get('serializer', 'unknown')}")

        # Session statistics
        logger.info("=== Session Statistics ===")
        logger.info(f"Session exists: {stats.get('session_exists', False)}")
        logger.info(f"Entities cached: {stats.get('entities_count', 0)}")
        logger.info(f"Update states: {stats.get('update_states_count', 0)}")
        logger.info(f"Files cached: {stats.get('sent_files_count', 0)}")
        logger.info(f"Has auth key: {stats.get('has_auth_key', False)}")
        logger.info(f"Data center: {stats.get('dc_id', 'none')}")

        # Configuration info
        settings = health.get('settings', {})
        logger.info("=== Configuration ===")
        logger.info(f"TTL: {settings.get('ttl_seconds', 0)}s")
        logger.info(f"Save entities: {settings.get('save_entities', False)}")

        session.close()

    except Exception as e:
        logger.error(f'Monitoring example failed: {e}')


async def performance_testing_example():
    """Example of performance testing patterns."""
    try:
        session = RedisSession('performance_test')

        with session:
            # Test basic operations speed
            import time

            # Measure session operations
            start_time = time.perf_counter()

            for i in range(10):
                session.set_dc(2, f'server_{i}.telegram.org', 443)
                health = session.get_health_info()
                stats = session.get_statistics()

            duration = time.perf_counter() - start_time
            ops_per_second = 30 / duration  # 3 ops × 10 iterations

            logger.info("=== Performance Metrics ===")
            logger.info(f"Operations/second: {ops_per_second:.0f}")
            logger.info(f"Average operation time: {(duration/30)*1000:.2f}ms")

            # Test serialization performance
            client_info = session._client.get_client_info()
            logger.info(f"Serializer: {client_info.get('serializer', 'unknown')}")

            # Measure serialization speed
            test_data = {'key': i for i in range(100)}

            start_time = time.perf_counter()
            for _ in range(1000):
                serialized = session._client.serialize(test_data)
                deserialized = session._client.deserialize(serialized)
            duration = time.perf_counter() - start_time

            logger.info(f"Serialization speed: {2000/duration:.0f} ops/sec")
            logger.info(f"Data size: {len(serialized)} bytes")

    except Exception as e:
        logger.error(f'Performance testing failed: {e}')


def configuration_validation_example():
    """Example of configuration validation."""
    # Production-ready configuration template
    production_config = {
        'session_name': 'production_app_v1',
        'host': 'redis-cluster.company.com',
        'port': 6379,
        'password': 'secure_redis_password',
        'username': 'redisthon_user',
        'max_connections': 100,
        'socket_keepalive': True,
        'connection_timeout': 10,
        'ttl_seconds': 86400 * 30,  # 30 days
        'save_entities': True,
        'key_prefix': 'myapp:sessions',
    }

    # Development configuration
    development_config = {
        'session_name': 'dev_session',
        'host': 'localhost',
        'port': 6379,
        'max_connections': 10,
        'ttl_seconds': 86400,  # 1 day
        'save_entities': True,
    }

    # Choose configuration based on environment
    import os
    is_production = os.getenv('ENVIRONMENT') == 'production'
    config = production_config if is_production else development_config

    try:
        session = RedisSession(**config)

        # Validate configuration
        health = session.get_health_info()
        if not health['connection_healthy']:
            raise ConnectionError(f"Configuration validation failed: {health.get('error')}")

        client_info = health.get('client_info', {})
        logger.info("=== Configuration Validation ===")
        logger.info(f"Environment: {'production' if is_production else 'development'}")
        logger.info(f"Host: {client_info.get('host')}")
        logger.info(f"Port: {client_info.get('port')}")
        logger.info(f"Max connections: {client_info.get('max_connections')}")
        logger.info(f"Dragonfly mode: {client_info.get('is_dragonfly', False)}")

        logger.info("✓ Configuration validated successfully")
        session.close()

    except Exception as e:
        logger.error(f'Configuration validation failed: {e}')


if __name__ == '__main__':
    """Run examples based on available Redis server."""

    # Test basic connection first
    try:
        test_session = RedisSession('connection_test')
        health = test_session.get_health_info()
        test_session.close()

        if health['connection_healthy']:
            logger.info("✓ Redis connection available - running all examples")

            # Run async examples
            asyncio.run(basic_usage_example())
            asyncio.run(advanced_configuration_example())
            asyncio.run(error_handling_example())

            # Run sync examples
            custom_redis_client_example()
            monitoring_example()
            asyncio.run(performance_testing_example())
            configuration_validation_example()

            logger.info("All examples completed successfully!")
        else:
            logger.warning("Redis server not available - showing configuration examples only")
            configuration_validation_example()

    except Exception as e:
        logger.error(f"Examples failed: {e}")
        logger.info("Please ensure Redis server is running on localhost:6379")
