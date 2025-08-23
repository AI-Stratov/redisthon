# redisthon 🚀

> High-performance Redis/Dragonfly session storage for Telethon

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Redis](https://img.shields.io/badge/Redis-5.0+-red.svg)](https://redis.io/)
[![Dragonfly](https://img.shields.io/badge/Dragonfly-1.0+-orange.svg)](https://dragonflydb.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI version](https://badge.fury.io/py/redisthon.svg)](https://badge.fury.io/py/redisthon)

**redisthon** is a modern, high-performance library for storing Telethon sessions in Redis or Dragonfly. Built from the ground up with cutting-edge technologies for maximum speed, reliability, and type safety.

## ✨ Features

- 🔥 **Maximum Performance** - Connection pooling, hiredis, msgpack serialization
- 🐉 **Dragonfly Support** - Modern Redis replacement with superior performance
- 🛡️ **Type Safety** - Full type annotations with modern Python 3.11+
- 🔄 **Connection Pooling** - Automatic connection management and reuse
- 💾 **Memory Optimization** - `__slots__`, efficient serialization with msgpack
- 🧹 **Resource Management** - Context manager support with automatic cleanup
- 📊 **Monitoring** - Built-in health checks and session statistics
- ⚡ **Batch Operations** - Optimized bulk operations for better throughput
- 🔒 **Production Ready** - Comprehensive error handling and logging

## 🚀 Quick Start

### Installation

```bash
# Install with pip
pip install redisthon

# Install with development dependencies
pip install redisthon[dev]

# Install with benchmark tools
pip install redisthon[benchmark]
```

### Basic Usage

```python
from telethon import TelegramClient
from redisthon import RedisSession

# Create a high-performance session
session = RedisSession(
    session_name='my_session',
    host='localhost',
    port=6379,
    max_connections=50,  # Connection pooling
    socket_keepalive=True
)

# Use with Telethon
client = TelegramClient(session, api_id, api_hash)

async with client:
    me = await client.get_me()
    print(f"Logged in as {me.username}")
    
# Session automatically saves to Redis!
```

### Using with Dragonfly

```python
# Dragonfly - modern Redis replacement
session = RedisSession(
    session_name='dragonfly_session',
    host='localhost', 
    port=6380,
    is_dragonfly=True,  # Enable Dragonfly optimizations
    max_connections=100
)

client = TelegramClient(session, api_id, api_hash)
```

### Context Manager (Recommended)

```python
# Automatic resource cleanup
with RedisSession('my_session') as session:
    client = TelegramClient(session, api_id, api_hash)
    # Your code here
# Connection pool automatically closed
```

## 🔧 Configuration

### Basic Configuration

```python
session = RedisSession(
    session_name='advanced_session',
    
    # Redis/Dragonfly settings
    host='localhost',
    port=6379,
    db=0,  # Ignored for Dragonfly
    password='your_password',
    username='your_username',  # Redis 6.0+
    
    # Performance settings
    max_connections=50,
    socket_keepalive=True,
    socket_keepalive_options={
        'TCP_KEEPIDLE': 600,
        'TCP_KEEPINTVL': 60,
        'TCP_KEEPCNT': 3
    },
    health_check_interval=30,
    connection_timeout=5,
    socket_timeout=5,
    
    # Session settings
    key_prefix='redisthon:session',
    ttl_seconds=86400 * 30,  # 30 days
    save_entities=True,
    
    # Special settings
    is_dragonfly=False
)
```

### Custom Redis Client

```python
import redis
from redisthon import RedisSession, RedisClient

# Create optimized Redis client
redis_client = RedisClient(
    host='localhost',
    port=6379,
    max_connections=100,
    socket_keepalive=True
)

session = RedisSession(
    'my_session',
    redis_client=redis_client
)
```

## 📊 Monitoring and Statistics

### Health Checks

```python
# Check Redis connection health
if session.ping():
    print("Redis connection is healthy")

# Get detailed server information
info = session.get_info()
print(f"Redis version: {info['redis_version']}")
print(f"Connected clients: {info['connected_clients']}")
print(f"Memory usage: {info['used_memory_human']}")
```

### Session Statistics

```python
# Get session statistics
stats = session.get_statistics()
print(f"Session exists: {stats['session_exists']}")
print(f"Entities cached: {stats['entities_count']}")
print(f"Files cached: {stats['sent_files_count']}")
print(f"Has auth key: {stats['has_auth_key']}")

# Get health information
health = session.get_health_info()
print(f"Connection healthy: {health['connection_healthy']}")
print(f"Server info: {health['server_info']}")
```

## 🏗️ Architecture

redisthon uses several key technologies for maximum performance:

- **msgpack** - Fast binary serialization format
- **hiredis** - High-performance Redis client
- **Connection Pooling** - Connection reuse and management
- **Base64 Encoding** - Safe storage of binary data in Redis hashes
- **Type Safety** - Full mypy compatibility
- **Async Support** - Native async/await support

### Data Storage

Sessions are stored in Redis using the following key structure:

```
redisthon:session:{session_name}:data        # Main session data
redisthon:session:{session_name}:entities    # Cached entities
redisthon:session:{session_name}:update_states  # Update states
redisthon:session:{session_name}:sent_files     # File cache
```

## 🧪 Testing

```bash
# Install development dependencies
pip install redisthon[dev]

# Run tests
pytest

# Run tests with coverage
pytest --cov=redisthon

# Run benchmark tests
pip install redisthon[benchmark]
pytest --benchmark-only
```

## 📈 Performance

redisthon shows significantly better performance compared to standard sessions:

- **Efficient Serialization** - msgpack is faster than pickle
- **Connection Pooling** - Reduced connection overhead
- **Base64 Encoding** - Safe binary data storage in Redis
- **Memory Optimization** - `__slots__` reduces memory footprint
- **Dragonfly Support** - Up to 10x better performance with Dragonfly

### Benchmarks

```python
# Example benchmark results (your mileage may vary)
# Session save: 0.5ms vs 2.0ms (standard)
# Entity lookup: 0.1ms vs 0.5ms (standard)  
# Memory usage: 50% reduction vs standard sessions
```

## 🔒 Security

- **Connection Security** - SSL/TLS support through Redis client
- **Authentication** - Username/password and Redis AUTH support  
- **Data Encryption** - Optional encryption of sensitive data
- **Access Control** - Redis ACL compatibility

## 🛠️ Development

```bash
# Clone repository
git clone https://github.com/yourusername/redisthon.git
cd redisthon

# Install with development dependencies
pip install -e .[dev]

# Run type checking
mypy redisthon/

# Run linting
ruff check redisthon/

# Format code
ruff format redisthon/

# Run all tests
pytest
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 Requirements

- Python 3.11+
- Redis 5.0+ or Dragonfly 1.0+
- Telethon 1.34.0+

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Acknowledgments

- [Telethon](https://github.com/LonamiWebs/Telethon) - The Telegram client library
- [Redis](https://redis.io/) - The in-memory data structure store
- [Dragonfly](https://dragonflydb.io/) - The modern Redis replacement

## 📞 Support

- Create an [issue](https://github.com/yourusername/redisthon/issues) for bug reports
- Start a [discussion](https://github.com/yourusername/redisthon/discussions) for questions
- Check the [documentation](https://redisthon.readthedocs.io/) for detailed guides

---

Made with ❤️ for the Python and Telegram communities
