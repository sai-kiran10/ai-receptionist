from fastapi import APIRouter
from app.services.bookings import HoldSlotRequest, ConfirmAppointmentRequest, hold_slot, confirm_appointment
from app.services.slots import get_available_slots

router = APIRouter()

@router.post("/slots/hold")
def hold(request: HoldSlotRequest):
    return hold_slot(request)

@router.post("/appointments/confirm")
def confirm(request: ConfirmAppointmentRequest):
    return confirm_appointment(request)

@router.get("/slots")
def list_slots():
    return get_available_slots()