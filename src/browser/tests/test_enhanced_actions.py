import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.browser.actions import browser_click, browser_switch_tab
from src.browser.structured_obs import BrowserObservation

@pytest.mark.asyncio
async def test_browser_switch_tab_by_title_and_url():
    # Mock engine
    engine = MagicMock()
    
    # Mock context record with multiple pages
    record = MagicMock()
    page1 = AsyncMock()
    page1.url = "https://example.com/home"
    page1.title = AsyncMock(return_value="Home Page - Welcome")
    
    page2 = AsyncMock()
    page2.url = "https://google.com/search"
    page2.title = AsyncMock(return_value="Google Search")
    
    record.pages = [page1, page2]
    engine.get_context.return_value = record
    
    # Build observation mock
    mock_obs = BrowserObservation(action="browser_switch_tab")
    engine.build_observation = AsyncMock(return_value=mock_obs)
    
    # 1. Switch by title keyword
    obs = await browser_switch_tab(engine, title="Google", context_id="ctx-1")
    assert obs.error is None
    engine.switch_tab.assert_called_with("ctx-1", 1)
    
    # 2. Switch by url keyword
    engine.switch_tab.reset_mock()
    obs = await browser_switch_tab(engine, url="example.com", context_id="ctx-1")
    assert obs.error is None
    engine.switch_tab.assert_called_with("ctx-1", 0)

    # 3. Switch by index
    engine.switch_tab.reset_mock()
    obs = await browser_switch_tab(engine, tab_index=1, context_id="ctx-1")
    assert obs.error is None
    engine.switch_tab.assert_called_with("ctx-1", 1)

    # 4. Switch by index alias ("index")
    engine.switch_tab.reset_mock()
    obs = await browser_switch_tab(engine, index=0, context_id="ctx-1")
    assert obs.error is None
    engine.switch_tab.assert_called_with("ctx-1", 0)


@pytest.mark.asyncio
async def test_resilient_click_fallbacks():
    engine = MagicMock()
    record = MagicMock()
    engine.get_context.return_value = record
    
    # Mock native page and locator
    page = AsyncMock()
    page.get_native_page = AsyncMock(return_value=page)
    context = MagicMock()
    context.wait_for_event = AsyncMock(side_effect=asyncio.TimeoutError())
    page.context = context
    
    locator = AsyncMock()
    
    # Mock locator click fails (standard click fails)
    locator.click.side_effect = Exception("Element obscured")
    locator.bounding_box = AsyncMock(return_value={"x": 100, "y": 200, "width": 50, "height": 30})
    
    page.get_by_text = MagicMock()
    page.get_by_text.return_value.first = locator
    page.locator = MagicMock()
    page.locator.return_value.first = locator
    
    # Mock mouse click succeeds
    page.mouse = AsyncMock()
    page.mouse.click.return_value = None
    
    # Mock engine open_page
    engine.open_page = AsyncMock(return_value=page)
    
    # Mock observation builder
    mock_obs = BrowserObservation(action="browser_click")
    engine.build_observation = AsyncMock(return_value=mock_obs)
    
    # Test retry policy mock
    retry_policy = MagicMock()
    async def fake_execute(coro_factory, action_name):
        return await coro_factory()
    retry_policy.execute = fake_execute
    engine.retry_policy = retry_policy
    
    # Execute resilient click (should fall back to mouse click by coordinates)
    obs = await browser_click(engine, text="Submit Button")
    assert obs.error is None
    page.mouse.click.assert_called_once_with(125.0, 215.0)
