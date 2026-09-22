# entity_resolution — player identity matching across sources.
#
# Pipeline: normalise → block → score → decide → record
# Grey-zone matches (score between LOW and HIGH threshold) go to
# staging.review_queue for manual review before being written to
# core.player_alias.
