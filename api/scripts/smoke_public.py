"""End-to-end check of a running server, e.g. through a Cloudflare tunnel:

    python -m api.scripts.smoke_public https://something.trycloudflare.com

Two players (separate cookie jars) create and play a room over the real URL: HTTPS cookie flags,
WebSockets, origin check, presence, live progress, turns, and the final winner. It leaves rows
named "smoke-*" in the server's database (delete them or let the 7-day cleanup remove them)."""
import json
import sys
import uuid

import httpx
from websockets.sync.client import connect


def main(base: str):
    base = base.rstrip("/")
    ws_base = base.replace("https://", "wss://").replace("http://", "ws://")
    host = base.split("://", 1)[1]
    secure = base.startswith("https://")
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not cond else ""))

    def player(name):
        c = httpx.Client(base_url=base, timeout=20)
        r = c.post("/api/guests", json={"display_name": f"smoke-{name}"})
        cookie = r.headers.get("set-cookie", "").lower()
        return c, r, f"guest_token={c.cookies.get('guest_token')}", cookie

    r = httpx.get(f"{base}/api/health", timeout=20)
    check("server reachable", r.status_code == 200, r.status_code)
    ready = httpx.get(f"{base}/api/ready", timeout=20).json()
    check("database ok", ready.get("database") == "ok", ready)

    (a, ra, a_cookie, set_cookie), (b, _, b_cookie, _) = player("a"), player("b")
    check("guest cookie is HttpOnly", "httponly" in set_cookie)
    if secure:
        check("guest cookie is Secure on HTTPS (needs COOKIE_SECURE=1)", "secure" in set_cookie, set_cookie)

    clip = a.get("/api/clips").json()[0]["id"]
    phrases = [p["id"] for p in a.get(f"/api/clips/{clip}/manifest").json()["phrases"]]
    room = a.post("/api/rooms", json={"clip_id": clip}).json()
    check("room created", "code" in room, room)
    check("second player joins by code", b.post("/api/rooms/join", json={"code": room["code"]}).status_code == 200)
    for c in (a, b):
        c.post(f"/api/rooms/{room['id']}/ready", json={"ready": True})

    url = f"{ws_base}/ws/rooms/{room['id']}"
    try:
        connect(url, additional_headers={"Cookie": a_cookie, "Origin": "https://evil.example"}, open_timeout=15)
        check("foreign Origin is refused", False)
    except Exception:
        check("foreign Origin is refused", True)

    def recv_until(ws, type_, pred=lambda e: True):
        for _ in range(20):
            e = json.loads(ws.recv(timeout=15))
            if e["type"] == type_ and pred(e):
                return e
        raise AssertionError(f"never saw {type_}")

    origin = f"{'https' if secure else 'http'}://{host}"
    with connect(url, additional_headers={"Cookie": a_cookie, "Origin": origin}, open_timeout=15) as wa, \
            connect(url, additional_headers={"Cookie": b_cookie, "Origin": origin}, open_timeout=15) as wb:
        both = lambda e: all(m["connected"] for m in e["members"])
        recv_until(wa, "room_snapshot", both)
        check("WebSocket connects and presence shows both players", True)

        start = a.post(f"/api/rooms/{room['id']}/start").json()
        recv_until(wb, "room_snapshot", lambda e: e["state"] == "playing")
        check("start reaches the other player live", True)

        def turn(client, attempt, pitch):
            client.post(f"/api/turns/{attempt}/begin", json={})
            body = {"phrases": [{"phrase_id": p, "rating": "great", "pitch": pitch, "timing": pitch, "coverage": 1}
                                for p in phrases]}
            return client.post(f"/api/turns/{attempt}/result", json=body, headers={"Idempotency-Key": uuid.uuid4().hex})

        wa.send(json.dumps({"type": "progress", "data": {"t": 1.0}}))
        check("live progress relayed to the waiting player", recv_until(wb, "turn_progress")["data"] == {"t": 1.0})
        check("host result saved", turn(a, start["attempt_id"], 70).status_code == 200)
        snap = recv_until(wb, "room_snapshot", lambda e: e["match"]["active_slot"] == 1)
        second = next(x["id"] for x in snap["match"]["attempts"] if x["slot"] == 1)
        check("second player's turn opens", True)
        check("guest result saved", turn(b, second, 90).status_code == 200)
        recv_until(wa, "match_finished")
        check("match_finished pushed to the host", True)

    seen = [c.get(f"/api/rooms/{room['id']}").json()["match"]["winner_slot"] for c in (a, b)]
    check("both players read the same winner (slot 1)", seen == [1, 1], seen)
    print("\nALL PASSED" if ok else "\nFAILURES ABOVE")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000")
