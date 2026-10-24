"""Initialize the approved stage-89 asset and lineage registry."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_platform.storage.asset_governance_store import AssetGovernanceStore


def main() -> None:
    store = AssetGovernanceStore("var/market/a_share_market.sqlite3")
    store.ensure_schema()
    assets = store.list_assets()
    lineage = store.list_lineage()
    print(f"[stage89] asset registry ready assets={len(assets)} lineage_edges={len(lineage)}")


if __name__ == "__main__":
    main()
