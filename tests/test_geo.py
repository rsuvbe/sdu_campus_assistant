"""
"Where am I": the map knows where it is on the Earth (app/site.py GEO), so the
phone's GPS fix can be drawn on the plan (static/app.js, the locate button).
"""
import math

import pytest

from app.main import BASE_DIR, campus_map
from app.site import GEO, from_ground, to_ground

APP_JS = (BASE_DIR / "static" / "app.js").read_text()
INDEX_HTML = (BASE_DIR / "static" / "index.html").read_text()
FLOOR1 = campus_map.floor_list()[0]


def metres(p, q):
    """Ground distance between two (lat, lon)."""
    return math.hypot((p[0] - q[0]) * GEO["m_per_lat"], (p[1] - q[1]) * GEO["m_per_lon"])


@pytest.mark.parametrize("point", [(0, 0), (1377, 795), (1722, 3615), (2660, 4460), (517, 3711)])
def test_ground_and_back_is_the_same_point(point):
    x, y = from_ground(*to_ground(*point))
    assert x == pytest.approx(point[0], abs=1e-6) and y == pytest.approx(point[1], abs=1e-6)


def test_main_building_lands_on_its_osm_outline():
    # the corners of OpenStreetMap's way 244454250, the main building
    lat0, lat1, lon0, lon1 = 43.206265, 43.208927, 76.669103, 76.670538
    lat, lon = to_ground(1722, (747 + 3615) / 2)   # the middle of the central corridor
    assert lat0 < lat < lat1 and lon0 < lon < lon1
    # the corridor runs the building's length: about 300 m, roughly north to south
    top, bottom = to_ground(1722, 747), to_ground(1722, 3615)
    assert 280 < metres(top, bottom) < 340
    assert top[0] > bottom[0]


def test_a_plan_unit_is_about_ten_centimetres():
    (a, b, _), (d, e, _) = GEO["affine"]
    assert 0.09 < math.sqrt(abs(a * e - b * d)) < 0.12


def test_the_map_carries_its_place_on_the_earth():
    assert campus_map.grounds()["geo"] == GEO


def test_the_plan_has_a_locate_button_wired_to_gps():
    assert 'id="locate"' in INDEX_HTML and 'id="i-locate"' in INDEX_HTML
    assert "watchPosition" in APP_JS and "enableHighAccuracy: true" in APP_JS
    assert "function groundToPlan" in APP_JS
