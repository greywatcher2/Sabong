from __future__ import annotations

import platform
import uuid


def get_device_id() -> str:
    node = uuid.getnode()
    mac = ":".join(f"{(node >> ele) & 0xFF:02x}" for ele in range(40, -8, -8))
    return f"{platform.node()}|{mac}"

