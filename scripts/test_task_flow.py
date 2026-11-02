#!/usr/bin/env python3
"""
Diagnostic script to test WebSocket task submission and Permission Gate approval against Julius server.
"""
import asyncio
import json
import sys
import aiohttp


async def run_test():
    url = "http://localhost:8080/ws"
    print(f"Connecting to {url}...")
    
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(url) as ws:
            print("Connected! Submitting task...")
            task_text = 'Open a public webpage, search for information about Raspberry Pi, and summarize the results.'
            await ws.send_json({"type": "start_task", "task": task_text})
            
            confirm_sent = False
            
            while True:
                try:
                    msg = await asyncio.wait_for(ws.receive(), timeout=90.0)
                except asyncio.TimeoutError:
                    print("Timeout waiting for server event.")
                    break
                    
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    event_type = data.get("type")
                    print(f"▶ Received Event: {event_type} | {data}")
                    
                    if event_type == "confirm_action":
                        print("🔐 PERMISSION GATE TRIGGERED!")
                        action = data.get("action")
                        args = data.get("args")
                        print(f"   Action: {action} with args: {args}")
                        print("👉 Sending APPROVAL: {'type': 'action_response', 'allow': True}...")
                        await ws.send_json({"type": "action_response", "allow": True})
                        confirm_sent = True
                        
                    elif event_type in ("done", "error"):
                        print(f"Final outcome: {event_type}")
                        break
                        
                elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                    print(f"WebSocket closed/error: {msg}")
                    break

if __name__ == "__main__":
    asyncio.run(run_test())
