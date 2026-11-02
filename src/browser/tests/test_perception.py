"""
Unit tests for the Julius Perception Engine
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from src.perception.capture import capture_state
from src.perception.accessibility import AccessibilityTreeParser
from src.perception.dom_parser import DOMParser
from src.perception.omniparser import OmniParser
from src.perception.fusion import DOMVisualFusion
from src.perception.scene_graph import SceneGraph
from src.perception.diff_engine import DiffEngine
from src.perception.cache import PerceptionCache
from src.planner.planner import Planner
from src.perception_runtime.scheduler import PerceptionScheduler

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.mark.anyio
async def test_capture_state():
    # Setup mock page
    mock_page = AsyncMock()
    mock_page.accessibility = AsyncMock()
    mock_page.accessibility.snapshot.return_value = {"role": "Root", "name": "Document"}
    mock_page.content.return_value = "<html><body>Test</body></html>"
    mock_page.screenshot.return_value = b"mock-image-bytes"

    ax_tree, dom_html, screenshot = await capture_state(mock_page)

    assert ax_tree == {"role": "Root", "name": "Document"}
    assert dom_html == "<html><body>Test</body></html>"
    assert screenshot == b"mock-image-bytes"

def test_accessibility_parser():
    parser = AccessibilityTreeParser()
    mock_ax = {
        "role": "WebArea",
        "name": "Title",
        "children": [
            {"role": "button", "name": "Submit"},
            {"role": "link", "name": "Home"}
        ]
    }

    nodes = parser.parse(mock_ax)
    assert len(nodes) == 3
    assert nodes[0]["role"] == "WebArea"
    assert nodes[0]["text"] == "Title"
    assert nodes[1]["role"] == "button"
    assert nodes[1]["parent_id"] == "ax-0"

@pytest.mark.anyio
async def test_dom_parser():
    mock_page = AsyncMock()
    mock_page.evaluate.return_value = [
        {"id": "input-1", "tag": "input", "role": "textbox", "text": "Search", "selector": "#input-1", "bbox": [10, 10, 100, 40], "enabled": True}
    ]

    parser = DOMParser()
    elements = await parser.parse(mock_page)

    assert len(elements) == 1
    assert elements[0]["id"] == "input-1"
    assert elements[0]["role"] == "textbox"
    mock_page.evaluate.assert_called_once()

def test_omniparser_heuristics():
    parser = OmniParser()
    # Create mock 100x100 white image bytes with a black square (mock element) in the center
    from PIL import Image
    import io
    img = Image.new('RGB', (100, 100), color='white')
    # Draw simple outline
    for y in range(40, 60):
        for x in range(20, 80):
            img.putpixel((x, y), (0, 0, 0)) # black pixel outline
            
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_bytes = img_byte_arr.getvalue()

    elements = parser.detect(img_bytes)
    assert isinstance(elements, list)
    # The heuristic should detect at least the outline rectangle
    assert len(elements) >= 1
    assert "bbox" in elements[0]
    assert "type" in elements[0]

def test_dom_visual_fusion():
    fusion = DOMVisualFusion()
    dom_elements = [
        {"id": "dom-btn", "tag": "button", "role": "button", "text": "Submit", "selector": "#dom-btn", "bbox": [10, 10, 100, 40], "enabled": True}
    ]
    visual_detections = [
        {"type": "button", "bbox": [12, 12, 98, 38], "confidence": 0.95, "text": ""}
    ]

    fused = fusion.fuse(dom_elements, visual_detections)
    assert len(fused) == 1
    assert fused[0]["id"] == "dom-btn"
    assert fused[0]["bbox"] == [12, 12, 98, 38]  # BBox should be updated to visual coordinate boundaries
    assert fused[0]["confidence"] == 0.95

def test_scene_graph():
    elements = [
        {"id": "root", "role": "window", "tag": "body", "text": "Main", "bbox": [0, 0, 800, 600], "enabled": True, "parent_id": ""},
        {"id": "btn-1", "role": "button", "tag": "button", "text": "OK", "bbox": [20, 20, 100, 50], "enabled": True, "parent_id": "root"}
    ]
    graph = SceneGraph()
    graph.build(elements)

    assert graph.root is not None
    assert graph.root.id == "root"
    assert len(graph.root.children) == 1
    assert graph.root.children[0].id == "btn-1"

def test_diff_engine():
    diff_engine = DiffEngine()
    
    # State 1
    elements_1 = [
        {"id": "root", "role": "window", "tag": "body", "text": "Main", "bbox": [0, 0, 800, 600], "enabled": True, "parent_id": ""},
        {"id": "btn-1", "role": "button", "tag": "button", "text": "Click", "bbox": [20, 20, 100, 50], "enabled": True, "parent_id": "root"}
    ]
    graph_1 = SceneGraph()
    graph_1.build(elements_1)
    diffs_1 = diff_engine.diff(graph_1)
    
    # First frame shows everything added
    assert any(d["id"] == "btn-1" and d["type"] == "added" for d in diffs_1)

    # State 2: Modify text
    elements_2 = [
        {"id": "root", "role": "window", "tag": "body", "text": "Main", "bbox": [0, 0, 800, 600], "enabled": True, "parent_id": ""},
        {"id": "btn-1", "role": "button", "tag": "button", "text": "Submit", "bbox": [20, 20, 100, 50], "enabled": True, "parent_id": "root"}
    ]
    graph_2 = SceneGraph()
    graph_2.build(elements_2)
    diffs_2 = diff_engine.diff(graph_2)

    assert len(diffs_2) == 1
    assert diffs_2[0]["id"] == "btn-1"
    assert diffs_2[0]["type"] == "modified"
    assert "text" in diffs_2[0]["changes"]
    assert diffs_2[0]["changes"]["text"] == ("Click", "Submit")

def test_perception_cache():
    cache = PerceptionCache(dhash_threshold=2)
    
    # Create simple dummy image bytes
    from PIL import Image
    import io
    img = Image.new('RGB', (50, 50), color='blue')
    img_byte_arr = io.BytesIO()
    img.save(img_byte_arr, format='PNG')
    img_bytes = img_byte_arr.getvalue()

    skip_1, data_1 = cache.should_skip(img_bytes)
    assert not skip_1
    
    cache.update([{"id": "node-1"}])
    
    # Pass same image again
    skip_2, data_2 = cache.should_skip(img_bytes)
    assert skip_2
    assert len(data_2) == 1
    assert data_2[0]["id"] == "node-1"

@pytest.mark.anyio
async def test_planner():
    planner = Planner()
    scene_graph = SceneGraph()
    scene_graph.build([
        {"id": "btn-ok", "role": "button", "tag": "button", "text": "OK", "bbox": [10, 10, 50, 50], "enabled": True, "parent_id": "root"}
    ])

    action, args, thought = await planner.plan("click ok button", scene_graph, [])
    assert action == "click"
    assert args == {"element_id": "btn-ok"}

@pytest.mark.anyio
async def test_scheduler_step():
    mock_page = AsyncMock()
    mock_page.accessibility = AsyncMock()
    mock_page.accessibility.snapshot.return_value = {"role": "Root", "name": "Document"}
    mock_page.content.return_value = "<html><body>Test</body></html>"
    mock_page.screenshot.return_value = b"mock-image-bytes"
    mock_page.url = "http://test.com"
    mock_page.evaluate.return_value = [
        {"id": "btn-1", "tag": "button", "role": "button", "text": "Submit", "selector": "button", "bbox": [10, 10, 100, 40], "enabled": True}
    ]

    scheduler = PerceptionScheduler()
    # Spy event listener
    events = []
    scheduler.event_bus.subscribe("step_start", lambda d: events.append("start"))
    scheduler.event_bus.subscribe("planner_decision", lambda d: events.append("planned"))

    done, summary = await scheduler.step(mock_page, "click Submit button")
    assert not done
    assert "Executed action:" in summary
    assert "start" in events
    assert "planned" in events
