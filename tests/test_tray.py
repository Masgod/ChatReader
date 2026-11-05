

def test_icon_is_a_purple_tile_with_a_white_bubble():
    from chatreader.tray import _image

    img = _image()
    assert img.size == (256, 256)
    assert img.getpixel((8, 128))[:3] == (145, 70, 255)  # tile
    assert img.getpixel((60, 100))[:3] == (255, 255, 255)  # bubble
    assert img.getpixel((0, 0))[3] == 0  # rounded corner is transparent

class _Ctl:
    paused = False

    def status(self):
        return {}

    def pause(self): ...

    def resume(self): ...

    def skip(self): ...


def _item(icon, prefix):
    return next((i for i in icon.menu.items if str(i.text).startswith(prefix)), None)


def test_update_menu_item_is_hidden_without_an_update_and_opens_the_release_page():
    from chatreader.tray import build_icon

    news, opened = [None], []
    icon = build_icon(_Ctl(), "s", "o", lambda: None, get_update=lambda: news[0], open_url=opened.append)
    item = _item(icon, "Version")
    assert item is not None and not item.visible
    news[0] = {"version": "0.6.0", "url": "https://github.com/Masgod/ChatReader/releases/tag/v0.6.0"}
    assert item.visible and "0.6.0" in item.text
    item(icon)
    assert opened == [news[0]["url"]]


def test_no_update_source_means_no_menu_item():
    from chatreader.tray import build_icon

    assert _item(build_icon(_Ctl(), "s", "o", lambda: None), "Version") is None
