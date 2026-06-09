# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""LoRA fine-tuning pipeline using Unsloth. Runs overnight via DreamingLoop."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from learning.training_collector import TrainingCollector

MIN_ENTRIES = 500
LORA_RANK = 8
MAX_SEQ_LEN = 2048


def finetune(domain: str | None = None, dry_run: bool = False) -> dict:
    collector = TrainingCollector()
    data = collector.export_for_training(domain=domain)

    if len(data) < MIN_ENTRIES:
        print(f"Need {MIN_ENTRIES} entries, have {len(data)}. Skipping.")
        return {"status": "skipped", "reason": "insufficient_data", "count": len(data)}

    if dry_run:
        print(f"DRY RUN: Would fine-tune on {len(data)} examples for domain={domain}")
        return {"status": "dry_run", "count": len(data)}

    try:
        from unsloth import FastLanguageModel
        import torch
    except ImportError:
        return {"status": "error", "reason": "unsloth not installed. Run: pip install unsloth"}

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name="unsloth/llama-3.1-8b-bnb-4bit",
        max_seq_length=MAX_SEQ_LEN,
        load_in_4bit=True,
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=LORA_RANK,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        lora_alpha=16,
        lora_dropout=0,
        bias="none",
    )

    dataset = _format_dataset(data, tokenizer)

    from trl import SFTTrainer
    from transformers import TrainingArguments
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        args=TrainingArguments(
            output_dir=f"./checkpoints/{domain or 'general'}",
            per_device_train_batch_size=1,
            gradient_accumulation_steps=4,
            num_train_epochs=3,
            learning_rate=2e-4,
            fp16=not torch.cuda.is_bf16_supported(),
            bf16=torch.cuda.is_bf16_supported(),
            logging_steps=10,
        )
    )
    trainer.train()

    output_path = f"./models/jarvis-{domain or 'general'}.gguf"
    model.save_pretrained_gguf(output_path, tokenizer)

    return {"status": "done", "model_path": output_path, "examples": len(data)}


def _format_dataset(data: list[dict], tokenizer) -> list:
    from datasets import Dataset

    def format_row(row):
        return {"text": f"### Instruction:\n{row['instruction']}\n\n### Response:\n{row['output']}"}

    return Dataset.from_list([format_row(r) for r in data])


def deploy_to_ollama(model_path: str, model_name: str) -> None:
    """Create Ollama model from GGUF checkpoint. Works on Windows."""
    import subprocess
    tmp_dir = Path(tempfile.gettempdir())
    modelfile_path = tmp_dir / f"{model_name}.Modelfile"
    modelfile = f"FROM {model_path}\nSYSTEM You are JARVIS specialized assistant."
    modelfile_path.write_text(modelfile)
    subprocess.run(["ollama", "create", model_name, "-f", str(modelfile_path)])
    print(f"Deployed: {model_name}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = finetune(domain=args.domain, dry_run=args.dry_run)
    print(json.dumps(result, indent=2))
