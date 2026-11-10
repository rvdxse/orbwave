import asyncio
import os
from io import BytesIO
from urllib.parse import unquote
from urllib.request import urlopen

from jeepney import DBusAddress, new_method_call
from jeepney.io.blocking import open_dbus_connection
from PIL import Image, ImageDraw, ImageFilter
import requests

_BUS = DBusAddress(
    "/org/freedesktop/DBus",
    bus_name="org.freedesktop.DBus",
    interface="org.freedesktop.DBus",
)


def _prop(conn, player, name):
    addr = DBusAddress(
        "/org/mpris/MediaPlayer2",
        bus_name=player,
        interface="org.freedesktop.DBus.Properties",
    )
    msg = new_method_call(addr, "Get", "ss", ("org.mpris.MediaPlayer2.Player", name))
    return conn.send_and_get_reply(msg, timeout=2).body[0][
        1
    ]  # (signature, value) -> value


def get_mpris_thumbnail_bytes():
    try:
        with open_dbus_connection(bus="SESSION") as conn:
            names = conn.send_and_get_reply(
                new_method_call(_BUS, "ListNames"), timeout=2
            ).body[0]
            players = [n for n in names if n.startswith("org.mpris.MediaPlayer2.")]
            if not players:
                delete_cover()
                return None

            # предпочитаем плеер, который реально играет
            player = next(
                (p for p in players if _prop(conn, p, "PlaybackStatus") == "Playing"),
                players[0],
            )

            metadata = _prop(conn, player, "Metadata")
            art_url = metadata.get("mpris:artUrl", ("s", ""))[1]
            if not art_url:
                delete_cover()
                return None

            if art_url.startswith("file://"):
                with open(unquote(art_url[7:]), "rb") as f:
                    return f.read()
            if art_url.startswith("http"):
                resp = requests.get(art_url, timeout=5)
                resp.raise_for_status()
                return resp.content
        return None
    except Exception as e:
        print(f"[art] could not get cover: {e}")
        return None


def delete_cover():
    if os.path.exists("current_media_art.png"):
        os.remove("current_media_art.png")


def save_circular_image(data: bytes, path="current_media_art.png"):
    try:
        img = Image.open(BytesIO(data))

        if img.mode != "RGBA":
            img = img.convert("RGBA")

        width, height = img.size

        side = min(width, height)
        left = (width - side) // 2
        top = (height - side) // 2
        img_to_process = img.crop((left, top, left + side, top + side))

        big_size = (side * 4, side * 4)
        mask = Image.new("L", big_size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0, big_size[0], big_size[1]), fill=255)

        mask = mask.resize(img_to_process.size, Image.LANCZOS)
        mask = mask.filter(ImageFilter.SMOOTH)

        circular_img = Image.new("RGBA", img_to_process.size, (0, 0, 0, 0))
        circular_img.paste(img_to_process, (0, 0), mask)

        circular_img.save(path, "PNG")
        return True

    except Exception as e:
        print(f"Error saving image: {e}")
        return False


async def media_art_loop():
    last_data = None
    while True:
        data = get_mpris_thumbnail_bytes()
        if data and data != last_data:
            if save_circular_image(data):
                last_data = data
        await asyncio.sleep(2.5)
