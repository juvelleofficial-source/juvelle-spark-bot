"""
Brand Profile & Business Knowledge Configuration.
Decouples brand-specific facts, products, pricing, policies, and greetings from the core agent engine.
"""

from typing import Dict, Any, List

BRAND_PROFILE: Dict[str, Any] = {
    "brand_name": "Juvelle",
    "business_niche": "Women's Boutique Fashion",
    "location": "Kerala, India",
    "primary_specialty": "Daily & Office Wear Churidar Tops",
    
    # Product Catalog & Fabrics
    "categories": [
        {
            "name": "Daily Wear Tops",
            "fabric": "Pure Breathable Cotton",
            "price_range": "₹399 to ₹699",
            "sizes": ["S", "M", "L", "XL", "XXL"]
        },
        {
            "name": "Office Wear Tops",
            "fabric": "Premium Soft Rayon",
            "price_range": "₹499 to ₹899",
            "sizes": ["S", "M", "L", "XL", "XXL"]
        }
    ],
    
    # Excluded Products
    "excluded_items": [
        "T-shirts", "Kids wear", "Sarees", "Jeans", "Frocks", "Men's wear"
    ],
    
    # Shipping & Delivery Policies
    "shipping": {
        "coverage": "Kerala only",
        "courier_partner": "Delhivery",
        "standard_fee": "₹50",
        "estimated_days": "2-3 business days",
        "cod_available": False,
        "payment_methods": ["UPI", "GPay", "PhonePe", "Bank Transfer"]
    },
    
    # Ordering Instructions
    "ordering_flow": {
        "catalog_source": "Instagram page posts & highlights",
        "order_method": "Share screenshot of selected top + size in chat",
        "payment_requirement": "100% online advance payment prior to dispatch"
    },
    
    # Default Greetings & Responses by Language
    "greetings": {
        "english": {
            "first_contact": "Hey there! Welcome to Juvelle. We specialize in daily and office wear Churidar tops. How can I help you today?",
            "returning_customer": "Hey again! Welcome back to Juvelle. How can I help you today?",
            "mid_chat_checkin": "Hey! Yes, tell me, how can I help you today?"
        },
        "manglish": {
            "first_contact": "Hey there! Welcome to Juvelle. Nammal daily and office wear Churidar topsil specialize cheyyunnu. Enganeya help cheyyendath?",
            "returning_customer": "Hey again! Welcome back to Juvelle. Enganeya help cheyyendath?",
            "mid_chat_checkin": "Hey! Parayuu, enganeya help cheyyendathu?"
        },
        "malayalam_script": {
            "first_contact": "നമസ്കാരം! ജുവല്ലിലേക്ക് സ്വാഗതം. ഞങ്ങൾ ചുരിദാർ ടോപ്പുകളിൽ സ്പെഷ്യലൈസ് ചെയ്യുന്നു. എങ്ങനെയാണ് സഹായിക്കേണ്ടത്?",
            "returning_customer": "സ്വാഗതം! എങ്ങനെയാണ് സഹായിക്കേണ്ടത്?",
            "mid_chat_checkin": "ഹലോ! പറയൂ, എങ്ങനെയാണ് സഹായിക്കേണ്ടത്?"
        }
    }
}
