"""
Pluggable registry for industry standards used in NPL.
Maps NPL namespaces (e.g., schemaorg, iso, swift) to semantic metadata.
"""

# The registry maps namespace prefixes to their metadata providers
STANDARDS_REGISTRY = {
    "schemaorg": {
        "standard_name": "schema.org",
        "types": {
            "MonetaryAmount": {
                "description": "Represents a value of money with its currency.",
                "fields": {"value": "Number", "currency": "Text (ISO 4217)"},
                "example": "{'value': 1200.00, 'currency': 'USD'}"
            },
            "QuantitativeValue": {
                "description": "A point value or interval for product characteristics.",
                "fields": {"value": "Number", "unitCode": "Text (UN/CEFACT)"},
                "example": "{'value': 100, 'unitCode': 'C62'}"
            },
            "PriceSpecification": {
                "description": "Detailed price information including tax and currency.",
                "fields": {"price": "Number", "priceCurrency": "Text", "valueAddedTaxIncluded": "Boolean"}
            }
        }
    },
    "iso.20022": {
        "standard_name": "ISO 20022 (Financial Services)",
        "types": {
            "Payment": {
                "description": "ISO 20022 Credit Transfer message logic.",
                "fields": {"instrId": "Instruction ID", "endToEndId": "End-to-End ID"}
            }
        }
    },
    "gs1": {
        "standard_name": "GS1 (Supply Chain)",
        "types": {
            "GTIN": {
                "description": "Global Trade Item Number",
                "format": "14-digit numeric code"
            }
        }
    }
}

def get_semantic_context(npl_import: str) -> str:
    """
    Given an NPL import (e.g., 'schemaorg.v1.MonetaryAmount'),
    return a Markdown description from the registry.
    """
    # Try to find a matching prefix in the registry
    for prefix, info in STANDARDS_REGISTRY.items():
        if npl_import.startswith(prefix):
            type_name = npl_import.split('.')[-1]
            standard = info["standard_name"]
            type_info = info["types"].get(type_name)
            
            if type_info:
                desc = type_info.get("description", "Standard type.")
                lines = [f"- `{type_name}` (Standard: {standard}): {desc}"]
                
                if "fields" in type_info:
                    fields = ", ".join([f"{k} ({v})" for k, v in type_info["fields"].items()])
                    lines.append(f"  * Fields: {fields}")
                
                if "example" in type_info:
                    lines.append(f"  * Example: `{type_info['example']}`")
                
                return "\n".join(lines)
            else:
                return f"- `{type_name}`: Part of the {standard} standard."
                
    return f"- `{npl_import.split('.')[-1]}`: External NPL type definition."

