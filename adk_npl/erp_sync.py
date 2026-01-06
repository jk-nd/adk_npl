"""
Copyright 2025 Noumena Digital AG

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import httpx

from .activity_logger import get_activity_logger
from .auth import create_auth_strategy
from .config import NPLConfig
from .inventory_tools import BuyerShoppingList, SupplierInventory

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PurchaseOrderItem:
    sku: str
    name: str
    quantity: int
    purchase_order_state: str


class ErpSyncService:
    """
    Deterministic "ERP-like" service:
    - listens to NPL notifications (via caller, e.g., chat_api)
    - queries NPL for authoritative protocol data
    - updates local demo read-model state (shopping list + inventory)

    IMPORTANT: This is NOT agent logic. It is deterministic and idempotent.
    """

    def __init__(
        self,
        *,
        npl_config: NPLConfig,
        buyer_shopping_list: BuyerShoppingList,
        supplier_inventory: SupplierInventory,
        state_file: Path,
    ):
        self._config = npl_config
        self._buyer_list = buyer_shopping_list
        self._supplier_inventory = supplier_inventory
        self._state_file = state_file
        self._lock = asyncio.Lock()
        self._activity_logger = get_activity_logger()

        # Idempotency state: track which PurchaseOrder IDs we've already applied per event type.
        self._state: Dict[str, Any] = self._load_state()

    def _load_state(self) -> Dict[str, Any]:
        try:
            if self._state_file.exists():
                return json.loads(self._state_file.read_text())
        except Exception as e:
            logger.warning(f"Failed to load ERP sync state file: {e}")
        return {"applied": {}}  # {"applied": {"OrderShippedNotification": {"<poId>": {...}}}}

    def _save_state(self) -> None:
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(self._state, indent=2))

    async def _npl_get_json(self, path: str) -> Dict[str, Any]:
        auth = create_auth_strategy(self._config)
        if not auth:
            raise RuntimeError("No auth strategy available for ERP sync")
        token = await auth.authenticate()

        url = f"{self._config.engine_url.rstrip('/')}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _coerce_int_quantity(qty: Any) -> int:
        if qty is None:
            raise ValueError("quantity is None")
        if isinstance(qty, bool):
            raise ValueError("quantity is boolean")
        if isinstance(qty, int):
            return qty
        if isinstance(qty, float):
            if qty.is_integer():
                return int(qty)
            raise ValueError(f"quantity is not an integer: {qty}")
        if isinstance(qty, str):
            f = float(qty)
            if f.is_integer():
                return int(f)
            raise ValueError(f"quantity is not an integer: {qty}")
        f = float(qty)
        if f.is_integer():
            return int(f)
        raise ValueError(f"quantity is not an integer: {qty}")

    async def _resolve_purchase_order_item(self, purchase_order_id: str) -> Optional[PurchaseOrderItem]:
        po = await self._npl_get_json(f"/npl/commerce/PurchaseOrder/{purchase_order_id}/")
        po_state = po.get("@state") or "unknown"
        qty = self._coerce_int_quantity(po.get("quantity"))
        offer_id = po.get("acceptedOffer")
        if not offer_id:
            return None

        offer = await self._npl_get_json(f"/npl/commerce/Offer/{offer_id}/")
        product_id = offer.get("itemOffered")
        if not product_id:
            return None

        product = await self._npl_get_json(f"/npl/commerce/Product/{product_id}/")
        sku = product.get("sku")
        name = product.get("name")
        if not sku or not name:
            return None

        return PurchaseOrderItem(sku=sku, name=name, quantity=qty, purchase_order_state=po_state)

    async def handle_notification(self, notification_name: str, purchase_order_id: str, payload: Dict[str, Any]) -> None:
        """
        Apply local state updates for selected notifications.

        Current policy (simple + deterministic):
        - On OrderShippedNotification:
          - supplier inventory decrements by PO.quantity
          - buyer shopping need decrements/removes by PO.quantity
        """
        if notification_name != "OrderShippedNotification":
            return

        async with self._lock:
            applied = self._state.setdefault("applied", {}).setdefault(notification_name, {})
            if purchase_order_id in applied:
                return

            item = await self._resolve_purchase_order_item(purchase_order_id)
            if not item:
                return

            # Only apply once the PO is actually shipped (or beyond).
            if item.purchase_order_state not in {"Shipped", "Closed"}:
                return

            inv_ok = self._supplier_inventory.update_quantity(item.sku, -item.quantity)
            list_ok = self._buyer_list.mark_fulfilled(item.name, item.quantity)

            applied[purchase_order_id] = {
                "sku": item.sku,
                "name": item.name,
                "quantity": item.quantity,
                "po_state": item.purchase_order_state,
                "inventory_updated": bool(inv_ok),
                "shopping_list_updated": bool(list_ok),
                "notification_payload_preview": {
                    "orderNumber": payload.get("orderNumber"),
                    "tracking": payload.get("tracking"),
                },
            }
            self._save_state()

            self._activity_logger.log_event(
                "bridge_operation",
                "erp_sync",
                "apply_order_shipped",
                {
                    "purchase_order_id": purchase_order_id,
                    "sku": item.sku,
                    "item": item.name,
                    "quantity": item.quantity,
                    "po_state": item.purchase_order_state,
                    "inventory_updated": bool(inv_ok),
                    "shopping_list_updated": bool(list_ok),
                },
            )

