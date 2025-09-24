from __future__ import annotations

from typing import Protocol, Any, Dict


class Scorer(Protocol):
	def score(self, item: Dict[str, Any]) -> Dict[str, Any]:
		"""Return a new dict with scoring results merged or attached."""
		...


class DummyScorer:
	def score(self, item: Dict[str, Any]) -> Dict[str, Any]:
		result = dict(item)
		text = str(item.get("text", ""))
		result["score"] = min(5.0, max(0.0, len(text) / 100.0))
		return result
