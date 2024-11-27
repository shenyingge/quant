# 自定义 JSON 序列化器
import json
from decimal import Decimal

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)  # 或者 str(obj)
        return super().default(obj)
