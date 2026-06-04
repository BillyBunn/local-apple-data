import EventKit
import Foundation

let isoFormatter = ISO8601DateFormatter()
isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

func emit(_ payload: [String: Any]) -> Never {
    let data = try! JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    FileHandle.standardOutput.write(data)
    FileHandle.standardOutput.write(Data("\n".utf8))
    exit(0)
}

func warning(_ code: String, _ message: String) -> [String: String] {
    return ["code": code, "message": message]
}

func intValue(_ request: [String: Any], _ key: String, _ defaultValue: Int) -> Int {
    if let value = request[key] as? Int {
        return value
    }
    if let value = request[key] as? Double {
        return Int(value)
    }
    return defaultValue
}

func stringValue(_ request: [String: Any], _ key: String) -> String {
    return (request[key] as? String) ?? ""
}

func authorizationName(_ status: EKAuthorizationStatus) -> String {
    if #available(macOS 14.0, *) {
        switch status {
        case .fullAccess:
            return "full_access"
        case .writeOnly:
            return "write_only"
        case .authorized:
            return "authorized"
        case .denied:
            return "denied"
        case .notDetermined:
            return "not_determined"
        case .restricted:
            return "restricted"
        @unknown default:
            return "unknown"
        }
    }

    switch status.rawValue {
    case 3:
        return "authorized"
    case 2:
        return "denied"
    case 0:
        return "not_determined"
    case 1:
        return "restricted"
    default:
        return "unknown"
    }
}

func calendarReadAuthorized(_ status: EKAuthorizationStatus) -> Bool {
    if #available(macOS 14.0, *) {
        return status == .fullAccess
    }
    return status.rawValue == 3
}

func readAuthorized(_ status: EKAuthorizationStatus) -> Bool {
    if #available(macOS 14.0, *) {
        return status == .fullAccess || status.rawValue == 3
    }
    return status.rawValue == 3
}

func eventPayload(_ event: EKEvent, includeContent: Bool) -> [String: Any]? {
    guard let eventId = event.eventIdentifier else {
        return nil
    }
    var payload: [String: Any] = [
        "event_id": eventId,
        "title": event.title ?? "",
        "calendar_title": event.calendar?.title ?? "",
        "start_date": isoFormatter.string(from: event.startDate),
        "end_date": isoFormatter.string(from: event.endDate),
        "all_day": event.isAllDay,
        "availability": event.availability.rawValue,
        "location_present": !(event.location ?? "").isEmpty,
        "notes_present": !(event.notes ?? "").isEmpty,
        "url_present": event.url != nil,
        "alarms_count": event.alarms?.count ?? 0,
        "attendees_count": event.attendees?.count ?? 0,
    ]
    if includeContent {
        payload["location"] = event.location ?? ""
        payload["notes"] = event.notes ?? ""
    }
    return payload
}

func reminderDateString(_ components: DateComponents?) -> String {
    guard let components = components,
          let date = Calendar.current.date(from: components)
    else {
        return ""
    }
    return isoFormatter.string(from: date)
}

func reminderPayload(_ reminder: EKReminder, includeContent: Bool) -> [String: Any] {
    var payload: [String: Any] = [
        "reminder_id": reminder.calendarItemIdentifier,
        "title": reminder.title ?? "",
        "list_name": reminder.calendar.title,
        "due_date": reminderDateString(reminder.dueDateComponents),
        "start_date": reminderDateString(reminder.startDateComponents),
        "completed": reminder.isCompleted,
        "priority": reminder.priority,
        "notes_present": !(reminder.notes ?? "").isEmpty,
        "url_present": reminder.url != nil,
        "alarms_count": reminder.alarms?.count ?? 0,
    ]
    if includeContent {
        payload["notes"] = reminder.notes ?? ""
    }
    return payload
}

func ensureAccess(_ entityType: EKEntityType, source: String, warningCode: String) -> EKEventStore? {
    let status = EKEventStore.authorizationStatus(for: entityType)
    if !readAuthorized(status) {
        emit([
            "schema_version": 1,
            "status": "degraded",
            "source": source,
            "authorization_status": authorizationName(status),
            "events": [],
            "reminders": [],
            "event": NSNull(),
            "reminder": NSNull(),
            "warnings": [
                warning(
                    warningCode,
                    "\(source.capitalized) access is not authorized for this process."
                )
            ],
        ])
    }
    return EKEventStore()
}

let input = FileHandle.standardInput.readDataToEndOfFile()
guard
    let object = try? JSONSerialization.jsonObject(with: input, options: []),
    let request = object as? [String: Any]
else {
    emit([
        "schema_version": 1,
        "status": "error",
        "source": "eventkit",
        "warnings": [warning("invalid_request", "Expected JSON request.")],
    ])
}

func fetchReminders(_ store: EKEventStore) -> [EKReminder]? {
    let predicate = store.predicateForReminders(in: nil)
    var fetched: [EKReminder]?
    let semaphore = DispatchSemaphore(value: 0)
    store.fetchReminders(matching: predicate) { reminders in
        fetched = reminders ?? []
        semaphore.signal()
    }
    if semaphore.wait(timeout: .now() + .seconds(8)) == .timedOut {
        return nil
    }
    return fetched
}

let command = stringValue(request, "command")

if command == "calendar_events" {
    let store = ensureAccess(
        .event,
        source: "calendar",
        warningCode: "calendar_access_unavailable"
    )!
    let query = stringValue(request, "query").lowercased()
    let limit = max(1, min(intValue(request, "limit", 20), 50))
    let maxEvents = max(1, min(intValue(request, "max_events", 2000), 10000))
    let daysBack = max(0, min(intValue(request, "days_back", 365), 3650))
    let daysForward = max(0, min(intValue(request, "days_forward", 730), 3650))
    let now = Date()
    let start = Calendar.current.date(byAdding: .day, value: -daysBack, to: now) ?? now
    let end = Calendar.current.date(byAdding: .day, value: daysForward, to: now) ?? now
    let predicate = store.predicateForEvents(withStart: start, end: end, calendars: nil)
    let events = store.events(matching: predicate).sorted {
        if $0.startDate == $1.startDate {
            return ($0.title ?? "") < ($1.title ?? "")
        }
        return $0.startDate < $1.startDate
    }

    var scanned = 0
    var scanTruncated = false
    var results: [[String: Any]] = []
    for event in events {
        if scanned >= maxEvents {
            scanTruncated = true
            break
        }
        scanned += 1
        if !query.isEmpty && !((event.title ?? "").lowercased().contains(query)) {
            continue
        }
        if let payload = eventPayload(event, includeContent: false) {
            results.append(payload)
        }
        if results.count >= limit {
            break
        }
    }

    var warnings: [[String: String]] = []
    if scanTruncated {
        warnings.append(warning("scan_truncated", "Calendar scan stopped at the scan limit."))
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .event)),
        "events": results,
        "scanned": scanned,
        "warnings": warnings,
    ])
}

if command == "calendar_event_by_id" {
    let store = ensureAccess(
        .event,
        source: "calendar",
        warningCode: "calendar_access_unavailable"
    )!
    let eventId = stringValue(request, "event_id")
    if eventId.isEmpty {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "calendar",
            "event": NSNull(),
            "warnings": [warning("invalid_event_id", "Expected EventKit event identifier.")],
        ])
    }
    guard let event = store.event(withIdentifier: eventId),
          let payload = eventPayload(event, includeContent: true)
    else {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "calendar",
            "event": NSNull(),
            "warnings": [],
        ])
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "event": payload,
        "warnings": [],
    ])
}

if command == "reminders" {
    let store = ensureAccess(
        .reminder,
        source: "reminders",
        warningCode: "reminders_access_unavailable"
    )!
    guard let reminders = fetchReminders(store) else {
        emit([
            "schema_version": 1,
            "status": "degraded",
            "source": "reminders",
            "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
            "reminders": [],
            "warnings": [warning("reminders_fetch_timeout", "Reminders fetch timed out through EventKit.")],
        ])
    }

    let query = stringValue(request, "query").lowercased()
    let limit = max(1, min(intValue(request, "limit", 20), 10000))
    let includeCompleted = (request["include_completed"] as? Bool) ?? false
    let sorted = reminders.sorted {
        let leftDue = Calendar.current.date(from: $0.dueDateComponents ?? DateComponents())
        let rightDue = Calendar.current.date(from: $1.dueDateComponents ?? DateComponents())
        if leftDue != rightDue {
            return (leftDue ?? Date.distantFuture) < (rightDue ?? Date.distantFuture)
        }
        return ($0.title ?? "") < ($1.title ?? "")
    }
    var results: [[String: Any]] = []
    var scanned = 0
    for reminder in sorted {
        scanned += 1
        if !includeCompleted && reminder.isCompleted {
            continue
        }
        if !query.isEmpty && !((reminder.title ?? "").lowercased().contains(query)) {
            continue
        }
        results.append(reminderPayload(reminder, includeContent: false))
        if results.count >= limit {
            break
        }
    }

    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "reminders",
        "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
        "reminders": results,
        "scanned": scanned,
        "warnings": [],
    ])
}

if command == "reminder_by_id" {
    let store = ensureAccess(
        .reminder,
        source: "reminders",
        warningCode: "reminders_access_unavailable"
    )!
    let reminderId = stringValue(request, "reminder_id")
    if reminderId.isEmpty {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "reminders",
            "reminder": NSNull(),
            "warnings": [warning("invalid_reminder_id", "Expected EventKit reminder identifier.")],
        ])
    }
    guard let reminders = fetchReminders(store),
          let reminder = reminders.first(where: { $0.calendarItemIdentifier == reminderId })
    else {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "reminders",
            "reminder": NSNull(),
            "warnings": [],
        ])
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "reminders",
        "reminder": reminderPayload(reminder, includeContent: true),
        "warnings": [],
    ])
}

emit([
    "schema_version": 1,
    "status": "error",
    "source": "eventkit",
    "warnings": [warning("unknown_command", "Unsupported EventKit helper command.")],
])
