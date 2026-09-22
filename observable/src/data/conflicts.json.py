"""conflicts.json.py — recent source conflicts (limit 200)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _pg import query, emit_json

rows = query(
    """
    select
        entity_type,
        entity_id,
        field,
        source_a_id,
        source_a_value,
        source_b_id,
        source_b_value,
        winning_source,
        logged_at
    from core.conflict_log
    order by logged_at desc nulls last
    limit 200
    """
)

emit_json(rows)
