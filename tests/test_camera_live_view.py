import base64
import os
import unittest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase

from src.web_agent import WebAgent
from src.agent_config import AgentConfig
from julius_gui import create_app

class TestWebAgentCamera(unittest.IsolatedAsyncioTestCase):
    async def test_run_with_image_path(self):
        # Mock the client
        mock_client = MagicMock()
        mock_client.provider_name = "Gemini"
        mock_client.is_initialized = True
        mock_client.check_login_status = AsyncMock(return_value=True)
        mock_client.send_message_with_image = AsyncMock()
        mock_client.send_message = AsyncMock()
        mock_client.close = AsyncMock()
        
        # Define response from LLM
        mock_response = MagicMock()
        mock_response.error = None
        mock_response.raw_text = '{"thought": "done", "action": "done", "args": {}}'
        mock_client.send_message_with_image.return_value = mock_response
        mock_client.send_message.return_value = mock_response
        
        config = AgentConfig(
            provider="gemini",
            max_steps=1,
            confirm_actions=False,
            allowed_directory="."
        )
        
        agent = WebAgent(config=config, shared_client=mock_client)
        
        # Patches to avoid file system lookups during the agent loop
        with patch.object(agent.executor, 'list_directory') as mock_list, \
             patch('src.web_agent.build_workspace_context', return_value=''), \
             patch('src.web_agent.build_initial_prompt', return_value=''), \
             patch.object(agent, '_parse_action', return_value={"action": "done", "args": {}}):
            
            # Setup mock returns
            mock_list.return_value.output = 'mock dir'
            
            # Run the agent with an image path
            result = await agent.run("test task", image_path="tests/mock_img.jpg")
            
            # Check that send_message_with_image was called since step_num == 1 and image_path is set
            mock_client.send_message_with_image.assert_called_once()
            mock_client.send_message.assert_not_called()


class TestGuiCameraHandler(AioHTTPTestCase):
    async def get_application(self):
        # Create the app using the temp directory as workspace
        self.workspace_dir = Path("/tmp/february_test_camera_ws")
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        return create_app(str(self.workspace_dir))

    def tearDown(self):
        import shutil
        if hasattr(self, 'workspace_dir') and self.workspace_dir.exists():
            try:
                shutil.rmtree(self.workspace_dir)
            except Exception:
                pass
        super().tearDown()

    async def test_websocket_camera_frame_caching(self):
        fake_session = {
            "session_token": "test-session-camera",
            "user_id": 1,
            "username": "tester",
            "role": "admin",
            "workspace": str(self.workspace_dir)
        }
        with patch("julius_gui.get_session", return_value=fake_session):
            async with self.client.ws_connect("/ws") as ws:
                # Send camera frame update
                test_frame = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP"
                await ws.send_json({
                    "type": "camera_frame",
                    "frame": test_frame
                })
                
                # Wait a short moment to process
                await asyncio.sleep(0.2)
                
                # Verify cached frame exists in the app session dictionary
                session_ids = list(self.app["session_camera_frames"].keys())
                self.assertEqual(len(session_ids), 1)
                self.assertEqual(self.app["session_camera_frames"][session_ids[0]], test_frame)


if __name__ == "__main__":
    unittest.main()
