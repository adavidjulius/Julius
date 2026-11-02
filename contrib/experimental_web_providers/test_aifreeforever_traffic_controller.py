import asyncio
import time
import pytest
from src.llm_web_client import AIFreeForeverTrafficController

@pytest.mark.asyncio
async def test_aff_traffic_controller_init():
    controller = AIFreeForeverTrafficController(min_gap_seconds=4.5)
    assert controller._semaphore._value == 1
    assert controller.min_gap_seconds == 4.5
    assert controller.total_requests == 0
    assert controller.successful_requests == 0


@pytest.mark.asyncio
async def test_aff_traffic_controller_record():
    controller = AIFreeForeverTrafficController(min_gap_seconds=4.0)
    controller.record_completion(success=True)
    assert controller.total_requests == 1
    assert controller.successful_requests == 1

    controller.record_completion(success=False)
    assert controller.total_requests == 2
    assert controller.successful_requests == 1


@pytest.mark.asyncio
async def test_aff_traffic_controller_time_gap():
    controller = AIFreeForeverTrafficController(min_gap_seconds=1.0)
    controller.record_completion(success=True)

    t0 = time.monotonic()
    waited = await controller.wait_for_time_gap()
    t1 = time.monotonic()

    assert (t1 - t0) >= 0.9
    assert waited > 0.0

    # Calling immediately again without recording completion should not wait
    waited_again = await controller.wait_for_time_gap()
    assert waited_again == 0.0
