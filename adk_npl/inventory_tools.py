"""
Inventory management tools for buyer and supplier agents.
Provides functions to query and manage inventories (not NPL-modeled).
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from google.adk.tools import FunctionTool


class InventoryManager:
    """Base class for managing inventory data."""
    
    def __init__(self, data_file: Path):
        self.data_file = data_file
        self._load_data()
    
    def _load_data(self):
        """Load inventory data from file."""
        if self.data_file.exists():
            with open(self.data_file, 'r') as f:
                self.data = json.load(f)
        else:
            self.data = {}
    
    def _save_data(self):
        """Save inventory data to file."""
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.data_file, 'w') as f:
            json.dump(self.data, f, indent=2)


class SupplierInventory(InventoryManager):
    """Manages supplier's product inventory."""
    
    def list_products(self) -> List[Dict[str, Any]]:
        """List all products in inventory."""
        return self.data.get('products', [])
    
    def get_product(self, sku: str) -> Optional[Dict[str, Any]]:
        """Get a specific product by SKU."""
        for product in self.data.get('products', []):
            if product['sku'] == sku:
                return product
        return None
    
    def update_quantity(self, sku: str, quantity_change: int):
        """Update available quantity for a product."""
        for product in self.data.get('products', []):
            if product['sku'] == sku:
                product['quantity_available'] += quantity_change
                self._save_data()
                return True
        return False


class BuyerShoppingList(InventoryManager):
    """Manages buyer's shopping needs."""
    
    def list_needs(self) -> List[Dict[str, Any]]:
        """List all items needed."""
        return self.data.get('needs', [])
    
    def get_need(self, item: str) -> Optional[Dict[str, Any]]:
        """Get a specific need by item name."""
        for need in self.data.get('needs', []):
            if need['item'].lower() == item.lower():
                return need
        return None
    
    def mark_fulfilled(self, item: str, quantity: int):
        """Mark a need as fulfilled or partially fulfilled."""
        for need in self.data.get('needs', []):
            if need['item'].lower() == item.lower():
                need['desired_quantity'] -= quantity
                if need['desired_quantity'] <= 0:
                    self.data['needs'].remove(need)
                self._save_data()
                return True
        return False


def create_supplier_inventory_tools(inventory: SupplierInventory) -> List[FunctionTool]:
    """Create ADK tools for supplier inventory management."""
    
    def list_supplier_products() -> Dict[str, Any]:
        """
        List all products available in supplier's inventory.
        
        Returns a list of products with SKU, name, description, quantity, price, and lead time.
        Use this to see what products you can sell.
        """
        products = inventory.list_products()
        return {
            "success": True,
            "products": products,
            "count": len(products)
        }
    
    def get_supplier_product(sku: str) -> Dict[str, Any]:
        """
        Get details for a specific product by SKU.
        
        Args:
            sku: The product SKU code (e.g., "WIDGET-001")
        
        Returns product details including availability and pricing.
        """
        product = inventory.get_product(sku)
        if product:
            return {
                "success": True,
                "product": product
            }
        return {
            "success": False,
            "error": f"Product {sku} not found in inventory"
        }
    
    def check_product_availability(sku: str, quantity: int) -> Dict[str, Any]:
        """
        Check if a product is available in the requested quantity.
        
        Args:
            sku: The product SKU code
            quantity: The desired quantity
        
        Returns availability status and current stock level.
        """
        product = inventory.get_product(sku)
        if not product:
            return {
                "success": False,
                "error": f"Product {sku} not found"
            }
        
        available = product['quantity_available'] >= quantity
        return {
            "success": True,
            "available": available,
            "quantity_requested": quantity,
            "quantity_in_stock": product['quantity_available']
        }
    
    return [
        FunctionTool(list_supplier_products),
        FunctionTool(get_supplier_product),
        FunctionTool(check_product_availability)
    ]


def create_buyer_shopping_tools(shopping_list: BuyerShoppingList) -> List[FunctionTool]:
    """Create ADK tools for buyer shopping list management."""
    
    def list_shopping_needs() -> Dict[str, Any]:
        """
        List all items on the shopping list that need to be purchased.
        
        Returns a list of needed items with desired quantity, budget, and urgency.
        Use this to see what you need to buy.
        """
        needs = shopping_list.list_needs()
        return {
            "success": True,
            "needs": needs,
            "count": len(needs)
        }
    
    def get_shopping_need(item: str) -> Dict[str, Any]:
        """
        Get details for a specific item on the shopping list.
        
        Args:
            item: The item name (e.g., "Premium Widget")
        
        Returns need details including quantity, budget, and urgency.
        """
        need = shopping_list.get_need(item)
        if need:
            return {
                "success": True,
                "need": need
            }
        return {
            "success": False,
            "error": f"Item '{item}' not found on shopping list"
        }
    
    def check_budget_fit(item: str, offered_price: float) -> Dict[str, Any]:
        """
        Check if an offered price fits within the budget for an item.
        
        Args:
            item: The item name
            offered_price: The price offered by supplier
        
        Returns whether the price is within budget and the budget limit.
        """
        need = shopping_list.get_need(item)
        if not need:
            return {
                "success": False,
                "error": f"Item '{item}' not found on shopping list"
            }
        
        within_budget = offered_price <= need['max_budget_per_unit']
        return {
            "success": True,
            "within_budget": within_budget,
            "offered_price": offered_price,
            "max_budget": need['max_budget_per_unit'],
            "difference": need['max_budget_per_unit'] - offered_price
        }
    
    return [
        FunctionTool(list_shopping_needs),
        FunctionTool(get_shopping_need),
        FunctionTool(check_budget_fit)
    ]

