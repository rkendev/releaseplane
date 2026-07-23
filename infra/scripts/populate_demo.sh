#!/usr/bin/env bash
#
# Put real data behind the public read-only dashboards (ADR 0009).
#
# This is the one deliberate live-spend path outside the eval baseline runs. It is
# owner-run, never automatic: CI never invokes it, nothing imports it, and it
# refuses to start without an explicit acknowledgement in the environment.
#
#   infra/scripts/populate_demo.sh --dry-run     # free, and worth running first
#   RELEASEPLANE_DEMO_SPEND=i-accept infra/scripts/populate_demo.sh
#
# --dry-run does everything that costs nothing: preconditions, seeding, the model
# config and routing rule, the dataset load, and creating both releases. It stops
# short of the two eval runs and the three invokes, which are the only steps that
# spend. Run it against the dummy-pinned stack to find a missing key, a stale
# schema, or a bad id before paying to discover the same thing.
#
# It drives the scripts that already exist rather than reimplementing them:
# control-plane/scripts/seed_invoice_v1.py, the evals CLI, and the control-plane
# API as the runbook's "Walk a release through the gate" section uses it.
#
# What it produces, which is exactly what the dashboards need:
#   - a v1 release the gate blocks, from the discount-as-negative-line failure
#   - a v2 release that passes and is promoted to active
#   - a few /invoke calls: the Sonnet default, one routed to gpt-4o-mini, and one
#     carrying a bad total so a policy event renders
#
# Estimated spend is printed before anything runs. Re-run cost is the same again;
# nothing here is free on the second pass.
#
# Afterwards the gateway must go back to the dummy provider. The script does that
# itself as its last step, and says so if it cannot.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

CP="${CONTROL_PLANE_URL:-http://localhost:${CONTROL_PLANE_HOST_PORT:-8001}}"
GW="${GATEWAY_URL:-http://localhost:${GATEWAY_HOST_PORT:-8002}}"

# Two live eval runs over 30 cases each, plus three invokes. The eval figure is the
# measured range from docs/EVALUATION.md; the invokes are cents.
ESTIMATED_SPEND="roughly \$0.60 to \$1.80"

DRY_RUN=0
case "${1:-}" in
  --dry-run) DRY_RUN=1 ;;
  "") ;;
  *) printf 'usage: %s [--dry-run]\n' "$0" >&2; exit 2 ;;
esac

say() { printf '\n=== %s ===\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------- preconditions

if [ "$DRY_RUN" = "1" ]; then
  say "dry run: everything except the two eval runs and the three invokes"
elif [ "${RELEASEPLANE_DEMO_SPEND:-}" != "i-accept" ]; then
  cat >&2 <<EOF
This script makes real, paid provider API calls.

  Estimated spend: $ESTIMATED_SPEND of the owner's own credit.

It runs two live evals against the pinned Sonnet 4.6 and three /invoke calls, one
of which routes to gpt-4o-mini. Nothing here is recoverable once spent.

To proceed:

  RELEASEPLANE_DEMO_SPEND=i-accept infra/scripts/populate_demo.sh

EOF
  exit 1
fi

command -v jq > /dev/null || die "jq is required"

for f in infra/secrets/claude_api_key infra/secrets/openai_api_key; do
  [ -s "$f" ] || die "$f is missing or empty; run 'make secrets' with both keys set"
done

# The gateway must not be pinned to dummy, or every eval scores zero and the run
# spends nothing while looking like it worked. Ask the gateway what it is serving
# rather than reading the compose files, since the running container is the truth.
# A dry run has nothing to spend, so the pin is fine there and is the normal state
# to rehearse in.
GATEWAY_PINNED="$(docker inspect releaseplane-gateway \
  --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
  | sed -n 's/^GATEWAY_PROVIDER=//p' || true)"
if [ "$DRY_RUN" = "0" ] && [ "$GATEWAY_PINNED" = "dummy" ]; then
  die "the gateway is pinned to GATEWAY_PROVIDER=dummy, so this would score 0 and spend nothing.
Clear the pin in infra/docker-compose.override.yml (set it to \"\"), recreate the gateway, then re-run.
The last step of this script puts the pin back."
fi

curl -sf "$CP/healthz" > /dev/null || die "control plane is not answering at $CP"
curl -sf "$GW/healthz" > /dev/null || die "gateway is not answering at $GW"

[ "$DRY_RUN" = "1" ] || say "spend acknowledged: $ESTIMATED_SPEND"

# ------------------------------------------------------------------- seed state

say "seeding prompts, policy bundle, and the default model config (idempotent)"
CONTROL_PLANE_URL="$CP" uv run python control-plane/scripts/seed_invoice_v1.py
curl -sf -X POST "$CP/model-configs/seed" > /dev/null

PROMPT_ID=$(curl -sf "$CP/prompts" | jq -r '.[] | select(.name=="invoice-extraction") | .id')
MODEL_ID=$(curl -sf "$CP/model-configs" | jq -r '.[] | select(.name=="v1_default") | .id')
BUNDLE_ID=$(curl -sf "$CP/policy-bundles" | jq -r '.[] | select(.name=="invoice_v1") | .id')
[ -n "$PROMPT_ID" ] && [ -n "$MODEL_ID" ] && [ -n "$BUNDLE_ID" ] || die "seeding did not produce the three ids"

# Routing rules are keyed on the prompt's use_case, which is not the prompt name:
# the gateway looks up rules by the use_case on the resolved release. Reading it
# from the prompt rather than writing the literal is what keeps a rule from being
# created that can never fire, which is a failure that costs a real invoke to
# notice and produces nothing on the dashboard.
USE_CASE=$(curl -sf "$CP/prompts" | jq -r '.[] | select(.name=="invoice-extraction") | .use_case')
[ -n "$USE_CASE" ] || die "prompt invoice-extraction has no use_case"
echo "use_case: $USE_CASE"

say "loading the 30-case golden dataset"
CONTROL_PLANE_URL="$CP" uv run python -m releaseplane_evals.cli load > /dev/null
DATASET_ID=$(curl -sf "$CP/eval-datasets" | jq -r '.[] | select(.name=="invoice_v1") | .id')
[ -n "$DATASET_ID" ] || die "dataset invoice_v1 did not load"

# The cost-routing beat needs a second model config and a rule that reaches it.
# Both are idempotent: reuse the existing rows on a re-run rather than duplicating.
say "ensuring the gpt-4o-mini model config and its routing rule exist"
MINI_ID=$(curl -sf "$CP/model-configs" | jq -r '.[] | select(.name=="v1_cost_tier") | .id')
if [ -z "$MINI_ID" ]; then
  MINI_ID=$(curl -sf -X POST "$CP/model-configs" -H 'content-type: application/json' -d '{
    "name": "v1_cost_tier",
    "provider": "openai",
    "model_name": "gpt-4o-mini",
    "model_version_pin": "gpt-4o-mini",
    "temperature": 0.0,
    "max_tokens": 4096,
    "timeout_ms": 30000,
    "tool_mode": "structured_output",
    "active": true,
    "cost_per_mtok_input_usd": 0.15,
    "cost_per_mtok_output_usd": 0.60
  }' | jq -r .id)
fi
[ -n "$MINI_ID" ] || die "could not resolve the gpt-4o-mini model config"

# Match on use_case as well as target: a rule pointing at the right model config
# under the wrong use_case is exactly the rule that never fires, so finding one
# must not count as "already done".
HAS_RULE=$(curl -sf "$CP/routing-rules" | jq -r --arg m "$MINI_ID" --arg u "$USE_CASE" \
  '[.[] | select(.target_model_config_id==$m and .use_case==$u)] | length')
if [ "$HAS_RULE" = "0" ]; then
  curl -sf -X POST "$CP/routing-rules" -H 'content-type: application/json' -d "{
    \"use_case\": \"$USE_CASE\",
    \"predicate\": {\"field\": \"routing_hint\", \"op\": \"eq\", \"value\": \"cost\"},
    \"target_model_config_id\": \"$MINI_ID\",
    \"priority\": 10
  }" > /dev/null
fi

# The rules API has no delete, so a wrong rule from an earlier attempt stays. Say
# so rather than letting a stale one shadow the right one at a lower priority.
STALE=$(curl -sf "$CP/routing-rules" | jq -r --arg m "$MINI_ID" --arg u "$USE_CASE" \
  '[.[] | select(.target_model_config_id==$m and .use_case!=$u) | .use_case] | join(", ")')
[ -z "$STALE" ] || printf 'note: rules also exist under use_case "%s"; they cannot match and cannot be deleted.\n' "$STALE"

# ------------------------------------------------------ v1: the gate blocks it

release_for_version() {
  local version="$1"
  local version_id
  version_id=$(curl -sf "$CP/prompts/$PROMPT_ID/versions" \
    | jq -r --arg v "$version" '.[] | select(.version==$v) | .id')
  [ -n "$version_id" ] || die "prompt version $version not found"
  curl -sf -X POST "$CP/releases" -H 'content-type: application/json' \
    -d "{\"prompt_version_id\":\"$version_id\",\"model_config_id\":\"$MODEL_ID\",\"policy_bundle_id\":\"$BUNDLE_ID\"}" \
    | jq -r .id
}

say "v1 release: live eval against the pinned Sonnet 4.6 (spends)"
V1_RELEASE=$(release_for_version v1)
echo "release $V1_RELEASE"

if [ "$DRY_RUN" = "1" ]; then
  echo "dry run: skipping the eval, the promotion attempt, and everything after"
  say "dry run complete"
  cat <<EOF
Everything that costs nothing worked:

  prompt        $PROMPT_ID
  model config  $MODEL_ID (v1_default)
  cost tier     $MINI_ID (v1_cost_tier, gpt-4o-mini, reachable by routing_hint=cost)
  policy bundle $BUNDLE_ID
  dataset       $DATASET_ID
  v1 release    $V1_RELEASE

The releases created here are drafts and cost nothing to leave behind, but the real
run creates its own, so clean them up if you would rather not accumulate drafts.
When ready:

  RELEASEPLANE_DEMO_SPEND=i-accept infra/scripts/populate_demo.sh
EOF
  exit 0
fi

CONTROL_PLANE_URL="$CP" GATEWAY_URL="$GW" \
  uv run python -m releaseplane_evals.cli run --release-id "$V1_RELEASE" --dataset-id "$DATASET_ID"

say "v1 promotion: the gate should refuse this"
# Expected: 409 naming the failing tier and metric. A 200 here means the v1 prompt
# passed, which is a finding about the dataset or the model, not a success. One
# call, not two: a second promote would be a second state transition attempt.
V1_BODY=$(curl -s -w '\n%{http_code}' -X POST "$CP/releases/$V1_RELEASE/promote")
V1_CODE=$(printf '%s' "$V1_BODY" | tail -n1)
if [ "$V1_CODE" = "409" ]; then
  printf '%s' "$V1_BODY" | sed '$d' | jq -r .detail
else
  printf 'warning: v1 promotion returned %s, expected 409. The blocked-release half\n' "$V1_CODE"
  printf 'of the dashboard story will not be there. Check the eval summary above.\n'
fi

# ------------------------------------------------------- v2: the gate passes it

say "v2 release: live eval against the pinned Sonnet 4.6 (spends)"
V2_RELEASE=$(release_for_version v2)
echo "release $V2_RELEASE"
CONTROL_PLANE_URL="$CP" GATEWAY_URL="$GW" \
  uv run python -m releaseplane_evals.cli run --release-id "$V2_RELEASE" --dataset-id "$DATASET_ID"

say "v2 promotion: draft to candidate, candidate to active. The gate runs on both."
curl -sf -X POST "$CP/releases/$V2_RELEASE/promote" | jq -r '.state'
curl -sf -X POST "$CP/releases/$V2_RELEASE/promote" | jq -r '.state'

# ------------------------------------------------- invokes: light up the panels

# $'...' so these carry real newlines. A literal backslash-n would reach the model
# as two characters and make the input look nothing like an invoice.
CLEAN_INVOICE=$'INVOICE\nInvoice Number: INV-2026-0042\nDate: 2026-03-14\nCurrency: EUR\n\nWidget A  10 x 100.00 = 1000.00\nWidget B   3 x  50.00 =  150.00\n\nSubtotal: 1150.00\nTax (8.5%): 97.75\nTotal: 1247.75\n'

# Arithmetic that does not hold: 1000.00 + 85.00 is 1085.00, not 9999.99. The
# runtime policy engine records a policy_event rather than repairing the object,
# which is the panel this invoke exists to light up.
BAD_TOTAL_INVOICE=$'INVOICE\nInvoice Number: INV-2026-0043\nDate: 2026-03-15\nCurrency: EUR\n\nWidget A  10 x 100.00 = 1000.00\n\nSubtotal: 1000.00\nTax (8.5%): 85.00\nTotal: 9999.99\n'

invoke() {
  local label="$1" hint="$2" text="$3"
  say "invoke: $label"
  local body
  body=$(jq -n --arg t "$text" --arg h "$hint" \
    '{prompt_name: "invoice-extraction", variables: {invoice_pdf_text: $t}}
     + (if $h == "" then {} else {routing_hint: $h} end)')
  curl -s "$GW/invoke" -H 'content-type: application/json' -d "$body" \
    | jq -r '.metadata | "provider=\(.provider) model=\(.model) cost=\(.estimated_cost_usd) policy=\(.policy_status) checks=\(.policy_checks_applied)"' \
    || echo "(invoke failed; the panels for this one will be empty)"
}

invoke "the Sonnet default" "" "$CLEAN_INVOICE"
invoke "routed to gpt-4o-mini (the cost beat)" "cost" "$CLEAN_INVOICE"
invoke "a bad total, so a policy event renders" "" "$BAD_TOTAL_INVOICE"

# --------------------------------------------------------- back to zero spend

say "re-pinning the gateway to the dummy provider"
cat <<'EOF'
This script does not edit your compose override for you, because on a shared host
that file is local state it has no business rewriting. Do it now, before walking
away from a stack that can spend:

  1. set GATEWAY_PROVIDER: "dummy" in infra/docker-compose.override.yml
  2. make demo-up
  3. confirm:  docker inspect releaseplane-gateway \
                 --format '{{range .Config.Env}}{{println .}}{{end}}' | grep GATEWAY_PROVIDER
EOF

say "done"
cat <<EOF
Populated. What to check on the dashboards:

  eval     the v1 series sits under the 100% line on Tier-2, v2 sits on it
  gateway  routing decisions split between the two providers, one policy event
  jaeger   three traces carrying release_id, provider, cost, and policy status

The metrics live in the control-plane process, not the database, so leave the stack
up. docs/RUNBOOK.md, "Why the dashboards default to a wide time range", has the
detail on what survives a restart and what does not.
EOF
