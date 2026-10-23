from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from common import (  # noqa: E402
    TARGET_UNIT,
    iter_jsonl,
    read_json,
    sha256_file,
    stable_hash,
    validate_answer_payload,
)
from run_benchmark import (  # noqa: E402
    JSON_OUTPUT_EXAMPLE,
    SYSTEM_PROMPT,
    api_url,
    build_request_body,
    validate_model_config,
)


class MockHandler(BaseHTTPRequestHandler):
    request_count = 0

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        if body.get("response_format") not in (
            {"type": "json_schema", "json_schema": body.get("response_format", {}).get("json_schema")},
            {"type": "json_object"},
        ):
            payload = json.dumps({"error": {"message": "unexpected response_format"}}).encode()
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        type(self).request_count += 1
        if type(self).request_count == 1:
            payload = json.dumps({"error": {"message": "simulated transient"}}).encode()
            self.send_response(503)
            self.send_header("Content-Type", "application/json")
            self.send_header("Retry-After", "0")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        prompt = body["messages"][1]["content"]
        prediction = 1.5 if "NaCl" in prompt else 1.0
        answer = json.dumps(
            {"diffusion_1e9_m2_s": prediction},
            separators=(",", ":"),
        )
        response = {
            "id": f"mock-{type(self).request_count}",
            "object": "chat.completion",
            "model": body["model"],
            "system_fingerprint": "mock-fingerprint",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": answer},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
        }
        payload = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("X-Request-Id", f"req-{type(self).request_count}")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class PipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp(prefix="llm_api_direct_test_"))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
        MockHandler.request_count = 0
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

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
                time.sleep(0.2)
        if last_error is not None:
            raise last_error

    def run_python(self, script: str, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["TEST_LLM_API_KEY"] = "not-a-real-key"
        env["PYTHONUTF8"] = "1"
        return subprocess.run(
            [sys.executable, str(ROOT / script), *map(str, args)],
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )

    def write_assets(self) -> Path:
        questions = [
            {
                "schema_version": "llm_api_direct/v1",
                "question_id": "test::1",
                "base_prompt_id": "test::1",
                "template_family_id": "test_v1",
                "system": "NaCl-H2O",
                "temperature_K": 298.15,
                "concentration_mol_L": 1.0,
                "prompt": "Predict NaCl-H2O at T = 298.15 K and c = 1.000000 mol/L.",
                "evidence_level": "pipeline_test",
            },
            {
                "schema_version": "llm_api_direct/v1",
                "question_id": "test::2",
                "base_prompt_id": "test::2",
                "template_family_id": "test_v1",
                "system": "CaCl2-H2O",
                "temperature_K": 298.15,
                "concentration_mol_L": 0.5,
                "prompt": "Predict CaCl2-H2O at T = 298.15 K and c = 0.500000 mol/L.",
                "evidence_level": "pipeline_test",
            },
        ]
        gold = [
            {
                "question_id": "test::1",
                "base_prompt_id": "test::1",
                "diffusion_1e9_m2_s": 1.5,
                "system": "NaCl-H2O",
                "temperature_K": 298.15,
                "concentration_mol_L": 1.0,
                "origin_lineage_id": "lineage-nacl",
                "split_role": "pipeline_test",
                "evidence_level": "pipeline_test",
            },
            {
                "question_id": "test::2",
                "base_prompt_id": "test::2",
                "diffusion_1e9_m2_s": 1.0,
                "system": "CaCl2-H2O",
                "temperature_K": 298.15,
                "concentration_mol_L": 0.5,
                "origin_lineage_id": "lineage-cacl2",
                "split_role": "pipeline_test",
                "evidence_level": "pipeline_test",
            },
        ]
        question_path = self.temp / "questions.jsonl"
        gold_path = self.temp / "gold.jsonl"
        question_path.write_text(
            "".join(json.dumps(row) + "\n" for row in questions), encoding="utf-8"
        )
        gold_path.write_text(
            "".join(json.dumps(row) + "\n" for row in gold), encoding="utf-8"
        )
        analysis_sets = {
            "schema_version": "llm_api_direct/v1",
            "artifact_type": "llm_api_direct_analysis_sets",
            "response_reuse": True,
            "additional_api_calls_for_sensitivity_subset": 0,
            "primary_question_file": str(question_path),
            "primary_question_file_sha256": sha256_file(question_path),
            "evaluator_gold_file": str(gold_path),
            "evaluator_gold_file_sha256": sha256_file(gold_path),
            "sets": [
                {
                    "analysis_set_id": "primary_all",
                    "role": "primary",
                    "question_count": 2,
                    "question_ids": ["test::1", "test::2"],
                    "question_ids_sha256": stable_hash(["test::1", "test::2"]),
                    "system_counts": {"CaCl2-H2O": 1, "NaCl-H2O": 1},
                },
                {
                    "analysis_set_id": "sensitivity_frozen",
                    "role": "sensitivity",
                    "question_count": 1,
                    "question_ids": ["test::1"],
                    "question_ids_sha256": stable_hash(["test::1"]),
                    "system_counts": {"NaCl-H2O": 1},
                },
            ],
        }
        analysis_sets["analysis_sets_content_sha256"] = stable_hash(analysis_sets)
        analysis_sets_path = self.temp / "analysis_sets.json"
        analysis_sets_path.write_text(
            json.dumps(analysis_sets, indent=2), encoding="utf-8"
        )
        config = {
            "schema_version": "llm_api_direct/v1",
            "question_file": str(question_path),
            "evaluator_gold_file": str(gold_path),
            "analysis_sets_file": str(analysis_sets_path),
            "answer_schema": str(ROOT / "schemas" / "diffusion_answer.schema.json"),
            "output_root": str(self.temp / "results"),
            "repetitions": 2,
            "order_seed": 1,
            "timeout_seconds": 2,
            "inter_request_seconds": 0,
            "retry": {
                "max_attempts_per_sample": 3,
                "max_elapsed_seconds_per_sample": 20,
                "base_wait_seconds": 0,
                "max_wait_seconds": 0,
                "jitter_fraction": 0,
            },
            "models": {
                "mock_model": {
                    "enabled": True,
                    "provider": "mock",
                    "endpoint_url": f"http://127.0.0.1:{self.server.server_port}/v1/chat/completions",
                    "endpoint": "chat_completions",
                    "api_key_env": "TEST_LLM_API_KEY",
                    "model_id": "mock-model-v1",
                    "snapshot_confirmed": True,
                    "evidence_level": "pipeline_test",
                    "structured_output": "json_schema",
                    "temperature": 0,
                    "seed": 1,
                    "max_output_tokens": 64,
                }
            },
        }
        config_path = self.temp / "config.json"
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        return config_path

    def test_schema(self) -> None:
        valid, errors = validate_answer_payload(
            {"diffusion_1e9_m2_s": 1.25}
        )
        self.assertTrue(valid, errors)
        invalid, _ = validate_answer_payload(
            {"diffusion_1e9_m2_s": 1.25, "unit": "m2/s"}
        )
        self.assertFalse(invalid)

    def test_deepseek_json_output_contract(self) -> None:
        model = {
            "provider": "deepseek",
            "base_url": "https://api.deepseek.com",
            "endpoint": "chat_completions",
            "model_id": "deepseek-v4-pro",
            "structured_output": "json_object",
            "thinking": {"type": "disabled"},
            "max_output_tokens": 256,
            "temperature": 0,
        }
        validate_model_config("deepseek_test", model)
        self.assertEqual(api_url(model), "https://api.deepseek.com/chat/completions")
        schema = read_json(ROOT / "schemas" / "diffusion_answer.schema.json")
        body = build_request_body(model, "Return the estimate as JSON.", "task-1", schema)
        self.assertEqual(body["response_format"], {"type": "json_object"})
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertIn("messages", body)
        self.assertNotIn("text", body)
        combined_prompt = "\n".join(message["content"] for message in body["messages"])
        self.assertIn("json", combined_prompt.lower())
        self.assertIn(JSON_OUTPUT_EXAMPLE, SYSTEM_PROMPT)

        invalid_endpoint = {**model, "endpoint": "responses"}
        with self.assertRaisesRegex(ValueError, "chat_completions"):
            validate_model_config("deepseek_test", invalid_endpoint)
        invalid_format = {**model, "structured_output": "json_schema"}
        with self.assertRaisesRegex(ValueError, "json_object"):
            validate_model_config("deepseek_test", invalid_format)

    def test_simplified_config_redacts_api_key(self) -> None:
        advanced_path = self.write_assets()
        advanced = json.loads(advanced_path.read_text(encoding="utf-8"))
        model = advanced["models"]["mock_model"]
        secret = "fake-secret-must-not-appear"
        simple = {
            "api_key": secret,
            "model_name": model["model_id"],
            "provider": model["provider"],
            "base_url": f"http://127.0.0.1:{self.server.server_port}/v1",
            "endpoint": "chat_completions",
            "question_file": advanced["question_file"],
            "evaluator_gold_file": advanced["evaluator_gold_file"],
            "analysis_sets_file": advanced["analysis_sets_file"],
            "answer_schema": advanced["answer_schema"],
            "output_root": str(self.temp / "simple-results"),
            "repetitions": 1,
            "order_seed": 1,
            "timeout_seconds": 2,
            "inter_request_seconds": 0,
            "temperature": 0,
            "seed": 1,
            "max_output_tokens": 64,
            "structured_output": "json_schema",
            "snapshot_confirmed": True,
            "retry": advanced["retry"],
        }
        simple_path = self.temp / "simple_config.json"
        simple_path.write_text(json.dumps(simple), encoding="utf-8")
        completed = self.run_python(
            "run_benchmark.py", "--config", str(simple_path), "--dry-run", "--new-run"
        )
        run_dir = Path(json.loads(completed.stdout.strip().splitlines()[-1])["run_dirs"][0])
        manifest_text = (run_dir / "run_manifest.json").read_text(encoding="utf-8")
        protocol_text = (run_dir / "protocol_material.json").read_text(encoding="utf-8")
        self.assertNotIn(secret, manifest_text)
        self.assertNotIn(secret, protocol_text)
        self.assertIn("<redacted>", manifest_text)

    def test_retry_resume_and_analysis(self) -> None:
        config = self.write_assets()
        dry = self.run_python(
            "run_benchmark.py", "--config", str(config), "--model-key", "mock_model", "--dry-run"
        )
        dry_run_dir = Path(json.loads(dry.stdout.strip().splitlines()[-1])["run_dirs"][0])
        self.assertEqual(read_json(dry_run_dir / "run_manifest.json")["status"], "dry_run_complete")
        started = self.run_python(
            "run_benchmark.py",
            "--config",
            str(config),
            "--model-key",
            "mock_model",
            "--dry-run",
            "--new-run",
        )
        run_dir = Path(json.loads(started.stdout.strip().splitlines()[-1])["run_dirs"][0])
        database = run_dir / "state.sqlite3"
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "UPDATE tasks SET status='in_progress' WHERE queue_index=(SELECT MIN(queue_index) FROM tasks)"
            )
            connection.commit()
        finally:
            connection.close()

        # Mark this dry-run manifest resumable to emulate a process crash after task creation.
        manifest_path = run_dir / "run_manifest.json"
        interrupted = read_json(manifest_path)
        interrupted["status"] = "interrupted"
        manifest_path.write_text(json.dumps(interrupted), encoding="utf-8")
        self.run_python("run_benchmark.py", "--config", str(config), "--model-key", "mock_model")
        manifest = read_json(run_dir / "run_manifest.json")
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["counts"]["completed"], 4)
        self.assertEqual(MockHandler.request_count, 5)
        self.assertFalse(manifest["protocol_pause_triggered"])
        self.assertEqual(len(list(iter_jsonl(run_dir / "sample_results.jsonl"))), 4)

        self.run_python(
            "analyze_results.py",
            "--config",
            str(config),
            "--run-dir",
            str(run_dir),
            "--analysis-id",
            "test-analysis",
            "--bootstrap-replicates",
            "50",
        )
        analysis_dir = self.temp / "results" / "_analysis" / "test-analysis"
        summary = read_json(analysis_dir / "analysis_summary.json")
        self.assertEqual(len(summary["summaries"]), 2)
        primary_summary = next(
            value
            for value in summary["summaries"].values()
            if value["analysis_set_role"] == "primary"
        )
        sensitivity_summary = next(
            value
            for value in summary["summaries"].values()
            if value["analysis_set_role"] == "sensitivity"
        )
        self.assertEqual(primary_summary["overall"]["n_base_prompts"], 2)
        self.assertEqual(sensitivity_summary["overall"]["n_base_prompts"], 1)
        self.assertEqual(
            primary_summary["overall"]["full_question_accuracy_10pct"], 1.0
        )
        self.assertEqual(
            sensitivity_summary["overall"]["full_question_accuracy_10pct"], 1.0
        )
        self.assertTrue(summary["analysis_sets"]["response_reuse"])
        self.assertEqual(
            summary["analysis_sets"]["additional_api_calls_for_sensitivity_subset"], 0
        )
        self.assertTrue((analysis_dir / "manuscript_model_metrics.csv").is_file())

    def test_resume_after_last_attempt_reserved_adds_no_api_call(self) -> None:
        config_path = self.write_assets()
        config = read_json(config_path)
        config["repetitions"] = 1
        config["retry"]["max_attempts_per_sample"] = 1
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        started = self.run_python(
            "run_benchmark.py",
            "--config",
            str(config_path),
            "--model-key",
            "mock_model",
            "--dry-run",
            "--new-run",
        )
        run_dir = Path(json.loads(started.stdout.strip().splitlines()[-1])["run_dirs"][0])
        database = run_dir / "state.sqlite3"
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "UPDATE tasks SET status='in_progress', attempt_count=1 "
                "WHERE queue_index=(SELECT MIN(queue_index) FROM tasks)"
            )
            connection.commit()
        finally:
            connection.close()
        manifest_path = run_dir / "run_manifest.json"
        interrupted = read_json(manifest_path)
        interrupted["status"] = "interrupted"
        manifest_path.write_text(json.dumps(interrupted), encoding="utf-8")

        self.run_python(
            "run_benchmark.py", "--config", str(config_path), "--model-key", "mock_model"
        )
        manifest = read_json(manifest_path)
        self.assertEqual(manifest["status"], "completed")
        self.assertEqual(manifest["counts"]["terminal_failure"], 2)
        self.assertEqual(MockHandler.request_count, 1)
        results = list(iter_jsonl(run_dir / "sample_results.jsonl"))
        interrupted_result = next(
            item
            for item in results
            if item.get("error", {}).get("type")
            == "interrupted_after_retry_budget_exhausted"
        )
        self.assertEqual(interrupted_result["attempt_count"], 1)
        self.assertIsNone(interrupted_result["accepted_response_sha256"])

    def test_retry_settings_change_the_run_fingerprint(self) -> None:
        config_path = self.write_assets()
        started = self.run_python(
            "run_benchmark.py",
            "--config",
            str(config_path),
            "--model-key",
            "mock_model",
            "--dry-run",
            "--new-run",
        )
        run_dir = Path(json.loads(started.stdout.strip().splitlines()[-1])["run_dirs"][0])
        manifest_path = run_dir / "run_manifest.json"
        interrupted = read_json(manifest_path)
        original_fingerprint = interrupted["run_fingerprint"]
        interrupted["status"] = "interrupted"
        manifest_path.write_text(json.dumps(interrupted), encoding="utf-8")

        config = read_json(config_path)
        config["retry"]["max_attempts_per_sample"] += 1
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")
        resumed = self.run_python(
            "run_benchmark.py",
            "--config",
            str(config_path),
            "--model-key",
            "mock_model",
            "--dry-run",
        )
        new_run_dir = Path(json.loads(resumed.stdout.strip().splitlines()[-1])["run_dirs"][0])
        self.assertNotEqual(new_run_dir, run_dir)
        self.assertNotEqual(
            read_json(new_run_dir / "run_manifest.json")["run_fingerprint"],
            original_fingerprint,
        )

    def test_bundled_full_and_sensitivity_question_sets(self) -> None:
        config = read_json(ROOT / "config.json")
        questions = list(iter_jsonl(ROOT / config["question_file"]))
        gold = list(iter_jsonl(ROOT / config["evaluator_gold_file"]))
        analysis_sets = read_json(ROOT / config["analysis_sets_file"])
        self.assertEqual(len(questions), 642)
        self.assertEqual(len(gold), 642)
        system_counts: dict[str, int] = {}
        for question in questions:
            system = str(question["system"])
            system_counts[system] = system_counts.get(system, 0) + 1
        self.assertEqual(
            system_counts,
            {"NaCl-H2O": 174, "KCl-H2O": 247, "LiCl-H2O": 132, "CaCl2-H2O": 89},
        )
        primary = next(item for item in analysis_sets["sets"] if item["role"] == "primary")
        sensitivity = next(
            item for item in analysis_sets["sets"] if item["role"] == "sensitivity"
        )
        self.assertEqual(primary["question_count"], 642)
        self.assertEqual(sensitivity["question_count"], 240)
        self.assertEqual(
            sensitivity["system_counts"],
            {"CaCl2-H2O": 60, "KCl-H2O": 60, "LiCl-H2O": 60, "NaCl-H2O": 60},
        )
        self.assertTrue(set(sensitivity["question_ids"]) < set(primary["question_ids"]))
        self.assertEqual(
            sensitivity["question_ids_sha256"],
            "dae63a99271de1286be373d7956315c3b802ade1d4a840f63ace99f644c05d89",
        )


if __name__ == "__main__":
    unittest.main()
