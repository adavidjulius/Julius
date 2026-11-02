"""
Julius WhatsApp Integration — Deterministic Timetable & Schedule Engine.

Zero-hallucination schedule and scheduled location resolution.
Never claims physical presence; strictly reports verified timetable schedule.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from .storage import WhatsAppStorage
from .tools import get_current_datetime

logger = logging.getLogger(__name__)

# David Julius's verified 1st Year B.Tech IT Batch 2 schedule (MIT Chromepet, Anna University)
DEFAULT_WEEKLY_SCHEDULE = [
    # Monday
    {"day": "Monday", "start": "08:30", "end": "09:30", "course": "Technical English", "code": "HS21C01", "room": "Room 004", "type": "class"},
    {"day": "Monday", "start": "09:30", "end": "10:30", "course": "Engineering Physics", "code": "PH21C01", "room": "Room 004 (Dr. Geetha)", "type": "class"},
    {"day": "Monday", "start": "10:30", "end": "10:45", "course": "Morning Tea Break", "code": "", "room": "Campus Canteen", "type": "break"},
    {"day": "Monday", "start": "10:45", "end": "11:45", "course": "Calculus and Linear Algebra", "code": "MA21C01", "room": "Room 004", "type": "class"},
    {"day": "Monday", "start": "11:45", "end": "12:45", "course": "Fundamentals of Electrical and Electronics (FEEE)", "code": "EE21C01", "room": "Room 004", "type": "class"},
    {"day": "Monday", "start": "12:45", "end": "13:45", "course": "Lunch Break", "code": "", "room": "Hostel / Canteen", "type": "lunch"},
    {"day": "Monday", "start": "13:45", "end": "15:45", "course": "Physics Laboratory", "code": "PH21C02", "room": "Physics Lab (Dr. Geetha)", "type": "lab"},
    {"day": "Monday", "start": "15:45", "end": "16:30", "course": "Free Period / Library", "code": "", "room": "Campus Library", "type": "free_period"},

    # Tuesday
    {"day": "Tuesday", "start": "08:30", "end": "10:30", "course": "Makerspace Laboratory", "code": "GE21C02", "room": "Makerspace Lab (Mr. Manoj)", "type": "lab"},
    {"day": "Tuesday", "start": "10:30", "end": "10:45", "course": "Morning Break", "code": "", "room": "Campus Canteen", "type": "break"},
    {"day": "Tuesday", "start": "10:45", "end": "12:45", "course": "Engineering Graphics (EG Drawing)", "code": "GE21C01", "room": "Drawing Hall (Mr. Srinivasan)", "type": "class"},
    {"day": "Tuesday", "start": "12:45", "end": "13:45", "course": "Lunch Break", "code": "", "room": "Hostel / Canteen", "type": "lunch"},
    {"day": "Tuesday", "start": "13:45", "end": "15:45", "course": "Engineering Physics", "code": "PH21C01", "room": "Room 004", "type": "class"},
    {"day": "Tuesday", "start": "15:45", "end": "16:30", "course": "Free Period", "code": "", "room": "Room 004 / Library", "type": "free_period"},

    # Wednesday
    {"day": "Wednesday", "start": "08:30", "end": "10:30", "course": "Engineering Physics", "code": "PH21C01", "room": "Room 004", "type": "class"},
    {"day": "Wednesday", "start": "10:30", "end": "10:45", "course": "Morning Break", "code": "", "room": "Campus Canteen", "type": "break"},
    {"day": "Wednesday", "start": "10:45", "end": "12:45", "course": "Makerspace Practice", "code": "GE21C02", "room": "Makerspace Lab", "type": "lab"},
    {"day": "Wednesday", "start": "12:45", "end": "13:45", "course": "Lunch Break", "code": "", "room": "Hostel / Canteen", "type": "lunch"},
    {"day": "Wednesday", "start": "13:45", "end": "15:45", "course": "English Language Laboratory", "code": "HS21C02", "room": "English Lab", "type": "lab"},
    {"day": "Wednesday", "start": "15:45", "end": "16:30", "course": "Library Study Period", "code": "", "room": "Campus Library", "type": "library"},

    # Thursday
    {"day": "Thursday", "start": "08:30", "end": "12:45", "course": "Engineering Graphics Laboratory", "code": "GE21C01", "room": "EG Drawing Hall", "type": "lab"},
    {"day": "Thursday", "start": "12:45", "end": "13:45", "course": "Lunch Break", "code": "", "room": "Hostel / Canteen", "type": "lunch"},
    {"day": "Thursday", "start": "13:45", "end": "15:45", "course": "NSS / NCC / Sports", "code": "MC21C01", "room": "Campus Grounds", "type": "activity"},
    {"day": "Thursday", "start": "15:45", "end": "16:30", "course": "Free Period", "code": "", "room": "Campus", "type": "free_period"},

    # Friday
    {"day": "Friday", "start": "08:30", "end": "10:30", "course": "Calculus and Linear Algebra", "code": "MA21C01", "room": "Room 004", "type": "class"},
    {"day": "Friday", "start": "10:30", "end": "10:45", "course": "Morning Break", "code": "", "room": "Campus Canteen", "type": "break"},
    {"day": "Friday", "start": "10:45", "end": "12:45", "course": "FEEE (Dr. Gomathi)", "code": "EE21C01", "room": "Room 004", "type": "class"},
    {"day": "Friday", "start": "12:45", "end": "13:45", "course": "Lunch Break", "code": "", "room": "Hostel / Canteen", "type": "lunch"},
    {"day": "Friday", "start": "13:45", "end": "15:45", "course": "Heritage of Tamils", "code": "GE21C03", "room": "Room 004", "type": "class"},
    {"day": "Friday", "start": "15:45", "end": "16:30", "course": "Seminar / Discussion", "code": "", "room": "Room 004", "type": "seminar"},
]


class TimetableEngine:
    """
    Deterministic query engine for David's college schedule.
    Prevents hallucinating physical location or class schedules.
    """

    def __init__(self, storage: WhatsAppStorage) -> None:
        self._storage = storage
        self._seed_schedule()

    def _seed_schedule(self) -> None:
        """Seed verified timetable entries if not already present."""
        try:
            existing = self._storage.get_all_timetable_entries("David Julius")
            if not existing:
                for item in DEFAULT_WEEKLY_SCHEDULE:
                    self._storage.save_timetable_entry({
                        "id": f"tt_{item['day'][:3].lower()}_{item['start'].replace(':', '')}",
                        "person": "David Julius",
                        "department": "IT",
                        "semester": 1,
                        "day_of_week": item["day"],
                        "start_time": item["start"],
                        "end_time": item["end"],
                        "course_name": item["course"],
                        "course_code": item.get("code", ""),
                        "room_location": item.get("room", "Room 004"),
                        "activity_type": item.get("type", "class"),
                        "source": "verified_schedule",
                    })
        except Exception as e:
            logger.warning("[TIMETABLE_ENGINE] Failed seeding schedule: %s", e)

    def get_schedule_now(self) -> Dict[str, Any]:
        """
        Determine David's scheduled activity right now using exact IST clock.
        Returns structured scheduled status and required phrasing.
        """
        now_dt = get_current_datetime("Asia/Kolkata")
        weekday = now_dt["weekday"]
        current_time_str = now_dt["time"][:5]  # HH:MM

        if weekday in ("Saturday", "Sunday"):
            return {
                "day": weekday,
                "current_time": current_time_str,
                "is_weekend": True,
                "active_slot": None,
                "phrasing": f"According to the schedule, it's {weekday} (the weekend) — no classes are scheduled.",
            }

        slots = self._storage.get_timetable_for_day("User", weekday) or self._storage.get_timetable_for_day("David Julius", weekday)
        if not slots:
            # Fallback to in-memory schedule
            slots = [s for s in DEFAULT_WEEKLY_SCHEDULE if s["day"].lower() == weekday.lower()]

        active_slot = None
        for slot in slots:
            start = slot["start_time"] if "start_time" in slot else slot["start"]
            end = slot["end_time"] if "end_time" in slot else slot["end"]
            if start <= current_time_str < end:
                active_slot = slot
                break

        if not active_slot:
            # Before or after hours
            if current_time_str < "08:30":
                phrasing = f"According to the schedule, classes start at 08:30 AM today ({weekday}). No class is scheduled right now."
            else:
                phrasing = f"According to the schedule, daily sessions for {weekday} ended at 04:30 PM. No classes are scheduled right now."
            return {
                "day": weekday,
                "current_time": current_time_str,
                "is_weekend": False,
                "active_slot": None,
                "phrasing": phrasing,
            }

        c_name = active_slot.get("course_name") or active_slot.get("course", "Class")
        room = active_slot.get("room_location") or active_slot.get("room", "")
        act_type = active_slot.get("activity_type") or active_slot.get("type", "class")
        start = active_slot.get("start_time") or active_slot.get("start", "")
        end = active_slot.get("end_time") or active_slot.get("end", "")

        if act_type == "lunch":
            phrasing = f"According to the schedule, it is currently Lunch break ({start}–{end})."
        elif act_type == "break":
            phrasing = f"According to the schedule, it is currently a short break ({start}–{end})."
        elif act_type == "free_period":
            phrasing = f"According to the schedule, there is currently a Free Period ({start}–{end})."
        elif act_type == "library":
            phrasing = f"According to the schedule, Library study is scheduled ({start}–{end})."
        elif act_type == "seminar":
            phrasing = f"According to the schedule, a Seminar session is scheduled ({start}–{end})."
        elif act_type == "lab":
            phrasing = f"According to the schedule, {c_name} is scheduled at {room} ({start}–{end})."
        else:
            phrasing = f"According to the schedule, {c_name} is scheduled in {room} from {start} to {end} today."

        return {
            "day": weekday,
            "current_time": current_time_str,
            "is_weekend": False,
            "active_slot": active_slot,
            "phrasing": phrasing,
        }

    def get_schedule_at(self, day: str, time_str: str) -> Dict[str, Any]:
        """Query schedule for a specific day and time (e.g. Monday 10:30)."""
        target_day = day.capitalize()
        if target_day in ("Saturday", "Sunday"):
            return {
                "day": target_day,
                "time": time_str,
                "phrasing": f"According to the schedule, {target_day} is a weekend — no classes are scheduled.",
            }

        slots = self._storage.get_timetable_for_day("User", target_day) or self._storage.get_timetable_for_day("David Julius", target_day)
        if not slots:
            slots = [s for s in DEFAULT_WEEKLY_SCHEDULE if s["day"].lower() == target_day.lower()]

        clean_time = time_str.strip()
        # Parse time into HH:MM
        m = re.search(r"(\d{1,2}):?(\d{2})?", clean_time)
        if m:
            hh = int(m.group(1))
            mm = int(m.group(2) or 0)
            clean_time = f"{hh:02d}:{mm:02d}"

        active_slot = None
        for slot in slots:
            start = slot.get("start_time") or slot.get("start", "")
            end = slot.get("end_time") or slot.get("end", "")
            if start <= clean_time < end:
                active_slot = slot
                break

        if not active_slot:
            return {
                "day": target_day,
                "time": clean_time,
                "active_slot": None,
                "phrasing": f"According to the schedule, no classes are scheduled on {target_day} at {clean_time}.",
            }

        c_name = active_slot.get("course_name") or active_slot.get("course", "Class")
        room = active_slot.get("room_location") or active_slot.get("room", "")
        start = active_slot.get("start_time") or active_slot.get("start", "")
        end = active_slot.get("end_time") or active_slot.get("end", "")
        act_type = active_slot.get("activity_type") or active_slot.get("type", "class")

        if act_type == "free_period":
            phrasing = f"According to the schedule, at {clean_time} on {target_day} there is a Free Period ({start}–{end})."
        elif act_type == "lunch":
            phrasing = f"According to the schedule, at {clean_time} on {target_day} it is Lunch break ({start}–{end})."
        elif act_type == "library":
            phrasing = f"According to the schedule, at {clean_time} on {target_day} Library study is scheduled ({start}–{end})."
        else:
            phrasing = f"According to the schedule, at {clean_time} on {target_day} {c_name} is scheduled in {room} ({start}–{end})."

        return {
            "day": target_day,
            "time": clean_time,
            "active_slot": active_slot,
            "phrasing": phrasing,
        }

    def get_schedule_status(self, weekday: str, hour: int, minute: int) -> Dict[str, Any]:
        """Convenience query for (weekday, hour, minute)."""
        time_str = f"{hour:02d}:{minute:02d}"
        res = self.get_schedule_at(weekday, time_str)
        slot = res.get("active_slot")
        act_type = slot.get("activity_type") or slot.get("type", "") if slot else ""
        c_name = slot.get("course_name") or slot.get("course", "") if slot else ""
        is_free = act_type in ("free_period", "lunch", "break") or slot is None
        return {
            "day": weekday,
            "time": time_str,
            "is_free": is_free,
            "activity": c_name or "Free Period",
            "formatted_message": res.get("phrasing", ""),
            "active_slot": slot,
        }


_TIMETABLE_INSTANCE: Optional[TimetableEngine] = None


def get_timetable_engine(storage: Optional[WhatsAppStorage] = None) -> TimetableEngine:
    global _TIMETABLE_INSTANCE
    if _TIMETABLE_INSTANCE is None:
        if storage is None:
            storage = WhatsAppStorage()
        _TIMETABLE_INSTANCE = TimetableEngine(storage)
    return _TIMETABLE_INSTANCE
