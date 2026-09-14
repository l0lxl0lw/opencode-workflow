# Shared runtime tracing procedure

This reference belongs to `explain-code-flow`. Apply its investigation and tree
rules in both modes; the parent skill selects the output sections. The full
seven-section template below is the debug-mode output.

Produce one thing: an ordered, verified map from the entry point (HTTP, cron, CLI, queue) down
to **the wire** — the literal SQL statement text and the literal outbound HTTP request — with
`relative/path.ext:LINE` at every step, accurate enough that the user can paste the lines into a
debugger without re-reading the code themselves.

The trace is only finished when both ends are concrete. The top end is a URL or a command
someone can actually run. The bottom end is the statement the database receives and/or the
`METHOD /path?query` the vendor receives — quoted from the source, not described. "It writes the
line items" and "it calls the Stripe API" are the two sentences this skill exists to replace.

**Core principle: every line number is re-derived from the working tree, now.** Numbers from
earlier in the conversation, from a doc, or from a previous trace are stale the moment anyone
merges or edits. A wrong line number is worse than no line number — it sends someone to the
wrong function and they believe it.

## When to use

- "Give me the call path for the checkout / the nightly sync / the approval flow"
- "Where do I put breakpoints to see X happen"
- "Step me through what runs when someone calls this endpoint"
- "Which query actually writes this column"

**Not this skill:**
- Uncommitted working-tree changes → `git-explain-diff`
- What the branch changes vs main → `git-explain-branch`
- "How does X work" conceptually, with no runtime-flow intent → `explain-college-level`

## Step 0 — anchor the repo

Language-agnostic tracing still needs three concrete anchors: **where requests enter**, **where
SQL lives**, and **where outbound HTTP leaves**. Spend two minutes finding them before tracing;
guessing here is what produces a trace that stops one layer above the answer.

**First, check whether the repo already documents them.** A project that names its router file
or its query layer saves the discovery entirely:

```bash
ls CLAUDE.md AGENTS.md README.md docs/ARCHITECTURE.md 2>/dev/null
ls .claude/skills/ 2>/dev/null          # a repo-local skill may already map the layers
```

If a project skill exists for route extraction, schema snapshots, or endpoint wiring, use it —
it is faster and more accurate than grepping, and it is maintained by people who work there.
Treat anything you read this way as a hint to verify, not as line numbers to quote: docs go
stale, and this skill's whole premise is that only the working tree is authoritative.

**Then discover what the docs did not cover.** `rg` if available, `grep -rn` otherwise:

```bash
# request entry points — routers and controller annotations across common stacks
rg -n "app\.(get|post|put|patch|delete)\(|router\.(get|post|put|patch|delete)\(|\.route\(|Handle(Func)?\(|@(Get|Post|Put|Patch|Delete|Router|RequestMapping)|add_url_rule|routes\.draw" -g '!*test*'

# non-HTTP entries — CLIs, schedulers, queue consumers
rg -n "func main\(|if __name__|#!/usr/bin/env|\.command\(|argparse|click\.command|cobra\.Command" -g '!*test*'
rg -n "cron|schedule\.every|CronJob|celery|@scheduled|sidekiq|consume|subscribe\(|on_message" -g '!*test*'

# where SQL literals live
rg -n "SELECT .* FROM |INSERT INTO |UPDATE .+ SET |DELETE FROM " -g '!*.sql' -g '!*test*' | head -30

# where requests leave the process
rg -n "fetch\(|axios\.|requests\.(get|post)|http\.Client|HttpClient|URLSession|RestTemplate|Net::HTTP" -g '!*test*' | head -30
```

Record in one line each: the router file, the query/ORM layer, the HTTP client wrapper. Every
later grep anchors on those.

Two conventions to identify while you are in there, because they decide how much work the rest
of the trace is:

- **The query executor.** Most codebases funnel statements through one or two helpers
  (`executeQuery`, `queryOne`, `pool.query`, a repository base class, an ORM session). Find it
  once and every SQL leaf becomes a two-step lookup: service call site → statement literal.
- **The transport.** Outbound calls usually funnel into one `do`/`request`/`send` method with
  paths as consts and query strings built at the call site. The call site is where the paging
  bound and the delta filter live — read it there, not in the transport.

## Four rules that make the trace correct

### 1. Enumerate every caller, at every level of the chain

Callers enter at different depths. A CLI often skips the top-level orchestrator and calls the
inner function directly, so grepping only the outermost name silently loses it. Grep **every
function in the chain** before writing a line of the answer:

```bash
rg -n "runDailyPipeline\(|syncReceivables\(" -g '!*test*'
```

That pair returns four callers where the outer name alone returns three — the fourth is a CLI
driver calling the inner function. Work down the chain and re-grep at each level until the names
stop having outside callers.

Real subsystems usually have several: a public route, an internal/admin route, and one or more
CLI or job entries. State the count. **Never write "the only entry point" unless your greps
returned exactly one** — a confident false negative stops the user from looking for the path
they were actually on.

### 2. Re-derive the line numbers

Anchor on symbol definitions, not remembered positions:

```bash
rg -n "^(export )?(async )?function checkoutOrder|^func DeltaSync|^\s*def sync_receivables|^\s*(public|private).*chargeOrder\(" src/
```

Cheap, and it makes the answer survive a rebase. If you traced this path earlier in the same
conversation and anything has been merged or edited since, re-derive anyway.

Name the branch you traced, and check it is still the branch when you finish:

```bash
git rev-parse --abbrev-ref HEAD
```

A checkout during a long trace silently swaps the tree underneath you, and the result is a trace
that is internally consistent and entirely wrong for the branch the reader is on. This is the
failure mode most likely to survive review, because nothing about the output looks suspect.

### 3. Order by execution, not by file

The reader is stepping forward through time. Follow the call, don't walk the package.

### 4. Follow every hop to the wire — no dispatch stubs, no gaps

A chain that ends at `this.repo.upsertOrder(...)` or `this.gateway.charge(...)` has stopped one
layer above the thing the user asked about. Both are dynamic dispatch — an interface, an abstract
method, an injected dependency, a duck-typed collaborator. They name intent, not behavior. Keep
going until you are holding a SQL string literal or a method plus path.

Two obligations follow:

**Resolve every dispatch to the concrete implementation, and say who picked it.** Any step that
goes through an interface, base class, DI container, factory or registry must name the thing that
chose the implementation, with its file:line — otherwise the reader sets a breakpoint on a method
with four implementations and guesses. Grep the method name for implementations, then grep the
constructor or container for which one is wired:

```bash
rg -n "charge\s*\(|def charge\(|\) charge\(" -g '!*test*'      # implementations
rg -n "new StripeGateway\(|bind\(.*Gateway|gatewayFactory"      # who wires one
```

**Quote the wire artifact, don't paraphrase it.** Both forms are mandatory when present:

- *SQL* — the statement as written in the source, trimmed to the shape (`INSERT INTO
  order_line_items (...) SELECT ... WHERE o.id = $1 AND o.tenant_id = $7`), with the file:line of
  the string literal and of the executor call that runs it, plus what binds to the placeholders
  that matter. If an ORM or query builder generates the statement, quote the builder chain **and**
  the statement shape it produces — the reader is going to see the generated SQL in the log.
- *Outbound HTTP* — method, full path including the query parameters actually set
  (`GET /invoices?page=1&per_page=200&modified_since=...`), the file:line of the call, the
  response key it decodes out of the envelope, and the field the caller wanted.

No chain may skip a layer between those two ends. If a hop is genuinely a one-line pass-through,
it still gets its own node in the call tree — a reader stepping in a debugger walks through it.

## Output template

In debug mode, use these seven headings, verbatim and in this order, with these
shapes. In explain mode, use the sections selected by the parent skill.

````markdown
## Entry points (N)

| # | Trigger | File:line | Gate | Reaches the chain via |
|---|---|---|---|---|

One row per caller found in rule 1 — routes, cron, queue consumers and CLI drivers alike. `N` in
the heading is the count. For an HTTP row, put the method and path in Trigger, the
middleware/authz in Gate, and name the decoder/handler and the function it calls in the last
column.

## Call tree

**An indented tree, never a table.** Indentation is the entire point: a deeper line is a step
*into*, and a line at a shallower indent is a step back *out*. Reading down at one fixed indent
level reads one function's body in order. A table flattens exactly the information the reader
came for — where the stack goes and where it returns.

One tree per entry point, unless two entries converge on a shared spine — then draw the spine
once and note where each entry joins it.

### The spine is two columns; the description column never moves

The **spine** — the call frames a debugger stops in — is two columns inside one code fence. This
is not cosmetic: the reader follows the flow by running their eye straight down the description
column, and a description that starts wherever the path happened to end forces them to hunt
left-and-right on every line.

```
<tree glyphs> <Symbol> (<full/relative/path.ext:LINE>) <dot leader>  <description>
└──────────────────── the spine ─────────────────────────────────┘   └── description column →
```

- **Left, the spine.** Tree glyphs, then the **symbol name**, then the **full relative path with
  line number in parentheses** (`src/payments/gateway.ts:41` — never a bare basename, never a
  bare `:41`). Fill the remainder with `·` leader dots. Symbol-first means the names sit right
  after the glyphs, so the call sequence reads down the left edge and the paths stay out of the
   way in parens. Keep full relative paths on every node, including repeated directories.
- **Right, the description column.** What this frame does and why. No symbol name (it is already
  on the left), and **no `→ some/other/file.ext:LINE`** — a jump to another file is a child node,
  not prose (see below).

**Derive the column once, then hold it for the whole answer.** It is the longest locator in the
answer plus 5 (one space, at least two dots, one space) — computed across *every* tree, so two
trees in one answer share one column. Never widen it for a single deep node: if a subtree
overflows, that subtree is too deep to nest — pull it out as its own tree and point at it with
`↳`. A column past ~100 means split, not widen.

### Stepping into another file is an indent level, not an arrow

The parenthesised path is the **call site** — where the debugger stops in the frame you are
reading. When that call lands in a different file, the callee gets **its own child node** marked
`⇢`, because that is literally a deeper stack frame:

```
├─ listOrderLineItems (src/services/orders/lines.ts:41) ·· line shape is structural, not a field-map fact
│  └─ ⇢ src/db/queries/order_lines.ts:52 ················· every live line item, in display order
```

A `⇢` node carries only the path — the symbol is already on the parent line, and repeating it is
noise. Its description says what the implementation does; its children are the calls that
implementation makes, ending in a leaf. Writing this as `… ····· → src/db/queries/order_lines.ts:52`
in the description instead flattens a real frame into prose and puts a location in the column
reserved for meaning.

Use `↳` rather than `⇢` when the callee is drawn as a separate shared tree.

### Leaves break out of the alignment

A wire leaf is content the reader stops and studies, not a line they skim down, so it breaks out
of the two-column alignment entirely and is drawn as a **labelled rectangle** hanging under its
`⇢` node. The box makes it unmistakable where prose ends and the literal artifact begins:

```
│  └─ ⇢ src/db/queries/order_lines.ts:52 ················· every live line item, in display order
│     ┌─ SQL ─────────────────────────────────────────────────────────┐
│     │ SELECT order_line_items{id, sku, unit_price, quantity, total} │
│     │ ← WHERE order_id = $1 AND deleted_at IS NULL                  │
│     │   ORDER BY line_number NULLS LAST, created_at                 │
│     │ literal :54 · pool.query :53                                  │
│     └───────────────────────────────────────────────────────────────┘
```

Rules: label the box `SQL`, `HTTP`, or the wire kind it is (`MSG`, `RPC`, `FS`, `CACHE`). Prefix
every box line with the ancestors' runners, indented to sit under the node it belongs to. Size
each box to its own longest line — do not stretch every box to one width. Put the
`literal :NN · executor :NN` pair *inside* the box, never in the spine's parens. For `HTTP`, use
`body` / `send` / `recv` label columns so the request, the transport and the decode read as three
facts:

```
      └─ ⇢ src/payments/stripe/client.ts:32 ·· the only transport; retries 3× on 5xx
         ┌─ HTTP ─────────────────────────────────────────────────────────────────────────────┐
         │ POST /v1/payment_intents?expand[]=latest_charge                                    │
         │ body  amount=<minor units> · currency=<order.currency> · idempotency_key=<orderId> │
         │ send  client.ts:32 · auth Bearer <secretKey> from src/config/secrets.ts:41         │
         │ recv  decodeEnvelope client.ts:148 → data.latest_charge.id → provider_charge_id    │
         └────────────────────────────────────────────────────────────────────────────────────┘
```

Notation, used exactly:

| Mark | Means |
|---|---|
| `▼ TRIGGER` | first line of a tree. Name the **kind** — `external API`, `internal API`, `cron`, `CLI`, `queue consumer`, `internal logic` (post-commit hook, callback from another service) — then the literal `METHOD /path`, command, or event |
| `├─` `└─` `│` | the call tree |
| `SQL▸` | a database leaf — the inline form of the `SQL` box, for a leaf short enough to sit on one line |
| `HTTP▸` | an outbound-request leaf — the inline form of the `HTTP` box |
| `↩` | early return / no-op exit, drawn at the indent of the frame it leaves |
| `⋯` | deferred work — a closure or job built here, invoked lower down. Say where it fires |
| `↻` | a loop. Say what it iterates and the bound |
| `⑂` | a branch. Draw both arms as siblings |
| `⇢` | step into the concrete implementation in another file — a real stack frame, so it is a child node |
| `↳` | "continues in shared tree N" — the only legal way to break a chain across trees |

**Leaf rule — every branch ends in a wire leaf, never in a dispatch method.** For `SQL`: the
verb, the table, the **columns** actually read or written, then the predicate, then the binds and
the `file:line` of the literal and its executor — each on its own line inside the box. A bare
table name is the failure this skill exists to prevent: write
`UPDATE orders{provider, provider_charge_id} ← WHERE id = $1`, not "stamps the order". For
`HTTP`: method, path, the query params the code really sets, the body keys that matter, and
`envelope → field` the caller wanted. A path that ends in a queue publish, gRPC call, file write
or cache set gets the same treatment under its own label.

A pure pass-through frame still gets its own node — the debugger stops there.

Shape, in miniature — descriptions all begin in the same column, leaves break out into boxes:

```
▼ TRIGGER   external API — POST /api/v1/orders/{order_id}/checkout
            route src/http/routes.ts:412 · JWT :88 → tenantScope :96 → requireScope("order:write")

└─ checkoutOrder (src/services/checkout.ts:118) ··· the order write; the charge is an epilogue step
   └─ chargeOrder (src/services/checkout.ts:174) ·· best-effort: error logged, HTTP stays 200
      └─ ⇢ src/payments/stripe/gateway.ts:41 ······ wired src/container.ts:57 — the only implementation
          ├─ loadOrderForCharge (src/payments/stripe/gateway.ts:42) ·· tenancy, currency, already-charged marker
         │  └─ ⇢ src/db/queries/orders.ts:26 ······ a deliberately narrow projection
         │     ┌─ SQL ─────────────────────────────────────────────────────────┐
         │     │ SELECT orders{id, tenant_id, currency, provider_charge_id}    │
         │     │ ← WHERE id = $1                                               │
         │     │ $1 = orderId · provider_charge_id selects capture over create │
         │     │ literal :29 · queryOne :28                                    │
         │     └───────────────────────────────────────────────────────────────┘
          └─ ↩ return null (src/payments/stripe/gateway.ts:63) ······· !found → payments opt-in; nothing written anywhere
```

Getting this right by counting characters fails at scale, and a leader that drifts by one or two
is worse than none. Write the tree in the DSL — `locator @@ description` per spine line, `##LABEL`
plus `>>` lines per box — and render it mechanically:

```bash
python3 {{WORKFLOW_ROOT}}/skills/understand/explain-code-flow/scripts/render_tree.py tree.txt
```

One invocation must cover the whole answer, or each tree gets its own column. Without the script,
the formula is `dots = DESC_COL - 3 - len(locator)` where the locator includes the tree glyphs.
Anything that reports an overflow is a subtree to split out with `↳`, not a reason to move the
column.

## The repeated unit

| Beat | <Entity A> | <Entity B> | … |
|---|---|---|---|

One column per entity, one row per beat (fetch, resolve, normalize, upsert, post-loop). If the
subsystem has no repeated unit, write `_Not applicable — single path._` and keep the heading.

## Outbound API calls

| # | Request | Called at | Decodes | Carries |
|---|---|---|---|---|

Every request that leaves the process on this path, in fire order. Request is the literal
`METHOD /path?param=value` with the query parameters the code actually sets and where each value
comes from (`per_page=200`, `modified_since=<checkpoint>`). Called at is the file:line of the
call plus the transport it goes through (`src/payments/stripe/client.ts:32`). Decodes is the
envelope key unwrapped (`data[]`, `invoice`) and the decoder's file:line. Carries is what the
caller wanted out of the response — and, when a field is missing from one endpoint and present
on another, say so on the row; that asymmetry is usually the whole reason the user is tracing.

If the path calls nothing external, write `_No outbound calls — DB only._` and keep the heading.
Follow the table with one line stating the auth/base-URL source (which client, which credential
loader) and the retry/paging bound.

## SQL at the leaf

| # | Statement | Runs at | Binds |
|---|---|---|---|

Every statement the path executes, in order, read and write alike. Statement is the SQL trimmed
to its shape, in a code fence or inline — `INSERT INTO orders (...) VALUES (...) RETURNING id`,
`SELECT id FROM orders WHERE provider=$1 AND provider_charge_id=$2` — never just a table name.
For an ORM, give the builder chain and the statement shape it emits. Runs at is the file:line of
the literal and of the executor call. Binds names the values behind the placeholders that decide
behavior.

Follow the table with a short prose paragraph: which branch (INSERT vs UPDATE) runs when, which
columns are INSERT-only, and what a re-run does. That paragraph is where the "why didn't my
change show up" answer lives.

## Forks and sibling paths

Bulleted. Two kinds, in one list: behavioral forks on the path (a source-of-truth check that
skips the write, an INSERT-only column, a best-effort step whose error is swallowed, a nil-able
dependency), and work that runs in the same request the user did not ask about (see the
checklist below).

## Suggested breakpoints

```
relative/path.ext:LINE    what is visible here
```

5–8 lines, in execution order. Mark the two highest-value ones with `★` and follow the block with
one sentence saying why those two.
````

Nothing else is required and nothing else is forbidden — if the subsystem has a quirk worth a
short paragraph, put it under the heading it belongs to rather than inventing an eighth section.

## Sibling-path checklist

Before finishing, ask what else runs in the same request. The usual suspects:

- A **best-effort prelude or epilogue** whose failure only logs — a reference-data sync before
  the main pull, a document backfill after it. Easy to miss because errors don't surface.
- A **second implementation of the same job** — an API path and a bulk-file path that share the
  writers; an inbound pipeline that is entirely separate from the outbound one. Name which one
  the user is on.
- **Audit, log and checkpoint writes** — sync logs, quarantine tables, cursor/checkpoint rows.
  Often where the evidence is when nothing visibly happened.
- **Notifications, webhooks, cache invalidations and other side-effects** fired mid-loop.

## Two things worth checking on every third-party integration trace

These explain most "the data isn't there" questions:

- **List vs detail.** List endpoints routinely omit nested collections (`line_items`, children);
  only `GET /{resource}/{id}` returns them, so a fetcher that looks like one call is actually
  1 + N. Find the detail call and put it in the table.
- **What a failed detail call degrades to.** These often fall back to the summary record rather
  than erroring, which is how a record imports with its children silently missing.

## Fixtures vs live backends

Many dispatch points have more implementations than are wired. Before recommending a breakpoint,
confirm the implementation is reachable from the entry point you documented — a fetcher that only
a test constructs will never fire, and saying so is worth a line in the answer.

## Common mistakes

| Mistake | Consequence |
|---|---|
| Reusing line numbers from earlier in the conversation | Silently wrong after any merge; the user lands in the wrong function |
| Quoting line numbers out of a doc or a project skill instead of the tree | Docs go stale between edits; the anchors are hints, the tree is the source |
| "The only entry point is…" after grepping one file | The user never finds the path they were actually on |
| Grepping only the outermost orchestrator | Misses CLI and job drivers that call the inner function directly — the easiest debugger targets |
| Listing every function at equal weight | No signal about where to actually stop |
| Skipping the sibling paths | The user debugs the wrong subsystem and blames their breakpoints |
| Grouping by package instead of call order | Unusable while stepping forward |
| Rendering the call path as a numbered table | Flattens the stack — the reader cannot see what is a step *into* vs a return back *out*, which is the one thing a tree shows |
| Letting the description start wherever the locator happens to end | The reader hunts left-and-right for the start of every line instead of reading straight down. Derive the column and hold it |
| Widening the column for one deep node | Breaks alignment for the whole answer. Split the subtree out with `↳` instead |
| Putting `call site → impl` both on the left | Blows the fixed width immediately; the impl path belongs in its own `⇢` node |
| Repeating the symbol name in the description | It is already the first thing on the left. The right column is for what the frame *does* |
| Hand-counting the leader dots | Reliably drifts by one or two on long trees, which is more distracting than no alignment. Pad with the script |
| A tree node that stops at a repository / client / gateway method | The branch has no wire leaf, so the wire fact is still missing at the exact place the reader is standing |
| `SQL▸ … orders` with no column list | "Touches the orders table" is not steppable; name the columns read or written and the `WHERE` |
| Not labelling the trigger kind | The reader cannot tell a user-facing request from a post-commit hook or queue consumer, so they curl the wrong thing |
| Naming a struct field, config key or interface method as a breakpoint | Not executable; anchor on function definitions and call sites |
| Ending the chain at the dispatch method (`this.repo.upsert…`, `this.gateway.charge…`) | The reader never learns which implementation runs or what it sends |
| Naming the table without quoting the statement | Hides the INSERT/UPDATE branch, the `RETURNING`, and the child-row loop — where the bug usually is |
| Writing "calls the Stripe API" without method, path and query params | Not reproducible with curl; the delta filter and paging bound stay invisible |
| Missing the 1 + N detail fetch behind a list call | The user breakpoints the list request and never sees the nested collection they came for |
