"""Generates Data/Resources/ECData/routes.json (curved approach routes).

Two layouts are produced so the 3-vs-5 route question can be compared in play:
  routes_5: pentagon pinwheel (72 deg apart), side routes tagged "flank".
  routes_3: three wider spirals (120 deg apart).
Each route starts at the arena edge and spirals clockwise to the approach radius,
so the ends are spread evenly around the citadel (a surrounding assault, not lanes).
"""
import json, math, os
HALF_W, HALF_H = 7.6, 9.6       # arena half size minus spawn inset (arena is 16 x 20)
END_R = 4.0

def edge_radius(theta):
    c, s = abs(math.cos(theta)), abs(math.sin(theta))
    rx = HALF_W / c if c > 1e-6 else 1e9
    ry = HALF_H / s if s > 1e-6 else 1e9
    return min(rx, ry)

def route(rid, theta_deg, sweep_deg, tag="any"):
    th0 = math.radians(theta_deg)
    pts = []
    for t in (0.0, 0.18, 0.4, 0.65, 0.85, 1.0):
        th = th0 + math.radians(sweep_deg) * (t ** 1.15)
        r0 = edge_radius(th0)
        ease = 1 - (1 - t) ** 1.6
        r = r0 + (END_R - r0) * ease
        x, y = r * math.cos(th), r * math.sin(th)
        x = max(-HALF_W, min(HALF_W, x)); y = max(-HALF_H, min(HALF_H, y))
        pts.append([round(x, 3), round(y, 3)])
    return {"id": rid, "tag": tag, "points": pts}

layouts = [
    {"id": "routes_5", "routes": [
        route("n", 90, -40), route("ene", 18, -40, "flank"), route("sse", -54, -40),
        route("ssw", -126, -40), route("wnw", 162, -40, "flank")]},
    {"id": "routes_3", "routes": [
        route("n", 90, -48), route("se", -30, -48), route("sw", -150, -48)]},
]
out = os.path.join(os.path.dirname(__file__), "..", "..", "EvilCats", "Assets", "_EvilCats", "Data", "Resources", "ECData", "routes.json")
with open(out, "w") as fh:
    json.dump({"layouts": layouts}, fh, indent=1)
print("wrote", os.path.normpath(out))
