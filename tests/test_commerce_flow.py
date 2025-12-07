import os
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from adk_npl import NPLConfig, NPLClient
from adk_npl.auth import KeycloakAuth


def _auth_token(realm: str, client_id: str, username: str, password: str) -> str:
    auth = KeycloakAuth(
        keycloak_url=os.getenv("NPL_KEYCLOAK_URL", "http://localhost:11000"),
        realm=realm,
        client_id=client_id,
        username=username,
        password=password,
    )
    return asyncio.run(auth.authenticate())


def _client_with_token(token: str) -> NPLClient:
    engine_url = os.getenv("NPL_ENGINE_URL", "http://localhost:12000")
    return NPLClient(engine_url, token)


def _iso_now(offset_days=0):
    return (datetime.now(timezone.utc) + timedelta(days=offset_days)).isoformat().replace("+00:00", "Z")


@pytest.mark.integration
def test_commerce_end_to_end():
    """
    End-to-end backend test (no LLM):
    - Supplier creates Product
    - Supplier creates/publishes Offer
    - Buyer accepts Offer and creates Order
    """
    password = os.getenv("SEED_TEST_USERS_PASSWORD", "Welcome123")

    # Tokens
    supplier_token = _auth_token("supplier", "supplier", "supplier_agent", password)
    buyer_token = _auth_token("purchasing", "purchasing", "purchasing_agent", password)

    supplier_client = _client_with_token(supplier_token)
    buyer_client = _client_with_token(buyer_token)

    # 1) Create Product (supplier, explicit @parties)
    product_payload = {
        "name": "Widget Batch",
        "description": "100 standard widgets",
        "sku": "WGT-100",
        "gtin": None,
        "brand": None,
        "category": "Widgets",
        "itemCondition": "NewCondition",
    }
    prod_resp = supplier_client.create_protocol(
        package="commerce",
        protocol_name="Product",
        parties={
            "seller": {
                "claims": {
                    "organization": ["Supplier Inc"],
                    "department": ["Sales"]
                }
            }
        },
        data=product_payload,
    )
    product_id = prod_resp.get("@id") or prod_resp.get("id") or prod_resp.get("instance") or prod_resp.get("uuid")
    assert product_id, f"Product create failed: {prod_resp}"

    # 2) Create Offer (supplier creates it, referencing Product)
    # Pass buyer's claims explicitly so buyer party is set correctly
    offer_payload = {
        "itemOffered": product_id,
        "priceSpecification": {
            "price": 45.0,
            "priceCurrency": "USD",
            "validFrom": _iso_now(),
            "validThrough": _iso_now(30),
        },
        "availableQuantity": {
            "value": 100,
            "unitCode": "EA",
            "unitText": "pieces",
        },
        "deliveryLeadTime": 10,
        "validFrom": _iso_now(),
        "validThrough": _iso_now(30),
    }
    # Create Offer with supplier token, explicit @parties for both roles
    offer_resp = supplier_client.create_protocol(
        package="commerce",
        protocol_name="Offer",
        parties={
            "seller": {
                "claims": {
                    "organization": ["Supplier Inc"],
                    "department": ["Sales"]
                }
            },
            "buyer": {
                "claims": {
                    "organization": ["Acme Corp"],
                    "department": ["Procurement"]
                }
            }
        },
        data=offer_payload,
    )
    offer_id = offer_resp.get("@id") or offer_resp.get("id") or offer_resp.get("instance") or offer_resp.get("uuid")
    assert offer_id, f"Offer create failed: {offer_resp}"

    # Publish offer (seller publishes)
    supplier_client.execute_action(
        package="commerce",
        protocol_name="Offer",
        instance_id=offer_id,
        action_name="publish",
        party="seller",
        params={},
    )

    # Buyer accepts offer (buyer is now an observer of Offer, so they can accept)
    buyer_client.execute_action(
        package="commerce",
        protocol_name="Offer",
        instance_id=offer_id,
        action_name="accept",
        party="buyer",
        params={},
    )

    # 3) Create Order (buyer creates it - buyer has observer access to Offer, and Product is accessed through Offer)
    # Order derives orderedItem from acceptedOffer.itemOffered, so buyer doesn't need direct observer access to Product
    order_payload = {
        "orderNumber": "ORD-1001",
        "orderDate": _iso_now(),
        "acceptedOffer": offer_id,
        "orderQuantity": {
            "value": 100,
            "unitCode": "EA",
            "unitText": "pieces",
        },
        "price": {
            "value": 4500.0,
            "currency": "USD",
        },
        "paymentMethod": "CreditCard",
    }
    order_resp = buyer_client.create_protocol(
        package="commerce",
        protocol_name="Order",
        parties={
            "buyer": {
                "claims": {
                    "organization": ["Acme Corp"],
                    "department": ["Procurement"]
                }
            },
            "sellerRole": {
                "claims": {
                    "organization": ["Supplier Inc"],
                    "department": ["Sales"]
                }
            }
        },
        data=order_payload,
    )
    order_id = order_resp.get("@id") or order_resp.get("id") or order_resp.get("instance") or order_resp.get("uuid")
    assert order_id, f"Order create failed: {order_resp}"


