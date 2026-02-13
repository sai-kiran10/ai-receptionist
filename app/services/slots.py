from boto3.dynamodb.conditions import Attr
from datetime import datetime, timedelta
from app.db import slots_table
from decimal import Decimal

def get_available_slots(date: str = None):
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    target_date = date if date else today_str

    # Run maintenance before searching
    cleanup_and_seed_slots(today_str)

    print(f"DEBUG: AI searching for date={target_date}")
    
    response = slots_table.scan(
        FilterExpression=Attr('date').eq(target_date) & Attr('is_available').eq(True)
    )

    items = response.get("Items", [])
    
    for item in items:
        for key, value in item.items():
            if isinstance(value, Decimal):
                item[key] = int(value) if value % 1 == 0 else float(value)

    items.sort(key=lambda x: x.get('slot_id', ''))
    return items

def cleanup_and_seed_slots(today_str: str):
    """Deletes old data and ensures a full week of slots exists."""
    try:
        #Delete anything older than today
        response = slots_table.scan(ProjectionExpression="slot_id, #d", ExpressionAttributeNames={"#d": "date"})
        all_items = response.get('Items', [])
        
        for item in all_items:
            sid = item.get('slot_id')
            sdate = item.get('date')
            if sid and (sdate is None or sdate < today_str):
                slots_table.delete_item(Key={'slot_id': sid})

        #Ensure the next 7 days are populated
        print(f"DEBUG: Ensuring 7-day slot availability starting from {today_str}...")
        
        # Define the hours you want available every day
        business_hours = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"]
        start_date = datetime.strptime(today_str, "%Y-%m-%d")

        for i in range(7):
            current_date_obj = start_date + timedelta(days=i)
            current_date_str = current_date_obj.strftime("%Y-%m-%d")

            for hr in business_hours:
                slot_id = f"{current_date_str}-{hr}"
                existing = slots_table.get_item(Key={'slot_id': slot_id})
                if not existing.get('Item'):
                    print(f"DEBUG: Seeding missing slot {slot_id}...")
                    slots_table.put_item(
                        Item={
                            'slot_id': slot_id,
                            'date': current_date_str,
                            'start_time': hr,
                            'status': 'AVAILABLE',
                            'is_available': True,
                            'version': 0
                        }
                    )
        print("DEBUG: 7-Day Seeding Complete.")

    except Exception as e:
        print(f"ERROR in Maintenance: {e}")