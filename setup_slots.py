# app/db/setup_slots.py
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta

# Professional Tip: Use a session or a central config for region/endpoints
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

def create_receptionist_tables():
    tables = [
        {"name": "Slots", "key": "slot_id"},
        {"name": "Appointments", "key": "appointment_id"}
    ]
    
    for t in tables:
        try:
            table = dynamodb.create_table(
                TableName=t["name"],
                KeySchema=[{'AttributeName': t["key"], 'KeyType': 'HASH'}],
                AttributeDefinitions=[{'AttributeName': t["key"], 'AttributeType': 'S'}],
                ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
            )
            table.wait_until_exists()
            print(f"✅ Table '{t['name']}' ready.")
        except ClientError as e:
            if e.response['Error']['Code'] == 'ResourceInUseException':
                print(f"ℹ️ Table '{t['name']}' already exists. Skipping creation.")

def seed_dynamic_data():
    table = dynamodb.Table("Slots")
    today = datetime.now()
    
    # Generate 5 days of slots (6 slots per day)
    for day_offset in range(5):
        date_str = (today + timedelta(days=day_offset)).strftime('%Y-%m-%d')
        for hour in [9, 10, 11, 14, 15, 16]:
            time_str = f"{hour:02d}:00"
            # Using a dash-separated ID is standard for DynamoDB sorting
            slot_id = f"{date_str}-{time_str}"
            
            table.put_item(Item={
                "slot_id": slot_id,
                "date": date_str,
                "start_time": time_str,
                "is_available": True,  # Critical for your AI filter
                "status": "AVAILABLE",
                "version": 0           # Good for handling concurrent bookings later
            })
    print(f"✨ Seeded dynamic slots starting from {today.strftime('%Y-%m-%d')}")

if __name__ == "__main__":
    create_receptionist_tables()
    seed_dynamic_data()