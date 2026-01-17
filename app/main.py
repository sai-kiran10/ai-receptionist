from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timedelta
import asyncio
import uuid

app = FastAPI()

# DynamoDB setup
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
slots_table = dynamodb.Table("Slots")
appointments_table = dynamodb.Table("Appointments")

# Helper functions
def current_ts():
    return int(datetime.utcnow().timestamp())

def current_iso():
    return datetime.utcnow().isoformat()

# Request Models
class HoldSlotRequest(BaseModel):
    slot_id: str
    phone_number: str
    hold_seconds: int = 30  # default hold duration

class ConfirmAppointmentRequest(BaseModel):
    slot_id: str
    phone_number: str

# Hold slot
@app.post("/slots/hold")
def hold_slot(request: HoldSlotRequest):
    ttl = current_ts() + request.hold_seconds
    try:
        response = slots_table.update_item(
            Key={"slot_id": request.slot_id},
            UpdateExpression="SET #s = :held, hold_expires_at = :ttl, version = version + :inc",
            ConditionExpression="#s = :avail",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":avail": "AVAILABLE", ":held": "HELD", ":ttl": ttl, ":inc": 1},
            ReturnValues="ALL_NEW"
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            slot = slots_table.get_item(Key={"slot_id": request.slot_id}).get("Item")
            if slot:
                if slot["status"] == "HELD":
                    raise HTTPException(status_code=400, detail="Slot already held")
                elif slot["status"] == "BOOKED":
                    raise HTTPException(status_code=400, detail="Slot already booked")
            raise HTTPException(status_code=400, detail="Slot not available")
        else:
            raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, "slot": response["Attributes"]}

# Confirm appointment
@app.post("/appointments/confirm")
def confirm_appointment(request: ConfirmAppointmentRequest):
    now_ts = current_ts()
    try:
        response = slots_table.update_item(
            Key={"slot_id": request.slot_id},
            UpdateExpression="SET #s = :booked",
            ConditionExpression="#s = :held AND hold_expires_at > :now",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":held": "HELD", ":booked": "BOOKED", ":now": now_ts},
            ReturnValues="ALL_NEW"
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            slot = slots_table.get_item(Key={"slot_id": request.slot_id}).get("Item")
            if slot and slot["status"] == "BOOKED":
                raise HTTPException(status_code=400, detail="Slot already booked")
            raise HTTPException(status_code=400, detail="Slot not held or expired")
        else:
            raise HTTPException(status_code=500, detail=str(e))

    # Create an appointment record
    appointment_id = str(uuid.uuid4())
    try:
        appointments_table.put_item(
            Item={
                "appointment_id": appointment_id,
                "slot_id": request.slot_id,
                "phone_number": request.phone_number,
                "status": "CONFIRMED",
                "created_at": current_iso()
            }
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Appointment creation failed: {str(e)}")

    return {"success": True, "appointment_id": appointment_id}

# List all slots (for testing)
@app.get("/slots")
def list_slots():
    response = slots_table.scan()
    items = response.get("Items", [])
    # Sort by date and time
    items.sort(key=lambda x: (x['date'], x['start_time']))
    return items

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

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(expire_held_slots())
