from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from slm_common import (  # noqa: E402
    EXPECTED_BASE_MODEL_KEYS,
    apply_chat_message_policy,
    formal_readiness_issues,
    load_config,
    preflight_model,
    read_json,
)


MODEL_KEY = "qwen3_4b_instruct_2507_base_q4km"


class MockLMStudioHandler(BaseHTTPRequestHandler):
    served_model_id = MODEL_KEY
    request_bodies: list[dict[str, Any]] = []

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/v1/models":
            self._send_json(
                {
                    "object": "list",
                    "data": [
                        {
                            "id": type(self).served_model_id,
                            "object": "model",
                            "owned_by": "organization-owner",
                        }
                    ],
                }
            )
            return
        if self.path == "/api/v1/models":
            self._send_json(
                {
                    "models": [
                        {
                            "key": "mock/model-q4_k_m.gguf",
                            "type": "llm",
                            "format": "gguf",
                            "architecture": "qwen3",
                            "quantization": {"name": "Q4_K_M", "bits_per_weight": 4.8},
                            "loaded_instances": [
                                {
                                    "id": type(self).served_model_id,
                                    "config": {"context_length": 4096},
                                }
                            ],
                        }
                    ]
                }
            )
            return
        self._send_json({"error": "not found"}, status=404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/chat/completions":
            self._send_json({"error": "not found"}, status=404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        type(self).request_bodies.append(body)
        response_format = body.get("response_format", {})
        schema = response_format.get("json_schema", {})
        if (
            body.get("model") != type(self).served_model_id
            or response_format.get("type") != "json_schema"
            or schema.get("strict") is not True
            or schema.get("schema", {}).get("additionalProperties") is not False
        ):
            self._send_json({"error": {"message": "request contract mismatch"}}, status=400)
            return
        answer = json.dumps({"diffusion_1e9_m2_s": 1.25}, separators=(",", ":"))
        self._send_json(
            {
                "id": f"mock-{len(type(self).request_bodies)}",
                "object": "chat.completion",
                "created": 0,
                "model": type(self).served_model_id,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": answer},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                },
            }
        )


class PipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp(prefix="slm_direct_test_"))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), MockLMStudioHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.config_path = self._write_config()
        config = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
        self.served_id = config["models"][MODEL_KEY]["served_model_id"]
        MockLMStudioHandler.served_model_id = self.served_id
        MockLMStudioHandler.request_bodies = []

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        last_error: OSError | None = None
        for _ in range(50):
            try:
                shutil.rmtree(self.temp)
                return
            except FileNotFoundError:
                return
            except OSError as exc:
                last_error = exc
                time.sleep(0.1)
        if last_error is not None:
            raise last_error

    def _write_config(self) -> Path:
        source_path = ROOT / "config.json"
        config = copy.deepcopy(read_json(source_path))
        for field in (
            "question_file",
            "question_manifest_file",
            "evaluator_gold_file",
            "analysis_sets_file",
            "answer_schema",
        ):
            config[field] = str((source_path.parent / config[field]).resolve())
        config["pipeline_test"] = True
        config["output_root"] = str(self.temp / "results")
        config["repetitions"] = 1
        config["inter_request_seconds"] = 0
        config["retry"] = {
            "max_attempts_per_sample": 2,
            "max_elapsed_seconds_per_sample": 10,
            "base_wait_seconds": 0,
            "max_wait_seconds": 0,
            "jitter_fraction": 0,
        }
        port = self.server.server_port
        config["server"]["base_url"] = f"http://127.0.0.1:{port}/v1"
        config["server"]["native_models_url"] = (
            f"http://127.0.0.1:{port}/api/v1/models"
        )
        config_path = self.temp / "config.json"
        config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return config_path

    def run_python(self, script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONPYCACHEPREFIX"] = str(self.temp / "pycache")
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / script),
                "--config",
                str(self.config_path),
                *arguments,
            ],
            cwd=ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )

    def run_pilot(self, experiment_name: str) -> Path:
        completed = self.run_python(
            "run_benchmark.py",
            "--model-key",
            MODEL_KEY,
            "--mode",
            "pilot",
            "--experiment-name",
            experiment_name,
            "--limit",
            "2",
            "--new-run",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        return Path(payload["run_dir"])

    def test_config_contains_exact_five_frozen_base_models(self) -> None:
        _, config = load_config(self.config_path)
        self.assertEqual(EXPECTED_BASE_MODEL_KEYS, set(config["models"]))
        served_ids = [model["served_model_id"] for model in config["models"].values()]
        self.assertEqual(len(served_ids), len(set(served_ids)))
        self.assertEqual(served_ids[0], "cet-gguf/qwen3-4b-instruct-2507@q4_k_m")

    def test_preflight_uses_both_interfaces_and_exact_loaded_identity(self) -> None:
        _, config = load_config(self.config_path)
        snapshot = preflight_model(config, MODEL_KEY)
        self.assertTrue(snapshot["passed"])
        self.assertEqual(snapshot["exact_loaded_instance_count"], 1)
        self.assertEqual(snapshot["total_loaded_instance_count"], 1)
        self.assertTrue(all(snapshot["metadata_checks"].values()))

        MockLMStudioHandler.served_model_id = "wrong_identifier"
        mismatch = preflight_model(config, MODEL_KEY)
        self.assertFalse(mismatch["passed"])
        self.assertEqual(mismatch["exact_loaded_instance_count"], 0)

    def test_pipeline_config_is_always_rejected_for_formal_runs(self) -> None:
        _, config = load_config(self.config_path)
        issues = formal_readiness_issues(config, MODEL_KEY)
        self.assertTrue(any("pipeline_test" in issue for issue in issues))
        self.assertTrue(any("repetitions" in issue for issue in issues))
        self.assertTrue(any("protocol_frozen" in issue for issue in issues))

    def test_gemma_system_message_is_deterministically_folded_into_user(self) -> None:
        body = {
            "model": "gemma",
            "messages": [
                {"role": "system", "content": "fixed system instructions"},
                {"role": "user", "content": "benchmark question"},
            ],
        }
        transformed = apply_chat_message_policy(
            body, {"system_message_policy": "fold_system_into_first_user"}
        )
        self.assertEqual([row["role"] for row in transformed["messages"]], ["user"])
        self.assertEqual(
            transformed["messages"][0]["content"],
            "fixed system instructions\n\nbenchmark question",
        )
        self.assertEqual(body["messages"][0]["role"], "system")

    def test_new_pilot_runs_are_distinct_and_emit_traceable_json(self) -> None:
        first = self.run_pilot("unit_json_contract")
        second = self.run_pilot("unit_json_contract")
        self.assertNotEqual(first, second)
        self.assertTrue(first.name.startswith("unit_json_contract__"))
        self.assertTrue(second.name.startswith("unit_json_contract__"))

        for run_dir in (first, second):
            manifest = read_json(run_dir / "run_manifest.json")
            self.assertEqual(manifest["artifact_type"], "slm_direct_run_manifest")
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(manifest["run_mode"], "pilot")
            self.assertEqual(manifest["experiment_arm"], "A_base_direct")
            self.assertEqual(manifest["pair_role"], "base")
            self.assertTrue(manifest["lm_studio_preflight"]["passed"])
            self.assertTrue(manifest["lm_studio_preflight"]["smoke_test"]["passed"])
            self.assertEqual(
                manifest["lm_studio_preflight"]["smoke_test"]["diagnostic_call_count"],
                1,
            )
            self.assertTrue(manifest["served_model_identity_check"]["passed"])
            self.assertEqual(manifest["returned_model_ids"], [self.served_id])
            records = [
                json.loads(line)
                for line in (run_dir / "sample_results.jsonl")
                .read_text(encoding="utf-8-sig")
                .splitlines()
                if line.strip()
            ]
            self.assertEqual(len(records), 2)
            self.assertEqual(len({record["pair_task_id"] for record in records}), 2)
            self.assertTrue(
                all(record["response_quality"]["answer_schema_valid"] for record in records)
            )
            self.assertTrue(
                all(
                    record["response_quality"]["parsed_prediction_1e9_m2_s"] == 1.25
                    for record in records
                )
            )
            self.assertTrue(
                all(record["language_model_artifact_id"] for record in records)
            )
            request_files = sorted((run_dir / "raw" / "requests").glob("*.json"))
            self.assertEqual(len(request_files), 2)
            for request_file in request_files:
                request = read_json(request_file)
                self.assertFalse(request["gold_in_request"])
                self.assertEqual(request["body"]["model"], self.served_id)
                self.assertEqual(
                    request["body"]["response_format"]["type"], "json_schema"
                )
                self.assertEqual(
                    [message["role"] for message in request["body"]["messages"]],
                    ["system", "user"],
                )

    def test_skip_preflight_is_only_allowed_for_dry_run(self) -> None:
        completed = self.run_python(
            "run_benchmark.py",
            "--model-key",
            MODEL_KEY,
            "--mode",
            "pilot",
            "--experiment-name",
            "invalid_skip",
            "--limit",
            "1",
            "--new-run",
            "--skip-preflight",
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("--skip-preflight", completed.stderr)


if __name__ == "__main__":
    unittest.main()
