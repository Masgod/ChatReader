

def test_icon_is_a_purple_tile_with_a_white_bubble():
    from chatreader.tray import _image

    img = _image()
    assert img.size == (256, 256)
    assert img.getpixel((8, 128))[:3] == (145, 70, 255)  # tile
    assert img.getpixel((60, 100))[:3] == (255, 255, 255)  # bubble
    assert img.getpixel((0, 0))[3] == 0  # rounded corner is transparent
