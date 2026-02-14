import uuid
import boto3
from decimal import Decimal
from datetime import datetime
from botocore.exceptions import ClientError
from app.db import slots_table, appointments_table
from pydantic import BaseModel
import os
from twilio.rest import Client
from dotenv import load_dotenv

#sns_client = boto3.client('sns', region_name='us-east-1')
load_dotenv()

account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
twilio_number = os.getenv('TWILIO_PHONE_NUMBER')
twilio_client = Client(account_sid, auth_token)

def send_sms_notification(phone_number: str, message: str):
    """Sends an SMS notification via Twilio WhatsApp Sandbox."""
    try:
        raw = phone_number.replace("whatsapp:", "").replace("+", "").strip()
        if len(raw) == 10:
            raw = "1" + raw  # add US country code
        e164 = "+" + raw
        to_whatsapp = f"whatsapp:{e164}"
        from_whatsapp = f"whatsapp:{twilio_number}"
        print(f"DEBUG: Sending WhatsApp to {to_whatsapp} from {from_whatsapp}")
        twilio_client.messages.create(
            body=message,
            from_=from_whatsapp,
            to=to_whatsapp,
        )
        return True
    except Exception as e:
        print(f"ERROR: Failed to send WhatsApp: {e}")
        return False
    

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


def hold_slot(slot_id: str, phone_number: str, hold_seconds: int = 300):  # 5 min
    """
    Temporarily holds an appointment slot. 
    
    IMPORTANT: The AI must find the correct 'slot_id' from the list of available slots 
    retrieved via 'get_available_slots'. Do NOT ask the user for the slot_id or 
    a specific format; use the ID that matches the time the user requested.

    Args:
        slot_id: The internal unique ID for the slot.
        phone_number: The user's contact number (without 'whatsapp:' prefix).
        hold_seconds: Duration of the hold in seconds.
    """
    print(f"DEBUG: AI invoking hold_slot for {slot_id}")
    ttl = current_ts() + hold_seconds
    
    try:
        response = slots_table.update_item(
            Key={"slot_id": slot_id},
            UpdateExpression="SET #s = :held, hold_expires_at = :ttl, held_by = :phone, version = version + :inc",
            ConditionExpression="#s = :avail",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":avail": "AVAILABLE",
                ":held": "HELD",
                ":ttl": ttl,
                ":phone": phone_number,
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
    Finalizes a booking. Handles two cases atomically:
      - Normal path: slot is HELD by this caller and hold is still active
      - Fast path:   slot is still AVAILABLE (Gemini skipped hold_slot)
    Uses a DynamoDB transaction so slot update + appointment record are atomic.
    """
    print(f"DEBUG: AI invoking confirm_appointment for {slot_id}")
    now_ts = current_ts()
    appointment_id = str(uuid.uuid4())

    # Read current slot state to decide which condition to use
    try:
        res = slots_table.get_item(Key={"slot_id": slot_id})
        slot = res.get("Item")
        if not slot:
            return {"success": False, "message": f"Slot {slot_id} not found."}

        status = slot.get("status")
        held_by = slot.get("held_by")
        hold_expires_at = int(slot.get("hold_expires_at", 0))

        if status == "BOOKED":
            return {"success": False, "message": "This slot is already booked. Please choose a different time."}

        if status == "HELD":
            if held_by and held_by != phone_number and hold_expires_at > now_ts:
                return {"success": False, "message": "This slot is held by another caller. Please choose a different time or try again shortly."}
            if hold_expires_at <= now_ts:
                status = "AVAILABLE"  # hold expired, treat as available

    except ClientError as e:
        return {"success": False, "message": f"Could not read slot: {str(e)}"}

    # Build condition based on current slot status
    if status == "HELD":
        condition    = "#s = :held AND hold_expires_at > :now"
        expr_values  = {":held": "HELD", ":booked": "BOOKED", ":now": now_ts, ":false": False}
    else:
        condition    = "#s = :avail"
        expr_values  = {":avail": "AVAILABLE", ":booked": "BOOKED", ":now": now_ts, ":false": False}

    try:
        dynamodb_client = boto3.client('dynamodb', region_name=os.getenv('AWS_REGION', 'us-east-1'))
        dynamodb_client.transact_write(
            TransactItems=[
                {
                    "Update": {
                        "TableName": slots_table.name,
                        "Key": {"slot_id": {"S": slot_id}},
                        "UpdateExpression": "SET #s = :booked, is_available = :false",
                        "ConditionExpression": condition,
                        "ExpressionAttributeNames": {"#s": "status"},
                        "ExpressionAttributeValues": {
                            k: {"S": v} if isinstance(v, str) else
                               {"BOOL": v} if isinstance(v, bool) else
                               {"N": str(v)}
                            for k, v in expr_values.items()
                        }
                    }
                },
                {
                    "Put": {
                        "TableName": appointments_table.name,
                        "Item": {
                            "appointment_id": {"S": appointment_id},
                            "slot_id":        {"S": slot_id},
                            "phone_number":   {"S": phone_number},
                            "status":         {"S": "CONFIRMED"},
                            "created_at":     {"S": current_iso()}
                        },
                        "ConditionExpression": "attribute_not_exists(appointment_id)"
                    }
                }
            ]
        )

        sms_msg = f"Confirmed! Your appointment at the Clinic is set for {slot_id}. Booking ID: {appointment_id}"
        send_sms_notification(phone_number, sms_msg)

        return {
            "success": True,
            "appointment_id": appointment_id,
            "message": "Appointment confirmed and SMS sent!"
        }

    except ClientError as e:
        code = e.response['Error']['Code']
        if code == 'TransactionCanceledException':
            reasons = e.response.get('CancellationReasons', [])
            if reasons and reasons[0].get('Code') == 'ConditionalCheckFailed':
                return {"success": False, "message": "Slot was just taken. Please choose a different time."}
            return {"success": False, "message": "Booking failed — please try again."}
        return {"success": False, "message": f"Database error: {str(e)}"}

def get_appointments_by_phone(phone_number: str):
    """
    Search for existing appointments using a patient's phone number.
    Use this when a user wants to cancel or check their booking but doesn't have an ID.
    """
    print(f"DEBUG: AI searching for appointments for phone: {phone_number}")
    try:
        #Using Scan with a FilterExpression to find the phone number
        from boto3.dynamodb.conditions import Attr
        response = appointments_table.scan(
            FilterExpression=Attr('phone_number').eq(phone_number)
        )
        items = response.get('Items', [])
        
        if not items:
            return {"success": True, "message": "No appointments found for this number.", "appointments": []}
            
        return {"success": True, "appointments": sanitize_decimal(items)}
    except Exception as e:
        return {"success": False, "message": str(e)}

def cancel_appointment(appointment_id: str):
    """
    Cancels an existing appointment and makes the slot available again.
    Sends SMS after cancelling.
    Args:
        appointment_id: The unique ID of the appointment to cancel.
    """
    print(f"DEBUG: AI invoking cancel_appointment for {appointment_id}")
    
    try:
        #Get the appointment to find the associated slot_id
        res = appointments_table.get_item(Key={"appointment_id": appointment_id})
        item = res.get("Item")
        if not item:
            return {"success": False, "message": "Appointment ID not found."}
        
        slot_id = item["slot_id"]
        phone_number = item.get("phone_number")

        #Mark the slot as AVAILABLE again
        slots_table.update_item(
            Key={"slot_id": slot_id},
            UpdateExpression="SET #s = :avail, is_available = :true",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":avail": "AVAILABLE", ":true": True}
        )

        appointments_table.delete_item(Key={"appointment_id": appointment_id})

        if phone_number:
            sms_msg = f"Your appointment for {slot_id} has been cancelled."
            send_sms_notification(phone_number, sms_msg)

        return {"success": True, "message": "Appointment successfully cancelled."}
    except Exception as e:
        return {"success": False, "message": str(e)}

def reschedule_appointment(appointment_id: str, new_slot_id: str):
    """Moves an existing appointment to a new time slot and sends SMS."""
    print(f"DEBUG: Executing Reschedule for {appointment_id} -> {new_slot_id}")
    
    res = appointments_table.get_item(Key={'appointment_id': appointment_id})
    item = res.get("Item", {})
    phone_number = item.get("phone_number")

    cancel_res = cancel_appointment(appointment_id)
    
    try:
        slots_table.update_item(
            Key={"slot_id": new_slot_id},
            UpdateExpression="SET #s = :booked, is_available = :false",
            ConditionExpression="#s = :avail",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":booked": "BOOKED", ":false": False, ":avail": "AVAILABLE"}
        )

        if not cancel_res["success"]:
            return cancel_res
        
        if phone_number:
            sms_msg = f"Your appointment has been rescheduled to {new_slot_id}."
            send_sms_notification(phone_number, sms_msg)

        return {"success": True, "message": f"Appointment moved to {new_slot_id}. Please confirm the new time."}
    except Exception as e:
        return {"success": False, "error": str(e)}
    