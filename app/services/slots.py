from boto3.dynamodb.conditions import Attr, Key
from datetime import datetime
from typing import List, Optional
from app.db import slots_table
from decimal import Decimal

def get_available_slots(date: str = None):
    """
    Returns a list of available appointment time slots. 
    Can be filtered by a specific date.
    
    Args:
        date (str, optional): The date to filter slots for, in YYYY-MM-DD format (e.g., '2026-01-17').
    """
    print(f"DEBUG: AI called get_available_slots with date={date}")
    
    if date:
        #Filter by date directly in DynamoDB
        response = slots_table.scan(
            FilterExpression=Attr('date').eq(date) & Attr('is_available').eq(True)
        )
    else:
        #Get all available slots
        response = slots_table.scan(
            FilterExpression=Attr('is_available').eq(True)
        )

    items = response.get("Items", [])
    
    for item in items:
        for key, value in item.items():
            if isinstance(value, Decimal):
                item[key] = int(value) if value % 1 == 0 else float(value)

    items.sort(key=lambda x: (x.get('date', ''), x.get('start_time', '')))
    return items