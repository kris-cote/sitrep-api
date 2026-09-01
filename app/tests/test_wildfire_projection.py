from app.services.wildfire_projection import angular_difference, bearing_deg


def test_angular_difference_wraps_cleanly():
    assert angular_difference(350, 10) == 20
    assert angular_difference(10, 350) == 20


def test_bearing_east_is_about_90_degrees():
    bearing = bearing_deg(49.0, -124.0, 49.0, -123.0)
    assert 80 <= bearing <= 100
