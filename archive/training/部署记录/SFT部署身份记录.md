# SFT 部署身份记录（Qwen3.6-27B，首个完成模型）

> 依据：方案 v2.13/v2.14、训练配置冻结清单、服务器 agent 执行报告（2026-08-19）。
> 本记录是 `py/SLM_direct/config.json` sft 条目（`sft_artifacts`/`training_provenance`）
> 的字段来源，也是论文方法与补充材料的部署身份留档。

## 1. 训练身份（服务器）

| 项 | 值 |
|---|---|
| 基座 | `E:\models\cet_formal\qwen3.6-27b`（ModelScope `Qwen/Qwen3.6-27B`，revision `cea40373…`，见 A 臂冻结清单） |
| 框架 | LLaMA-Factory 0.9.5（Python 3.13.12，torch 2.11.0+cu128，CUDA 12.8） |
| 配置 | `configs/qwen3_6_27b_sft_lora.yaml`（冻结，SHA-256 `d3623a93…`） |
| 数据集 | `train_642`（642 条，SHA-256 `f95b8a55…`） |
| LoRA | r=64、α=128、dropout=0、lr=1e-4、5 epochs、有效 batch 16、cosine、warmup 0.1、cutoff 512、bf16、seed 42、paged_adamw_8bit、gradient_checkpointing、max_grad_norm 1.0 |
| target_modules（实测，模板默认） | in_proj_qkv, out_proj, o_proj, k_proj, up_proj, v_proj, down_proj, in_proj_b, gate_proj, in_proj_z, in_proj_a, q_proj（12 模块） |
| trainable params | 466,911,232（1.6781%） |
| loss | 1.0403（step 5）→ 0.2082（step 205）；train_runtime 7876 s（2:11:16） |
| 显存峰值 | 63,471 MB / 85,651 MB |
| checkpoints | checkpoint-41/82/123/164/205（全保留，未删除） |
| adapter 目录 | `E:\models\cet_formal_sft\qwen3.6-27b-lora-r64`（13 文件 SHA-256 见执行报告 Phase 3） |

## 2. 合并与量化（服务器）

| 项 | 值 |
|---|---|
| 合并目录 | `E:\models\cet_formal_sft\qwen3.6-27b-lora-r64-merged`（12 分片，SHA-256 见执行报告 Phase 4） |
| llama.cpp | `D:\llama.cpp` @ b10188（`d0bfb1981266c271cd0536a8aa7c5e863e7cdf61`），转换加 `--no-mtp`（MTP 头排除；Base 侧一致性待 check_gguf_mtp.py 复核） |
| f16 GGUF | `E:\gguf\cet_sft\qwen3.6-27b-lora-r64-f16.gguf`（53.8 GB，851 tensors） |
| Q4_K_M GGUF | `E:\gguf\cet_sft\qwen3.6-27b-lora-r64-q4_k_m.gguf`（15.77 GB，4.92 BPW），**SHA-256 `7EDE95F348E2764668C97E404CCAA917058A600DE86B9A09655163EB58A56B8B`** |

## 3. 部署身份（LM Studio，2026-08-21 实测）

| 项 | 值 |
|---|---|
| served model id | `qwen3.6-27b-lora-r64`（自定义 user-repo，无 `@q4_k_m` 后缀） |
| 量化 | Q4_K_M（API 确认） |
| context length | 4096 |
| Runtime | **llama.cpp nvidia-cuda12-avx2 2.29.0**（v2.14 记录：Base 为 avx2，SFT 用 CUDA，差异如实记录） |
| LM Studio | 0.4.20+1 |
| Reasoning | 部署级 **Off**（普通请求探测：`reasoning_tokens=0`、`content='4'`、`finish_reason=stop`，2026-08-21） |
| 聊天模板 | merged 与 base `chat_template` **逐字一致**（SHA-256 `e84f32a23fdda27689f868aa4a1a5621f41133e51a48d7f3efcbea2839574259`） |

## 4. 待补

- [x] `check_gguf_mtp.py` 复核完成（2026-08-21）：**Base GGUF 含 MTP 头（blk.64=True）**、
  **SFT GGUF 无 MTP 头（--no-mtp）**。记录性偏差说明：MTP（多 token 预测头）仅在
  训练时使用，推理生成不经过 MTP 头，主路径权重一致 → 对评测无实质影响；
  偏差由 LM Studio CUDA12 runtime 无法加载含 MTP 头的 GGUF 强制产生，
  与 v2.14 的 CUDA 部署决定一并记录，论文方法如实标注。
- [ ] 其余四模型训练与部署（后续任务书）；
- [ ] `py/SLM_direct/config.json` 增 sft 条目（pair_id `qwen3_6_27b`、pair_role=sft、
      本记录各哈希填入 sft_artifacts/training_provenance）→ 菜单 4 跑 642 掌握度（1926 次调用）。
