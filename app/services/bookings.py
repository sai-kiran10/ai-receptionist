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
       # If the incoming phone_number doesn't already have the prefix, add it
        to_whatsapp = phone_number if phone_number.startswith("whatsapp:") else f"whatsapp:{phone_number}"
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

# ----------------- AI-Facing Tools -----------------

def hold_slot(slot_id: str, phone_number: str, hold_seconds: int = 60):
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
    After finalizing the appointment send an SMS.
    Args:
        slot_id: The unique ID of the slot (e.g., '2026-01-22-10:00')
        phone_number: The user's contact number.
    """
    print(f"DEBUG: AI invoking confirm_appointment for {slot_id}")
    now_ts = current_ts()
    
    try:
        #Update Slot status to BOOKED
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
        
        #Create the permanent Appointment record
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
        
        sms_msg = f"Confirmed! Your appointment at the Clinic is set for {slot_id}. Booking ID: {appointment_id}"
        send_sms_notification(phone_number, sms_msg)

        return {
            "success": True, 
            "appointment_id": appointment_id,
            "message": "Appointment confirmed and SMS sent!"
        }

    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return {"success": False, "message": "Hold expired or slot was already booked. Please try again."}
        return {"success": False, "message": f"Database error: {str(e)}"}


def resend_confirmation(phone_number: str):
    """
    Resend confirmation SMS for the patient's most recent appointment.
    Use when patient says they didn't receive the confirmation or asks you to resend it.
    """
    print(f"DEBUG: AI invoking resend_confirmation for {phone_number}")
    try:
        from boto3.dynamodb.conditions import Attr
        response = appointments_table.scan(
            FilterExpression=Attr('phone_number').eq(phone_number)
        )
        items = response.get('Items', [])
        
        if not items:
            return {"success": False, "message": "No appointments found for this number."}
        
        # Get most recent appointment
        items_sorted = sorted(items, key=lambda x: x.get('created_at', ''), reverse=True)
        appt = items_sorted[0]
        
        slot_id = appt['slot_id']
        appointment_id = appt['appointment_id']
        
        sms_msg = f"Confirmed! Your appointment at the Clinic is set for {slot_id}. Booking ID: {appointment_id}"
        send_sms_notification(phone_number, sms_msg)
        print(f"DEBUG: Resent confirmation for {appointment_id}")
        
        return {
            "success": True,
            "message": "Confirmation SMS resent successfully!",
            "appointment_id": appointment_id,
            "slot_id": slot_id
        }
    except Exception as e:
        print(f"ERROR in resend_confirmation: {e}")
        return {"success": False, "message": f"Error: {str(e)}"}

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