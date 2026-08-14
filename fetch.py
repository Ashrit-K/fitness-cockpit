import json
import os
import sys
import urllib.request

API = "https://www.liftosaur.com/mcp"
TOKEN = os.environ.get("LIFTOSAUR_TOKEN")
if not TOKEN:
    sys.exit("LIFTOSAUR_TOKEN not set")


def call(method, params=None, rid=1):
    body = json.dumps(
        {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}
    ).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {TOKEN}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def get_all_weights():
    values = []
    cursor = None
    while True:
        args = {"key": "weight", "limit": "200"}
        if cursor:
            args["cursor"] = cursor
        res = call("tools/call", {"name": "get_measurement", "arguments": args})
        content = json.loads(res["result"]["content"][0]["text"])
        values.extend(content["values"])
        if content.get("hasMore") and content.get("nextCursor"):
            cursor = content["nextCursor"]
        else:
            break
    values.sort(key=lambda v: v["timestamp"])
    return values


def get_all_history():
    records = []
    cursor = None
    while True:
        args = {"limit": "200"}
        if cursor:
            args["cursor"] = cursor
        res = call("tools/call", {"name": "get_history", "arguments": args})
        content = json.loads(res["result"]["content"][0]["text"])
        records.extend(content["records"])
        if content.get("hasMore") and content.get("nextCursor"):
            cursor = content["nextCursor"]
        else:
            break
    return records


def get_custom_exercises():
    res = call("tools/call", {"name": "list_custom_exercises", "arguments": {}})
    return json.loads(res["result"]["content"][0]["text"])


def main():
    with open("weights.json", "w") as f:
        json.dump({"updated_at": None, "values": get_all_weights()}, f, indent=2)
    with open("history.json", "w") as f:
        json.dump({"records": get_all_history()}, f, indent=2)
    with open("custom_exercises.json", "w") as f:
        json.dump(get_custom_exercises(), f, indent=2)
    print("fetched weights + history + custom exercises")


if __name__ == "__main__":
    main()
