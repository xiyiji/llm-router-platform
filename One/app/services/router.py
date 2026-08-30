"""Rule-based query router (Phase 1)."""

from app.schemas import QueryRequest, RouterConfig, RoutingDecision

LONG_QUERY_THRESHOLD = 1000

CODING_KEYWORDS = (
    "code",
    "function",
    "class",
    "bug",
    "debug",
    "python",
    "javascript",
    "script",
    "algorithm",
    "compile",
)


class QueryRouter:
    """Selects a model for an incoming query using simple rules."""

    def __init__(self, config: RouterConfig):
        self._config = config

    def route(self, request: QueryRequest) -> RoutingDecision:
        query = request.query

        if len(query) > LONG_QUERY_THRESHOLD and self._has_model("long-context"):
            return RoutingDecision(
                selected_model="long-context",
                routing_reason=(
                    f"Query length {len(query)} exceeds {LONG_QUERY_THRESHOLD} "
                    "characters; using long-context model."
                ),
                confidence=0.9,
                query_type="long_context",
            )

        lowered = query.lower()
        matched = [kw for kw in CODING_KEYWORDS if kw in lowered]
        if matched and self._has_model("coding-pro"):
            return RoutingDecision(
                selected_model="coding-pro",
                routing_reason="Detected coding-related keywords in the query.",
                confidence=0.82,
                query_type="coding",
            )

        return RoutingDecision(
            selected_model=self._config.default_model,
            routing_reason="Using default general-purpose model.",
            confidence=0.65,
            query_type="general",
        )

    def _has_model(self, model_name: str) -> bool:
        return model_name in self._config.models

    def healthy(self) -> bool:
        return self._config.default_model in self._config.models
