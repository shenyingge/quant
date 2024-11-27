import redis

class RedisTool:
    def __init__(self):
        self.redis = redis.StrictRedis(host='localhost', port=6379, db=0)

    def get(self, key):
        return self.redis.get(key)
