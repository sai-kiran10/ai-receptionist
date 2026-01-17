import boto3
from botocore.exceptions import ClientError
from datetime import datetime

dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# ---------------- Slots Table ----------------
SLOTS_TABLE_NAME = "Slots"
try:
    table = dynamodb.create_table(
        TableName=SLOTS_TABLE_NAME,
        KeySchema=[{'AttributeName': 'slot_id', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'slot_id', 'AttributeType': 'S'}],
        ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
    )
    table.wait_until_exists()
    print(f"Table '{SLOTS_TABLE_NAME}' created successfully.")
except ClientError as e:
    if e.response['Error']['Code'] == 'ResourceInUseException':
        print(f"Table '{SLOTS_TABLE_NAME}' already exists.")
    table = dynamodb.Table(SLOTS_TABLE_NAME)

# ---------------- Populate Slots ----------------
date = "2026-01-17"
start_hour = 9
end_hour = 17

for hour in range(start_hour, end_hour):
    for minute in [0, 30]:
        slot_id = f"{date}-{hour:02d}:{minute:02d}"
        table.put_item(
            Item={
                "slot_id": slot_id,
                "date": date,
                "start_time": f"{hour:02d}:{minute:02d}",
                "duration": 30,
                "status": "AVAILABLE",
                "hold_expires_at": None,
                "version": 0
            }
        )
print("Initial slots populated successfully.")

# ---------------- Appointments Table ----------------
APPOINTMENTS_TABLE_NAME = "Appointments"
try:
    table = dynamodb.create_table(
        TableName=APPOINTMENTS_TABLE_NAME,
        KeySchema=[{'AttributeName': 'appointment_id', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'appointment_id', 'AttributeType': 'S'}],
        ProvisionedThroughput={'ReadCapacityUnits': 5, 'WriteCapacityUnits': 5}
    )
    table.wait_until_exists()
    print(f"Table '{APPOINTMENTS_TABLE_NAME}' created successfully.")
except ClientError as e:
    if e.response['Error']['Code'] == 'ResourceInUseException':
        print(f"Table '{APPOINTMENTS_TABLE_NAME}' already exists.")
