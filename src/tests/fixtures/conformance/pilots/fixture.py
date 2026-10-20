"""Observe the native pilots' local output artifact, with no simulated services."""
import json
import os
import sys
from pathlib import Path

marker = Path(os.environ['GOOBITS_CONFORMANCE_STATE']) / 'native-result.json'
request = json.load(sys.stdin)
if request['action'] == 'reset':
    marker.unlink(missing_ok=True)
receipt = json.loads(marker.read_text()) if marker.exists() else {}
print(json.dumps({'effects': 0, 'prompts': 0, 'service_calls': 0, 'request_ids': [],
                  'postcondition': receipt.get('payload', {}).get('value') == 'value'}))
