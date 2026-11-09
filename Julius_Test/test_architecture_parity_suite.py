"""
Comprehensive Parity Verification Test Suite for Julius.
Tests all phases of the architecture:
1. Context Management, Prompt-Cache TTL & Macro-Compaction
2. Canonical Tool Registry & Dynamic ToolSearch Engine
3. Auto-Memory System & Auto-Dream Background Consolidation
4. Subagents (Fork / Worktree) & Deterministic Workflow DSL
5. Permission Modes (Bypass, Normal, Plan, Strict)
6. Live Inference Verification with NVIDIA Build API
"""

import os
import sys
import time
import json
import unittest
from pathlib import Path
from dotenv import load_dotenv

# Ensure Julius project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env")


class TestArchitectureParitySuite(unittest.TestCase):

    def setUp(self):
        self.workspace = PROJECT_ROOT
        self.test_tmp_dir = PROJECT_ROOT / ".julius" / "test_scratch"
        self.test_tmp_dir.mkdir(parents=True, exist_ok=True)

    # ── Phase 1: Context Management & Compaction ─────────────────────────────

    def test_01_prompt_cache_ttl_and_pacing(self):
        from src.context import AgentContextManager
        ctx = AgentContextManager(context_window_limit=128000)

        # 1. Initially cache is cold
        self.assertFalse(ctx.is_cache_warm())

        # 2. Record API call
        ctx.record_usage(input_tokens=1500, output_tokens=300, cache_read_tokens=1000)
        self.assertTrue(ctx.is_cache_warm())
        self.assertEqual(ctx.usage.total_tokens, 1800)
        self.assertGreater(ctx.time_to_cache_expiry(), 290.0)

        # 3. Pacing recommendations (enforcing prompt cache alignment rules)
        delay, reason = ctx.recommend_pacing_delay(60.0)
        self.assertEqual(delay, 60.0)
        self.assertEqual(reason, "cache_warm")

        # 300s requested: should be clamped to 270s to keep cache warm
        delay, reason = ctx.recommend_pacing_delay(300.0)
        self.assertEqual(delay, 270.0)
        self.assertEqual(reason, "clamped_to_keep_cache_warm")

        # 700s requested: should be promoted to >= 1200s to amortize cache miss
        delay, reason = ctx.recommend_pacing_delay(700.0)
        self.assertEqual(delay, 1200.0)
        self.assertEqual(reason, "promoted_to_amortize_cache_miss")

        # 4. Micro-compaction on tool outputs (head 70% + tail 30%)
        huge_text = "\n".join([f"log line {i}" for i in range(3000)])
        micro_compacted = ctx.micro_compact_tool_output(huge_text, max_chars=1000, max_lines=500)
        self.assertLessEqual(len(micro_compacted), 1200)
        self.assertIn("truncated for context budget", micro_compacted)
        self.assertTrue(micro_compacted.startswith("log line 0"))

    def test_02_macro_compaction_and_thinking_stripping(self):
        from src.memory.compression import ConversationCompressor
        comp = ConversationCompressor()

        # 1. Thinking block stripping
        raw_msg = "<thought>\nInternal deliberation that should never leak.\n</thought>Here is the final answer."
        cleaned = comp.strip_thinking_blocks(raw_msg)
        self.assertEqual(cleaned, "Here is the final answer.")

        # 2. Macro-compaction
        turns = [
            {"role": "user", "content": "Refactor auth middleware to comply with security standard"},
            {"role": "assistant", "content": "<thought>Analyzing files</thought>Modified file `src/auth.py` and updated class AuthManager."},
            {"role": "user", "content": "Make sure to run unit tests"},
            {"role": "assistant", "content": "Fixed error in tests and updated `src/auth_test.py`."},
            {"role": "user", "content": "Now add the logout route"},
            {"role": "assistant", "content": "Added logout handler."},
            {"role": "user", "content": "Check status"},
            {"role": "assistant", "content": "All systems operational."},
        ]

        res = comp.compact_conversation(turns, preserved_tail_count=3, git_diff_summary="M src/auth.py")
        self.assertTrue(res["is_compacted"])
        self.assertEqual(res["turns_summarized"], 5)
        self.assertIn("src/auth.py", res["summary"])
        self.assertIn("Files Created / Modified:", res["summary"])

        # Boundary marker was placed at head of turns
        compacted_turns = res["compacted_turns"]
        self.assertEqual(len(compacted_turns), 4)  # 1 boundary marker + 3 tail turns
        self.assertTrue(compacted_turns[0].get("is_compaction_marker"))
        self.assertIn("Compacted Prior Conversation Summary", compacted_turns[0]["content"])

    # ── Phase 2: Tool Registry & Deferred ToolSearch ─────────────────────────

    def test_03_tool_registry_and_dynamic_tool_search(self):
        from src.tools import CORE_TOOL_SCHEMAS, DEFERRED_TOOL_SCHEMAS, resolve_tool_search

        # 1. Schemas registered
        self.assertIn("Read", CORE_TOOL_SCHEMAS)
        self.assertIn("Edit", CORE_TOOL_SCHEMAS)
        self.assertIn("Write", CORE_TOOL_SCHEMAS)
        self.assertIn("Bash", CORE_TOOL_SCHEMAS)
        self.assertIn("ToolSearch", CORE_TOOL_SCHEMAS)

        self.assertIn("Workflow", DEFERRED_TOOL_SCHEMAS)
        self.assertIn("TaskCreate", DEFERRED_TOOL_SCHEMAS)
        self.assertIn("ScheduleWakeup", DEFERRED_TOOL_SCHEMAS)

        # 2. Dynamic ToolSearch resolution
        # Exact select
        xml = resolve_tool_search("select:Workflow")
        self.assertIn("<functions>", xml)
        self.assertIn('"name":"Workflow"', xml)

        # Multiple select
        xml_multi = resolve_tool_search("select:TaskCreate,ScheduleWakeup")
        self.assertIn('"name":"TaskCreate"', xml_multi)
        self.assertIn('"name":"ScheduleWakeup"', xml_multi)

        # Keyword search
        xml_kw = resolve_tool_search("orchestrate subagents")
        self.assertIn('"name":"Workflow"', xml_kw)

    def test_04_action_executor_canonical_tools(self):
        from src.action_executor import ActionExecutor
        executor = ActionExecutor(str(PROJECT_ROOT))

        test_file = self.test_tmp_dir / "sample_test.txt"

        # 1. Write tool
        res_write = executor.execute("Write", {"file_path": str(test_file), "content": "alpha\nbeta\ngamma\n"})
        self.assertTrue(res_write.success)
        self.assertTrue(test_file.exists())

        # 2. Read tool (cat -n numbered format)
        res_read = executor.execute("Read", {"file_path": str(test_file), "offset": 1, "limit": 2})
        self.assertTrue(res_read.success)
        self.assertIn("alpha", res_read.output)
        self.assertIn("beta", res_read.output)

        # 3. Edit tool with uniqueness enforcement
        # Write ambiguous text first
        executor.execute("Write", {"file_path": str(test_file), "content": "dup\ndup\nunique\n"})
        res_fail_edit = executor.execute("Edit", {"file_path": str(test_file), "old_string": "dup", "new_string": "replaced"})
        self.assertFalse(res_fail_edit.success)
        self.assertIn("must be unique", res_fail_edit.output)

        # Edit with replace_all=True
        res_ok_edit = executor.execute("Edit", {"file_path": str(test_file), "old_string": "dup", "new_string": "replaced", "replace_all": True})
        self.assertTrue(res_ok_edit.success)
        self.assertIn("replaced 2 occurrence(s)", res_ok_edit.output)

        # 4. Glob tool
        res_glob = executor.execute("Glob", {"pattern": "*.txt", "path": str(self.test_tmp_dir)})
        self.assertTrue(res_glob.success)
        self.assertIn("sample_test.txt", res_glob.output)

        # 5. Background Bash command
        res_bg = executor.execute("Bash", {"command": "sleep 0.1 && echo bg_done", "run_in_background": True})
        self.assertTrue(res_bg.success)
        self.assertIn("running detached in background", res_bg.output)
        bg_id = res_bg.data["task_id"]
        time.sleep(0.3)
        self.assertIn(bg_id, executor._background_tasks)
        self.assertEqual(executor._background_tasks[bg_id]["status"], "completed")

        # Cleanup test file
        test_file.unlink(missing_ok=True)

    # ── Phase 3: Auto-Memory & Auto-Dream ────────────────────────────────────

    def test_05_auto_memory_and_auto_dream(self):
        from src.memory.auto_memory import AutoMemoryManager
        from src.memory.auto_dream import AutoDreamEngine

        mem_dir = self.test_tmp_dir / "test_memory"
        mem_mgr = AutoMemoryManager(workspace_root=str(PROJECT_ROOT), memory_dir=str(mem_dir))

        # 1. Save typed memories
        mem_mgr.save_memory(
            slug="user-preference-terse",
            title="Terse Responses",
            description="User prefers concise answers with no fluff",
            memory_type="feedback",
            content="Always provide short, concise answers. Never narrate deliberation.",
            why="User requested high information density.",
            how_to_apply="In all user responses.",
        )

        mem_mgr.save_memory(
            slug="user-preference-terse-dup",
            title="Terse Responses",
            description="Duplicate preference entry",
            memory_type="feedback",
            content="Keep answers terse and direct.",
        )

        mem_mgr.save_memory(
            slug="fake-deleted-reference",
            title="Deleted Reference",
            description="Reference to non-existent file",
            memory_type="reference",
            content="Check file `src/non_existent_file_xyz123.py` for pipeline state.",
        )

        # Verify MEMORY.md was updated
        index_text = mem_mgr.load_index()
        self.assertIn("[Terse Responses](user-preference-terse.md)", index_text)

        # 2. Run Auto-Dream Consolidation
        dream = AutoDreamEngine(workspace_root=str(PROJECT_ROOT), memory_manager=mem_mgr, min_sessions_threshold=1)
        report = dream.run_dream_consolidation(force=True)

        self.assertTrue(report.success)
        self.assertGreaterEqual(report.duplicates_merged, 1)
        self.assertGreaterEqual(report.obsolete_pruned, 1)

        # Verify duplicate was merged and obsolete pruned
        remaining = mem_mgr.list_memories()
        remaining_slugs = [r.slug for r in remaining]
        self.assertIn("user-preference-terse", remaining_slugs)
        self.assertNotIn("fake-deleted-reference", remaining_slugs)

    # ── Phase 4: Subagents & Deterministic Workflows ─────────────────────────

    def test_06_subagents_and_workflows(self):
        from src.coordinator.workflow_engine import WorkflowEngine, WorkflowAgentCapError
        wf_engine = WorkflowEngine(workspace_root=str(PROJECT_ROOT))

        # 1. Subagent execution
        res_sub = wf_engine.run_subagent(
            prompt="Analyze dependency count in pyproject.toml",
            description="analyze dependencies",
            subagent_type="fork",
            parent_context=[{"role": "user", "content": "Initial prompt"}],
        )
        self.assertTrue(res_sub.success)
        self.assertIn("sub_", res_sub.subagent_id)

        # 2. Deterministic Workflow Execution with DSL
        sample_workflow = """
export const meta = {
  name: 'test-build-review',
  description: 'Multi-stage test pipeline',
  phases: [{ title: 'Analyze' }, { title: 'Execute' }]
};

phase('Analyze')
items = ['task_a', 'task_b']
analyzed = pipeline(items, lambda x: agent(f"Analyze {x}", {'label': x}))

phase('Execute')
results = parallel([lambda: agent("Run final check", {'label': 'check'})])
"""
        res_wf = wf_engine.execute_workflow(sample_workflow)
        self.assertTrue(res_wf.success)
        self.assertEqual(res_wf.name, "test-build-review")
        self.assertIn("Analyze", res_wf.phases_completed)
        self.assertIn("Execute", res_wf.phases_completed)
        self.assertEqual(res_wf.agent_calls_count, 3)

    # ── Phase 5: Permission Modes & Plan Mode ────────────────────────────────

    def test_07_permission_modes(self):
        import asyncio
        from src.permission_gate import PermissionGate, PermissionMode, ActionType, PermissionResponse

        # 1. BYPASS mode: auto-approves all
        gate_bypass = PermissionGate(mode=PermissionMode.BYPASS)
        res = asyncio.run(gate_bypass.request_permission(ActionType.BASH_COMMAND, "rm -rf /tmp/some_dir"))
        self.assertEqual(res, PermissionResponse.APPROVE_ONCE)

        # 2. PLAN mode: strictly blocks mutating operations without prompting
        gate_plan = PermissionGate(mode=PermissionMode.PLAN)
        res_bash = asyncio.run(gate_plan.request_permission(ActionType.BASH_COMMAND, "npm install"))
        self.assertEqual(res_bash, PermissionResponse.REJECT)

        res_write = asyncio.run(gate_plan.request_permission(ActionType.FILE_WRITE, "path/to/file"))
        self.assertEqual(res_write, PermissionResponse.REJECT)

        # Safe read operations in PLAN mode pass
        res_read = asyncio.run(gate_plan.request_permission(ActionType.MCP_CALL, "read_file", tool_name="read_file"))
        self.assertEqual(res_read, PermissionResponse.APPROVE_ONCE)

    # ── Phase 6: Live Inference with NVIDIA Build API ────────────────────────

    def test_08_live_nvidia_model_inference(self):
        from src.providers.nim import NvidiaNIMProvider
        from src.providers.base import ChatRequest, ChatMessage

        api_key = os.getenv("NVIDIA_API_KEY", "")
        self.assertTrue(api_key.startswith("nvapi-"), f"NVIDIA_API_KEY must be configured, got: {api_key[:10]}...")

        # Test with official default model on the NVIDIA Build endpoint
        provider = NvidiaNIMProvider(
            api_key=api_key,
            model="nvidia/nemotron-3-ultra-550b-a55b",
        )

        req = ChatRequest(
            model="nvidia/nemotron-3-ultra-550b-a55b",
            messages=[
                ChatMessage(role="user", content="Respond with the single word: 'JULIUS_ONLINE'."),
            ],
            temperature=0.0,
            max_tokens=60,
        )

        resp = provider.chat(req)
        self.assertIsNotNone(resp)
        self.assertTrue(len(resp.strip()) > 0)
        print(f"\n[LIVE NVIDIA INFERENCE RESULT]: {resp.strip()}")
        self.assertIn("JULIUS", resp.upper())


if __name__ == "__main__":
    unittest.main()
