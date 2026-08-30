# Phase 2 notes

## Routing steps (router.py)

1. Classify the query by keywords into coding / analysis / reasoning /
   general, with a rough confidence.
2. Estimate token count (about 4 chars per token).
3. Try the routing rules from config.yaml in order. Conditions are boolean
   expressions like `query_type == 'coding'`. They go through ast.parse and
   a node whitelist (comparisons, and/or/not, names, constants, lists), so
   function calls or imports in a rule just make it get skipped with a
   warning. eval runs with empty builtins on the whitelisted tree.
4. Filter candidates: user tier supported, capability matches the query
   type, context window big enough, estimated cost under the tier limit.
   If nothing survives, retry without the capability requirement.
5. Score what's left: success rate 0.35, relative cost 0.25, latency 0.20,
   priority 0.10, context fit 0.10. Highest wins.
6. Build the fallback chain: follow fallback_model links from the selected
   model, then the rule's fallback, then the default model.

## Providers (inference.py)

BaseProvider has three subclasses. LocalProvider always works and echoes the
query. OpenAIProvider and AnthropicProvider check their API key env var; no
key means unavailable, which triggers fallback. They don't call the real
APIs yet, `_generate_text` is where that would go.

InferenceEngine.run walks [selected] + fallback chain, records every attempt
and error, and returns a unified result. If the whole chain fails, main.py
still returns a normal JSON body with the error field set instead of a 500.

## Trying fallback

Run without OPENAI_API_KEY / ANTHROPIC_API_KEY and send a premium query.
The response shows fallback_used, attempted_models and provider_errors.
