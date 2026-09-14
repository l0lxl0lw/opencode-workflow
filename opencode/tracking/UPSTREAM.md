# Upstream provenance

The workflow commands and codebase/thoughts/web specialist agents derive from
[Cluster444/agentic](https://github.com/Cluster444/agentic), reference commit
`3a3915310d3d03d4a45114b7b0c0a17c34bf0e8b`.

These are maintained derivatives, not an unmodified upstream distribution:
thin commands load stage skills, each stage uses a fresh-context worker,
specialists have bounded tasks, and GitHub issue/comment artifacts replace local
ticket files. The dispatcher, tracking, handoff, verification, setup and snapshot
launcher are additions. Upstream originals are available at the pinned upstream
commit; they are not included in this repository's initial history.

Retain [LICENSE.agentic](LICENSE.agentic), including its copyright and permission
notice, with copies or substantial portions of upstream-derived resources. The
launcher includes this notice in every resource snapshot. The repository's own
MIT notice is in the root `LICENSE` and is also included in snapshots.

Review future upstream changes explicitly. Do not run `agentic pull -g` over a
managed workflow catalog. The Agentic CLI is not a runtime dependency.
