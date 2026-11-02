import unittest
import asyncio
from src.web_agent import WebAgent
from src.agent_config import AgentConfig

class TestWebAgentConfirmationFlow(unittest.IsolatedAsyncioTestCase):
    async def test_human_confirmation_async_approve(self):
        # Mock config and agent event callbacks
        config = AgentConfig(confirm_actions=True)
        events = []
        def on_event(ev):
            events.append(ev)
            
        agent = WebAgent(config=config, on_event=on_event)
        
        # Start _get_human_confirmation in a task
        confirm_task = asyncio.create_task(agent._get_human_confirmation("run_bash", {"command": "echo hello"}))
        
        # Allow it to run and emit event
        await asyncio.sleep(0.05)
        
        # Verify event was emitted
        confirm_events = [e for e in events if e["type"] == "confirm_action"]
        self.assertEqual(len(confirm_events), 1)
        self.assertEqual(confirm_events[0]["action"], "run_bash")
        self.assertEqual(confirm_events[0]["args"]["command"], "echo hello")
        
        # Verify confirm future is pending
        self.assertIsNotNone(agent._confirm_future)
        self.assertFalse(agent._confirm_future.done())
        
        # Resolve the future to True (Approve)
        agent._confirm_future.set_result(True)
        
        # Await the task result
        result = await confirm_task
        self.assertTrue(result)
        self.assertIsNone(agent._confirm_future)

    async def test_human_confirmation_async_reject(self):
        config = AgentConfig(confirm_actions=True)
        events = []
        def on_event(ev):
            events.append(ev)
            
        agent = WebAgent(config=config, on_event=on_event)
        
        confirm_task = asyncio.create_task(agent._get_human_confirmation("run_bash", {"command": "echo hello"}))
        await asyncio.sleep(0.05)
        
        self.assertIsNotNone(agent._confirm_future)
        
        # Resolve the future to False (Reject)
        agent._confirm_future.set_result(False)
        
        result = await confirm_task
        self.assertFalse(result)
        self.assertIsNone(agent._confirm_future)

    async def test_confirm_writes_needs_confirmation(self):
        # When confirm_actions is False but confirm_writes is True:
        # write_file and edit_file require confirmation, but read_file and run_bash do not
        config = AgentConfig(confirm_actions=False, confirm_writes=True)
        self.assertTrue(config.needs_confirmation("write_file"))
        self.assertTrue(config.needs_confirmation("edit_file"))
        self.assertFalse(config.needs_confirmation("read_file"))
        self.assertFalse(config.needs_confirmation("run_bash"))

        # When confirm_writes is False in Autonomous mode:
        config_auto = AgentConfig(confirm_actions=False, confirm_writes=False)
        self.assertFalse(config_auto.needs_confirmation("write_file"))
        self.assertFalse(config_auto.needs_confirmation("edit_file"))

if __name__ == "__main__":
    unittest.main()
