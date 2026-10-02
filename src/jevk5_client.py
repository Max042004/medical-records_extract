"""Client for JevK5 served by llama-server.

Follows the model card's standalone client: the answer is read from the
next-token log-probabilities of the option letters (nothing is generated),
then calibrated with the file's temperature.
"""
import json
import math
import urllib.request

LETTERS = "ABCDEFGHIJKLMNOP"
SYSTEM = ("Apply the supplied criterion to the supplied evidence. Choose exactly one listed option. "
          "Respond with only its uppercase letter, with no explanation or reasoning.")
# Temperature published on the model card for jevk5-9b-v0.3.3-*.gguf
TEMPERATURE_9B_V033 = 1.316


class JevK5:
    def __init__(self, url="http://127.0.0.1:8080", temperature=TEMPERATURE_9B_V033):
        self.url, self.t = url, temperature

    def _post(self, path, body):
        req = urllib.request.Request(self.url + path, json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            return json.load(r)

    def n_tokens(self, text):
        return len(self._post("/tokenize", {"content": text})["tokens"])

    def decide(self, evidence, criterion, options):
        """options: {id: description}, at most 16. Returns {id: probability}."""
        ids = list(options)
        assert 1 <= len(ids) <= len(LETTERS)
        # Evidence comes first so consecutive questions about one document share a cached prefix.
        user = json.dumps({"evidence": evidence, "criterion": criterion,
                           "options": [{"letter": LETTERS[i], "description": f"{k}: {options[k]}"}
                                       for i, k in enumerate(ids)]}, ensure_ascii=False)
        prompt = (f"<|im_start|>system\n{SYSTEM}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n"
                  "<|im_start|>assistant\n<think>\n\n</think>\n\n")
        tokens = self._post("/tokenize", {"content": prompt, "add_special": False,
                                          "parse_special": True})["tokens"]
        top = self._post("/completion", {"prompt": tokens, "n_predict": 1, "n_probs": 40,
                                         "temperature": 0, "cache_prompt": True}
                         )["completion_probabilities"][0]["top_logprobs"]
        seen = {t["token"]: t["logprob"] for t in top}
        floor = min(seen.values()) - 2.0
        z = [seen.get(LETTERS[i], floor) for i in range(len(ids))]
        w = [math.exp((v - max(z)) / self.t) for v in z]
        return {k: x / sum(w) for k, x in zip(ids, w)}
