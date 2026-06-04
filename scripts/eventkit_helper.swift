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

func boolValue(_ request: [String: Any], _ key: String) -> Bool? {
    if let value = request[key] as? Bool {
        return value
    }
    if let value = request[key] as? String {
        let lowered = value.lowercased()
        if lowered == "true" {
            return true
        }
        if lowered == "false" {
            return false
        }
    }
    return nil
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

func dateComponents(fromDueDate value: String) -> DateComponents? {
    if value.isEmpty {
        return nil
    }
    let dateOnlyPattern = #"^\d{4}-\d{2}-\d{2}$"#
    if value.range(of: dateOnlyPattern, options: .regularExpression) != nil {
        let parts = value.split(separator: "-").compactMap { Int($0) }
        if parts.count == 3 {
            return DateComponents(calendar: Calendar.current, year: parts[0], month: parts[1], day: parts[2])
        }
        return nil
    }
    let parser = ISO8601DateFormatter()
    parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    var parsed = parser.date(from: value)
    if parsed == nil {
        parser.formatOptions = [.withInternetDateTime]
        parsed = parser.date(from: value)
    }
    guard let date = parsed else {
        return nil
    }
    return Calendar.current.dateComponents(in: TimeZone.current, from: date)
}

func dueDateMatches(_ components: DateComponents?, _ value: String) -> Bool {
    guard let desired = dateComponents(fromDueDate: value) else {
        return components == nil || reminderDateString(components).isEmpty
    }
    guard let left = Calendar.current.date(from: components ?? DateComponents()),
          let right = Calendar.current.date(from: desired)
    else {
        return false
    }
    return abs(left.timeIntervalSince(right)) < 1
}

func emitReminderApplyError(
    _ status: String,
    _ code: String,
    _ message: String,
    authorizationStatus: EKAuthorizationStatus = EKEventStore.authorizationStatus(for: .reminder)
) -> Never {
    emit([
        "schema_version": 1,
        "status": status,
        "source": "reminders",
        "authorization_status": authorizationName(authorizationStatus),
        "reminder": NSNull(),
        "warnings": [warning(code, message)],
    ])
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

if command == "reminder_apply_change" {
    let store = ensureAccess(
        .reminder,
        source: "reminders",
        warningCode: "reminders_access_unavailable"
    )!
    let operation = stringValue(request, "operation")
    if operation != "create" && operation != "complete" && operation != "update_due_date" {
        emitReminderApplyError("error", "invalid_operation", "Unsupported Reminder apply operation.")
    }

    if operation == "create" {
        let title = stringValue(request, "title")
        let listName = stringValue(request, "list_name")
        let dueDate = stringValue(request, "due_date")
        let notes = stringValue(request, "notes")
        if title.isEmpty || listName.isEmpty {
            emitReminderApplyError("error", "missing_required_field", "Reminder create requires a title and list.")
        }
        let matchingLists = store.calendars(for: .reminder).filter { $0.title == listName }
        if matchingLists.isEmpty {
            emitReminderApplyError("not_found", "target_list_not_found", "Reminder list was not found.")
        }
        if matchingLists.count > 1 {
            emitReminderApplyError("error", "ambiguous_target_list", "Reminder list name matched more than one list.")
        }
        guard dueDate.isEmpty || dateComponents(fromDueDate: dueDate) != nil else {
            emitReminderApplyError("error", "invalid_due_date", "Reminder due date could not be parsed.")
        }
        let list = matchingLists[0]
        if let reminders = fetchReminders(store) {
            if let existing = reminders.first(where: {
                $0.calendar.calendarIdentifier == list.calendarIdentifier
                    && ($0.title ?? "") == title
                    && !$0.isCompleted
                    && dueDateMatches($0.dueDateComponents, dueDate)
            }) {
                emit([
                    "schema_version": 1,
                    "status": "ok",
                    "source": "reminders",
                    "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
                    "reminder": reminderPayload(existing, includeContent: false),
                    "warnings": [warning("already_applied", "Reminder create already matches an existing item.")],
                ])
            }
        }

        let reminder = EKReminder(eventStore: store)
        reminder.title = title
        reminder.calendar = list
        if !notes.isEmpty {
            reminder.notes = notes
        }
        reminder.dueDateComponents = dateComponents(fromDueDate: dueDate)
        do {
            try store.save(reminder, commit: true)
        } catch {
            emitReminderApplyError("error", "eventkit_apply_failed", "Reminder create could not be applied.")
        }
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
            "reminder": reminderPayload(reminder, includeContent: false),
            "warnings": [],
        ])
    }

    let reminderId = stringValue(request, "reminder_id")
    if reminderId.isEmpty {
        emitReminderApplyError("error", "invalid_reminder_id", "Expected EventKit reminder identifier.")
    }
    guard let reminders = fetchReminders(store),
          let reminder = reminders.first(where: { $0.calendarItemIdentifier == reminderId })
    else {
        emitReminderApplyError("not_found", "target_not_found", "Reminder target was not found.")
    }

    let expectedTitle = stringValue(request, "expected_title")
    if expectedTitle.isEmpty || (reminder.title ?? "") != expectedTitle {
        emitReminderApplyError("error", "expected_state_mismatch", "Reminder title did not match expected state.")
    }

    if operation == "complete" {
        if reminder.isCompleted {
            emit([
                "schema_version": 1,
                "status": "ok",
                "source": "reminders",
                "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
                "reminder": reminderPayload(reminder, includeContent: false),
                "warnings": [warning("already_applied", "Reminder is already complete.")],
            ])
        }
        if let expectedCompleted = boolValue(request, "expected_completed"),
           reminder.isCompleted != expectedCompleted {
            emitReminderApplyError("error", "expected_state_mismatch", "Reminder completion state did not match expected state.")
        }
        reminder.isCompleted = true
        reminder.completionDate = Date()
    } else {
        if let expectedCompleted = boolValue(request, "expected_completed"),
           reminder.isCompleted != expectedCompleted {
            emitReminderApplyError("error", "expected_state_mismatch", "Reminder completion state did not match expected state.")
        }
        let dueDate = stringValue(request, "due_date")
        guard !dueDate.isEmpty, let components = dateComponents(fromDueDate: dueDate) else {
            emitReminderApplyError("error", "invalid_due_date", "Reminder due date could not be parsed.")
        }
        if dueDateMatches(reminder.dueDateComponents, dueDate) {
            emit([
                "schema_version": 1,
                "status": "ok",
                "source": "reminders",
                "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
                "reminder": reminderPayload(reminder, includeContent: false),
                "warnings": [warning("already_applied", "Reminder due date already matches.")],
            ])
        }
        reminder.dueDateComponents = components
    }

    do {
        try store.save(reminder, commit: true)
    } catch {
        emitReminderApplyError("error", "eventkit_apply_failed", "Reminder change could not be applied.")
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "reminders",
        "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
        "reminder": reminderPayload(reminder, includeContent: false),
        "warnings": [],
    ])
}

emit([
    "schema_version": 1,
    "status": "error",
    "source": "eventkit",
    "warnings": [warning("unknown_command", "Unsupported EventKit helper command.")],
])
