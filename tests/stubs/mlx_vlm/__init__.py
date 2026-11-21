"""Hermetic stand-in for mlx_vlm, injected via PYTHONPATH in tests.

Frame captions encode the frame filename stem (the keyframe time), so tests
can assert time->caption alignment. Text-only prompts (num images 0) return a
fixed summary sentence.
"""

import os
from pathlib import Path
from types import SimpleNamespace


def load(repo):
    model = SimpleNamespace(config={"stub": True, "repo": repo})
    processor = SimpleNamespace()
    return model, processor


JUNK = "<|im_start|>\n addCriterion\n"  # real Qwen2.5-VL/mlx-vlm leakage shape


def generate(model, processor, prompt, image=None, **kwargs):
    if image:
        stem = Path(image[0]).stem
        junk_stems = os.environ.get("STUB_VLM_JUNK_STEMS", "").split(",")
        if stem in junk_stems:  # simulate the junk-only collapse on this frame
            return SimpleNamespace(text=" addCriterion")
        return SimpleNamespace(text=f"{JUNK}Stub caption of frame {stem}.")
    return SimpleNamespace(text=f"{JUNK}A stub visual summary of the whole clip.")
