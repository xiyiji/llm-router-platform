"""Intelligent query router for Phase 2.

Routing pipeline:
1. classify the query -> query_type
2. count tokens
3. match configured routing rules (safe AST-based expressions)
4. filter candidates by tier / capabilities / max_tokens / cost limits
5. score remaining candidates (success rate, cost, priority, latency, context fit)
6. build a fallback chain
"""

import ast
import logging
from typing import Dict, List, Optional, Tuple

from schema import ModelConfig, QueryRequest, RouterConfig, RoutingDecision

logger = logging.getLogger(__name__)

CLASSIFICATION_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "coding": (
        "code", "function", "class", "bug", "debug", "python", "javascript",
        "script", "algorithm", "compile", "implement", "parse", "json", "sql",
    ),
    "analysis": (
        "analyze", "analysis", "compare", "comparison", "tradeoff", "trade-off",
        "evaluate", "assess", "pros and cons", "impact", "trend",
    ),
    "reasoning": (
        "why", "prove", "reason", "logic", "step by step", "deduce", "explain why",
    ),
}

# Capability a model must advertise to serve each query type.
REQUIRED_CAPABILITY: Dict[str, str] = {
    "coding": "coding",
    "analysis": "analysis",
    "reasoning": "reasoning",
    "general": "general",
}

# AST nodes allowed in rule condition expressions. Anything else is rejected,
# so a rule can never execute arbitrary code.
_ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Name, ast.Load, ast.Constant, ast.List, ast.Tuple,
)


def classify_query(query: str) -> Tuple[str, float]:
    """Return (query_type, classification_confidence) from keyword evidence."""
    lowered = query.lower()
    best_type, best_hits = "general", 0
    for query_type, keywords in CLASSIFICATION_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in lowered)
        if hits > best_hits:
            best_type, best_hits = query_type, hits
    if best_hits == 0:
        return "general", 0.6
    return best_type, min(0.55 + 0.1 * best_hits, 0.95)


def count_tokens(query: str) -> int:
    """Rough token estimate: ~4 characters per token, at least 1."""
    return max(1, len(query) // 4)


def evaluate_rule(condition: str, context: Dict[str, object]) -> Optional[bool]:
    """Safely evaluate a rule condition against the routing context.

    Returns True/False, or None when the expression is invalid or uses
    disallowed syntax — the caller skips such rules instead of crashing.
    """
    try:
        tree = ast.parse(condition, mode="eval")
    except SyntaxError:
        logger.warning("Skipping rule with invalid syntax: %r", condition)
        return None

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            logger.warning(
                "Skipping rule %r: disallowed syntax node %s",
                condition, type(node).__name__,
            )
            return None

    try:
        return bool(eval(  # noqa: S307 - AST-whitelisted expression, no builtins
            compile(tree, "<rule>", "eval"), {"__builtins__": {}}, dict(context)
        ))
    except Exception as exc:
        logger.warning("Skipping rule %r: evaluation failed (%s)", condition, exc)
        return None


class QueryRouter:
    """Configuration-driven router with rules, filtering, and scoring."""

    def __init__(self, config: RouterConfig):
        self._config = config

    # -- public API ---------------------------------------------------------

    def route(self, request: QueryRequest) -> RoutingDecision:
        query_type, classification_confidence = classify_query(request.query)
        token_count = count_tokens(request.query)

        context = {
            "query_type": query_type,
            "token_count": token_count,
            "user_tier": request.user_tier,
            "query_length": len(request.query),
        }

        matched_rule, candidates, rule_fallback = self._match_rules(context)
        filtered = self._filter_candidates(candidates, request, query_type, token_count)

        if filtered:
            min_cost = min(self._estimate_cost(name, token_count) for name in filtered)
            scored = sorted(
                filtered,
                key=lambda name: self._score(name, token_count, min_cost),
                reverse=True,
            )
            selected = scored[0]
            confidence = min(0.6 + 0.1 * len(filtered), 0.95)
            if matched_rule:
                reason = f"Rule-based selection ({matched_rule}): scored best among {scored}."
            else:
                reason = (
                    f"Capability/score-based selection: best of {scored} "
                    f"for query_type={query_type}."
                )
        else:
            selected = rule_fallback or self._config.default_model
            confidence = 0.5
            reason = (
                "No candidate passed tier/capability filtering; "
                f"using fallback model {selected}."
            )

        model_config = self._config.models[selected]
        return RoutingDecision(
            selected_model=selected,
            provider=model_config.provider,
            routing_reason=reason,
            confidence=confidence,
            query_type=query_type,
            token_count=token_count,
            classification_confidence=classification_confidence,
            estimated_cost=self._estimate_cost(selected, token_count),
            matched_rule=matched_rule,
            fallback_models=self._build_fallback_chain(selected, rule_fallback),
        )

    def healthy(self) -> bool:
        return self._config.default_model in self._config.models

    def details(self) -> dict:
        return {
            "default_model": self._config.default_model,
            "model_count": len(self._config.models),
            "strategy": self._config.strategy,
        }

    # -- pipeline steps -----------------------------------------------------

    def _match_rules(
        self, context: Dict[str, object]
    ) -> Tuple[Optional[str], List[str], Optional[str]]:
        """First matching rule narrows the candidate pool; broken rules are skipped."""
        for rule in self._config.routing_rules:
            if evaluate_rule(rule.condition, context) is True:
                known = [m for m in rule.candidates if m in self._config.models]
                if known:
                    return rule.name, known, rule.fallback
        return None, list(self._config.models.keys()), None

    def _filter_candidates(
        self,
        candidates: List[str],
        request: QueryRequest,
        query_type: str,
        token_count: int,
    ) -> List[str]:
        required = REQUIRED_CAPABILITY.get(query_type, "general")
        tier_limit = self._config.tier_cost_limits.get(request.user_tier)

        def passes(name: str, check_capability: bool) -> bool:
            model = self._config.models[name]
            if request.user_tier not in model.supported_tiers:
                return False
            if model.max_tokens < token_count:
                return False
            if check_capability and required not in model.capabilities:
                return False
            if tier_limit is not None and self._estimate_cost(name, token_count) > tier_limit:
                return False
            return True

        strict = [name for name in candidates if passes(name, check_capability=True)]
        if strict:
            return strict
        # Relax the capability requirement rather than returning nothing.
        return [name for name in candidates if passes(name, check_capability=False)]

    def _score(self, name: str, token_count: int, min_cost: float) -> float:
        model = self._config.models[name]
        max_priority = max(m.priority for m in self._config.models.values())

        cost = self._estimate_cost(name, token_count)
        cost_score = min_cost / cost if cost > 0 else 1.0
        latency_score = 1.0 - min(model.avg_latency_ms / 2000.0, 1.0)
        context_fit = 1.0 if model.max_tokens >= token_count * 4 else 0.5

        return (
            model.success_rate * 0.35
            + cost_score * 0.25
            + (model.priority / max_priority) * 0.10
            + latency_score * 0.20
            + context_fit * 0.10
        )

    def _estimate_cost(self, name: str, token_count: int) -> float:
        """Estimated cost assuming output roughly the size of the input."""
        model = self._config.models[name]
        return round(
            token_count / 1000 * (model.cost_per_1k_input + model.cost_per_1k_output), 8
        )

    def _build_fallback_chain(
        self, selected: str, rule_fallback: Optional[str]
    ) -> List[str]:
        """Follow fallback_model links, then rule fallback, then the default model."""
        chain: List[str] = []
        seen = {selected}
        cursor = self._config.models[selected].fallback_model
        while cursor and cursor in self._config.models and cursor not in seen and len(chain) < 3:
            chain.append(cursor)
            seen.add(cursor)
            cursor = self._config.models[cursor].fallback_model
        for extra in (rule_fallback, self._config.default_model):
            if extra and extra in self._config.models and extra not in seen:
                chain.append(extra)
                seen.add(extra)
        return chain
