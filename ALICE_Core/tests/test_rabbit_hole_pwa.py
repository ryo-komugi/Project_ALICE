import json
import pytest
from pathlib import Path
from portal.rabbit_hole import rabbit_hole_home, rabbit_hole_manifest, RABBIT_HOLE_MANIFEST, RABBIT_HOLE_PAGE, RABBIT_HOLE_DIR

@pytest.mark.anyio
async def test_rabbit_hole_manifest_endpoint():
    response = await rabbit_hole_manifest()
    assert response.status_code == 200
    assert response.media_type == "application/manifest+json"
    assert Path(response.path).exists()
    data = json.loads(Path(response.path).read_text(encoding="utf-8"))
    assert data["name"] == "Project ALICE Rabbit-Hole"
    assert data["display"] == "standalone"
    assert data["start_url"] == "/rabbit-hole"
    assert data["scope"] == "/"
    assert len(data["icons"]) >= 2

@pytest.mark.anyio
async def test_rabbit_hole_html_pwa_tags():
    response = await rabbit_hole_home()
    assert response.status_code == 200
    html = Path(response.path).read_text(encoding="utf-8")
    assert '<link rel="manifest" href="/rabbit-hole/manifest.json">' in html
    assert '<meta name="apple-mobile-web-app-capable" content="yes">' in html
    assert '<link rel="apple-touch-icon" href="/rabbit-hole/assets/apple-touch-icon.png">' in html
    assert '<link rel="icon" type="image/png" href="/rabbit-hole/assets/rabbit_hole_icon_192.png">' in html

def test_rabbit_hole_icons_exist():
    img_dir = RABBIT_HOLE_DIR / "images"
    assert (img_dir / "rabbit_hole_icon_512.png").exists()
    assert (img_dir / "rabbit_hole_icon_192.png").exists()
    assert (img_dir / "apple-touch-icon.png").exists()
