import json


print(json.dumps({
    "score": 0.0,
    "gates": {"shape": True},
    "feedback": {"not": "a string or string array"},
}, separators=(",", ":")))
