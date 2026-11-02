import pytest
import asyncio
import json
from pathlib import Path
from src.llm_web_client import KimiTrafficController

@pytest.mark.asyncio
async def test_kimi_traffic_controller_init():
    controller = KimiTrafficController()
    assert controller._semaphore._value == 2
    assert controller._tpm_capacity == 50000.0
    assert controller._tpm_refill_rate == 50000.0 / 60.0

@pytest.mark.asyncio
async def test_kimi_traffic_controller_daily_cap(tmp_path, monkeypatch):
    # Mock daily usage path to a temp location
    temp_file = tmp_path / ".kimi_daily_usage.json"
    monkeypatch.setattr(Path, "__new__", lambda cls, *args, **kwargs: temp_file if args and ".kimi_daily_usage.json" in args[0] else object.__new__(cls))
    
    controller = KimiTrafficController()
    # Should pass under the cap
    await controller.check_daily_cap(1000)
    
    # Should raise error if cap is exceeded
    with pytest.raises(RuntimeError, match="Daily token cap of 1.4 million tokens reached"):
        await controller.check_daily_cap(1400001)

@pytest.mark.asyncio
async def test_kimi_traffic_controller_time_gap():
    controller = KimiTrafficController()
    controller.record_completion()
    
    # Record time before wait
    import time
    start = time.monotonic()
    await controller.wait_for_time_gap()
    end = time.monotonic()
    
    # Gap should be at least 3.5 seconds
    assert (end - start) >= 3.4


@pytest.mark.asyncio
async def test_kimi_payload_parameters():
    from src.llm_web_client import WebLLMClient
    import os
    os.environ["KIMI_API_KEY"] = "sk-test-kimi-key-12345"
    client = WebLLMClient()
    await client.initialize("kimi", "/tmp/kimi_test_profile")
    
    assert client._use_api is True
    assert client._api_base == "https://api.moonshot.ai/v1"
    assert client._model_name == "kimi-k3"
