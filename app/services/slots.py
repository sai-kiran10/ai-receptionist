from boto3.dynamodb.conditions import Attr
from datetime import datetime
from typing import List

from app.db import slots_table

from app.db import slots_table

def get_available_slots():
    response = slots_table.scan()
    items = response.get("Items", [])
    items.sort(key=lambda x: (x['date'], x['start_time']))
    return items
