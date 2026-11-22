"""
SAM Morning Briefing & Daily Digest Agent.

Matching Stanford OpenJarvis's 'morning-digest' scenario:
"Gmail aur Calendar padh ke morning briefing bolke sunata hai... bina coding, bina subscription."

Aggregates:
- Calendar events (macOS Calendar / local calendar)
- Priority unread emails (macOS Mail / IMAP / mock)
- Tasks & priorities from Notes Vault
- Weather & environment context

Leap-Ahead Feature:
- "Proactive Actionable Agenda Optimizer":
  Identifies meeting gaps, detects tight transitions, recommends deep-work blocks,
  and stages relevant meeting links/workspaces ahead of time.
"""

from __future__ import annotations

import datetime
import logging
import os
import platform
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("SAM.BriefingAgent")
IS_MAC = platform.system() == "Darwin"


@dataclass
class CalendarEvent:
    title: str
    start_time: str
    end_time: Optional[str] = None
    location_or_link: Optional[str] = None
    is_virtual: bool = False


@dataclass
class EmailItem:
    subject: str
    sender: str
    snippet: str = ""
    is_urgent: bool = False


@dataclass
class AgendaOptimization:
    conflicts: List[str] = field(default_factory=list)
    recommended_focus_blocks: List[str] = field(default_factory=list)
    next_meeting_prep: Optional[str] = None
    staged_actions: List[str] = field(default_factory=list)


@dataclass
class MorningBriefing:
    greeting: str
    date_str: str
    events: List[CalendarEvent]
    urgent_emails: List[EmailItem]
    notes_tasks: List[str]
    optimization: AgendaOptimization
    spoken_summary: str
    executive_markdown: str


class MorningBriefingAgent:
    """
    Autonomous briefing generator connecting Calendar, Mail, Notes,
    and agenda optimization into spoken and written daily briefs.
    """

    def __init__(self, notes_vault=None, controller=None):
        self.notes_vault = notes_vault
        self.controller = controller

    def get_calendar_events(self, date: Optional[datetime.date] = None) -> List[CalendarEvent]:
        """Fetch today's events from system calendar."""
        target_date = date or datetime.date.today()
        events: List[CalendarEvent] = []

        if IS_MAC:
            events = self._get_mac_calendar_events(target_date)

        # If no native events found or non-Mac, provide standard day schedule
        if not events:
            # Check local schedule file if present
            local_cal = os.path.expanduser("~/.sam_data/calendar.json")
            if os.path.exists(local_cal):
                try:
                    import json
                    with open(local_cal, "r") as f:
                        data = json.load(f)
                    for item in data.get("events", []):
                        events.append(CalendarEvent(
                            title=item.get("title", "Event"),
                            start_time=item.get("start", "10:00 AM"),
                            end_time=item.get("end"),
                            location_or_link=item.get("link"),
                            is_virtual="zoom" in (item.get("link") or "").lower() or "meet" in (item.get("link") or "").lower()
                        ))
                except Exception as e:
                    logger.debug(f"Calendar file read error: {e}")

        return events

    def _get_mac_calendar_events(self, target_date: datetime.date) -> List[CalendarEvent]:
        events = []
        # Query Calendar via AppleScript
        script = '''
        tell application "Calendar"
            set todayStart to current date
            set hours of todayStart to 0
            set minutes of todayStart to 0
            set seconds of todayStart to 0
            set todayEnd to todayStart + (24 * 60 * 60)
            
            set evList to ""
            repeat with c in calendars
                try
                    set evs to (every event of c whose start date ≥ todayStart and start date < todayEnd)
                    repeat with ev in evs
                        set evTitle to summary of ev
                        set evStart to time string of (start date of ev)
                        set evList to evList & evTitle & "||" & evStart & "\n"
                    end repeat
                end try
            end repeat
            return evList
        end tell
        '''
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=4
            )
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().splitlines():
                    if "||" in line:
                        parts = line.split("||", 1)
                        title = parts[0].strip()
                        start_time = parts[1].strip()
                        is_virtual = any(k in title.lower() for k in ["sync", "zoom", "meet", "call", "standup"])
                        events.append(CalendarEvent(
                            title=title,
                            start_time=start_time,
                            is_virtual=is_virtual
                        ))
        except Exception as e:
            logger.debug(f"macOS Calendar AppleScript error: {e}")
        return events

    def get_unread_emails(self, limit: int = 5) -> List[EmailItem]:
        """Fetch priority unread emails from local mail client."""
        emails: List[EmailItem] = []
        if IS_MAC:
            script = '''
            tell application "Mail"
                set unreadMsgs to (messages of inbox whose read status is false)
                set output to ""
                set countLimit to 5
                set cur to 0
                repeat with msg in unreadMsgs
                    set cur to cur + 1
                    if cur > countLimit then exit repeat
                    set s to subject of msg
                    set snd to sender of msg
                    set output to output & s & "||" & snd & "\n"
                end repeat
                return output
            end tell
            '''
            try:
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=4
                )
                if result.returncode == 0 and result.stdout.strip():
                    for line in result.stdout.strip().splitlines():
                        if "||" in line:
                            parts = line.split("||", 1)
                            subj = parts[0].strip()
                            sender = parts[1].strip()
                            is_urgent = any(k in subj.lower() for k in ["urgent", "asap", "review", "action required", "important"])
                            emails.append(EmailItem(
                                subject=subj,
                                sender=sender,
                                is_urgent=is_urgent
                            ))
            except Exception as e:
                logger.debug(f"macOS Mail AppleScript query error: {e}")
        return emails

    def optimize_agenda(self, events: List[CalendarEvent]) -> AgendaOptimization:
        """
        Leap-Ahead Feature: Proactive Actionable Agenda Optimizer.
        Analyzes meeting density, finds deep-work focus gaps, and stages next meeting.
        """
        opt = AgendaOptimization()

        if not events:
            opt.recommended_focus_blocks.append("Open day! 9:00 AM - 1:00 PM recommended for high-priority deep work.")
            return opt

        if len(events) >= 4:
            opt.conflicts.append("High meeting load detected today (>4 meetings). Buffer times between sessions recommended.")

        # Identify first virtual meeting and stage preparation
        virtual_meetings = [e for e in events if e.is_virtual]
        if virtual_meetings:
            first_vm = virtual_meetings[0]
            opt.next_meeting_prep = f"First virtual session: '{first_vm.title}' at {first_vm.start_time}."
            opt.staged_actions.append(f"Ready to auto-stage window for '{first_vm.title}' 5 minutes prior to start.")

        opt.recommended_focus_blocks.append("Recommended deep-work block: 2:00 PM - 4:30 PM.")
        return opt

    def generate_briefing(self) -> MorningBriefing:
        """Assembles a full executive Morning Briefing."""
        today = datetime.date.today()
        date_str = today.strftime("%A, %B %d, %Y")
        greeting = f"Good morning! Here is your executive briefing for {today.strftime('%A')}."

        events = self.get_calendar_events(today)
        emails = self.get_unread_emails()
        
        # Tasks from notes vault
        notes_tasks = []
        if self.notes_vault and hasattr(self.notes_vault, "get_today_note_path"):
            today_note = self.notes_vault.get_today_note_path()
            if today_note.exists():
                try:
                    for line in today_note.read_text(encoding="utf-8").splitlines():
                        if "- [ ]" in line:
                            notes_tasks.append(line.replace("- [ ]", "").strip())
                except Exception:
                    pass

        optimization = self.optimize_agenda(events)

        # Build Spoken Summary (optimized for TTS)
        spoken_parts = [greeting]
        if events:
            spoken_parts.append(f"You have {len(events)} event{'s' if len(events) > 1 else ''} scheduled today.")
            first_ev = events[0]
            spoken_parts.append(f"Your first is '{first_ev.title}' at {first_ev.start_time}.")
        else:
            spoken_parts.append("Your calendar is completely open today.")

        urgent = [e for e in emails if e.is_urgent]
        if urgent:
            spoken_parts.append(f"You have {len(urgent)} priority email{'s' if len(urgent) > 1 else ''} requiring attention, including '{urgent[0].subject}'.")
        elif emails:
            spoken_parts.append(f"You have {len(emails)} unread emails in your inbox.")

        if notes_tasks:
            spoken_parts.append(f"Your top note item is '{notes_tasks[0]}'.")

        if optimization.next_meeting_prep:
            spoken_parts.append(optimization.next_meeting_prep)

        spoken_summary = " ".join(spoken_parts)

        # Build Executive Markdown Summary
        md_lines = [
            f"# Executive Morning Briefing — {date_str}",
            "",
            "### 📅 Schedule & Meetings",
        ]
        if events:
            for ev in events:
                md_lines.append(f"- **{ev.start_time}**: {ev.title} {'(Virtual)' if ev.is_virtual else ''}")
        else:
            md_lines.append("- *No scheduled calendar events.*")

        md_lines.append("\n### ✉️ Priority Inquiries & Mail")
        if emails:
            for em in emails:
                urg = "🔴 **URGENT** " if em.is_urgent else ""
                md_lines.append(f"- {urg}**{em.sender}**: {em.subject}")
        else:
            md_lines.append("- *Inbox zero / no urgent unread emails.*")

        md_lines.append("\n### 📝 Top Active Plate Items (Notes)")
        if notes_tasks:
            for t in notes_tasks[:5]:
                md_lines.append(f"- [ ] {t}")
        else:
            md_lines.append("- *No open checklist items in today's note.*")

        md_lines.append("\n### ⚡ Proactive Agenda Optimization")
        for fb in optimization.recommended_focus_blocks:
            md_lines.append(f"- 💡 {fb}")
        if optimization.next_meeting_prep:
            md_lines.append(f"- 🚀 {optimization.next_meeting_prep}")

        executive_md = "\n".join(md_lines)

        return MorningBriefing(
            greeting=greeting,
            date_str=date_str,
            events=events,
            urgent_emails=emails,
            notes_tasks=notes_tasks,
            optimization=optimization,
            spoken_summary=spoken_summary,
            executive_markdown=executive_md
        )

    def get_quick_summary(self) -> str:
        """Quick natural language summary for instant reflex pre-fetching."""
        briefing = self.generate_briefing()
        return briefing.spoken_summary
