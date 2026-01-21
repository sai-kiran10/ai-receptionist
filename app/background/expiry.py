from app.db import slots_table
from datetime import datetime
import asyncio
from app.services.bookings import current_ts
import app

# Auto-expire HELD slots
async def expire_held_slots():
    while True:
        now_ts = current_ts()
        response = slots_table.scan(
            FilterExpression="#s = :held AND hold_expires_at <= :now",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":held": "HELD", ":now": now_ts}
        )
        for slot in response.get("Items", []):
            slots_table.update_item(
                Key={"slot_id": slot["slot_id"]},
                UpdateExpression="SET #s = :avail, hold_expires_at = :null",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={":avail": "AVAILABLE", ":null": None}
            )
            print(f"Expired slot {slot['slot_id']} back to AVAILABLE")
        await asyncio.sleep(5)
