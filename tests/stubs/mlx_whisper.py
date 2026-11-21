"""Hermetic stand-in for mlx_whisper, injected via PYTHONPATH in tests.

Returns two fixed sentence-grain segments with word timings, tagged with the
model repo so tests can assert the config value was honored.
"""

CALLS = []


def transcribe(path, path_or_hf_repo=None, word_timestamps=False):
    return {
        "language": "en",
        "segments": [
            {"start": 0.0, "end": 1.5, "text": f" Hello from {path_or_hf_repo}.",
             "words": [{"word": " Hello", "start": 0.0, "end": 0.5},
                       {"word": " from", "start": 0.5, "end": 0.8},
                       {"word": f" {path_or_hf_repo}.", "start": 0.8, "end": 1.5}]},
            {"start": 1.5, "end": 2.9, "text": " Second sentence here. ",
             "words": [{"word": " Second", "start": 1.5, "end": 2.0},
                       {"word": " sentence", "start": 2.0, "end": 2.5},
                       {"word": " here.", "start": 2.5, "end": 2.9}]},
            {"start": 2.9, "end": 3.0, "text": "   ",
             "words": []},  # blank segment: must be skipped, idx must not gap
        ],
    }
