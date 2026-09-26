#!/usr/bin/env python3
"""Draw Cynqra's app icon with the standard library and write it as PNG, ICO (Windows) and ICNS (macOS).

    python desktop/make_icon.py

The mark: an open ring (the organization) around a warm centre (the founder), on the app's green.
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GREEN, WHITE, AMBER = (15, 107, 92), (255, 255, 255), (240, 201, 155)


def clamp(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def render(n: int) -> bytes:
    """RGBA rows for an n x n icon, anti-aliased with signed distances measured in pixels."""
    c, half, r = n / 2, n * 0.42, n * 0.1
    ring_r, ring_t, dot_r, gap = n * 0.215, n * 0.085, n * 0.075, math.radians(42)
    caps = [(c + ring_r * math.cos(a), c + ring_r * math.sin(a)) for a in (gap, -gap)]
    rows = bytearray()
    for y in range(n):
        rows.append(0)  # PNG filter: none
        py = y + 0.5
        for x in range(n):
            px = x + 0.5
            qx, qy = abs(px - c) - (half - r), abs(py - c) - (half - r)
            d_box = math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - r
            a_box = clamp(0.5 - d_box)
            if a_box == 0:
                rows += b"\0\0\0\0"
                continue
            dx, dy = px - c, py - c
            dist = math.hypot(dx, dy)
            if abs(math.atan2(dy, dx)) < gap:
                d_ring = min(math.hypot(px - cx, py - cy) for cx, cy in caps) - ring_t / 2
            else:
                d_ring = abs(dist - ring_r) - ring_t / 2
            a_ring, a_dot = clamp(0.5 - d_ring), clamp(0.5 - (dist - dot_r))
            col = [g + (w - g) * a_ring for g, w in zip(GREEN, WHITE)]
            col = [v + (a - v) * a_dot for v, a in zip(col, AMBER)]
            rows += bytes(int(round(v)) for v in col) + bytes([int(round(255 * a_box))])
    return bytes(rows)


def png(n: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    head = struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"IDAT", zlib.compress(render(n), 9)) + chunk(b"IEND", b"")


def ico(images: dict[int, bytes]) -> bytes:
    sizes = sorted(images)
    out, offset = struct.pack("<HHH", 0, 1, len(sizes)), 6 + 16 * len(sizes)
    body = b""
    for s in sizes:
        data = images[s]
        out += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset + len(body))
        body += data
    return out + body


def icns(images: dict[int, bytes]) -> bytes:
    kinds = [(b"icp4", 16), (b"icp5", 32), (b"ic11", 32), (b"ic12", 64), (b"ic07", 128), (b"ic13", 256),
             (b"ic08", 256), (b"ic14", 512), (b"ic09", 512), (b"ic10", 1024)]
    body = b"".join(k + struct.pack(">I", 8 + len(images[s])) + images[s] for k, s in kinds)
    return b"icns" + struct.pack(">I", 8 + len(body)) + body


def main() -> None:
    images = {s: png(s) for s in (16, 32, 48, 64, 128, 256, 512, 1024)}
    out = ROOT / "desktop" / "icon"
    out.mkdir(parents=True, exist_ok=True)
    (out / "cynqra.png").write_bytes(images[512])
    (out / "cynqra.ico").write_bytes(ico({s: images[s] for s in (16, 32, 48, 64, 128, 256)}))
    (out / "cynqra.icns").write_bytes(icns(images))
    (ROOT / "poc" / "ui" / "icon.png").write_bytes(images[256])
    print("wrote", ", ".join(str(p.relative_to(ROOT)) for p in sorted(out.iterdir())), "and poc/ui/icon.png")


if __name__ == "__main__":
    main()
