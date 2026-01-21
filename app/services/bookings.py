import app
from app.db import slots_table, appointments_table
from fastapi import HTTPException
from botocore.exceptions import ClientError
import uuid
from datetime import datetime
from pydantic import BaseModel

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


#  Hold slot
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
