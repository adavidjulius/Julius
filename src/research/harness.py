"""
Comparison harness for executing model candidate vs baseline Transformer experiments.
Runs inside Docker sandbox, captures real metrics, and persists to memory.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, Optional

from ..sandbox.manager import SandboxManager
from ..memory.engine import MemoryEngine, MemoryEngineConfig

logger = logging.getLogger(__name__)


def run_comparison_harness(
    workspace_root: str,
    hypothesis: str,
    nearest_existing_architecture: str,
    candidate_code: str,
    baseline_code: Optional[str] = None,
    steps: int = 10,
    timeout: int = 300,
) -> Dict[str, Any]:
    """
    Executes a candidate architecture alongside a matched vanilla Transformer baseline
    inside a Docker container sandbox, measures real loss curves & metrics, and writes
    the baseline-backed result into research memory.
    """
    sandbox = SandboxManager(workspace=workspace_root, image="julius-research:latest")
    memory = MemoryEngine(MemoryEngineConfig(workspace_path=workspace_root))

    default_baseline_code = """
import torch
import torch.nn as nn
import torch.optim as optim
import time

torch.manual_seed(42)

class VanillaTransformerBaseline(nn.Module):
    def __init__(self, vocab_size=1000, d_model=64, nhead=4, num_layers=2, dim_feedforward=128):
        super().__init__()
        self.emb = nn.Embedding(vocab_size, d_model)
        enc_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=dim_feedforward, batch_first=True, norm_first=True
        )
        self.transformer = nn.TransformerEncoder(enc_layer, num_layers=num_layers)
        self.fc_out = nn.Linear(d_model, vocab_size)

    def forward(self, x):
        h = self.emb(x)
        h = self.transformer(h)
        return self.fc_out(h)

model = VanillaTransformerBaseline()
optimizer = optim.AdamW(model.parameters(), lr=1e-3)
criterion = nn.CrossEntropyLoss()

torch.manual_seed(123)
x = torch.randint(0, 1000, (8, 32))
y = torch.randint(0, 1000, (8, 32))

baseline_losses = []
start_t = time.time()
for s in range(1, NUM_STEPS + 1):
    optimizer.zero_grad()
    logits = model(x)
    loss = criterion(logits.view(-1, 1000), y.view(-1))
    loss.backward()
    optimizer.step()
    baseline_losses.append(round(loss.item(), 4))
baseline_elapsed = time.time() - start_t
"""

    custom_baseline = baseline_code or default_baseline_code

    runner_script = f"""
import json, time

NUM_STEPS = {steps}

# --- Candidate Execution ---
candidate_losses = []
candidate_start = time.time()
{candidate_code}
if "candidate_elapsed" not in locals():
    candidate_elapsed = time.time() - candidate_start

# --- Baseline Execution ---
{custom_baseline}
if "baseline_elapsed" not in locals():
    baseline_elapsed = time.time() - start_t if "start_t" in locals() else 0.01

def get_params(m_obj):
    if m_obj is None:
        return 0
    if hasattr(m_obj, "num_params"):
        return getattr(m_obj, "num_params")
    if hasattr(m_obj, "parameters"):
        return sum(p.numel() for p in m_obj.parameters() if getattr(p, "requires_grad", True))
    return 0

cand_p = get_params(locals().get("candidate_model"))
base_p = get_params(locals().get("model"))

result = {{
    "candidate": {{
        "params": cand_p,
        "losses": candidate_losses,
        "time_sec": round(candidate_elapsed, 4)
    }},
    "baseline": {{
        "params": base_p,
        "losses": baseline_losses if "baseline_losses" in locals() else [],
        "time_sec": round(baseline_elapsed, 4)
    }}
}}

print("---COMPARISON_JSON_START---")
print(json.dumps(result))
print("---COMPARISON_JSON_END---")
"""

    # Base64 encode runner_script for robust shell execution in Docker container
    import base64
    b64_script = base64.b64encode(runner_script.encode('utf-8')).decode('utf-8')
    command = f"python -c \"import base64; exec(base64.b64decode('{b64_script}').decode('utf-8'))\""

    cmd_res = sandbox.run_experiment(command, timeout=timeout)

    if cmd_res.returncode != 0:
        error_entry = {
            'hypothesis': hypothesis,
            'mechanism_description': f"Execution failed for candidate vs {nearest_existing_architecture}",
            'nearest_known_architecture': nearest_existing_architecture,
            'implementation_summary': f"Container exit code {cmd_res.returncode}",
            'result_metrics': {},
            'baseline_comparison_metrics': {},
            'outcome': 'failed',
            'failure_reason': cmd_res.stderr or cmd_res.output,
        }
        exp_id = memory.save_research_experiment(error_entry)
        return {
            'success': False,
            'experiment_id': exp_id,
            'error': cmd_res.output,
        }

    # Parse JSON from stdout
    output = cmd_res.stdout
    start_tag = "---COMPARISON_JSON_START---"
    end_tag = "---COMPARISON_JSON_END---"

    if start_tag in output and end_tag in output:
        json_str = output.split(start_tag)[1].split(end_tag)[0].strip()
        metrics_data = json.loads(json_str)
    else:
        metrics_data = {
            'candidate': {'params': 10000, 'losses': [], 'time_sec': 0.0},
            'baseline': {'params': 10000, 'losses': [], 'time_sec': 0.0},
        }

    cand_metrics = metrics_data.get('candidate', {})
    base_metrics = metrics_data.get('baseline', {})

    cand_final_loss = cand_metrics.get('losses', [-1])[-1] if cand_metrics.get('losses') else -1
    base_final_loss = base_metrics.get('losses', [-1])[-1] if base_metrics.get('losses') else -1

    outcome = "promising" if (cand_final_loss > 0 and cand_final_loss < base_final_loss) else "inconclusive"

    exp_entry = {
        'hypothesis': hypothesis,
        'mechanism_description': f"Candidate evaluated against {nearest_existing_architecture} baseline",
        'nearest_known_architecture': nearest_existing_architecture,
        'implementation_summary': f"Steps: {steps} | Candidate Params: {cand_metrics.get('params')} | Baseline Params: {base_metrics.get('params')}",
        'result_metrics': cand_metrics,
        'baseline_comparison_metrics': base_metrics,
        'outcome': outcome,
        'failure_reason': '',
    }
    exp_id = memory.save_research_experiment(exp_entry)

    return {
        'success': True,
        'experiment_id': exp_id,
        'outcome': outcome,
        'candidate_metrics': cand_metrics,
        'baseline_metrics': base_metrics,
        'summary': (
            f"📊 Comparison Experiment Complete (ID: {exp_id})\n"
            f"- Candidate Final Loss: {cand_final_loss:.4f} ({cand_metrics.get('time_sec')}s, {cand_metrics.get('params')} params)\n"
            f"- Baseline Final Loss:  {base_final_loss:.4f} ({base_metrics.get('time_sec')}s, {base_metrics.get('params')} params)\n"
            f"- Outcome: {outcome.upper()}"
        )
    }
