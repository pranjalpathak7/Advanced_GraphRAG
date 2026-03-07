import json
import os

TELEMETRY_FILE = "data/telemetry.json"

def _init_telemetry():
    if not os.path.exists("data"):
        os.makedirs("data")
    if not os.path.exists(TELEMETRY_FILE):
        with open(TELEMETRY_FILE, "w") as f:
            json.dump({
                "extraction_successes": 0, 
                "extraction_failures": 0, 
                "rag_thumbs_up": 0, 
                "rag_thumbs_down": 0
            }, f)

def log_extraction(success: bool):
    _init_telemetry()
    with open(TELEMETRY_FILE, "r") as f:
        data = json.load(f)
    if success:
        data["extraction_successes"] += 1
    else:
        data["extraction_failures"] += 1
    with open(TELEMETRY_FILE, "w") as f:
        json.dump(data, f)

def log_feedback(is_positive: bool):
    _init_telemetry()
    with open(TELEMETRY_FILE, "r") as f:
        data = json.load(f)
    if is_positive:
        data["rag_thumbs_up"] += 1
    else:
        data["rag_thumbs_down"] += 1
    with open(TELEMETRY_FILE, "w") as f:
        json.dump(data, f)

def get_telemetry():
    _init_telemetry()
    with open(TELEMETRY_FILE, "r") as f:
        return json.load(f)