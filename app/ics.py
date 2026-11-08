"""
A timetable as an iCalendar file (RFC 5545), for a phone's own calendar.

Each class is a weekly event with a reminder before it, the room as its place
and a link that opens the assistant on the way there. A phone's calendar keeps
reminding with the site closed, which a web page cannot do on its own.

Times are written in UTC. Kazakhstan moved to UTC+5 in March 2024, and a phone
whose time-zone files are older would put an "Asia/Almaty" class an hour out;
the country keeps no summer time, so a weekly repeat in UTC never drifts.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from .engine import CAMPUS_TZ, campus_now


def _escape(text: str) -> str:
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> str:
    """Lines longer than 75 octets go on in a continuation line that starts with a space."""
    out, chunk = [], b""
    for ch in line:
        enc = ch.encode()
        if len(chunk) + len(enc) > (75 if not out else 74):
            out.append(chunk.decode())
            chunk = b""
        chunk += enc
    out.append(chunk.decode())
    return "\r\n ".join(out)


def _utc(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def first_meeting(day: int, start: str, now: datetime) -> datetime:
    """The first time a class meets from this week on, in campus time: this week's
    day, even if it has passed, so the series covers the whole current week."""
    monday = (now - timedelta(days=now.weekday())).date()
    hour, minute = map(int, start.split(":"))
    return datetime(monday.year, monday.month, monday.day, hour, minute, tzinfo=CAMPUS_TZ) + timedelta(days=day)


def route_link(site: str, entry: dict) -> str:
    """The assistant, asked for the way to a class's room."""
    return f"{site}/?ask={quote('How do I get to ' + entry['room_value'] + '?')}"


def timetable_calendar(classes: list[dict], site: str, lead: int, user_id: int,
                       now: datetime | None = None) -> str:
    now = campus_now(now)
    stamp = _utc(now)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SDU Campus Assistant//Timetable//EN",
             "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:SDU timetable",
             "X-WR-TIMEZONE:Asia/Almaty"]
    for entry in classes:
        begins = first_meeting(entry["day"], entry["start"], now)
        hour, minute = map(int, entry["end"].split(":"))
        ends = begins.replace(hour=hour, minute=minute)
        place = (f"{entry['room_label']}, {entry['where']}, SDU University" if entry.get("on_campus", True)
                 else entry["room_label"])
        about = [f"{entry['subject']} in {entry['room_label']} ({entry['where']})."]
        if entry.get("on_campus", True):
            link = route_link(site, entry)
            about.append(f"The way there: {link}")
        lines += ["BEGIN:VEVENT",
                  f"UID:class-{entry['class_id']}-{user_id}@sdu-campus-assistant",
                  f"DTSTAMP:{stamp}",
                  f"DTSTART:{_utc(begins)}",
                  f"DTEND:{_utc(ends)}",
                  "RRULE:FREQ=WEEKLY",
                  f"SUMMARY:{_escape(entry['subject'])}",
                  f"LOCATION:{_escape(place)}",
                  f"DESCRIPTION:{_escape(' '.join(about))}"]
        if entry.get("on_campus", True):
            lines.append(f"URL:{link}")
        if lead:
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"TRIGGER:-PT{lead}M",
                      f"DESCRIPTION:{_escape(entry['subject'] + ' in ' + entry['room_label'] + ' in ' + str(lead) + ' min')}",
                      "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
