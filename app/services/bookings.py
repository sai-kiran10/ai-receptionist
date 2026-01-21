import uuid
import boto3
from decimal import Decimal
from datetime import datetime
from botocore.exceptions import ClientError
from app.db import slots_table, appointments_table

from pydantic import BaseModel

# Add these back so routes.py can import them
class HoldSlotRequest(BaseModel):
    slot_id: str
    phone_number: str
    hold_seconds: int = 60

class ConfirmAppointmentRequest(BaseModel):
    slot_id: str
    phone_number: str

def current_ts():
    """Returns current UTC timestamp as integer."""
    return int(datetime.utcnow().timestamp())

def current_iso():
    """Returns current UTC time in ISO 8601 format."""
    return datetime.utcnow().isoformat()

def sanitize_decimal(data):
    """
    Recursively converts DynamoDB Decimal types to standard Python ints/floats.
    This is required for JSON serialization when sending data to the Gemini API.
    """
    if isinstance(data, list):
        return [sanitize_decimal(i) for i in data]
    elif isinstance(data, dict):
        return {k: sanitize_decimal(v) for k, v in data.items()}
    elif isinstance(data, Decimal):
        return int(data) if data % 1 == 0 else float(data)
    return data

# ----------------- AI-Facing Tools -----------------

def hold_slot(slot_id: str, phone_number: str, hold_seconds: int = 60):
    """
    Temporarily holds an appointment slot to prevent others from booking it.
    Use this when a user selects a time but has not yet given final confirmation.
    
    Args:
        slot_id: The unique ID of the slot (e.g., '2026-01-22-10:00')
        phone_number: The user's contact number.
        hold_seconds: How long the hold lasts before expiring (default 60s).
    """
    print(f"DEBUG: AI invoking hold_slot for {slot_id}")
    ttl = current_ts() + hold_seconds
    
    try:
        response = slots_table.update_item(
            Key={"slot_id": slot_id},
            UpdateExpression="SET #s = :held, hold_expires_at = :ttl, version = version + :inc",
            ConditionExpression="#s = :avail",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":avail": "AVAILABLE", 
                ":held": "HELD", 
                ":ttl": ttl, 
                ":inc": 1
            },
            ReturnValues="ALL_NEW"
        )
        
        # Sanitize result so Gemini doesn't crash on Decimals
        safe_attributes = sanitize_decimal(response.get("Attributes", {}))
        
        return {
            "success": True, 
            "message": f"Slot {slot_id} is now on hold.",
            "data": safe_attributes
        }

    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'ConditionalCheckFailedException':
            return {"success": False, "message": "Slot is no longer available (already held or booked)."}
        return {"success": False, "message": f"Database error: {str(e)}"}

def confirm_appointment(slot_id: str, phone_number: str):
    """
    Finalizes a booking that is currently being held.
    Call this ONLY after the user confirms they definitely want to book the appointment.
    
    Args:
        slot_id: The unique ID of the slot (e.g., '2026-01-22-10:00')
        phone_number: The user's contact number.
    """
    print(f"DEBUG: AI invoking confirm_appointment for {slot_id}")
    now_ts = current_ts()
    
    try:
        # 1. Update Slot status to BOOKED
        slots_table.update_item(
            Key={"slot_id": slot_id},
            UpdateExpression="SET #s = :booked, is_available = :false",
            ConditionExpression="#s = :held AND hold_expires_at > :now",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":held": "HELD", 
                ":booked": "BOOKED", 
                ":now": now_ts,
                ":false": False
            }
        )
        
        # 2. Create the permanent Appointment record
        appointment_id = str(uuid.uuid4())
        appointments_table.put_item(
            Item={
                "appointment_id": appointment_id,
                "slot_id": slot_id,
                "phone_number": phone_number,
                "status": "CONFIRMED",
                "created_at": current_iso()
            }
        )
        
        return {
            "success": True, 
            "appointment_id": appointment_id,
            "message": "Appointment successfully confirmed!"
        }

    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return {"success": False, "message": "Hold expired or slot was already booked. Please try again."}
        return {"success": False, "message": f"Database error: {str(e)}"}