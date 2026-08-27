import EventKit
import AppKit
import CoreFoundation
import Foundation
import CryptoKit
import CoreLocation

let maxAlarmOffsets = 8
let minAlarmOffsetMinutes = -40320
let maxAlarmOffsetMinutes = 40320
let maxAlarmSoundNameCharacters = 128
let maxAlarmEmailAddressCharacters = 254
let maxRecurrenceInterval = 4
let minRecurrenceCount = 2
let maxRecurrenceCount = 52
let maxRecurrenceEndDays = 3650.0
let maxEventURLCharacters = 2048
let safeEventURLSchemes: Set<String> = ["http", "https", "mailto", "tel"]
let mailtoEventURLPattern = #"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"#
let telEventURLPattern = #"^\+?[0-9][0-9().-]{1,31}(?:;ext=[0-9]{1,10})?$"#
let calendarTestPrefix = "LAD-TEST-"
let calendarSafetyWindowStart = Calendar.current.date(from: DateComponents(year: 1900, month: 1, day: 1))!
let calendarSafetyWindowEnd = Calendar.current.date(from: DateComponents(year: 2100, month: 1, day: 1))!

let isoFormatter = ISO8601DateFormatter()
isoFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

func commandLineOptionValue(_ name: String) -> String? {
    let arguments = CommandLine.arguments
    guard let index = arguments.firstIndex(of: name) else {
        return nil
    }
    let valueIndex = arguments.index(after: index)
    guard valueIndex < arguments.endIndex else {
        return nil
    }
    return arguments[valueIndex]
}

let inputJSONFilePath = commandLineOptionValue("--input-json-file")
let outputJSONFilePath = commandLineOptionValue("--output-json-file")

func dateOnlyString(from date: Date) -> String {
    let components = Calendar.current.dateComponents([.year, .month, .day], from: date)
    guard let year = components.year,
          let month = components.month,
          let day = components.day
    else {
        return isoFormatter.string(from: date)
    }
    return String(format: "%04d-%02d-%02d", year, month, day)
}

func eventDateString(from date: Date, allDay: Bool) -> String {
    if allDay {
        return dateOnlyString(from: date)
    }
    return isoFormatter.string(from: date)
}

func emit(_ payload: [String: Any]) -> Never {
    let data = try! JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
    if let outputJSONFilePath {
        try! data.write(to: URL(fileURLWithPath: outputJSONFilePath))
        exit(0)
    }
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

func optionalIntValue(_ request: [String: Any], _ key: String) -> Int? {
    if let value = request[key] as? Int {
        return value
    }
    if let value = request[key] as? Double {
        return Int(value)
    }
    if let value = request[key] as? String {
        return Int(value)
    }
    return nil
}

func isBooleanNumber(_ value: Any?) -> Bool {
    if value is Bool {
        return true
    }
    guard let numberItem = value as? NSNumber else {
        return false
    }
    return CFGetTypeID(numberItem) == CFBooleanGetTypeID()
}

func intArrayValue(_ request: [String: Any], _ key: String) -> [Int]? {
    guard let value = request[key] else {
        return []
    }
    guard let array = value as? [Any] else {
        return nil
    }
    if array.count > maxAlarmOffsets {
        return nil
    }
    var normalized: [Int] = []
    for item in array {
        if isBooleanNumber(item) {
            return nil
        }
        if let intItem = item as? Int {
            if intItem < minAlarmOffsetMinutes || intItem > maxAlarmOffsetMinutes {
                return nil
            }
            normalized.append(intItem)
            continue
        }
        if let numberItem = item as? NSNumber {
            let doubleValue = numberItem.doubleValue
            if !doubleValue.isFinite || doubleValue.rounded() != doubleValue {
                return nil
            }
            if doubleValue < Double(minAlarmOffsetMinutes) || doubleValue > Double(maxAlarmOffsetMinutes) {
                return nil
            }
            normalized.append(Int(doubleValue))
            continue
        }
        return nil
    }
    return Array(Set(normalized)).sorted()
}

func monthDayArrayValue(_ request: [String: Any], _ key: String) -> [Int]? {
    guard let value = request[key] else {
        return []
    }
    guard let array = value as? [Any] else {
        return nil
    }
    if array.count > 62 {
        return nil
    }
    var normalized = Set<Int>()
    for item in array {
        let intItem: Int
        if isBooleanNumber(item) {
            return nil
        }
        if let value = item as? Int {
            intItem = value
        } else if let numberItem = item as? NSNumber {
            let doubleValue = numberItem.doubleValue
            if !doubleValue.isFinite || doubleValue.rounded() != doubleValue {
                return nil
            }
            intItem = Int(doubleValue)
        } else {
            return nil
        }
        if intItem == 0 || intItem < -31 || intItem > 31 {
            return nil
        }
        normalized.insert(intItem)
    }
    return normalized.sorted()
}

func monthWeekdayArrayValue(_ request: [String: Any], _ key: String) -> [[String: Any]]? {
    guard let value = request[key] else {
        return []
    }
    guard let array = value as? [Any] else {
        return nil
    }
    if array.count > 70 {
        return nil
    }
    var normalized: [String: (weekday: String, rawValue: Int, weekNumber: Int)] = [:]
    for item in array {
        guard let object = item as? [String: Any],
              let weekdayValue = object["weekday"] as? String,
              let rawValue = recurrenceWeekdayRawValue(weekdayValue)
        else {
            return nil
        }
        let weekNumber: Int
        let weekNumberValue = object["week_number"]
        if isBooleanNumber(weekNumberValue) {
            return nil
        }
        if let intValue = weekNumberValue as? Int {
            weekNumber = intValue
        } else if let numberItem = weekNumberValue as? NSNumber {
            let doubleValue = numberItem.doubleValue
            if !doubleValue.isFinite || doubleValue.rounded() != doubleValue {
                return nil
            }
            weekNumber = Int(doubleValue)
        } else {
            return nil
        }
        if weekNumber == 0 || weekNumber < -5 || weekNumber > 5 {
            return nil
        }
        guard let weekday = recurrenceWeekdayName(rawValue) else {
            return nil
        }
        normalized["\(weekNumber):\(weekday)"] = (weekday, rawValue, weekNumber)
    }
    return normalized.values.sorted {
        ($0.weekNumber, $0.rawValue) < ($1.weekNumber, $1.rawValue)
    }.map {
        ["weekday": $0.weekday, "week_number": $0.weekNumber]
    }
}

func monthWeekdayComparisonKeys(_ request: [String: Any], _ key: String) -> [String]? {
    guard let values = monthWeekdayArrayValue(request, key) else {
        return nil
    }
    return values.compactMap { item in
        guard let weekday = item["weekday"] as? String,
              let weekNumber = item["week_number"] as? Int
        else {
            return nil
        }
        return "\(weekNumber):\(weekday)"
    }
}

func yearMonthArrayValue(_ request: [String: Any], _ key: String) -> [Int]? {
    guard let value = request[key] else {
        return []
    }
    guard let array = value as? [Any] else {
        return nil
    }
    if array.count > 12 {
        return nil
    }
    var normalized: Set<Int> = []
    for item in array {
        let month: Int
        if isBooleanNumber(item) {
            return nil
        }
        if let intValue = item as? Int {
            month = intValue
        } else if let numberItem = item as? NSNumber {
            let doubleValue = numberItem.doubleValue
            if !doubleValue.isFinite || doubleValue.rounded() != doubleValue {
                return nil
            }
            month = Int(doubleValue)
        } else {
            return nil
        }
        if month < 1 || month > 12 {
            return nil
        }
        normalized.insert(month)
    }
    return normalized.sorted()
}

func signedRecurrenceIntArrayValue(
    _ request: [String: Any],
    _ key: String,
    minValue: Int,
    maxValue: Int,
    maxCount: Int
) -> [Int]? {
    guard let value = request[key] else {
        return []
    }
    guard let array = value as? [Any] else {
        return nil
    }
    if array.count > maxCount {
        return nil
    }
    var normalized = Set<Int>()
    for item in array {
        let intItem: Int
        if isBooleanNumber(item) {
            return nil
        }
        if let value = item as? Int {
            intItem = value
        } else if let numberItem = item as? NSNumber {
            let doubleValue = numberItem.doubleValue
            if !doubleValue.isFinite || doubleValue.rounded() != doubleValue {
                return nil
            }
            intItem = Int(doubleValue)
        } else {
            return nil
        }
        if intItem == 0 || intItem < minValue || intItem > maxValue {
            return nil
        }
        normalized.insert(intItem)
    }
    return normalized.sorted()
}

func yearDayArrayValue(_ request: [String: Any], _ key: String) -> [Int]? {
    return signedRecurrenceIntArrayValue(
        request,
        key,
        minValue: -366,
        maxValue: 366,
        maxCount: 732
    )
}

func yearWeekArrayValue(_ request: [String: Any], _ key: String) -> [Int]? {
    return signedRecurrenceIntArrayValue(
        request,
        key,
        minValue: -53,
        maxValue: 53,
        maxCount: 106
    )
}

func recurrenceSetPositionsArrayValue(_ request: [String: Any], _ key: String) -> [Int]? {
    return signedRecurrenceIntArrayValue(
        request,
        key,
        minValue: -366,
        maxValue: 366,
        maxCount: 732
    )
}

func dateStringArrayValue(_ request: [String: Any], _ key: String) -> [String]? {
    guard let value = request[key] else {
        return []
    }
    guard let array = value as? [Any] else {
        return nil
    }
    if array.count > maxAlarmOffsets {
        return nil
    }
    var normalized = Set<String>()
    for item in array {
        guard let stringItem = item as? String,
              let parsed = eventDate(from: stringItem)
        else {
            return nil
        }
        normalized.insert(isoFormatter.string(from: parsed))
    }
    return Array(normalized).sorted()
}

func isValidAlarmSoundName(_ value: String) -> Bool {
    if value.isEmpty || value.count > maxAlarmSoundNameCharacters {
        return false
    }
    if value.trimmingCharacters(in: .whitespacesAndNewlines) != value {
        return false
    }
    let allowed = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 _.-")
    return value.rangeOfCharacter(from: allowed.inverted) == nil
}

func alarmSoundNameValue(_ request: [String: Any], _ key: String) -> String? {
    guard let value = request[key] else {
        return ""
    }
    guard let stringValue = value as? String else {
        return nil
    }
    let normalized = stringValue.trimmingCharacters(in: .whitespacesAndNewlines)
    if normalized.isEmpty {
        return ""
    }
    if !isValidAlarmSoundName(normalized) {
        return nil
    }
    return normalized
}

func isValidAlarmEmailAddress(_ value: String) -> Bool {
    if value.isEmpty || value.count > maxAlarmEmailAddressCharacters {
        return false
    }
    if value.trimmingCharacters(in: .whitespacesAndNewlines) != value {
        return false
    }
    for scalar in value.unicodeScalars {
        if scalar.value < 33 || scalar.value > 126 {
            return false
        }
    }
    guard let atIndex = value.firstIndex(of: "@"),
          atIndex != value.startIndex,
          atIndex != value.index(before: value.endIndex),
          value[value.index(after: atIndex)...].contains(".")
    else {
        return false
    }
    let pattern = #"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}$"#
    return value.range(of: pattern, options: .regularExpression) != nil
}

func alarmEmailAddressValue(_ request: [String: Any], _ key: String) -> String? {
    guard let value = request[key] else {
        return ""
    }
    guard let stringValue = value as? String else {
        return nil
    }
    let normalized = stringValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    if normalized.isEmpty {
        return ""
    }
    if !isValidAlarmEmailAddress(normalized) {
        return nil
    }
    return normalized
}

func alarmProximityValue(_ request: [String: Any], _ key: String) -> String? {
    guard let value = request[key] else {
        return ""
    }
    guard let stringValue = value as? String else {
        return nil
    }
    let normalized = stringValue.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    if normalized.isEmpty {
        return ""
    }
    if normalized == "enter" || normalized == "leave" {
        return normalized
    }
    return nil
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

func isDateOnlyString(_ value: String) -> Bool {
    let dateOnlyPattern = #"^\d{4}-\d{2}-\d{2}$"#
    return value.range(of: dateOnlyPattern, options: .regularExpression) != nil
}

func sha256Hex(_ value: String) -> String {
    let digest = SHA256.hash(data: Data(value.utf8))
    return digest.map { String(format: "%02x", $0) }.joined()
}

func isSHA256Hex(_ value: String) -> Bool {
    if value.isEmpty {
        return true
    }
    let pattern = #"^[0-9a-f]{64}$"#
    return value.range(of: pattern, options: .regularExpression) != nil
}

func alarmTypeName(_ type: EKAlarmType) -> String {
    switch type {
    case .display:
        return "display"
    case .audio:
        return "audio"
    case .procedure:
        return "procedure"
    case .email:
        return "email"
    @unknown default:
        return "unknown"
    }
}

func eventURLString(_ event: EKEvent) -> String {
    return event.url?.absoluteString ?? ""
}

func normalizedEventURLOrError(_ value: String, _ field: String) -> URL? {
    if value.isEmpty {
        return nil
    }
    if value.count > maxEventURLCharacters || value.rangeOfCharacter(from: .whitespacesAndNewlines) != nil {
        emitCalendarApplyError("error", "invalid_event_url", "Calendar \(field) must be a bounded allowed URL without whitespace.")
    }
    guard let components = URLComponents(string: value),
          let scheme = components.scheme?.lowercased(),
          safeEventURLSchemes.contains(scheme),
          let url = components.url
    else {
        emitCalendarApplyError("error", "invalid_event_url", "Calendar \(field) must use http, https, mailto, or tel without embedded credentials.")
    }
    if ["http", "https"].contains(scheme) {
        if components.host?.isEmpty != false || components.user != nil || components.password != nil {
            emitCalendarApplyError("error", "invalid_event_url", "Calendar \(field) must include a host and no embedded credentials.")
        }
        return url
    }
    if scheme == "mailto" {
        if components.host != nil || components.query != nil || components.fragment != nil || components.path.range(of: mailtoEventURLPattern, options: .regularExpression) == nil {
            emitCalendarApplyError("error", "invalid_event_url", "Calendar \(field) mailto URL must contain one recipient address.")
        }
        return url
    }
    if scheme == "tel" {
        if components.host != nil || components.query != nil || components.fragment != nil || components.path.range(of: telEventURLPattern, options: .regularExpression) == nil {
            emitCalendarApplyError("error", "invalid_event_url", "Calendar \(field) tel URL must contain one bounded dial string.")
        }
        return url
    }
    return url
}

func normalizedReminderURLOrError(_ value: String, _ field: String) -> URL? {
    if value.isEmpty {
        return nil
    }
    if value.utf8.contains(where: { $0 < 0x21 || $0 > 0x7E }) {
        emitReminderApplyError("error", "invalid_url", "Reminder \(field) must contain only bounded ASCII URL characters without whitespace.")
    }
    if value.count > maxEventURLCharacters || value.rangeOfCharacter(from: .whitespacesAndNewlines) != nil {
        emitReminderApplyError("error", "invalid_url", "Reminder \(field) must be a bounded allowed URL without whitespace.")
    }
    guard let components = URLComponents(string: value),
          let scheme = components.scheme?.lowercased(),
          safeEventURLSchemes.contains(scheme),
          let url = components.url
    else {
        emitReminderApplyError("error", "invalid_url", "Reminder \(field) must use http, https, mailto, or tel without embedded credentials.")
    }
    if ["http", "https"].contains(scheme) {
        if components.host?.isEmpty != false || components.user != nil || components.password != nil {
            emitReminderApplyError("error", "invalid_url", "Reminder \(field) must include a host and no embedded credentials.")
        }
        return url
    }
    if scheme == "mailto" {
        if components.host != nil || components.query != nil || components.fragment != nil || components.path.range(of: mailtoEventURLPattern, options: .regularExpression) == nil {
            emitReminderApplyError("error", "invalid_url", "Reminder \(field) mailto URL must contain one recipient address.")
        }
        return url
    }
    if scheme == "tel" {
        if components.host != nil || components.query != nil || components.fragment != nil || components.path.range(of: telEventURLPattern, options: .regularExpression) == nil {
            emitReminderApplyError("error", "invalid_url", "Reminder \(field) tel URL must contain one bounded dial string.")
        }
        return url
    }
    return url
}

func doubleValue(_ value: Any?) -> Double? {
    if value is Bool {
        return nil
    }
    if let number = value as? NSNumber {
        return number.doubleValue
    }
    if let value = value as? Double {
        return value
    }
    if let value = value as? Int {
        return Double(value)
    }
    return nil
}

func structuredLocationRequest(_ request: [String: Any], _ key: String) -> [String: Any]? {
    guard let value = request[key] as? [String: Any], !value.isEmpty else {
        return nil
    }
    guard let title = value["title"] as? String, !title.isEmpty else {
        emitCalendarApplyError("error", "invalid_structured_location", "Calendar \(key).title must be non-empty text.")
    }
    let geoPresent = (value["geo_present"] as? Bool) ?? false
    var payload: [String: Any] = [
        "title": title,
        "geo_present": geoPresent,
    ]
    if geoPresent {
        guard let latitude = doubleValue(value["latitude"]),
              let longitude = doubleValue(value["longitude"]),
              let radius = doubleValue(value["radius_meters"])
        else {
            emitCalendarApplyError("error", "invalid_structured_location", "Calendar \(key) coordinates must be numeric.")
        }
        if latitude < -90 || latitude > 90 {
            emitCalendarApplyError("error", "invalid_structured_location", "Calendar \(key).latitude must be between -90 and 90.")
        }
        if longitude < -180 || longitude > 180 {
            emitCalendarApplyError("error", "invalid_structured_location", "Calendar \(key).longitude must be between -180 and 180.")
        }
        if radius < 0 || radius > 100000 {
            emitCalendarApplyError("error", "invalid_structured_location", "Calendar \(key).radius_meters must be between 0 and 100000.")
        }
        payload["latitude"] = latitude
        payload["longitude"] = longitude
        payload["radius_meters"] = radius
    }
    return payload
}

func structuredLocationPayload(_ location: EKStructuredLocation?, fallbackTitle: String) -> [String: Any]? {
    guard let location = location else {
        return nil
    }
    var payload: [String: Any] = [
        "title": location.title ?? fallbackTitle,
        "geo_present": false,
    ]
    if let geoLocation = location.geoLocation {
        payload["geo_present"] = true
        payload["latitude"] = geoLocation.coordinate.latitude
        payload["longitude"] = geoLocation.coordinate.longitude
        payload["radius_meters"] = location.radius
    }
    return payload
}

func structuredLocationPayload(_ event: EKEvent) -> [String: Any]? {
    return structuredLocationPayload(event.structuredLocation, fallbackTitle: event.location ?? "")
}

func structuredLocationPayloadMatches(_ current: [String: Any]?, _ expected: [String: Any]?) -> Bool {
    guard let expected = expected else {
        return true
    }
    guard let current = current,
          let currentTitle = current["title"] as? String,
          let expectedTitle = expected["title"] as? String,
          currentTitle == expectedTitle
    else {
        return false
    }
    let currentGeo = (current["geo_present"] as? Bool) ?? false
    let expectedGeo = (expected["geo_present"] as? Bool) ?? false
    if currentGeo != expectedGeo {
        return false
    }
    if expectedGeo {
        guard let currentLatitude = doubleValue(current["latitude"]),
              let currentLongitude = doubleValue(current["longitude"]),
              let currentRadius = doubleValue(current["radius_meters"]),
              let expectedLatitude = doubleValue(expected["latitude"]),
              let expectedLongitude = doubleValue(expected["longitude"]),
              let expectedRadius = doubleValue(expected["radius_meters"])
        else {
            return false
        }
        return abs(currentLatitude - expectedLatitude) < 0.000001
            && abs(currentLongitude - expectedLongitude) < 0.000001
            && abs(currentRadius - expectedRadius) < 0.001
    }
    return true
}

func structuredLocationPayloadsEqual(_ first: [String: Any]?, _ second: [String: Any]?) -> Bool {
    if first == nil && second == nil {
        return true
    }
    guard first != nil && second != nil else {
        return false
    }
    return structuredLocationPayloadMatches(first, second)
        && structuredLocationPayloadMatches(second, first)
}

func structuredLocationSafeSHA256(_ event: EKEvent) -> String {
    guard let payload = structuredLocationPayload(event),
          let title = payload["title"] as? String else {
        return ""
    }
    let geoPresent = (payload["geo_present"] as? Bool) ?? false
    var parts = [
        "title=\(title)",
        "geo_present=\(geoPresent ? "true" : "false")",
    ]
    if geoPresent,
       let latitude = doubleValue(payload["latitude"]),
       let longitude = doubleValue(payload["longitude"]),
       let radius = doubleValue(payload["radius_meters"]) {
        parts.append(String(format: "latitude=%.6f", latitude))
        parts.append(String(format: "longitude=%.6f", longitude))
        parts.append(String(format: "radius_meters=%.3f", radius))
    } else {
        parts.append("latitude=")
        parts.append("longitude=")
        parts.append("radius_meters=")
    }
    return sha256Hex(parts.joined(separator: "\n"))
}

func structuredLocationMatches(_ event: EKEvent, _ expected: [String: Any]?) -> Bool {
    return structuredLocationPayloadMatches(structuredLocationPayload(event), expected)
}

func makeStructuredLocation(_ structuredLocation: [String: Any], fallbackLocation: String) -> EKStructuredLocation {
    let title = (structuredLocation["title"] as? String) ?? fallbackLocation
    let location = EKStructuredLocation(title: title)
    if (structuredLocation["geo_present"] as? Bool) == true,
       let latitude = doubleValue(structuredLocation["latitude"]),
       let longitude = doubleValue(structuredLocation["longitude"]),
       let radius = doubleValue(structuredLocation["radius_meters"]) {
        location.geoLocation = CLLocation(latitude: latitude, longitude: longitude)
        location.radius = radius
    }
    return location
}

func applyStructuredLocation(_ event: EKEvent, _ structuredLocation: [String: Any]?, fallbackLocation: String) {
    guard let structuredLocation = structuredLocation else {
        event.location = fallbackLocation.isEmpty ? nil : fallbackLocation
        return
    }
    let title = (structuredLocation["title"] as? String) ?? fallbackLocation
    event.location = title.isEmpty ? nil : title
    let location = makeStructuredLocation(structuredLocation, fallbackLocation: fallbackLocation)
    event.structuredLocation = location
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

// EventKit's TCC prompt is only presented for a genuinely-running, foreground
// app driven by a real NSApplication run loop AND signed with a stable
// identity. A manual RunLoop.current.run loop does not complete the launch
// handshake tccd requires, so the prompt never appears and the request hangs.
// This delegate kicks the request off inside applicationDidFinishLaunching and
// emits (which exits the process) from the completion/timeout paths, so
// NSApplication.run() never needs to return.
final class EventKitAccessDelegate: NSObject, NSApplicationDelegate {
    let entityType: EKEntityType
    let source: String
    let unavailableCode: String
    let unavailableMessage: String
    let timeoutCode: String
    let timeoutMessage: String

    init(
        entityType: EKEntityType,
        source: String,
        unavailableCode: String,
        unavailableMessage: String,
        timeoutCode: String,
        timeoutMessage: String
    ) {
        self.entityType = entityType
        self.source = source
        self.unavailableCode = unavailableCode
        self.unavailableMessage = unavailableMessage
        self.timeoutCode = timeoutCode
        self.timeoutMessage = timeoutMessage
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.activate(ignoringOtherApps: true)
        let store = EKEventStore()
        let handler: (Bool, Error?) -> Void = { [self] granted, error in
            DispatchQueue.main.async { [self] in
                let finalStatus = EKEventStore.authorizationStatus(for: entityType)
                if granted && readAuthorized(finalStatus) {
                    emit([
                        "schema_version": 1,
                        "status": "ok",
                        "source": source,
                        "authorization_status": authorizationName(finalStatus),
                        "request_result": "granted",
                        "warnings": [],
                    ])
                }
                emit([
                    "schema_version": 1,
                    "status": "degraded",
                    "source": source,
                    "authorization_status": authorizationName(finalStatus),
                    "request_result": error != nil ? "failed" : "not_granted",
                    "warnings": [warning(unavailableCode, unavailableMessage)],
                ])
            }
        }
        if #available(macOS 14.0, *) {
            if entityType == .event {
                store.requestFullAccessToEvents(completion: handler)
            } else {
                store.requestFullAccessToReminders(completion: handler)
            }
        } else {
            store.requestAccess(to: entityType, completion: handler)
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 120) { [self] in
            emit([
                "schema_version": 1,
                "status": "degraded",
                "source": source,
                "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: entityType)),
                "request_result": "timeout",
                "warnings": [warning(timeoutCode, timeoutMessage)],
            ])
        }
    }
}

// Retained for the lifetime of the process so NSApplication's weak delegate
// reference stays valid.
private var eventKitAccessDelegate: EventKitAccessDelegate?

func runEventKitAccessRequest(_ delegate: EventKitAccessDelegate) -> Never {
    eventKitAccessDelegate = delegate
    let app = NSApplication.shared
    app.setActivationPolicy(.regular)
    app.delegate = delegate
    app.run()
    // app.run() only returns if the loop is stopped without emitting; treat as
    // a degraded outcome rather than exiting silently.
    emit([
        "schema_version": 1,
        "status": "degraded",
        "source": delegate.source,
        "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: delegate.entityType)),
        "request_result": "not_granted",
        "warnings": [warning(delegate.unavailableCode, delegate.unavailableMessage)],
    ])
}

func requestCalendarFullAccess() {
    let initialStatus = EKEventStore.authorizationStatus(for: .event)
    if readAuthorized(initialStatus) {
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": authorizationName(initialStatus),
            "request_result": "already_full_access",
            "warnings": [],
        ])
    }
    _ = runEventKitAccessRequest(
        EventKitAccessDelegate(
            entityType: .event,
            source: "calendar",
            unavailableCode: "calendar_access_unavailable",
            unavailableMessage: "Calendar full access was not granted to this process.",
            timeoutCode: "calendar_access_request_timeout",
            timeoutMessage: "Calendar access prompt did not complete before timeout."
        )
    )
}

func requestRemindersFullAccess() {
    let initialStatus = EKEventStore.authorizationStatus(for: .reminder)
    if readAuthorized(initialStatus) {
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": authorizationName(initialStatus),
            "request_result": "already_full_access",
            "warnings": [],
        ])
    }
    _ = runEventKitAccessRequest(
        EventKitAccessDelegate(
            entityType: .reminder,
            source: "reminders",
            unavailableCode: "reminders_access_unavailable",
            unavailableMessage: "Reminders full access was not granted to this process.",
            timeoutCode: "reminders_access_request_timeout",
            timeoutMessage: "Reminders access prompt did not complete before timeout."
        )
    )
}

func alarmOffsetsMinutes(_ event: EKEvent) -> [Int]? {
    let state = alarmState(event)
    if state.absoluteDates == nil || state.absoluteDates?.isEmpty == false {
        return nil
    }
    return state.offsets
}

func alarmAbsoluteDates(_ event: EKEvent) -> [String]? {
    let state = alarmState(event)
    if state.offsets == nil || state.offsets?.isEmpty == false {
        return nil
    }
    return state.absoluteDates
}

func alarmProximityName(_ proximity: EKAlarmProximity) -> String {
    switch proximity {
    case .enter:
        return "enter"
    case .leave:
        return "leave"
    case .none:
        return ""
    @unknown default:
        return ""
    }
}

func alarmProximityFromName(_ name: String) -> EKAlarmProximity? {
    if name == "enter" {
        return .enter
    }
    if name == "leave" {
        return .leave
    }
    if name.isEmpty {
        return EKAlarmProximity.none
    }
    return nil
}

func alarmState(_ event: EKEvent) -> (offsets: [Int]?, absoluteDates: [String]?, soundName: String?, proximity: String?, structuredLocation: [String: Any]?, emailAddressSHA256: String?) {
    let alarms = event.alarms ?? []
    if alarms.count > maxAlarmOffsets {
        return (nil, nil, nil, nil, nil, nil)
    }
    if alarms.contains(where: { $0.structuredLocation != nil || $0.proximity != .none }) {
        if alarms.count != 1 {
            return (nil, nil, nil, nil, nil, nil)
        }
        let alarm = alarms[0]
        if alarm.type == .email || alarm.type == .procedure || alarm.type == .audio || alarm.emailAddress != nil {
            return (nil, nil, nil, nil, nil, nil)
        }
        if !(alarm.soundName ?? "").isEmpty || alarm.absoluteDate != nil {
            return (nil, nil, nil, nil, nil, nil)
        }
        if alarm.relativeOffset != 0 {
            return (nil, nil, nil, nil, nil, nil)
        }
        let proximity = alarmProximityName(alarm.proximity)
        guard !proximity.isEmpty,
              let location = structuredLocationPayload(alarm.structuredLocation, fallbackTitle: "")
        else {
            return (nil, nil, nil, nil, nil, nil)
        }
        return ([], [], "", proximity, location, "")
    }
    var offsets = Set<Int>()
    var absoluteDates = Set<String>()
    var soundName = ""
    var emailAddressSHA256 = ""
    var sawDisplayAlarm = false
    var sawAudioAlarm = false
    var sawEmailAlarm = false
    for alarm in alarms {
        if alarm.structuredLocation != nil || alarm.proximity != .none {
            return (nil, nil, nil, nil, nil, nil)
        }
        if alarm.type == .procedure {
            return (nil, nil, nil, nil, nil, nil)
        }
        let currentSoundName = alarm.soundName ?? ""
        let currentEmailAddress = (alarm.emailAddress ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if alarm.type == .email || !currentEmailAddress.isEmpty {
            if sawDisplayAlarm || sawAudioAlarm || !currentSoundName.isEmpty || !isValidAlarmEmailAddress(currentEmailAddress) {
                return (nil, nil, nil, nil, nil, nil)
            }
            sawEmailAlarm = true
            let currentEmailSHA256 = sha256Hex(currentEmailAddress)
            if emailAddressSHA256.isEmpty {
                emailAddressSHA256 = currentEmailSHA256
            } else if emailAddressSHA256 != currentEmailSHA256 {
                return (nil, nil, nil, nil, nil, nil)
            }
        } else if alarm.type == .audio {
            if sawDisplayAlarm || sawEmailAlarm || !isValidAlarmSoundName(currentSoundName) {
                return (nil, nil, nil, nil, nil, nil)
            }
            sawAudioAlarm = true
            if soundName.isEmpty {
                soundName = currentSoundName
            } else if soundName != currentSoundName {
                return (nil, nil, nil, nil, nil, nil)
            }
        } else {
            if sawAudioAlarm || sawEmailAlarm || !currentSoundName.isEmpty {
                return (nil, nil, nil, nil, nil, nil)
            }
            sawDisplayAlarm = true
        }
        if let absoluteDate = alarm.absoluteDate {
            if !offsets.isEmpty {
                return (nil, nil, nil, nil, nil, nil)
            }
            absoluteDates.insert(isoFormatter.string(from: absoluteDate))
            continue
        }
        if !absoluteDates.isEmpty {
            return (nil, nil, nil, nil, nil, nil)
        }
        let minuteValue = alarm.relativeOffset / 60.0
        if !minuteValue.isFinite || minuteValue.rounded() != minuteValue {
            return (nil, nil, nil, nil, nil, nil)
        }
        if minuteValue < Double(minAlarmOffsetMinutes) || minuteValue > Double(maxAlarmOffsetMinutes) {
            return (nil, nil, nil, nil, nil, nil)
        }
        let offset = Int(minuteValue)
        if offsets.contains(offset) {
            return (nil, nil, nil, nil, nil, nil)
        }
        offsets.insert(offset)
    }
    return (Array(offsets).sorted(), Array(absoluteDates).sorted(), soundName, "", nil, emailAddressSHA256)
}

func structuredLocationPayloadSafeSHA256(_ payload: [String: Any]?) -> String {
    guard let payload = payload,
          let title = payload["title"] as? String else {
        return ""
    }
    let geoPresent = (payload["geo_present"] as? Bool) ?? false
    var parts = [
        "title=\(title)",
        "geo_present=\(geoPresent ? "true" : "false")",
    ]
    if geoPresent,
       let latitude = doubleValue(payload["latitude"]),
       let longitude = doubleValue(payload["longitude"]),
       let radius = doubleValue(payload["radius_meters"]) {
        parts.append(String(format: "latitude=%.6f", latitude))
        parts.append(String(format: "longitude=%.6f", longitude))
        parts.append(String(format: "radius_meters=%.3f", radius))
    } else {
        parts.append("latitude=")
        parts.append("longitude=")
        parts.append("radius_meters=")
    }
    return sha256Hex(parts.joined(separator: "\n"))
}

func alarmStateSafeSHA256(_ event: EKEvent) -> String {
    guard event.alarms?.isEmpty == false else {
        return ""
    }
    let state = alarmState(event)
    guard let offsets = state.offsets,
          let absoluteDates = state.absoluteDates,
          let soundName = state.soundName,
          let proximity = state.proximity,
          let emailAddressSHA256 = state.emailAddressSHA256 else {
        return ""
    }
    let structuredLocationSHA256 = structuredLocationPayloadSafeSHA256(state.structuredLocation)
    let parts = [
        "offsets=\(offsets.map(String.init).joined(separator: ","))",
        "absolute_dates=\(absoluteDates.joined(separator: ","))",
        "sound_name=\(soundName)",
        "proximity=\(proximity)",
        "structured_location_sha256=\(structuredLocationSHA256)",
        "email_address_sha256=\(emailAddressSHA256)",
    ]
    return sha256Hex(parts.joined(separator: "\n"))
}

func applyAlarms(_ event: EKEvent, offsets: [Int], absoluteDates: [String], soundName: String, emailAddress: String, proximity: String, structuredLocation: [String: Any]?) {
    if !proximity.isEmpty {
        guard let alarmProximity = alarmProximityFromName(proximity),
              alarmProximity != .none,
              let structuredLocation = structuredLocation
        else {
            event.alarms = []
            return
        }
        let alarm = EKAlarm()
        alarm.proximity = alarmProximity
        alarm.structuredLocation = makeStructuredLocation(structuredLocation, fallbackLocation: "")
        event.alarms = [alarm]
        return
    }
    if !absoluteDates.isEmpty {
        event.alarms = absoluteDates.compactMap { value in
            guard let date = eventDate(from: value) else {
                return nil
            }
            let alarm = EKAlarm(absoluteDate: date)
            if !soundName.isEmpty {
                alarm.soundName = soundName
            } else if !emailAddress.isEmpty {
                alarm.emailAddress = emailAddress
            }
            return alarm
        }
        return
    }
    event.alarms = offsets.map {
        let alarm = EKAlarm(relativeOffset: TimeInterval($0) * 60.0)
        if !soundName.isEmpty {
            alarm.soundName = soundName
        } else if !emailAddress.isEmpty {
            alarm.emailAddress = emailAddress
        }
        return alarm
    }
}

func emptyRecurrencePayload() -> [String: Any] {
    return [
        "frequency": "",
        "interval": 0,
        "count": 0,
        "recurrence_present": false,
    ]
}

func recurrenceFrequencyName(_ frequency: EKRecurrenceFrequency) -> String? {
    switch frequency {
    case .daily:
        return "daily"
    case .weekly:
        return "weekly"
    case .monthly:
        return "monthly"
    case .yearly:
        return "yearly"
    default:
        return nil
    }
}

func recurrenceFrequency(_ name: String) -> EKRecurrenceFrequency? {
    switch name {
    case "daily":
        return .daily
    case "weekly":
        return .weekly
    case "monthly":
        return .monthly
    case "yearly":
        return .yearly
    default:
        return nil
    }
}

func recurrenceWeekdayName(_ rawValue: Int) -> String? {
    switch rawValue {
    case 1:
        return "sunday"
    case 2:
        return "monday"
    case 3:
        return "tuesday"
    case 4:
        return "wednesday"
    case 5:
        return "thursday"
    case 6:
        return "friday"
    case 7:
        return "saturday"
    default:
        return nil
    }
}

func recurrenceWeekdayRawValue(_ name: String) -> Int? {
    switch name.lowercased().replacingOccurrences(of: "-", with: "_") {
    case "1", "sun", "sunday":
        return 1
    case "2", "mon", "monday":
        return 2
    case "3", "tue", "tues", "tuesday":
        return 3
    case "4", "wed", "wednesday":
        return 4
    case "5", "thu", "thur", "thurs", "thursday":
        return 5
    case "6", "fri", "friday":
        return 6
    case "7", "sat", "saturday":
        return 7
    default:
        return nil
    }
}

func recurrenceWeekdaysPayload(_ rule: EKRecurrenceRule) -> [String]? {
    guard let days = rule.daysOfTheWeek else {
        return []
    }
    var values: Set<Int> = []
    for day in days {
        if day.weekNumber != 0 {
            return nil
        }
        let rawValue = day.dayOfTheWeek.rawValue
        guard rawValue >= 1, rawValue <= 7 else {
            return nil
        }
        values.insert(rawValue)
    }
    return values.sorted().compactMap { recurrenceWeekdayName($0) }
}

func recurrenceMonthDaysPayload(_ rule: EKRecurrenceRule) -> [Int]? {
    guard let days = rule.daysOfTheMonth else {
        return []
    }
    var values = Set<Int>()
    for day in days {
        let rawValue = day.intValue
        guard rawValue != 0, rawValue >= -31, rawValue <= 31 else {
            return nil
        }
        values.insert(rawValue)
    }
    return values.sorted()
}

func recurrenceMonthWeekdaysPayload(_ rule: EKRecurrenceRule) -> [[String: Any]]? {
    guard let days = rule.daysOfTheWeek else {
        return []
    }
    var normalized: [String: (weekday: String, rawValue: Int, weekNumber: Int)] = [:]
    for day in days {
        let rawValue = day.dayOfTheWeek.rawValue
        let weekNumber = day.weekNumber
        guard rawValue >= 1,
              rawValue <= 7,
              weekNumber != 0,
              weekNumber >= -5,
              weekNumber <= 5,
              let weekday = recurrenceWeekdayName(rawValue)
        else {
            return nil
        }
        normalized["\(weekNumber):\(weekday)"] = (weekday, rawValue, weekNumber)
    }
    return normalized.values.sorted {
        ($0.weekNumber, $0.rawValue) < ($1.weekNumber, $1.rawValue)
    }.map {
        ["weekday": $0.weekday, "week_number": $0.weekNumber]
    }
}

func recurrenceYearMonthsPayload(_ rule: EKRecurrenceRule) -> [Int]? {
    guard let months = rule.monthsOfTheYear else {
        return []
    }
    var values: Set<Int> = []
    for item in months {
        let value = item.intValue
        if value < 1 || value > 12 {
            return nil
        }
        values.insert(value)
    }
    return values.sorted()
}

func recurrenceYearDaysPayload(_ rule: EKRecurrenceRule) -> [Int]? {
    guard let days = rule.daysOfTheYear else {
        return []
    }
    var values: Set<Int> = []
    for item in days {
        let value = item.intValue
        if value == 0 || value < -366 || value > 366 {
            return nil
        }
        values.insert(value)
    }
    return values.sorted()
}

func recurrenceYearWeeksPayload(_ rule: EKRecurrenceRule) -> [Int]? {
    guard let weeks = rule.weeksOfTheYear else {
        return []
    }
    var values: Set<Int> = []
    for item in weeks {
        let value = item.intValue
        if value == 0 || value < -53 || value > 53 {
            return nil
        }
        values.insert(value)
    }
    return values.sorted()
}

func recurrenceSetPositionsPayload(_ rule: EKRecurrenceRule) -> [Int]? {
    guard let positions = rule.setPositions else {
        return []
    }
    var values: Set<Int> = []
    for item in positions {
        let value = item.intValue
        if value == 0 || value < -366 || value > 366 {
            return nil
        }
        values.insert(value)
    }
    return values.sorted()
}

func recurrencePayload(_ event: EKCalendarItem) -> [String: Any]? {
    guard let rules = event.recurrenceRules, !rules.isEmpty else {
        return emptyRecurrencePayload()
    }
    guard rules.count == 1,
          let rule = rules.first,
          let frequency = recurrenceFrequencyName(rule.frequency),
          rule.interval >= 1,
          rule.interval <= maxRecurrenceInterval,
          let rawMonthDays = recurrenceMonthDaysPayload(rule),
          let yearMonths = recurrenceYearMonthsPayload(rule),
          (yearMonths.isEmpty || rule.frequency == .yearly),
          let yearDays = recurrenceYearDaysPayload(rule),
          (yearDays.isEmpty || rule.frequency == .yearly),
          let yearWeeks = recurrenceYearWeeksPayload(rule),
          (yearWeeks.isEmpty || rule.frequency == .yearly),
          let setPositions = recurrenceSetPositionsPayload(rule)
    else {
        return nil
    }
    let yearlySelectorCount = [!yearMonths.isEmpty, !yearDays.isEmpty, !yearWeeks.isEmpty]
        .filter { $0 }
        .count
    if yearlySelectorCount > 1 {
        return nil
    }
    let recurrenceSelectorPresent = !(rule.daysOfTheWeek ?? []).isEmpty
        || !(rule.daysOfTheMonth ?? []).isEmpty
        || !yearMonths.isEmpty
        || !yearDays.isEmpty
        || !yearWeeks.isEmpty
    if !setPositions.isEmpty && !recurrenceSelectorPresent {
        return nil
    }
    let monthDays = rule.frequency == .monthly ? rawMonthDays : []
    let yearMonthDays = (rule.frequency == .yearly && !yearMonths.isEmpty) ? rawMonthDays : []
    if !rawMonthDays.isEmpty && monthDays.isEmpty && yearMonthDays.isEmpty {
        return nil
    }
    let recurrenceCount: Int
    let recurrenceEndDate: String
    let recurrenceUnbounded: Bool
    if let end = rule.recurrenceEnd {
        if end.occurrenceCount > 0 {
            guard end.occurrenceCount >= minRecurrenceCount,
                  end.occurrenceCount <= maxRecurrenceCount,
                  end.endDate == nil
            else {
                return nil
            }
            recurrenceCount = end.occurrenceCount
            recurrenceEndDate = ""
            recurrenceUnbounded = false
        } else {
            guard let endDate = end.endDate else {
                return nil
            }
            recurrenceCount = 0
            recurrenceEndDate = isoFormatter.string(from: endDate)
            recurrenceUnbounded = false
        }
    } else {
        recurrenceCount = 0
        recurrenceEndDate = ""
        recurrenceUnbounded = true
    }
    let weekdays: [String]
    let monthWeekdays: [[String: Any]]
    let yearMonthWeekdays: [[String: Any]]
    if rule.frequency == .weekly {
        guard let currentWeekdays = recurrenceWeekdaysPayload(rule) else {
            return nil
        }
        weekdays = currentWeekdays
        monthWeekdays = []
        yearMonthWeekdays = []
    } else if rule.frequency == .monthly {
        let rawWeekdayRules = rule.daysOfTheWeek ?? []
        if !monthDays.isEmpty && !rawWeekdayRules.isEmpty {
            return nil
        }
        if rawWeekdayRules.isEmpty {
            weekdays = []
            monthWeekdays = []
        } else if rawWeekdayRules.allSatisfy({ $0.weekNumber == 0 }) {
            guard let currentWeekdays = recurrenceWeekdaysPayload(rule) else {
                return nil
            }
            weekdays = currentWeekdays
            monthWeekdays = []
        } else if rawWeekdayRules.allSatisfy({ $0.weekNumber != 0 }) {
            guard let currentMonthWeekdays = recurrenceMonthWeekdaysPayload(rule) else {
                return nil
            }
            weekdays = []
            monthWeekdays = currentMonthWeekdays
        } else {
            return nil
        }
        yearMonthWeekdays = []
    } else if rule.frequency == .yearly && !yearMonths.isEmpty {
        guard let currentYearMonthWeekdays = recurrenceMonthWeekdaysPayload(rule) else {
            return nil
        }
        if !yearMonthDays.isEmpty && !currentYearMonthWeekdays.isEmpty {
            return nil
        }
        weekdays = []
        monthWeekdays = []
        yearMonthWeekdays = currentYearMonthWeekdays
    } else if rule.frequency == .yearly && !yearWeeks.isEmpty {
        guard let currentWeekdays = recurrenceWeekdaysPayload(rule),
              !currentWeekdays.isEmpty
        else {
            return nil
        }
        weekdays = currentWeekdays
        monthWeekdays = []
        yearMonthWeekdays = []
    } else {
        if let days = rule.daysOfTheWeek, !days.isEmpty {
            return nil
        }
        weekdays = []
        monthWeekdays = []
        yearMonthWeekdays = []
    }
    var payload: [String: Any] = [
        "frequency": frequency,
        "interval": rule.interval,
        "count": recurrenceCount,
        "recurrence_present": true,
    ]
    if !recurrenceEndDate.isEmpty {
        payload["end_date"] = recurrenceEndDate
    }
    if recurrenceUnbounded {
        payload["unbounded"] = true
    }
    if !weekdays.isEmpty {
        payload["weekdays"] = weekdays
    }
    if !monthDays.isEmpty {
        payload["month_days"] = monthDays
    }
    if !monthWeekdays.isEmpty {
        payload["month_weekdays"] = monthWeekdays
    }
    if !yearMonths.isEmpty {
        payload["year_months"] = yearMonths
    }
    if !yearMonthDays.isEmpty {
        payload["year_month_days"] = yearMonthDays
    }
    if !yearMonthWeekdays.isEmpty {
        payload["year_month_weekdays"] = yearMonthWeekdays
    }
    if !yearDays.isEmpty {
        payload["year_days"] = yearDays
    }
    if !yearWeeks.isEmpty {
        payload["year_weeks"] = yearWeeks
    }
    if !setPositions.isEmpty {
        payload["set_positions"] = setPositions
    }
    return payload
}

func recurrenceRequest(_ request: [String: Any], key: String = "recurrence") -> [String: Any]? {
    guard let value = request[key] else {
        return emptyRecurrencePayload()
    }
    guard let recurrence = value as? [String: Any] else {
        return nil
    }
    let frequency = (recurrence["frequency"] as? String) ?? ""
    let interval = optionalIntValue(recurrence, "interval") ?? 0
    let count = optionalIntValue(recurrence, "count") ?? 0
    let endDateValue = stringValue(recurrence, "end_date")
    let unbounded = boolValue(recurrence, "unbounded") ?? false
    let present = (recurrence["recurrence_present"] as? Bool) ?? false
    let weekdaysValue = recurrence["weekdays"]
    let weekdayStrings = weekdaysValue as? [String] ?? []
    guard let monthDays = monthDayArrayValue(recurrence, "month_days") else {
        return nil
    }
    guard let monthWeekdays = monthWeekdayArrayValue(recurrence, "month_weekdays") else {
        return nil
    }
    guard let yearMonths = yearMonthArrayValue(recurrence, "year_months") else {
        return nil
    }
    guard let yearMonthDays = monthDayArrayValue(recurrence, "year_month_days") else {
        return nil
    }
    guard let yearMonthWeekdays = monthWeekdayArrayValue(recurrence, "year_month_weekdays") else {
        return nil
    }
    guard let yearDays = yearDayArrayValue(recurrence, "year_days") else {
        return nil
    }
    guard let yearWeeks = yearWeekArrayValue(recurrence, "year_weeks") else {
        return nil
    }
    guard let setPositions = recurrenceSetPositionsArrayValue(recurrence, "set_positions") else {
        return nil
    }
    if !present && frequency.isEmpty && interval == 0 && count == 0 && endDateValue.isEmpty && !unbounded && weekdayStrings.isEmpty && monthDays.isEmpty && monthWeekdays.isEmpty && yearMonths.isEmpty && yearMonthDays.isEmpty && yearMonthWeekdays.isEmpty && yearDays.isEmpty && yearWeeks.isEmpty && setPositions.isEmpty {
        return emptyRecurrencePayload()
    }
    guard present,
          let recurrenceFrequencyValue = recurrenceFrequency(frequency),
          interval >= 1,
          interval <= maxRecurrenceInterval
    else {
        return nil
    }
    let countBound = count != 0
    let endDateBound = !endDateValue.isEmpty
    let unboundedBound = unbounded
    if [countBound, endDateBound, unboundedBound].filter({ $0 }).count != 1 {
        return nil
    }
    if countBound && (count < minRecurrenceCount || count > maxRecurrenceCount) {
        return nil
    }
    if endDateBound {
        guard !isDateOnlyString(endDateValue),
              eventDate(from: endDateValue) != nil
        else {
            return nil
        }
    }
    var weekdayRawValues: Set<Int> = []
    for value in weekdayStrings {
        guard let rawValue = recurrenceWeekdayRawValue(value) else {
            return nil
        }
        weekdayRawValues.insert(rawValue)
    }
    let monthlyWeekdaySelector = recurrenceFrequencyValue == .monthly && !weekdayRawValues.isEmpty
    let yearlyWeekWithWeekdays = recurrenceFrequencyValue == .yearly && !yearWeeks.isEmpty
    if !weekdayRawValues.isEmpty && !(recurrenceFrequencyValue == .weekly || monthlyWeekdaySelector || yearlyWeekWithWeekdays) {
        return nil
    }
    if !monthDays.isEmpty && recurrenceFrequencyValue != .monthly {
        return nil
    }
    if !monthWeekdays.isEmpty && recurrenceFrequencyValue != .monthly {
        return nil
    }
    if !monthDays.isEmpty && !monthWeekdays.isEmpty {
        return nil
    }
    if monthlyWeekdaySelector && (!monthDays.isEmpty || !monthWeekdays.isEmpty) {
        return nil
    }
    if !yearMonths.isEmpty && recurrenceFrequencyValue != .yearly {
        return nil
    }
    if !yearMonthDays.isEmpty && recurrenceFrequencyValue != .yearly {
        return nil
    }
    if !yearMonthDays.isEmpty && yearMonths.isEmpty {
        return nil
    }
    if !yearMonthWeekdays.isEmpty && recurrenceFrequencyValue != .yearly {
        return nil
    }
    if !yearMonthWeekdays.isEmpty && yearMonths.isEmpty {
        return nil
    }
    if !yearDays.isEmpty && recurrenceFrequencyValue != .yearly {
        return nil
    }
    if !yearWeeks.isEmpty && recurrenceFrequencyValue != .yearly {
        return nil
    }
    if !yearWeeks.isEmpty && weekdayRawValues.isEmpty {
        return nil
    }
    if !yearMonthDays.isEmpty && !yearMonthWeekdays.isEmpty {
        return nil
    }
    if !yearMonthDays.isEmpty && (!yearDays.isEmpty || !yearWeeks.isEmpty) {
        return nil
    }
    if !yearMonthWeekdays.isEmpty && (!yearDays.isEmpty || !yearWeeks.isEmpty) {
        return nil
    }
    let yearlySelectorCount = [!yearMonths.isEmpty, !yearDays.isEmpty, !yearWeeks.isEmpty]
        .filter { $0 }
        .count
    if yearlySelectorCount > 1 {
        return nil
    }
    let selectorPresent = !weekdayRawValues.isEmpty || !monthDays.isEmpty || !monthWeekdays.isEmpty || !yearMonths.isEmpty || !yearMonthDays.isEmpty || !yearMonthWeekdays.isEmpty || !yearDays.isEmpty || !yearWeeks.isEmpty
    if !setPositions.isEmpty && !selectorPresent {
        return nil
    }
    var payload: [String: Any] = [
        "frequency": frequency,
        "interval": interval,
        "count": count,
        "recurrence_present": true,
    ]
    if !endDateValue.isEmpty {
        payload["end_date"] = endDateValue
    }
    if unbounded {
        payload["unbounded"] = true
    }
    if !weekdayRawValues.isEmpty {
        payload["weekdays"] = weekdayRawValues.sorted().compactMap { recurrenceWeekdayName($0) }
    }
    if !monthDays.isEmpty {
        payload["month_days"] = monthDays
    }
    if !monthWeekdays.isEmpty {
        payload["month_weekdays"] = monthWeekdays
    }
    if !yearMonths.isEmpty {
        payload["year_months"] = yearMonths
    }
    if !yearMonthDays.isEmpty {
        payload["year_month_days"] = yearMonthDays
    }
    if !yearMonthWeekdays.isEmpty {
        payload["year_month_weekdays"] = yearMonthWeekdays
    }
    if !yearDays.isEmpty {
        payload["year_days"] = yearDays
    }
    if !yearWeeks.isEmpty {
        payload["year_weeks"] = yearWeeks
    }
    if !setPositions.isEmpty {
        payload["set_positions"] = setPositions
    }
    return payload
}

func applyRecurrence(_ event: EKCalendarItem, recurrence: [String: Any]) {
    guard (recurrence["recurrence_present"] as? Bool) == true,
          let frequencyName = recurrence["frequency"] as? String,
          let frequency = recurrenceFrequency(frequencyName),
          let interval = recurrence["interval"] as? Int,
          let count = recurrence["count"] as? Int
    else {
        event.recurrenceRules = nil
        return
    }
    let endDateValue = stringValue(recurrence, "end_date")
    let end: EKRecurrenceEnd?
    if !endDateValue.isEmpty {
        guard !isDateOnlyString(endDateValue),
              let endDate = eventDate(from: endDateValue)
        else {
            event.recurrenceRules = nil
            return
        }
        end = EKRecurrenceEnd(end: endDate)
    } else if (recurrence["unbounded"] as? Bool) == true {
        end = nil
    } else {
        end = EKRecurrenceEnd(occurrenceCount: count)
    }
    let weekdays = (recurrence["weekdays"] as? [String] ?? []).compactMap {
        recurrenceWeekdayRawValue($0).flatMap { EKWeekday(rawValue: $0) }
    }.map { EKRecurrenceDayOfWeek($0) }
    let monthDays = recurrence["month_days"] as? [Int] ?? []
    guard let monthWeekdayValues = monthWeekdayArrayValue(recurrence, "month_weekdays") else {
        event.recurrenceRules = nil
        return
    }
    guard let yearMonths = yearMonthArrayValue(recurrence, "year_months") else {
        event.recurrenceRules = nil
        return
    }
    guard let yearMonthDays = monthDayArrayValue(recurrence, "year_month_days") else {
        event.recurrenceRules = nil
        return
    }
    guard let yearMonthWeekdayValues = monthWeekdayArrayValue(recurrence, "year_month_weekdays") else {
        event.recurrenceRules = nil
        return
    }
    guard let yearDays = yearDayArrayValue(recurrence, "year_days") else {
        event.recurrenceRules = nil
        return
    }
    guard let yearWeeks = yearWeekArrayValue(recurrence, "year_weeks") else {
        event.recurrenceRules = nil
        return
    }
    guard let setPositions = recurrenceSetPositionsArrayValue(recurrence, "set_positions") else {
        event.recurrenceRules = nil
        return
    }
    let recurrenceSetPositions = setPositions.isEmpty ? nil : setPositions.map { NSNumber(value: $0) }
    if !weekdays.isEmpty && frequency == .weekly {
        event.recurrenceRules = [
            EKRecurrenceRule(
                recurrenceWith: frequency,
                interval: interval,
                daysOfTheWeek: weekdays,
                daysOfTheMonth: nil,
                monthsOfTheYear: nil,
                weeksOfTheYear: nil,
                daysOfTheYear: nil,
                setPositions: recurrenceSetPositions,
                end: end
            )
        ]
        return
    }
    if !weekdays.isEmpty && frequency == .monthly {
        event.recurrenceRules = [
            EKRecurrenceRule(
                recurrenceWith: frequency,
                interval: interval,
                daysOfTheWeek: weekdays,
                daysOfTheMonth: nil,
                monthsOfTheYear: nil,
                weeksOfTheYear: nil,
                daysOfTheYear: nil,
                setPositions: recurrenceSetPositions,
                end: end
            )
        ]
        return
    }
    if !monthDays.isEmpty && frequency == .monthly {
        event.recurrenceRules = [
            EKRecurrenceRule(
                recurrenceWith: frequency,
                interval: interval,
                daysOfTheWeek: nil,
                daysOfTheMonth: monthDays.map { NSNumber(value: $0) },
                monthsOfTheYear: nil,
                weeksOfTheYear: nil,
                daysOfTheYear: nil,
                setPositions: recurrenceSetPositions,
                end: end
            )
        ]
        return
    }
    if !monthWeekdayValues.isEmpty && frequency == .monthly {
        let monthWeekdays = monthWeekdayValues.compactMap { item -> EKRecurrenceDayOfWeek? in
            guard let weekday = item["weekday"] as? String,
                  let rawValue = recurrenceWeekdayRawValue(weekday),
                  let weekDay = EKWeekday(rawValue: rawValue),
                  let weekNumber = item["week_number"] as? Int
            else {
                return nil
            }
            return EKRecurrenceDayOfWeek(weekDay, weekNumber: weekNumber)
        }
        guard monthWeekdays.count == monthWeekdayValues.count else {
            event.recurrenceRules = nil
            return
        }
        event.recurrenceRules = [
            EKRecurrenceRule(
                recurrenceWith: frequency,
                interval: interval,
                daysOfTheWeek: monthWeekdays,
                daysOfTheMonth: nil,
                monthsOfTheYear: nil,
                weeksOfTheYear: nil,
                daysOfTheYear: nil,
                setPositions: recurrenceSetPositions,
                end: end
            )
        ]
        return
    }
    if !yearMonths.isEmpty && frequency == .yearly {
        guard yearMonthDays.isEmpty || yearMonthWeekdayValues.isEmpty else {
            event.recurrenceRules = nil
            return
        }
        let yearMonthWeekdays = yearMonthWeekdayValues.compactMap { item -> EKRecurrenceDayOfWeek? in
            guard let weekday = item["weekday"] as? String,
                  let rawValue = recurrenceWeekdayRawValue(weekday),
                  let weekDay = EKWeekday(rawValue: rawValue),
                  let weekNumber = item["week_number"] as? Int
            else {
                return nil
            }
            return EKRecurrenceDayOfWeek(weekDay, weekNumber: weekNumber)
        }
        guard yearMonthWeekdays.count == yearMonthWeekdayValues.count else {
            event.recurrenceRules = nil
            return
        }
        event.recurrenceRules = [
            EKRecurrenceRule(
                recurrenceWith: frequency,
                interval: interval,
                daysOfTheWeek: yearMonthWeekdays.isEmpty ? nil : yearMonthWeekdays,
                daysOfTheMonth: yearMonthDays.isEmpty ? nil : yearMonthDays.map { NSNumber(value: $0) },
                monthsOfTheYear: yearMonths.map { NSNumber(value: $0) },
                weeksOfTheYear: nil,
                daysOfTheYear: nil,
                setPositions: recurrenceSetPositions,
                end: end
            )
        ]
        return
    }
    if !yearDays.isEmpty && frequency == .yearly {
        event.recurrenceRules = [
            EKRecurrenceRule(
                recurrenceWith: frequency,
                interval: interval,
                daysOfTheWeek: nil,
                daysOfTheMonth: nil,
                monthsOfTheYear: nil,
                weeksOfTheYear: nil,
                daysOfTheYear: yearDays.map { NSNumber(value: $0) },
                setPositions: recurrenceSetPositions,
                end: end
            )
        ]
        return
    }
    if !yearWeeks.isEmpty && frequency == .yearly && !weekdays.isEmpty {
        event.recurrenceRules = [
            EKRecurrenceRule(
                recurrenceWith: frequency,
                interval: interval,
                daysOfTheWeek: weekdays,
                daysOfTheMonth: nil,
                monthsOfTheYear: nil,
                weeksOfTheYear: yearWeeks.map { NSNumber(value: $0) },
                daysOfTheYear: nil,
                setPositions: recurrenceSetPositions,
                end: end
            )
        ]
        return
    }
    event.recurrenceRules = [
        EKRecurrenceRule(recurrenceWith: frequency, interval: interval, end: end)
    ]
}

func recurrenceMatches(_ event: EKCalendarItem, _ recurrence: [String: Any]) -> Bool {
    guard let current = recurrencePayload(event) else {
        return false
    }
    guard let currentMonthWeekdays = monthWeekdayComparisonKeys(current, "month_weekdays"),
          let expectedMonthWeekdays = monthWeekdayComparisonKeys(recurrence, "month_weekdays"),
          let currentYearMonthWeekdays = monthWeekdayComparisonKeys(current, "year_month_weekdays"),
          let expectedYearMonthWeekdays = monthWeekdayComparisonKeys(recurrence, "year_month_weekdays")
    else {
        return false
    }
    return (current["recurrence_present"] as? Bool) == (recurrence["recurrence_present"] as? Bool)
        && (current["frequency"] as? String) == (recurrence["frequency"] as? String)
        && (current["interval"] as? Int) == (recurrence["interval"] as? Int)
        && (current["count"] as? Int) == (recurrence["count"] as? Int)
        && ((current["end_date"] as? String) ?? "") == ((recurrence["end_date"] as? String) ?? "")
        && ((current["unbounded"] as? Bool) ?? false) == ((recurrence["unbounded"] as? Bool) ?? false)
        && ((current["weekdays"] as? [String]) ?? []) == ((recurrence["weekdays"] as? [String]) ?? [])
        && ((current["month_days"] as? [Int]) ?? []) == ((recurrence["month_days"] as? [Int]) ?? [])
        && currentMonthWeekdays == expectedMonthWeekdays
        && ((current["year_months"] as? [Int]) ?? []) == ((recurrence["year_months"] as? [Int]) ?? [])
        && ((current["year_month_days"] as? [Int]) ?? []) == ((recurrence["year_month_days"] as? [Int]) ?? [])
        && currentYearMonthWeekdays == expectedYearMonthWeekdays
        && ((current["year_days"] as? [Int]) ?? []) == ((recurrence["year_days"] as? [Int]) ?? [])
        && ((current["year_weeks"] as? [Int]) ?? []) == ((recurrence["year_weeks"] as? [Int]) ?? [])
        && ((current["set_positions"] as? [Int]) ?? []) == ((recurrence["set_positions"] as? [Int]) ?? [])
}

func availabilityName(_ availability: EKEventAvailability) -> String {
    switch availability {
    case .notSupported:
        return "not_supported"
    case .busy:
        return "busy"
    case .free:
        return "free"
    case .tentative:
        return "tentative"
    case .unavailable:
        return "unavailable"
    @unknown default:
        return "unknown"
    }
}

func availabilityFromRawValue(_ value: Int, allowNotSupported: Bool) -> EKEventAvailability? {
    switch value {
    case -1 where allowNotSupported:
        return .notSupported
    case 0:
        return .busy
    case 1:
        return .free
    case 2:
        return .tentative
    case 3:
        return .unavailable
    default:
        return nil
    }
}

func availabilityRequest(_ request: [String: Any], _ key: String, allowNotSupported: Bool) -> EKEventAvailability? {
    guard request[key] != nil else {
        return nil
    }
    guard let value = optionalIntValue(request, key),
          let availability = availabilityFromRawValue(value, allowNotSupported: allowNotSupported)
    else {
        emitCalendarApplyError("error", "invalid_availability", "Calendar availability must be busy, free, tentative, unavailable, or an approved expected not_supported value.")
    }
    return availability
}

func calendarSupportsAvailability(_ calendar: EKCalendar, _ availability: EKEventAvailability) -> Bool {
    switch availability {
    case .busy:
        return calendar.supportedEventAvailabilities.contains(.busy)
    case .free:
        return calendar.supportedEventAvailabilities.contains(.free)
    case .tentative:
        return calendar.supportedEventAvailabilities.contains(.tentative)
    case .unavailable:
        return calendar.supportedEventAvailabilities.contains(.unavailable)
    default:
        return false
    }
}

func availabilityMatches(_ event: EKEvent, _ expectedAvailability: EKEventAvailability?) -> Bool {
    guard let expectedAvailability = expectedAvailability else {
        return true
    }
    return event.availability.rawValue == expectedAvailability.rawValue
}

func eventTimeZoneIdentifier(_ event: EKEvent) -> String {
    return event.timeZone?.identifier ?? ""
}

func timeZoneOrError(_ identifier: String, _ field: String) -> TimeZone? {
    if identifier.isEmpty {
        return nil
    }
    guard let zone = TimeZone(identifier: identifier) else {
        emitCalendarApplyError("error", "invalid_time_zone", "Calendar \(field) must be an IANA time zone identifier.")
    }
    return zone
}

func eventPayload(
    _ event: EKEvent,
    includeContent: Bool,
    includeAlarmOffsets: Bool = false,
    includeTimeZone: Bool = false,
    includeURLProof: Bool = false,
    includeStructuredLocation: Bool = false,
    includeLocationProof: Bool = false,
    includeStructuredLocationProof: Bool = false,
    includeAlarmProof: Bool = false,
    includeParticipants: Bool = false
) -> [String: Any]? {
    guard let eventId = event.eventIdentifier else {
        return nil
    }
    var payload: [String: Any] = [
        "event_id": eventId,
        "title": event.title ?? "",
        "calendar_id": event.calendar?.calendarIdentifier ?? "",
        "calendar_title": event.calendar?.title ?? "",
        "start_date": eventDateString(from: event.startDate, allDay: event.isAllDay),
        "end_date": eventDateString(from: event.endDate, allDay: event.isAllDay),
        "all_day": event.isAllDay,
        "availability": event.availability.rawValue,
        "availability_name": availabilityName(event.availability),
        "location_present": !(event.location ?? "").isEmpty,
        "notes_present": !(event.notes ?? "").isEmpty,
        "url_present": event.url != nil,
        "alarms_count": event.alarms?.count ?? 0,
        "attendees_count": event.attendees?.count ?? 0,
        "recurrence_present": event.recurrenceRules?.isEmpty == false,
    ]
    if let recurrence = recurrencePayload(event) {
        payload["recurrence"] = recurrence
    }
    if includeContent {
        payload["location"] = event.location ?? ""
        payload["notes"] = event.notes ?? ""
    }
    if includeURLProof, let urlString = event.url?.absoluteString, !urlString.isEmpty {
        payload["event_url_safe_sha256"] = sha256Hex(urlString)
    }
    if includeLocationProof, let location = event.location, !location.isEmpty {
        payload["location_safe_sha256"] = sha256Hex(location)
    }
    if includeStructuredLocation {
        if let structuredLocation = structuredLocationPayload(event) {
            payload["structured_location"] = structuredLocation
            payload["structured_location_present"] = true
        } else {
            payload["structured_location_present"] = false
        }
    }
    if includeStructuredLocationProof {
        let structuredLocationSHA256 = structuredLocationSafeSHA256(event)
        payload["structured_location_present"] = !structuredLocationSHA256.isEmpty
        if !structuredLocationSHA256.isEmpty {
            payload["structured_location_safe_sha256"] = structuredLocationSHA256
        }
    }
    if includeAlarmProof {
        let alarmStateSHA256 = alarmStateSafeSHA256(event)
        payload["alarm_state_present"] = event.alarms?.isEmpty == false
        if !alarmStateSHA256.isEmpty {
            payload["alarm_state_safe_sha256"] = alarmStateSHA256
        }
    }
    if includeTimeZone {
        payload["time_zone"] = eventTimeZoneIdentifier(event)
    }
    if includeAlarmOffsets {
        let state = alarmState(event)
        if let offsets = state.offsets,
           let absoluteDates = state.absoluteDates,
           let soundName = state.soundName,
           let proximity = state.proximity,
           let emailAddressSHA256 = state.emailAddressSHA256 {
            if !proximity.isEmpty {
                payload["alarm_proximity"] = proximity
                if let alarmStructuredLocation = state.structuredLocation {
                    payload["alarm_structured_location"] = alarmStructuredLocation
                }
            } else if absoluteDates.isEmpty {
                payload["alarm_offsets_minutes"] = offsets
            } else if offsets.isEmpty {
                payload["alarm_absolute_dates"] = absoluteDates
            }
            payload["alarm_sound_name"] = soundName
            if !emailAddressSHA256.isEmpty {
                payload["alarm_email_address_sha256"] = emailAddressSHA256
            }
            payload["alarm_action"] = !proximity.isEmpty ? "geofence" : (!emailAddressSHA256.isEmpty ? "email" : (soundName.isEmpty ? "display" : "audio"))
        }
    }
    if includeParticipants {
        payload["participants"] = eventParticipantsPayload(event)
    }
    return payload
}

func eventParticipantsPayload(_ event: EKEvent) -> [[String: Any]] {
    var payloads: [[String: Any]] = []
    let organizerURL = event.organizer?.url.absoluteString ?? ""
    let organizerName = event.organizer?.name ?? ""
    var organizerIncluded = false

    for participant in event.attendees ?? [] {
        let isOrganizer = participant.url.absoluteString == organizerURL
            && (participant.name ?? "") == organizerName
            && !organizerURL.isEmpty
        if isOrganizer {
            organizerIncluded = true
        }
        payloads.append(participantPayload(
            participant,
            index: payloads.count,
            kind: isOrganizer ? "attendee_organizer" : "attendee",
            organizer: isOrganizer
        ))
    }

    if let organizer = event.organizer, !organizerIncluded {
        payloads.append(participantPayload(
            organizer,
            index: payloads.count,
            kind: "organizer",
            organizer: true
        ))
    }
    return payloads
}

func eventParticipantContainerPayload(_ event: EKEvent) -> [String: Any]? {
    guard let eventId = event.eventIdentifier else {
        return nil
    }
    return [
        "event_id": eventId,
        "start_date": eventDateString(from: event.startDate, allDay: event.isAllDay),
        "end_date": eventDateString(from: event.endDate, allDay: event.isAllDay),
        "participants": eventParticipantsPayload(event),
    ]
}

func participantPayload(
    _ participant: EKParticipant,
    index: Int,
    kind: String,
    organizer: Bool
) -> [String: Any] {
    return [
        "index": index,
        "participant_kind": kind,
        "organizer": organizer,
        "name": participant.name ?? "",
        "url": participant.url.absoluteString,
        "participant_status": participant.participantStatus.rawValue,
        "participant_status_name": participantStatusName(participant.participantStatus),
        "participant_role": participant.participantRole.rawValue,
        "participant_role_name": participantRoleName(participant.participantRole),
        "participant_type": participant.participantType.rawValue,
        "participant_type_name": participantTypeName(participant.participantType),
        "current_user": participant.isCurrentUser,
    ]
}

func participantStatusName(_ status: EKParticipantStatus) -> String {
    switch status {
    case .pending:
        return "pending"
    case .accepted:
        return "accepted"
    case .declined:
        return "declined"
    case .tentative:
        return "tentative"
    case .delegated:
        return "delegated"
    case .completed:
        return "completed"
    case .inProcess:
        return "in_process"
    default:
        return "unknown"
    }
}

func participantRoleName(_ role: EKParticipantRole) -> String {
    switch role {
    case .required:
        return "required"
    case .optional:
        return "optional"
    case .chair:
        return "chair"
    case .nonParticipant:
        return "non_participant"
    default:
        return "unknown"
    }
}

func participantTypeName(_ type: EKParticipantType) -> String {
    switch type {
    case .person:
        return "person"
    case .room:
        return "room"
    case .resource:
        return "resource"
    case .group:
        return "group"
    default:
        return "unknown"
    }
}

func reminderDateString(_ components: DateComponents?) -> String {
    guard let components = components,
          let date = Calendar.current.date(from: components)
    else {
        return ""
    }
    return isoFormatter.string(from: date)
}

func reminderAlarmStateSafeSHA256(_ reminder: EKReminder) -> String {
    let alarms = reminder.alarms ?? []
    guard !alarms.isEmpty else {
        return ""
    }
    let parts = alarms.enumerated().map { index, alarm -> String in
        let structuredLocationSHA256 = structuredLocationPayloadSafeSHA256(
            structuredLocationPayload(alarm.structuredLocation, fallbackTitle: "")
        )
        return [
            "index=\(index)",
            "type=\(alarmTypeName(alarm.type))",
            "absolute_date=\(alarm.absoluteDate.map { isoFormatter.string(from: $0) } ?? "")",
            "relative_offset=\(String(format: "%.3f", alarm.relativeOffset))",
            "sound_name_sha256=\((alarm.soundName ?? "").isEmpty ? "" : sha256Hex(alarm.soundName ?? ""))",
            "email_address_sha256=\((alarm.emailAddress ?? "").isEmpty ? "" : sha256Hex((alarm.emailAddress ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()))",
            "proximity=\(alarmProximityName(alarm.proximity))",
            "structured_location_sha256=\(structuredLocationSHA256)",
        ].joined(separator: "\n")
    }
    return sha256Hex(parts.joined(separator: "\n---\n"))
}

func reminderAbsoluteAlarmDates(_ reminder: EKReminder) -> [String]? {
    let alarms = reminder.alarms ?? []
    if alarms.count > maxAlarmOffsets {
        return nil
    }
    var dates = Set<String>()
    for alarm in alarms {
        if alarm.type != .display
            || alarm.structuredLocation != nil
            || alarm.proximity != .none
            || !(alarm.soundName ?? "").isEmpty
            || !(alarm.emailAddress ?? "").isEmpty {
            return nil
        }
        guard let absoluteDate = alarm.absoluteDate else {
            return nil
        }
        dates.insert(isoFormatter.string(from: absoluteDate))
    }
    return Array(dates).sorted()
}

func reminderRelativeAlarmOffsets(_ reminder: EKReminder) -> [Int]? {
    let alarms = reminder.alarms ?? []
    if alarms.count > maxAlarmOffsets {
        return nil
    }
    var offsets = Set<Int>()
    for alarm in alarms {
        if alarm.type != .display
            || alarm.absoluteDate != nil
            || alarm.structuredLocation != nil
            || alarm.proximity != .none
            || !(alarm.soundName ?? "").isEmpty
            || !(alarm.emailAddress ?? "").isEmpty {
            return nil
        }
        let minuteValue = alarm.relativeOffset / 60.0
        if !minuteValue.isFinite || minuteValue.rounded() != minuteValue {
            return nil
        }
        if minuteValue < Double(minAlarmOffsetMinutes) || minuteValue > Double(maxAlarmOffsetMinutes) {
            return nil
        }
        offsets.insert(Int(minuteValue))
    }
    return Array(offsets).sorted()
}

func reminderMixedDisplayAlarmState(_ reminder: EKReminder) -> (offsets: [Int], absoluteDates: [String])? {
    let alarms = reminder.alarms ?? []
    if alarms.count > maxAlarmOffsets {
        return nil
    }
    var offsets = Set<Int>()
    var dates = Set<String>()
    for alarm in alarms {
        if alarm.type != .display
            || alarm.structuredLocation != nil
            || alarm.proximity != .none
            || !(alarm.soundName ?? "").isEmpty
            || !(alarm.emailAddress ?? "").isEmpty {
            return nil
        }
        if let absoluteDate = alarm.absoluteDate {
            dates.insert(isoFormatter.string(from: absoluteDate))
            continue
        }
        let minuteValue = alarm.relativeOffset / 60.0
        if !minuteValue.isFinite || minuteValue.rounded() != minuteValue {
            return nil
        }
        if minuteValue < Double(minAlarmOffsetMinutes) || minuteValue > Double(maxAlarmOffsetMinutes) {
            return nil
        }
        offsets.insert(Int(minuteValue))
    }
    return (Array(offsets).sorted(), Array(dates).sorted())
}

func reminderDisplayAlarmStateSupported(_ reminder: EKReminder) -> Bool {
    return reminderMixedDisplayAlarmState(reminder) != nil
}

func reminderPayload(
    _ reminder: EKReminder,
    includeContent: Bool,
    includeURLProof: Bool = false,
    includeAlarmProof: Bool = false,
    includeAlarmDates: Bool = false,
    includeAlarmOffsets: Bool = false,
    includeRecurrenceProof: Bool = false
) -> [String: Any] {
    let reminderURLString = reminder.url?.absoluteString ?? ""
    var payload: [String: Any] = [
        "reminder_id": reminder.calendarItemIdentifier,
        "title": reminder.title ?? "",
        "list_id": reminder.calendar.calendarIdentifier,
        "list_name": reminder.calendar.title,
        "due_date": reminderDateString(reminder.dueDateComponents),
        "start_date": reminderDateString(reminder.startDateComponents),
        "completed": reminder.isCompleted,
        "priority": reminder.priority,
        "notes_present": !(reminder.notes ?? "").isEmpty,
        "url_present": !reminderURLString.isEmpty,
        "alarms_count": reminder.alarms?.count ?? 0,
    ]
    if includeRecurrenceProof {
        payload["recurrence_present"] = reminder.recurrenceRules?.isEmpty == false
        payload["recurrence"] = recurrencePayload(reminder) ?? emptyRecurrencePayload()
    }
    if !reminderURLString.isEmpty && (includeContent || includeURLProof) {
        payload["url_safe_sha256"] = sha256Hex(reminderURLString)
    }
    if includeContent || includeAlarmProof {
        payload["alarms_safe_sha256"] = reminderAlarmStateSafeSHA256(reminder)
    }
    if includeAlarmDates && includeAlarmOffsets {
        if let mixedState = reminderMixedDisplayAlarmState(reminder) {
            payload["alarm_absolute_dates"] = mixedState.absoluteDates
            payload["alarm_offsets_minutes"] = mixedState.offsets
        }
    } else {
        if includeAlarmDates, let absoluteDates = reminderAbsoluteAlarmDates(reminder) {
            payload["alarm_absolute_dates"] = absoluteDates
        }
        if includeAlarmOffsets, let offsets = reminderRelativeAlarmOffsets(reminder) {
            payload["alarm_offsets_minutes"] = offsets
        }
    }
    if includeContent {
        payload["notes"] = reminder.notes ?? ""
    }
    return payload
}

// EventKit has no public sharing API for calendars/lists. Detection probes
// private-but-stable EKCalendar accessors via responds(to:)-guarded KVC and
// emits only a boolean plus a sharee count — never sharee identities. When no
// probe responds (future macOS removing the accessors), the keys are omitted
// so callers report sharing state as unknown instead of a false negative.
func calendarSharingState(_ list: EKCalendar) -> (isShared: Bool, shareeCount: Int)? {
    var probeResponded = false
    var shared = false
    var shareeCount = 0
    if list.responds(to: NSSelectorFromString("sharees")) {
        probeResponded = true
        if let sharees = list.value(forKey: "sharees") as? [Any] {
            shareeCount = sharees.count
            shared = shared || !sharees.isEmpty
        }
    }
    if list.responds(to: NSSelectorFromString("sharingStatus")) {
        probeResponded = true
        if let status = list.value(forKey: "sharingStatus") as? Int {
            shared = shared || status != 0
        }
    }
    if list.responds(to: NSSelectorFromString("sharedOwnerName")) {
        probeResponded = true
        if let ownerName = list.value(forKey: "sharedOwnerName") as? String {
            shared = shared || !ownerName.isEmpty
        }
    }
    if !probeResponded {
        return nil
    }
    return (isShared: shared, shareeCount: shareeCount)
}

func reminderListPayload(_ list: EKCalendar, reminders: [EKReminder]? = nil) -> [String: Any] {
    var payload: [String: Any] = [
        "list_id": list.calendarIdentifier,
        "title": list.title,
        "allows_content_modifications": list.allowsContentModifications,
        "is_subscribed": list.isSubscribed,
        "is_immutable": list.isImmutable,
        "calendar_type": calendarTypeName(list.type),
        "source_id": list.source.sourceIdentifier,
        "source_type": sourceTypeName(list.source.sourceType),
        "allowed_entity_types": entityTypeNames(list.allowedEntityTypes),
    ]
    if let sharing = calendarSharingState(list) {
        payload["is_shared"] = sharing.isShared
        // sharees is often empty even for shared lists (e.g. subscriber side);
        // emit the count only when it is a real positive signal.
        if sharing.shareeCount > 0 {
            payload["sharee_count"] = sharing.shareeCount
        }
    }
    if let reminders = reminders {
        payload["reminder_count"] = reminders.filter {
            $0.calendar.calendarIdentifier == list.calendarIdentifier
        }.count
    }
    return payload
}

func calendarTypeName(_ value: EKCalendarType) -> String {
    switch value {
    case .local:
        return "local"
    case .calDAV:
        return "caldav"
    case .exchange:
        return "exchange"
    case .subscription:
        return "subscription"
    case .birthday:
        return "birthday"
    @unknown default:
        return "unknown"
    }
}

func sourceTypeName(_ value: EKSourceType) -> String {
    switch value {
    case .local:
        return "local"
    case .exchange:
        return "exchange"
    case .calDAV:
        return "caldav"
    case .mobileMe:
        return "mobileme"
    case .subscribed:
        return "subscribed"
    case .birthdays:
        return "birthdays"
    @unknown default:
        return "unknown"
    }
}

func availabilityNames(_ mask: EKCalendarEventAvailabilityMask) -> [String] {
    var names: [String] = []
    if mask.contains(.busy) {
        names.append("busy")
    }
    if mask.contains(.free) {
        names.append("free")
    }
    if mask.contains(.tentative) {
        names.append("tentative")
    }
    if mask.contains(.unavailable) {
        names.append("unavailable")
    }
    return names
}

func entityTypeNames(_ mask: EKEntityMask) -> [String] {
    var names: [String] = []
    if mask.contains(.event) {
        names.append("event")
    }
    if mask.contains(.reminder) {
        names.append("reminder")
    }
    return names
}

func calendarEventCount(_ store: EKEventStore, _ calendar: EKCalendar) -> Int {
    let predicate = store.predicateForEvents(
        withStart: calendarSafetyWindowStart,
        end: calendarSafetyWindowEnd,
        calendars: [calendar]
    )
    return store.events(matching: predicate).count
}

func calendarPayload(_ calendar: EKCalendar, defaultCalendarId: String?, includeSafetyCounts: Bool = false, store: EKEventStore? = nil) -> [String: Any] {
    var payload: [String: Any] = [
        "calendar_id": calendar.calendarIdentifier,
        "title": calendar.title,
        "is_default_calendar": calendar.calendarIdentifier == defaultCalendarId,
        "allows_content_modifications": calendar.allowsContentModifications,
        "is_subscribed": calendar.isSubscribed,
        "is_immutable": calendar.isImmutable,
        "calendar_type": calendarTypeName(calendar.type),
        "source_id": calendar.source.sourceIdentifier,
        "source_type": sourceTypeName(calendar.source.sourceType),
        "allowed_entity_types": entityTypeNames(calendar.allowedEntityTypes),
        "supported_event_availabilities": availabilityNames(calendar.supportedEventAvailabilities),
    ]
    if includeSafetyCounts, let store = store {
        payload["event_count_in_safety_window"] = calendarEventCount(store, calendar)
        payload["safety_window_start"] = dateOnlyString(from: calendarSafetyWindowStart)
        payload["safety_window_end"] = dateOnlyString(from: calendarSafetyWindowEnd)
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

let input: Data
if let inputJSONFilePath {
    input = (try? Data(contentsOf: URL(fileURLWithPath: inputJSONFilePath))) ?? Data()
} else {
    input = FileHandle.standardInput.readDataToEndOfFile()
}
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

func fetchReminders(_ store: EKEventStore, calendars: [EKCalendar]? = nil) -> [EKReminder]? {
    let predicate = store.predicateForReminders(in: calendars)
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

func eventDate(from value: String) -> Date? {
    if value.isEmpty {
        return nil
    }
    let dateOnlyPattern = #"^\d{4}-\d{2}-\d{2}$"#
    if value.range(of: dateOnlyPattern, options: .regularExpression) != nil {
        let parts = value.split(separator: "-").compactMap { Int($0) }
        guard parts.count == 3 else {
            return nil
        }
        let calendar = Calendar.current
        guard let date = calendar.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2])) else {
            return nil
        }
        let roundTrip = calendar.dateComponents([.year, .month, .day], from: date)
        guard roundTrip.year == parts[0],
              roundTrip.month == parts[1],
              roundTrip.day == parts[2]
        else {
            return nil
        }
        return date
    }
    let parser = ISO8601DateFormatter()
    parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    var parsed = parser.date(from: value)
    if parsed == nil {
        parser.formatOptions = [.withInternetDateTime]
        parsed = parser.date(from: value)
    }
    return parsed
}

func eventDatesMatch(_ left: Date, _ right: Date) -> Bool {
    return abs(left.timeIntervalSince(right)) < 1
}

func eventSlotMatches(_ leftStart: Date, _ leftEnd: Date, _ rightStart: Date, _ rightEnd: Date) -> Bool {
    return eventDatesMatch(leftStart, rightStart) && eventDatesMatch(leftEnd, rightEnd)
}

func dayShiftedReadBackDate(
    _ futureDate: Date,
    expectedSelectedDate: Date,
    proposedSelectedDate: Date,
    calendar: Calendar
) -> Date {
    // Calendar-day arithmetic for all-day set/clear/date-only reschedule
    // read-back slots. Absolute TimeInterval deltas are DST-wrong for
    // date-only/all-day semantics, so shift by whole calendar days and
    // re-anchor the wall-clock time of the proposed selected date instead.
    let expectedDay = calendar.startOfDay(for: expectedSelectedDate)
    let proposedDay = calendar.startOfDay(for: proposedSelectedDate)
    let dayDelta = calendar.dateComponents([.day], from: expectedDay, to: proposedDay).day ?? 0
    let futureDay = calendar.startOfDay(for: futureDate)
    let shiftedDay = calendar.date(byAdding: .day, value: dayDelta, to: futureDay) ?? futureDay
    var components = calendar.dateComponents([.year, .month, .day], from: shiftedDay)
    let timeComponents = calendar.dateComponents([.hour, .minute, .second], from: proposedSelectedDate)
    components.hour = timeComponents.hour
    components.minute = timeComponents.minute
    components.second = timeComponents.second
    return calendar.date(from: components) ?? shiftedDay
}

func occurrenceCandidates(
    _ store: EKEventStore,
    eventId: String,
    startDate: Date,
    endDate: Date
) -> [EKEvent] {
    let predicateStart = startDate.addingTimeInterval(-1)
    let predicateEnd = endDate.addingTimeInterval(1)
    let predicate = store.predicateForEvents(
        withStart: predicateStart,
        end: predicateEnd,
        calendars: nil
    )
    return store.events(matching: predicate).filter { event in
        event.eventIdentifier == eventId
            && eventDatesMatch(event.startDate, startDate)
            && eventDatesMatch(event.endDate, endDate)
    }
}

func relativeOccurrenceCandidates(
    _ store: EKEventStore,
    eventId: String,
    selectedStartDate: Date,
    direction: String
) -> [EKEvent] {
    let day: TimeInterval = 24 * 60 * 60
    let predicateStart: Date
    let predicateEnd: Date
    if direction == "previous" {
        predicateStart = selectedStartDate.addingTimeInterval(-3650 * day)
        predicateEnd = selectedStartDate.addingTimeInterval(-1)
    } else {
        predicateStart = selectedStartDate.addingTimeInterval(1)
        predicateEnd = selectedStartDate.addingTimeInterval(3650 * day)
    }
    let predicate = store.predicateForEvents(
        withStart: predicateStart,
        end: predicateEnd,
        calendars: nil
    )
    return store.events(matching: predicate).filter { event in
        guard event.eventIdentifier == eventId else {
            return false
        }
        if direction == "previous" {
            return event.startDate < selectedStartDate
        }
        return event.startDate > selectedStartDate
    }
}

func eventMatchesState(
    _ event: EKEvent,
    title: String,
    calendarTitle: String,
    startDate: Date,
    endDate: Date,
    expectedTimeZone: String,
    allDay: Bool,
    expectedAvailability: EKEventAvailability?,
    alarmOffsetsMinutes expectedAlarmOffsetsMinutes: [Int],
    alarmAbsoluteDates expectedAlarmAbsoluteDates: [String],
    alarmSoundName expectedAlarmSoundName: String,
    alarmEmailAddressSHA256 expectedAlarmEmailAddressSHA256: String,
    alarmProximity expectedAlarmProximity: String,
    alarmStructuredLocation expectedAlarmStructuredLocation: [String: Any]?,
    eventURLPresent expectedEventURLPresent: Bool?,
    eventURLSHA256 expectedEventURLSHA256: String,
    location: String,
    structuredLocation expectedStructuredLocation: [String: Any]? = nil,
    notes: String
) -> Bool {
    let state = alarmState(event)
    guard let currentAlarmOffsetsMinutes = state.offsets,
          let currentAlarmAbsoluteDates = state.absoluteDates,
          let currentAlarmSoundName = state.soundName,
          let currentAlarmProximity = state.proximity,
          let currentAlarmEmailAddressSHA256 = state.emailAddressSHA256 else {
        return false
    }
    if let expectedEventURLPresent = expectedEventURLPresent {
        let currentURL = eventURLString(event)
        if expectedEventURLPresent != !currentURL.isEmpty {
            return false
        }
        if expectedEventURLPresent && sha256Hex(currentURL) != expectedEventURLSHA256 {
            return false
        }
    }
    return (event.title ?? "") == title
        && (event.calendar?.title ?? "") == calendarTitle
        && eventDatesMatch(event.startDate, startDate)
        && eventDatesMatch(event.endDate, endDate)
        && (expectedTimeZone.isEmpty || eventTimeZoneIdentifier(event) == expectedTimeZone)
        && event.isAllDay == allDay
        && availabilityMatches(event, expectedAvailability)
        && currentAlarmOffsetsMinutes == expectedAlarmOffsetsMinutes
        && currentAlarmAbsoluteDates == expectedAlarmAbsoluteDates
        && currentAlarmSoundName == expectedAlarmSoundName
        && currentAlarmEmailAddressSHA256 == expectedAlarmEmailAddressSHA256
        && currentAlarmProximity == expectedAlarmProximity
        && structuredLocationPayloadMatches(state.structuredLocation, expectedAlarmStructuredLocation)
        && (event.location ?? "") == location
        && structuredLocationMatches(event, expectedStructuredLocation)
        && (event.notes ?? "") == notes
}

func eventURLStateMatches(_ event: EKEvent, present expectedPresent: Bool, sha256 expectedSHA256: String) -> Bool {
    let currentURL = eventURLString(event)
    if expectedPresent != !currentURL.isEmpty {
        return false
    }
    if expectedPresent && sha256Hex(currentURL) != expectedSHA256 {
        return false
    }
    return true
}

func eventLocationProofStateMatches(
    _ event: EKEvent,
    locationPresent expectedLocationPresent: Bool,
    locationSHA256 expectedLocationSHA256: String,
    structuredLocationPresent expectedStructuredLocationPresent: Bool,
    structuredLocationSHA256 expectedStructuredLocationSHA256: String
) -> Bool {
    let currentLocation = event.location ?? ""
    if expectedLocationPresent != !currentLocation.isEmpty {
        return false
    }
    if expectedLocationPresent && sha256Hex(currentLocation) != expectedLocationSHA256 {
        return false
    }
    let currentStructuredLocationSHA256 = structuredLocationSafeSHA256(event)
    if expectedStructuredLocationPresent != !currentStructuredLocationSHA256.isEmpty {
        return false
    }
    if expectedStructuredLocationPresent
        && currentStructuredLocationSHA256 != expectedStructuredLocationSHA256 {
        return false
    }
    return true
}

func eventAlarmProofStateMatches(
    _ event: EKEvent,
    present expectedPresent: Bool,
    sha256 expectedSHA256: String
) -> Bool {
    let currentPresent = event.alarms?.isEmpty == false
    if expectedPresent != currentPresent {
        return false
    }
    if expectedPresent && alarmStateSafeSHA256(event) != expectedSHA256 {
        return false
    }
    return true
}

func calendarTitleIsAmbiguous(_ store: EKEventStore, _ title: String) -> Bool {
    return store.calendars(for: .event).filter { $0.title == title }.count > 1
}

func eventHasRecurrence(_ event: EKEvent) -> Bool {
    return event.recurrenceRules?.isEmpty == false
}

func eventHasUnsupportedAttendeeOrAlarmState(_ event: EKEvent) -> Bool {
    let state = alarmState(event)
    return (event.attendees?.isEmpty == false)
        || state.offsets == nil
        || state.absoluteDates == nil
        || state.soundName == nil
        || state.proximity == nil
        || state.emailAddressSHA256 == nil
}

func eventIsUnsupportedForBoundedMutation(_ event: EKEvent) -> Bool {
    return eventHasRecurrence(event) || eventHasUnsupportedAttendeeOrAlarmState(event)
}

func emitCalendarApplyError(
    _ status: String,
    _ code: String,
    _ message: String,
    authorizationStatus: EKAuthorizationStatus = EKEventStore.authorizationStatus(for: .event)
) -> Never {
    emit([
        "schema_version": 1,
        "status": status,
        "source": "calendar",
        "authorization_status": authorizationName(authorizationStatus),
        "event": NSNull(),
        "warnings": [warning(code, message)],
    ])
}

func emitReminderApplyError(
    _ status: String,
    _ code: String,
    _ message: String,
    authorizationStatus: EKAuthorizationStatus = EKEventStore.authorizationStatus(for: .reminder),
    mutationApplied: Bool = false
) -> Never {
    emit([
        "schema_version": 1,
        "status": status,
        "source": "reminders",
        "authorization_status": authorizationName(authorizationStatus),
        "mutation_applied": mutationApplied,
        "reminder": NSNull(),
        "warnings": [warning(code, message)],
    ])
}

let command = stringValue(request, "command")

if command == "request_calendar_full_access" {
    requestCalendarFullAccess()
}

if command == "request_reminders_full_access" {
    requestRemindersFullAccess()
}

if command == "calendar_authorization_status" {
    let status = EKEventStore.authorizationStatus(for: .event)
    emit([
        "schema_version": 1,
        "status": readAuthorized(status) ? "ok" : "degraded",
        "source": "calendar",
        "authorization_status": authorizationName(status),
        "warnings": readAuthorized(status) ? [] : [
            warning("calendar_access_unavailable", "Calendar access is not authorized for this process.")
        ],
    ])
}

if command == "calendar_calendars" {
    let store = ensureAccess(
        .event,
        source: "calendar",
        warningCode: "calendar_access_unavailable"
    )!
    let query = stringValue(request, "query").lowercased()
    let limit = max(1, min(intValue(request, "limit", 20), 10000))
    let includeDefault = (request["include_default"] as? Bool) ?? false
    let includeAll = (request["include_all"] as? Bool) ?? false
    let includeSafetyCounts = (request["include_safety_counts"] as? Bool) ?? false
    let defaultCalendarId = store.defaultCalendarForNewEvents?.calendarIdentifier
    let calendars = store.calendars(for: .event).sorted {
        if $0.title == $1.title {
            return $0.calendarIdentifier < $1.calendarIdentifier
        }
        return $0.title < $1.title
    }

    var results: [[String: Any]] = []
    for calendar in calendars {
        let matchesQuery = !query.isEmpty && calendar.title.lowercased().contains(query)
        let matchesDefault = includeDefault && calendar.calendarIdentifier == defaultCalendarId
        if !includeAll && !matchesQuery && !matchesDefault {
            continue
        }
        results.append(
            calendarPayload(
                calendar,
                defaultCalendarId: defaultCalendarId,
                includeSafetyCounts: includeSafetyCounts,
                store: store
            )
        )
        if results.count >= limit {
            break
        }
    }

    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .event)),
        "calendars": results,
        "warnings": [],
    ])
}

if command == "calendar_events" {
    let store = ensureAccess(
        .event,
        source: "calendar",
        warningCode: "calendar_access_unavailable"
    )!
    let query = stringValue(request, "query").lowercased()
    let limit = max(1, min(intValue(request, "limit", 20), 10000))
    let maxEvents = max(1, min(intValue(request, "max_events", 2000), 10000))
    let daysBack = max(0, min(intValue(request, "days_back", 365), 3650))
    let daysForward = max(0, min(intValue(request, "days_forward", 730), 3650))
    let includeURLProof = boolValue(request, "include_url_proof") ?? false
    let includeLocationProof = boolValue(request, "include_location_proof") ?? false
    let includeStructuredLocationProof = boolValue(request, "include_structured_location_proof") ?? false
    let includeAlarmProof = boolValue(request, "include_alarm_proof") ?? false
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
        if let payload = eventPayload(
            event,
            includeContent: false,
            includeURLProof: includeURLProof,
            includeLocationProof: includeLocationProof,
            includeStructuredLocationProof: includeStructuredLocationProof,
            includeAlarmProof: includeAlarmProof
        ) {
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

if command == "calendar_events_for_calendar" {
    let store = ensureAccess(
        .event,
        source: "calendar",
        warningCode: "calendar_access_unavailable"
    )!
    let calendarId = stringValue(request, "calendar_id")
    let startDateValue = stringValue(request, "start_date")
    let endDateValue = stringValue(request, "end_date")
    let limit = max(1, min(intValue(request, "limit", 20), 10000))
    guard !calendarId.isEmpty,
          let start = eventDate(from: startDateValue),
          let end = eventDate(from: endDateValue),
          end > start
    else {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "calendar",
            "events": [],
            "warnings": [warning("invalid_date_window", "Calendar selected-calendar event listing requires calendar_id plus start/end dates where end is after start.")],
        ])
    }
    guard let calendar = store.calendars(for: .event).first(where: { $0.calendarIdentifier == calendarId }) else {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "calendar",
            "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .event)),
            "calendar": NSNull(),
            "events": [],
            "warnings": [],
        ])
    }
    let predicate = store.predicateForEvents(withStart: start, end: end, calendars: [calendar])
    let events = store.events(matching: predicate).sorted {
        if $0.startDate == $1.startDate {
            if ($0.title ?? "") == ($1.title ?? "") {
                return ($0.eventIdentifier ?? "") < ($1.eventIdentifier ?? "")
            }
            return ($0.title ?? "") < ($1.title ?? "")
        }
        return $0.startDate < $1.startDate
    }
    let payloads = events.compactMap { eventPayload($0, includeContent: false) }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .event)),
        "calendar": calendarPayload(calendar, defaultCalendarId: store.defaultCalendarForNewEvents?.calendarIdentifier),
        "events": Array(payloads.prefix(limit)),
        "truncated": payloads.count > limit,
        "warnings": [],
    ])
}

if command == "calendar_event_by_id" {
    let store = ensureAccess(
        .event,
        source: "calendar",
        warningCode: "calendar_access_unavailable"
    )!
    let eventId = stringValue(request, "event_id")
    let includeParticipants = boolValue(request, "include_participants") ?? false
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
          let payload = eventPayload(
            event,
            includeContent: true,
            includeAlarmOffsets: true,
            includeTimeZone: true,
            includeURLProof: true,
            includeStructuredLocation: true,
            includeParticipants: includeParticipants
          )
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

if command == "calendar_event_participants_by_id" {
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
          let payload = eventParticipantContainerPayload(event)
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

if command == "calendar_event_by_occurrence" {
    let store = ensureAccess(
        .event,
        source: "calendar",
        warningCode: "calendar_access_unavailable"
    )!
    let eventId = stringValue(request, "event_id")
    let startDateValue = stringValue(request, "start_date")
    let endDateValue = stringValue(request, "end_date")
    let includeParticipants = boolValue(request, "include_participants") ?? false
    guard !eventId.isEmpty,
          let startDate = eventDate(from: startDateValue),
          let endDate = eventDate(from: endDateValue),
          endDate > startDate
    else {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "calendar",
            "event": NSNull(),
            "warnings": [warning("invalid_event_occurrence", "Expected EventKit event identifier plus start/end dates.")],
        ])
    }
    let matches = occurrenceCandidates(store, eventId: eventId, startDate: startDate, endDate: endDate)
    guard matches.count == 1,
          let payload = eventPayload(
            matches[0],
            includeContent: true,
            includeAlarmOffsets: true,
            includeTimeZone: true,
            includeURLProof: true,
            includeStructuredLocation: true,
            includeParticipants: includeParticipants
          )
    else {
        emit([
            "schema_version": 1,
            "status": matches.isEmpty ? "not_found" : "error",
            "source": "calendar",
            "event": NSNull(),
            "warnings": matches.isEmpty ? [] : [warning("ambiguous_event_occurrence", "Calendar occurrence handle matched more than one event.")],
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

if command == "calendar_event_participants_by_occurrence" {
    let store = ensureAccess(
        .event,
        source: "calendar",
        warningCode: "calendar_access_unavailable"
    )!
    let eventId = stringValue(request, "event_id")
    let startDateValue = stringValue(request, "start_date")
    let endDateValue = stringValue(request, "end_date")
    guard !eventId.isEmpty,
          let startDate = eventDate(from: startDateValue),
          let endDate = eventDate(from: endDateValue),
          endDate > startDate
    else {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "calendar",
            "event": NSNull(),
            "warnings": [warning("invalid_event_occurrence", "Expected EventKit event identifier plus start/end dates.")],
        ])
    }
    let matches = occurrenceCandidates(store, eventId: eventId, startDate: startDate, endDate: endDate)
    guard matches.count == 1,
          let payload = eventParticipantContainerPayload(matches[0])
    else {
        emit([
            "schema_version": 1,
            "status": matches.isEmpty ? "not_found" : "error",
            "source": "calendar",
            "event": NSNull(),
            "warnings": matches.isEmpty ? [] : [warning("ambiguous_event_occurrence", "Calendar occurrence handle matched more than one event.")],
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

if command == "calendar_calendar_apply_change" {
    let store = ensureAccess(
        .event,
        source: "calendar",
        warningCode: "calendar_access_unavailable"
    )!
    let operation = stringValue(request, "operation")
    let defaultCalendarId = store.defaultCalendarForNewEvents?.calendarIdentifier

    func emitCalendarManagementError(_ status: String, _ code: String, _ message: String, mutationApplied: Bool = false) -> Never {
        emit([
            "schema_version": 1,
            "status": status,
            "source": "calendar",
            "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .event)),
            "mutation_applied": mutationApplied,
            "calendar": NSNull(),
            "read_back": NSNull(),
            "warnings": [warning(code, message)],
        ])
    }

    func calendarWithTitleInSource(_ title: String, sourceIdentifier: String, excluding calendarIdentifier: String = "") -> EKCalendar? {
        return store.calendars(for: .event).first {
            $0.title == title
                && $0.source.sourceIdentifier == sourceIdentifier
                && (calendarIdentifier.isEmpty || $0.calendarIdentifier != calendarIdentifier)
        }
    }

    if operation == "create_calendar" {
        let sourceCalendarId = stringValue(request, "source_calendar_id")
        let calendarTitle = stringValue(request, "calendar_title")
        if sourceCalendarId.isEmpty || calendarTitle.isEmpty {
            emitCalendarManagementError("error", "missing_required_field", "Calendar create-calendar requires source_calendar_id and calendar_title.")
        }
        if !calendarTitle.hasPrefix(calendarTestPrefix) {
            emitCalendarManagementError("error", "non_synthetic_calendar_title", "Calendar calendar management is limited to LAD-TEST-* titles.")
        }
        guard let sourceCalendar = store.calendar(withIdentifier: sourceCalendarId) else {
            emitCalendarManagementError("not_found", "target_calendar_not_found", "Calendar source target was not found.")
        }
        if sourceCalendar.source.sourceType == .subscribed || sourceCalendar.source.sourceType == .birthdays {
            emitCalendarManagementError("error", "unsupported_calendar_source", "Calendar create-calendar refuses subscribed or birthday sources.")
        }
        if sourceCalendar.isSubscribed || sourceCalendar.isImmutable {
            emitCalendarManagementError("error", "unsupported_calendar_source", "Calendar create-calendar refuses subscribed or immutable source calendars.")
        }
        if !sourceCalendar.allowsContentModifications {
            emitCalendarManagementError("error", "target_calendar_not_writable", "Calendar source target does not allow changes.")
        }
        if calendarWithTitleInSource(calendarTitle, sourceIdentifier: sourceCalendar.source.sourceIdentifier) != nil {
            emitCalendarManagementError("error", "calendar_already_exists", "A calendar with that title already exists in the selected source.")
        }
        let calendar = EKCalendar(for: .event, eventStore: store)
        calendar.title = calendarTitle
        calendar.source = sourceCalendar.source
        do {
            try store.saveCalendar(calendar, commit: true)
        } catch {
            emitCalendarManagementError("error", "eventkit_apply_failed", "Calendar could not be created.")
        }
        guard let readBack = store.calendar(withIdentifier: calendar.calendarIdentifier),
              readBack.title == calendarTitle,
              readBack.source.sourceIdentifier == sourceCalendar.source.sourceIdentifier
        else {
            emitCalendarManagementError("apply_unknown", "read_back_unavailable", "Calendar was created but read-back was unavailable.", mutationApplied: true)
        }
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .event)),
            "mutation_applied": true,
            "calendar": calendarPayload(readBack, defaultCalendarId: defaultCalendarId, includeSafetyCounts: true, store: store),
            "read_back": [
                "source_calendar_verified": true,
                "calendar_empty_verified": calendarEventCount(store, readBack) == 0,
            ],
            "warnings": [],
        ])
    }

    if operation == "rename_calendar" || operation == "delete_calendar" {
        let calendarId = stringValue(request, "calendar_id")
        let expectedTitle = stringValue(request, "expected_calendar_title")
        let expectedSourceType = stringValue(request, "expected_source_type")
        if calendarId.isEmpty || expectedTitle.isEmpty {
            emitCalendarManagementError("error", "missing_required_field", "Calendar calendar management requires calendar_id and expected_calendar_title.")
        }
        guard let calendar = store.calendar(withIdentifier: calendarId) else {
            emitCalendarManagementError("not_found", "target_calendar_not_found", "Calendar target was not found.")
        }
        if calendar.title != expectedTitle || sourceTypeName(calendar.source.sourceType) != expectedSourceType {
            emitCalendarManagementError("error", "expected_state_mismatch", "Calendar target did not match expected state.")
        }
        if !calendar.title.hasPrefix(calendarTestPrefix) || calendar.isSubscribed || calendar.isImmutable || calendar.calendarIdentifier == defaultCalendarId {
            emitCalendarManagementError("error", "unsupported_calendar_state", "Calendar calendar management refuses non-synthetic, default, subscribed, or immutable calendars.")
        }
        if !calendar.allowsContentModifications {
            emitCalendarManagementError("error", "target_calendar_not_writable", "Calendar target does not allow changes.")
        }
        if operation == "delete_calendar" && entityTypeNames(calendar.allowedEntityTypes) != ["event"] {
            emitCalendarManagementError("error", "unsupported_calendar_state", "Calendar delete-calendar refuses calendars that may contain reminders.")
        }
        if calendarEventCount(store, calendar) != 0 {
            emitCalendarManagementError("error", "calendar_not_empty", "Calendar calendar management refuses non-empty calendars.")
        }
        if operation == "rename_calendar" {
            let newTitle = stringValue(request, "new_calendar_title")
            if newTitle.isEmpty {
                emitCalendarManagementError("error", "missing_required_field", "Calendar rename-calendar requires new_calendar_title.")
            }
            if !newTitle.hasPrefix(calendarTestPrefix) {
                emitCalendarManagementError("error", "non_synthetic_calendar_title", "Calendar calendar management is limited to LAD-TEST-* titles.")
            }
            if calendarWithTitleInSource(newTitle, sourceIdentifier: calendar.source.sourceIdentifier, excluding: calendar.calendarIdentifier) != nil {
                emitCalendarManagementError("error", "calendar_already_exists", "A calendar with that title already exists in the selected source.")
            }
            calendar.title = newTitle
            do {
                try store.saveCalendar(calendar, commit: true)
            } catch {
                emitCalendarManagementError("error", "eventkit_apply_failed", "Calendar could not be renamed.")
            }
            guard let readBack = store.calendar(withIdentifier: calendar.calendarIdentifier),
                  readBack.title == newTitle
            else {
                emitCalendarManagementError("apply_unknown", "read_back_unavailable", "Calendar was renamed but read-back was unavailable.", mutationApplied: true)
            }
            let calendarEmptyVerified = calendarEventCount(store, readBack) == 0
            if !calendarEmptyVerified {
                emitCalendarManagementError("apply_unknown", "calendar_rename_read_back_mismatch", "Calendar was renamed but empty-window proof failed.", mutationApplied: true)
            }
            emit([
                "schema_version": 1,
                "status": "ok",
                "source": "calendar",
                "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .event)),
                "mutation_applied": true,
                "calendar": calendarPayload(readBack, defaultCalendarId: defaultCalendarId, includeSafetyCounts: true, store: store),
                "read_back": [
                    "calendar_renamed_verified": true,
                    "calendar_empty_verified": calendarEmptyVerified,
                ],
                "warnings": [],
            ])
        }
        if operation == "delete_calendar" {
            do {
                try store.removeCalendar(calendar, commit: true)
            } catch {
                emitCalendarManagementError("error", "eventkit_apply_failed", "Calendar could not be deleted.")
            }
            if store.calendar(withIdentifier: calendarId) != nil {
                emitCalendarManagementError("apply_unknown", "calendar_delete_read_back_mismatch", "Calendar was deleted but absence proof failed.", mutationApplied: true)
            }
            emit([
                "schema_version": 1,
                "status": "ok",
                "source": "calendar",
                "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .event)),
                "mutation_applied": true,
                "calendar": NSNull(),
                "read_back": [
                    "calendar_deleted_verified": true,
                    "calendar_absent_verified": true,
                    "calendar_empty_verified": true,
                ],
                "warnings": [],
            ])
        }
    }

    emitCalendarManagementError("error", "invalid_operation", "Unsupported Calendar calendar management operation.")
}

if command == "calendar_apply_change" {
    let store = ensureAccess(
        .event,
        source: "calendar",
        warningCode: "calendar_access_unavailable"
    )!
    let operation = stringValue(request, "operation")
    if operation != "create" && operation != "update" && operation != "delete" {
        emitCalendarApplyError("error", "invalid_operation", "Unsupported Calendar apply operation.")
    }

    if operation == "delete" {
        if request["recurrence"] != nil {
            guard let expectedRecurrence = recurrenceRequest(request) else {
                emitCalendarApplyError("error", "invalid_recurrence", "Calendar recurrence must be a bounded daily, weekly, monthly, or yearly rule.")
            }
            if (expectedRecurrence["recurrence_present"] as? Bool) == true {
                emitCalendarApplyError("error", "unsupported_recurrence_for_operation", "Calendar recurrence is not supported for delete operations.")
            }
        }
        let expectedRecurrence: [String: Any]?
        if request["expected_recurrence"] != nil {
            guard let currentExpectedRecurrence = recurrenceRequest(request, key: "expected_recurrence") else {
                emitCalendarApplyError("error", "invalid_expected_recurrence", "Calendar expected recurrence must be a bounded daily, weekly, monthly, or yearly rule.")
            }
            expectedRecurrence = currentExpectedRecurrence
        } else {
            expectedRecurrence = nil
        }
        let eventId = stringValue(request, "event_id")
        let expectedTitle = stringValue(request, "expected_title")
        let expectedCalendarTitle = stringValue(request, "expected_calendar_title")
        let expectedStartDateValue = stringValue(request, "expected_start_date")
        let expectedEndDateValue = stringValue(request, "expected_end_date")
        let expectedTimeZone = stringValue(request, "expected_time_zone")
        let expectedAllDay = boolValue(request, "expected_all_day") ?? false
        let expectedAvailability = availabilityRequest(request, "expected_availability", allowNotSupported: true)
        let expectedEventURLPresent = boolValue(request, "expected_event_url_present") ?? false
        let expectedEventURLSHA256 = stringValue(request, "expected_event_url_sha256")
        let recurrenceDeleteScope = stringValue(request, "recurrence_delete_scope")
        let occurrenceStartDateValue = stringValue(request, "occurrence_start_date")
        let occurrenceEndDateValue = stringValue(request, "occurrence_end_date")
        let adjacentOccurrenceStartDateValue = stringValue(request, "adjacent_occurrence_start_date")
        let adjacentOccurrenceEndDateValue = stringValue(request, "adjacent_occurrence_end_date")
        if !recurrenceDeleteScope.isEmpty && recurrenceDeleteScope != "this_event" && recurrenceDeleteScope != "future_events" && recurrenceDeleteScope != "all_events" {
            emitCalendarApplyError("error", "unsupported_recurrence_delete_scope", "Calendar recurring-event delete supports only this_event, future_events, or all_events scope.")
        }
        if expectedEventURLPresent && expectedEventURLSHA256.isEmpty {
            emitCalendarApplyError("error", "missing_required_field", "Calendar delete requires expected_event_url_sha256 when expected_event_url_present is true.")
        }
        _ = timeZoneOrError(expectedTimeZone, "expected_time_zone")
        if expectedAllDay && !expectedTimeZone.isEmpty {
            emitCalendarApplyError("error", "unsupported_time_zone_for_all_day", "Calendar expected_time_zone is supported only for timed events.")
        }
        guard let expectedAlarmOffsetsMinutes = intArrayValue(request, "expected_alarm_offsets_minutes") else {
            emitCalendarApplyError("error", "invalid_alarm_offsets", "Calendar expected alarm offsets must be integer minute offsets.")
        }
        guard let expectedAlarmAbsoluteDates = dateStringArrayValue(request, "expected_alarm_absolute_dates") else {
            emitCalendarApplyError("error", "invalid_alarm_absolute_dates", "Calendar expected absolute alarm dates must be ISO 8601 timestamps with timezones.")
        }
        if !expectedAlarmOffsetsMinutes.isEmpty && !expectedAlarmAbsoluteDates.isEmpty {
            emitCalendarApplyError("error", "conflicting_alarm_fields", "Use either expected alarm offsets or expected absolute alarm dates, not both.")
        }
        guard let expectedAlarmSoundName = alarmSoundNameValue(request, "expected_alarm_sound_name") else {
            emitCalendarApplyError("error", "invalid_alarm_sound_name", "Calendar expected alarm sound name must be a bounded system sound name.")
        }
        if !expectedAlarmSoundName.isEmpty && expectedAlarmOffsetsMinutes.isEmpty && expectedAlarmAbsoluteDates.isEmpty {
            emitCalendarApplyError("error", "missing_alarm_trigger", "Calendar expected alarm sound name requires expected alarm offsets or absolute alarm dates.")
        }
        let expectedAlarmEmailAddressSHA256 = stringValue(request, "expected_alarm_email_address_sha256")
        if !isSHA256Hex(expectedAlarmEmailAddressSHA256) {
            emitCalendarApplyError("error", "invalid_expected_alarm_email_address_sha256", "Calendar expected alarm email address SHA-256 must be empty or lowercase hex.")
        }
        if !expectedAlarmEmailAddressSHA256.isEmpty && expectedAlarmOffsetsMinutes.isEmpty && expectedAlarmAbsoluteDates.isEmpty {
            emitCalendarApplyError("error", "missing_alarm_trigger", "Calendar expected alarm email address requires expected alarm offsets or absolute alarm dates.")
        }
        guard let expectedAlarmProximity = alarmProximityValue(request, "expected_alarm_proximity") else {
            emitCalendarApplyError("error", "invalid_alarm_proximity", "Calendar expected alarm proximity must be enter or leave.")
        }
        let expectedAlarmStructuredLocation = structuredLocationRequest(request, "expected_alarm_structured_location")
        if !expectedAlarmProximity.isEmpty && expectedAlarmStructuredLocation == nil {
            emitCalendarApplyError("error", "missing_alarm_structured_location", "Calendar expected alarm proximity requires expected alarm structured location.")
        }
        if expectedAlarmProximity.isEmpty && expectedAlarmStructuredLocation != nil {
            emitCalendarApplyError("error", "missing_alarm_proximity", "Calendar expected alarm structured location requires expected alarm proximity.")
        }
        if !expectedAlarmProximity.isEmpty && (!expectedAlarmOffsetsMinutes.isEmpty || !expectedAlarmAbsoluteDates.isEmpty || !expectedAlarmSoundName.isEmpty || !expectedAlarmEmailAddressSHA256.isEmpty) {
            emitCalendarApplyError("error", "conflicting_alarm_fields", "Use only one expected alarm trigger: offsets, absolute dates, or geofence.")
        }
        if [!expectedAlarmSoundName.isEmpty, !expectedAlarmProximity.isEmpty, !expectedAlarmEmailAddressSHA256.isEmpty].filter({ $0 }).count > 1 {
            emitCalendarApplyError("error", "conflicting_alarm_fields", "Use only one expected alarm action: sound, geofence, or email.")
        }
        let expectedLocation = stringValue(request, "expected_location")
        let expectedStructuredLocation = structuredLocationRequest(request, "expected_structured_location")
        let expectedNotes = stringValue(request, "expected_notes")
        if eventId.isEmpty || expectedTitle.isEmpty || expectedCalendarTitle.isEmpty || expectedStartDateValue.isEmpty || expectedEndDateValue.isEmpty {
            emitCalendarApplyError("error", "missing_required_field", "Calendar delete requires event_id and expected current state.")
        }
        guard let expectedStartDate = eventDate(from: expectedStartDateValue),
              let expectedEndDate = eventDate(from: expectedEndDateValue),
              expectedEndDate > expectedStartDate
        else {
            emitCalendarApplyError("error", "invalid_expected_state", "Calendar expected state dates could not be parsed.")
        }
        let event: EKEvent
        var adjacentOccurrenceStartDate: Date? = nil
        var adjacentOccurrenceEndDate: Date? = nil
        var previousOccurrenceStartDate: Date? = nil
        var previousOccurrenceEndDate: Date? = nil
        var futureOccurrenceStartDate: Date? = nil
        var futureOccurrenceEndDate: Date? = nil
        var previousOccurrenceVerifiedAbsent = false
        if !recurrenceDeleteScope.isEmpty {
            guard let occurrenceStartDate = eventDate(from: occurrenceStartDateValue),
                  let occurrenceEndDate = eventDate(from: occurrenceEndDateValue),
                  occurrenceEndDate > occurrenceStartDate
            else {
                emitCalendarApplyError("error", "missing_occurrence_identity", "Selected recurring occurrence delete requires occurrence start/end identity.")
            }
            if !eventDatesMatch(occurrenceStartDate, expectedStartDate) || !eventDatesMatch(occurrenceEndDate, expectedEndDate) {
                emitCalendarApplyError("error", "expected_state_mismatch", "Calendar occurrence identity did not match expected state.")
            }
            let candidates = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: occurrenceStartDate,
                endDate: occurrenceEndDate
            )
            if candidates.isEmpty {
                emitCalendarApplyError("not_found", "target_not_found", "Calendar target occurrence was not found.")
            }
            if candidates.count > 1 {
                emitCalendarApplyError("error", "ambiguous_event_occurrence", "Calendar occurrence handle matched more than one event.")
            }
            if recurrenceDeleteScope == "this_event" {
                guard let adjacentStartDate = eventDate(from: adjacentOccurrenceStartDateValue),
                      let adjacentEndDate = eventDate(from: adjacentOccurrenceEndDateValue),
                      adjacentEndDate > adjacentStartDate
                else {
                    emitCalendarApplyError("error", "missing_adjacent_occurrence_identity", "Selected recurring occurrence delete requires sibling occurrence identity.")
                }
                if eventDatesMatch(adjacentStartDate, occurrenceStartDate) && eventDatesMatch(adjacentEndDate, occurrenceEndDate) {
                    emitCalendarApplyError("error", "invalid_adjacent_occurrence_identity", "Sibling occurrence identity must differ from selected occurrence identity.")
                }
                let adjacentCandidates = occurrenceCandidates(
                    store,
                    eventId: eventId,
                    startDate: adjacentStartDate,
                    endDate: adjacentEndDate
                )
                if adjacentCandidates.isEmpty {
                    emitCalendarApplyError("error", "adjacent_occurrence_not_found", "Calendar sibling occurrence was not found before delete.")
                }
                if adjacentCandidates.count > 1 {
                    emitCalendarApplyError("error", "ambiguous_adjacent_occurrence", "Calendar sibling occurrence identity matched more than one event.")
                }
                adjacentOccurrenceStartDate = adjacentStartDate
                adjacentOccurrenceEndDate = adjacentEndDate
            } else if recurrenceDeleteScope == "future_events" {
                let previousOccurrenceStartDateValue = stringValue(request, "previous_occurrence_start_date")
                let previousOccurrenceEndDateValue = stringValue(request, "previous_occurrence_end_date")
                let futureOccurrenceStartDateValue = stringValue(request, "future_occurrence_start_date")
                let futureOccurrenceEndDateValue = stringValue(request, "future_occurrence_end_date")
                guard let previousStartDate = eventDate(from: previousOccurrenceStartDateValue),
                      let previousEndDate = eventDate(from: previousOccurrenceEndDateValue),
                      previousEndDate > previousStartDate
                else {
                    emitCalendarApplyError("error", "missing_previous_occurrence_identity", "Future recurring occurrence delete requires previous occurrence identity.")
                }
                guard let futureStartDate = eventDate(from: futureOccurrenceStartDateValue),
                      let futureEndDate = eventDate(from: futureOccurrenceEndDateValue),
                      futureEndDate > futureStartDate
                else {
                    emitCalendarApplyError("error", "missing_future_occurrence_identity", "Future recurring occurrence delete requires future occurrence identity.")
                }
                if previousStartDate >= occurrenceStartDate || futureStartDate <= occurrenceStartDate {
                    emitCalendarApplyError("error", "invalid_recurrence_delete_scope", "Future recurring occurrence delete requires previous, selected, and future occurrence order.")
                }
                let previousCandidates = occurrenceCandidates(
                    store,
                    eventId: eventId,
                    startDate: previousStartDate,
                    endDate: previousEndDate
                )
                if previousCandidates.isEmpty {
                    emitCalendarApplyError("error", "previous_occurrence_not_found", "Calendar previous occurrence was not found before delete.")
                }
                if previousCandidates.count > 1 {
                    emitCalendarApplyError("error", "ambiguous_previous_occurrence", "Calendar previous occurrence identity matched more than one event.")
                }
                let futureCandidates = occurrenceCandidates(
                    store,
                    eventId: eventId,
                    startDate: futureStartDate,
                    endDate: futureEndDate
                )
                if futureCandidates.isEmpty {
                    emitCalendarApplyError("error", "future_occurrence_not_found", "Calendar future occurrence was not found before delete.")
                }
                if futureCandidates.count > 1 {
                    emitCalendarApplyError("error", "ambiguous_future_occurrence", "Calendar future occurrence identity matched more than one event.")
                }
                previousOccurrenceStartDate = previousStartDate
                previousOccurrenceEndDate = previousEndDate
                futureOccurrenceStartDate = futureStartDate
                futureOccurrenceEndDate = futureEndDate
            } else {
                let futureOccurrenceStartDateValue = stringValue(request, "future_occurrence_start_date")
                let futureOccurrenceEndDateValue = stringValue(request, "future_occurrence_end_date")
                guard let futureStartDate = eventDate(from: futureOccurrenceStartDateValue),
                      let futureEndDate = eventDate(from: futureOccurrenceEndDateValue),
                      futureEndDate > futureStartDate
                else {
                    emitCalendarApplyError("error", "missing_future_occurrence_identity", "Whole-series recurring delete requires future occurrence identity.")
                }
                if futureStartDate <= occurrenceStartDate {
                    emitCalendarApplyError("error", "invalid_recurrence_delete_scope", "Whole-series recurring delete requires selected and future occurrence order.")
                }
                let previousCandidates = relativeOccurrenceCandidates(
                    store,
                    eventId: eventId,
                    selectedStartDate: occurrenceStartDate,
                    direction: "previous"
                )
                if !previousCandidates.isEmpty {
                    emitCalendarApplyError("error", "previous_occurrence_present", "Whole-series recurring delete requires selecting the first same-series occurrence.")
                }
                let futureCandidates = occurrenceCandidates(
                    store,
                    eventId: eventId,
                    startDate: futureStartDate,
                    endDate: futureEndDate
                )
                if futureCandidates.isEmpty {
                    emitCalendarApplyError("error", "future_occurrence_not_found", "Calendar future occurrence was not found before delete.")
                }
                if futureCandidates.count > 1 {
                    emitCalendarApplyError("error", "ambiguous_future_occurrence", "Calendar future occurrence identity matched more than one event.")
                }
                previousOccurrenceVerifiedAbsent = true
                futureOccurrenceStartDate = futureStartDate
                futureOccurrenceEndDate = futureEndDate
            }
            event = candidates[0]
        } else {
            guard let resolvedEvent = store.event(withIdentifier: eventId) else {
                emitCalendarApplyError("not_found", "target_not_found", "Calendar target was not found.")
            }
            event = resolvedEvent
        }
        if (event.calendar?.title ?? "") == expectedCalendarTitle && calendarTitleIsAmbiguous(store, expectedCalendarTitle) {
            emitCalendarApplyError("error", "ambiguous_expected_calendar", "Calendar expected calendar title matched more than one calendar.")
        }
        if eventHasUnsupportedAttendeeOrAlarmState(event) {
            emitCalendarApplyError("error", "unsupported_event_state", "Calendar event has unsupported attendee or alarm state.")
        }
        if let expectedRecurrencePresent = boolValue(request, "expected_recurrence_present"),
           eventHasRecurrence(event) != expectedRecurrencePresent {
            emitCalendarApplyError("error", "expected_state_mismatch", "Calendar event did not match expected recurrence state.")
        }
        if let expectedRecurrence = expectedRecurrence,
           !recurrenceMatches(event, expectedRecurrence) {
            emitCalendarApplyError("error", "expected_state_mismatch", "Calendar event did not match expected recurrence state.")
        }
        if !recurrenceDeleteScope.isEmpty {
            if !eventHasRecurrence(event) {
                emitCalendarApplyError("error", "expected_state_mismatch", "Calendar event did not match expected recurrence state.")
            }
        } else if eventHasRecurrence(event) {
            emitCalendarApplyError("error", "unsupported_event_state", "Calendar event has unsupported recurrence state.")
        }
        if !eventMatchesState(event, title: expectedTitle, calendarTitle: expectedCalendarTitle, startDate: expectedStartDate, endDate: expectedEndDate, expectedTimeZone: expectedTimeZone, allDay: expectedAllDay, expectedAvailability: expectedAvailability, alarmOffsetsMinutes: expectedAlarmOffsetsMinutes, alarmAbsoluteDates: expectedAlarmAbsoluteDates, alarmSoundName: expectedAlarmSoundName, alarmEmailAddressSHA256: expectedAlarmEmailAddressSHA256, alarmProximity: expectedAlarmProximity, alarmStructuredLocation: expectedAlarmStructuredLocation, eventURLPresent: expectedEventURLPresent, eventURLSHA256: expectedEventURLSHA256, location: expectedLocation, structuredLocation: expectedStructuredLocation, notes: expectedNotes) {
            emitCalendarApplyError("error", "expected_state_mismatch", "Calendar event did not match expected state.")
        }
        do {
            try store.remove(event, span: recurrenceDeleteScope == "this_event" ? .thisEvent : .futureEvents, commit: true)
        } catch {
            emitCalendarApplyError("error", "eventkit_apply_failed", "Calendar event delete could not be applied.")
        }
        if recurrenceDeleteScope == "this_event" {
            let remaining = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: expectedStartDate,
                endDate: expectedEndDate
            )
            if !remaining.isEmpty {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar occurrence was deleted but absence proof was unavailable.")
            }
            let adjacentRemaining = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: adjacentOccurrenceStartDate!,
                endDate: adjacentOccurrenceEndDate!
            )
            if adjacentRemaining.count != 1 {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar occurrence was deleted but sibling preservation proof was unavailable.")
            }
        } else if recurrenceDeleteScope == "future_events" {
            let selectedRemaining = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: expectedStartDate,
                endDate: expectedEndDate
            )
            if !selectedRemaining.isEmpty {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar future recurring delete lacked selected occurrence absence proof.")
            }
            let futureRemaining = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: futureOccurrenceStartDate!,
                endDate: futureOccurrenceEndDate!
            )
            if !futureRemaining.isEmpty {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar future recurring delete lacked future occurrence absence proof.")
            }
            let previousRemaining = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: previousOccurrenceStartDate!,
                endDate: previousOccurrenceEndDate!
            )
            if previousRemaining.count != 1 {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar future recurring delete lacked previous occurrence preservation proof.")
            }
        } else if recurrenceDeleteScope == "all_events" {
            let selectedRemaining = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: expectedStartDate,
                endDate: expectedEndDate
            )
            if !selectedRemaining.isEmpty {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar whole-series recurring delete lacked selected occurrence absence proof.")
            }
            let futureRemaining = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: futureOccurrenceStartDate!,
                endDate: futureOccurrenceEndDate!
            )
            if !futureRemaining.isEmpty {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar whole-series recurring delete lacked future occurrence absence proof.")
            }
            let previousRemaining = relativeOccurrenceCandidates(
                store,
                eventId: eventId,
                selectedStartDate: expectedStartDate,
                direction: "previous"
            )
            if !previousOccurrenceVerifiedAbsent || !previousRemaining.isEmpty {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar whole-series recurring delete lacked previous occurrence absence proof.")
            }
        } else if store.event(withIdentifier: eventId) != nil {
            emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar event was deleted but absence proof was unavailable.")
        }
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .event)),
            "deleted": true,
            "read_back": [
                "deleted": true,
                "verified_absent": true,
                "selected_occurrence_verified_absent": !recurrenceDeleteScope.isEmpty,
                "adjacent_occurrence_verified_present": recurrenceDeleteScope == "this_event",
                "future_occurrence_verified_absent": recurrenceDeleteScope == "future_events" || recurrenceDeleteScope == "all_events",
                "previous_occurrence_verified_present": recurrenceDeleteScope == "future_events",
                "previous_occurrence_verified_absent": recurrenceDeleteScope == "all_events",
            ],
            "warnings": [],
        ])
    }

    let title = stringValue(request, "title")
    let startDateValue = stringValue(request, "start_date")
    let endDateValue = stringValue(request, "end_date")
    let timeZoneIdentifier = stringValue(request, "time_zone")
    let allDay = boolValue(request, "all_day") ?? false
    guard let proposedAlarmOffsetsMinutes = intArrayValue(request, "alarm_offsets_minutes") else {
        emitCalendarApplyError("error", "invalid_alarm_offsets", "Calendar alarm offsets must be integer minute offsets.")
    }
    guard let proposedAlarmAbsoluteDates = dateStringArrayValue(request, "alarm_absolute_dates") else {
        emitCalendarApplyError("error", "invalid_alarm_absolute_dates", "Calendar absolute alarm dates must be ISO 8601 timestamps with timezones.")
    }
    if !proposedAlarmOffsetsMinutes.isEmpty && !proposedAlarmAbsoluteDates.isEmpty {
        emitCalendarApplyError("error", "conflicting_alarm_fields", "Use either alarm offsets or absolute alarm dates, not both.")
    }
    guard let proposedAlarmSoundName = alarmSoundNameValue(request, "alarm_sound_name") else {
        emitCalendarApplyError("error", "invalid_alarm_sound_name", "Calendar alarm sound name must be a bounded system sound name.")
    }
    if !proposedAlarmSoundName.isEmpty && proposedAlarmOffsetsMinutes.isEmpty && proposedAlarmAbsoluteDates.isEmpty {
        emitCalendarApplyError("error", "missing_alarm_trigger", "Calendar alarm sound name requires alarm offsets or absolute alarm dates.")
    }
    guard let proposedAlarmEmailAddress = alarmEmailAddressValue(request, "alarm_email_address") else {
        emitCalendarApplyError("error", "invalid_alarm_email_address", "Calendar alarm email address must be a bounded plain email address.")
    }
    let proposedAlarmEmailAddressSHA256 = proposedAlarmEmailAddress.isEmpty ? "" : sha256Hex(proposedAlarmEmailAddress)
    if !proposedAlarmEmailAddressSHA256.isEmpty && proposedAlarmOffsetsMinutes.isEmpty && proposedAlarmAbsoluteDates.isEmpty {
        emitCalendarApplyError("error", "missing_alarm_trigger", "Calendar alarm email address requires alarm offsets or absolute alarm dates.")
    }
    guard let proposedAlarmProximity = alarmProximityValue(request, "alarm_proximity") else {
        emitCalendarApplyError("error", "invalid_alarm_proximity", "Calendar alarm proximity must be enter or leave.")
    }
    let proposedAlarmStructuredLocation = structuredLocationRequest(request, "alarm_structured_location")
    if !proposedAlarmProximity.isEmpty && proposedAlarmStructuredLocation == nil {
        emitCalendarApplyError("error", "missing_alarm_structured_location", "Calendar alarm proximity requires alarm structured location.")
    }
    if proposedAlarmProximity.isEmpty && proposedAlarmStructuredLocation != nil {
        emitCalendarApplyError("error", "missing_alarm_proximity", "Calendar alarm structured location requires alarm proximity.")
    }
    if !proposedAlarmProximity.isEmpty && (!proposedAlarmOffsetsMinutes.isEmpty || !proposedAlarmAbsoluteDates.isEmpty || !proposedAlarmSoundName.isEmpty || !proposedAlarmEmailAddressSHA256.isEmpty) {
        emitCalendarApplyError("error", "conflicting_alarm_fields", "Use only one alarm trigger: offsets, absolute dates, or geofence.")
    }
    if [!proposedAlarmSoundName.isEmpty, !proposedAlarmProximity.isEmpty, !proposedAlarmEmailAddressSHA256.isEmpty].filter({ $0 }).count > 1 {
        emitCalendarApplyError("error", "conflicting_alarm_fields", "Use only one alarm action: sound, geofence, or email.")
    }
    guard let proposedRecurrence = recurrenceRequest(request) else {
        emitCalendarApplyError("error", "invalid_recurrence", "Calendar recurrence must be a bounded daily, weekly, monthly, or yearly rule.")
    }
    let proposedEventURLRequested = boolValue(request, "event_url_requested") ?? false
    let proposedEventURLClearRequested = boolValue(request, "event_url_clear_requested") ?? false
    if proposedEventURLRequested && proposedEventURLClearRequested {
        emitCalendarApplyError("error", "conflicting_event_url_fields", "Use either event_url or clear_event_url, not both.")
    }
    if operation != "update" && proposedEventURLClearRequested {
        emitCalendarApplyError("error", "unsupported_event_url_for_operation", "Calendar clear_event_url is supported only for update operations.")
    }
    let proposedEventURLValue = stringValue(request, "event_url")
    let proposedEventURL = proposedEventURLRequested ? normalizedEventURLOrError(proposedEventURLValue, "event_url") : nil
    let proposedEventURLSHA256 = proposedEventURLRequested ? sha256Hex(proposedEventURLValue) : ""
    let location = stringValue(request, "location")
    let proposedStructuredLocation = structuredLocationRequest(request, "structured_location")
    let proposedStructuredLocationClearRequested = boolValue(request, "structured_location_clear_requested") ?? false
    if proposedStructuredLocation != nil && proposedStructuredLocationClearRequested {
        emitCalendarApplyError("error", "conflicting_structured_location_fields", "Use either structured_location or clear_structured_location, not both.")
    }
    if operation != "update" && proposedStructuredLocationClearRequested {
        emitCalendarApplyError("error", "unsupported_structured_location_for_operation", "Calendar clear_structured_location is supported only for update operations.")
    }
    if proposedStructuredLocationClearRequested && !location.isEmpty {
        emitCalendarApplyError("error", "conflicting_location_fields", "Calendar clear_structured_location requires empty location.")
    }
    let notes = stringValue(request, "notes")
    if title.isEmpty || startDateValue.isEmpty || endDateValue.isEmpty {
        emitCalendarApplyError("error", "missing_required_field", "Calendar apply requires title, start_date, and end_date.")
    }
    guard let startDate = eventDate(from: startDateValue),
          let endDate = eventDate(from: endDateValue),
          endDate > startDate
    else {
        emitCalendarApplyError("error", "invalid_time_range", "Calendar event start_date and end_date could not be parsed.")
    }
    if let recurrenceEndDateValue = proposedRecurrence["end_date"] as? String,
       !recurrenceEndDateValue.isEmpty {
        guard let recurrenceEndDate = eventDate(from: recurrenceEndDateValue),
              recurrenceEndDate > startDate,
              recurrenceEndDate.timeIntervalSince(startDate) <= maxRecurrenceEndDays * 24.0 * 60.0 * 60.0
        else {
            emitCalendarApplyError("error", "invalid_recurrence", "Calendar recurrence_end_date must be after start_date and within the bounded horizon.")
        }
    }
    let proposedTimeZone = timeZoneOrError(timeZoneIdentifier, "time_zone")
    let proposedAvailability = availabilityRequest(request, "availability", allowNotSupported: false)
    if allDay && proposedTimeZone != nil {
        emitCalendarApplyError("error", "unsupported_time_zone_for_all_day", "Calendar time_zone is supported only for timed events.")
    }

    if operation == "update" {
        let recurrenceClearRequested = boolValue(request, "clear_recurrence") ?? false
        let recurrenceUpdateScope = stringValue(request, "recurrence_update_scope")
        let selectedOccurrenceUpdateRequested = recurrenceUpdateScope == "this_event" && !recurrenceClearRequested
        let selectedOccurrenceAlarmUpdateRequested = boolValue(request, "selected_occurrence_alarm_update_requested") ?? false
        let futureSeriesScalarUpdateRequested = boolValue(request, "future_series_scalar_update_requested") ?? false
        let futureSeriesRescheduleRequested = boolValue(request, "future_series_reschedule_requested") ?? false
        let futureSeriesAvailabilityUpdateRequested = boolValue(request, "future_series_availability_update_requested") ?? false
        let futureSeriesEventURLUpdateRequested = boolValue(request, "future_series_event_url_update_requested") ?? false
        let futureSeriesStructuredLocationUpdateRequested = boolValue(request, "future_series_structured_location_update_requested") ?? false
        let futureSeriesDisplayAlarmUpdateRequested = boolValue(request, "future_series_display_alarm_update_requested") ?? false
        let futureSeriesActionAlarmUpdateRequested = boolValue(request, "future_series_action_alarm_update_requested") ?? false
        let futureSeriesAllDayUpdateRequested = boolValue(request, "future_series_all_day_update_requested") ?? false
        let futureSeriesCalendarMoveRequested = boolValue(request, "future_series_calendar_move_requested") ?? false
        let futureSeriesUpdateRequested = futureSeriesScalarUpdateRequested || futureSeriesRescheduleRequested || futureSeriesAvailabilityUpdateRequested || futureSeriesEventURLUpdateRequested || futureSeriesStructuredLocationUpdateRequested || futureSeriesDisplayAlarmUpdateRequested || futureSeriesActionAlarmUpdateRequested || futureSeriesAllDayUpdateRequested || futureSeriesCalendarMoveRequested
        let recurrenceUpdateRequested = request["recurrence"] != nil
            && (proposedRecurrence["recurrence_present"] as? Bool) == true
        let midSeriesRecurrenceReplaceRequested = recurrenceUpdateScope == "future_events"
            && !recurrenceClearRequested
            && recurrenceUpdateRequested
        if !recurrenceUpdateScope.isEmpty
            && recurrenceUpdateScope != "this_event"
            && !(recurrenceClearRequested && recurrenceUpdateScope == "future_events")
            && !midSeriesRecurrenceReplaceRequested
            && !futureSeriesUpdateRequested {
            emitCalendarApplyError("error", "unsupported_recurrence_update_scope", "Calendar recurring-event update supports this_event scope, or future_events for recurrence clear/replacement, title/location/notes, timed reschedule, availability updates, event URL updates, structured-location updates, display-alarm set/clear, action-alarm set/clear, all-day set/clear/date-only reschedule, or target-calendar move.")
        }
        if recurrenceClearRequested && recurrenceUpdateRequested {
            emitCalendarApplyError("error", "conflicting_recurrence_fields", "Use either recurrence fields or clear_recurrence, not both.")
        }
        if selectedOccurrenceUpdateRequested && (recurrenceClearRequested || recurrenceUpdateRequested) {
            emitCalendarApplyError("error", "unsupported_recurring_occurrence_update_shape", "Selected recurring occurrence update cannot change or clear recurrence.")
        }
        if futureSeriesUpdateRequested && (recurrenceUpdateScope != "future_events" || recurrenceClearRequested || recurrenceUpdateRequested) {
            emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series update requires recurrence_update_scope=future_events without recurrence clear/replacement.")
        }
        guard let expectedRecurrence = recurrenceRequest(request, key: "expected_recurrence") else {
            emitCalendarApplyError("error", "invalid_expected_recurrence", "Calendar expected recurrence must be a bounded daily, weekly, monthly, or yearly rule.")
        }
        let eventId = stringValue(request, "event_id")
        let expectedTitle = stringValue(request, "expected_title")
        let expectedCalendarTitle = stringValue(request, "expected_calendar_title")
        let expectedStartDateValue = stringValue(request, "expected_start_date")
        let expectedEndDateValue = stringValue(request, "expected_end_date")
        let expectedTimeZone = stringValue(request, "expected_time_zone")
        let expectedAllDay = boolValue(request, "expected_all_day") ?? false
        let expectedAvailability = availabilityRequest(request, "expected_availability", allowNotSupported: true)
        let expectedEventURLPresent = boolValue(request, "expected_event_url_present") ?? false
        let expectedEventURLSHA256 = stringValue(request, "expected_event_url_sha256")
        let adjacentOccurrenceEventURLPresent = boolValue(request, "adjacent_occurrence_event_url_present") ?? false
        let adjacentOccurrenceEventURLSHA256 = stringValue(request, "adjacent_occurrence_event_url_sha256")
        let adjacentOccurrenceLocationPresent = boolValue(request, "adjacent_occurrence_location_present") ?? false
        let adjacentOccurrenceLocationSHA256 = stringValue(request, "adjacent_occurrence_location_sha256")
        let adjacentOccurrenceStructuredLocationPresent = boolValue(request, "adjacent_occurrence_structured_location_present") ?? false
        let adjacentOccurrenceStructuredLocationSHA256 = stringValue(request, "adjacent_occurrence_structured_location_sha256")
        let adjacentOccurrenceAlarmStatePresent = boolValue(request, "adjacent_occurrence_alarm_state_present") ?? false
        let adjacentOccurrenceAlarmStateSHA256 = stringValue(request, "adjacent_occurrence_alarm_state_sha256")
        if expectedEventURLPresent && expectedEventURLSHA256.isEmpty {
            emitCalendarApplyError("error", "missing_required_field", "Calendar update requires expected_event_url_sha256 when expected_event_url_present is true.")
        }
        if !recurrenceUpdateScope.isEmpty && adjacentOccurrenceEventURLPresent && adjacentOccurrenceEventURLSHA256.isEmpty {
            emitCalendarApplyError("error", "missing_required_field", "Calendar selected occurrence update requires adjacent_occurrence_event_url_sha256 when the adjacent occurrence has an event URL.")
        }
        if !isSHA256Hex(adjacentOccurrenceLocationSHA256) {
            emitCalendarApplyError("error", "invalid_adjacent_occurrence_location_sha256", "Calendar adjacent occurrence location SHA-256 must be empty or lowercase hex.")
        }
        if !isSHA256Hex(adjacentOccurrenceStructuredLocationSHA256) {
            emitCalendarApplyError("error", "invalid_adjacent_occurrence_structured_location_sha256", "Calendar adjacent occurrence structured-location SHA-256 must be empty or lowercase hex.")
        }
        if !isSHA256Hex(adjacentOccurrenceAlarmStateSHA256) {
            emitCalendarApplyError("error", "invalid_adjacent_occurrence_alarm_state_sha256", "Calendar adjacent occurrence alarm-state SHA-256 must be empty or lowercase hex.")
        }
        if !recurrenceUpdateScope.isEmpty && adjacentOccurrenceLocationPresent && adjacentOccurrenceLocationSHA256.isEmpty {
            emitCalendarApplyError("error", "missing_required_field", "Calendar selected occurrence update requires adjacent_occurrence_location_sha256 when the adjacent occurrence has a location.")
        }
        if !recurrenceUpdateScope.isEmpty && adjacentOccurrenceStructuredLocationPresent && adjacentOccurrenceStructuredLocationSHA256.isEmpty {
            emitCalendarApplyError("error", "missing_required_field", "Calendar selected occurrence update requires adjacent_occurrence_structured_location_sha256 when the adjacent occurrence has a structured location.")
        }
        if !recurrenceUpdateScope.isEmpty && adjacentOccurrenceAlarmStatePresent && adjacentOccurrenceAlarmStateSHA256.isEmpty {
            emitCalendarApplyError("error", "missing_required_field", "Calendar selected occurrence update requires adjacent_occurrence_alarm_state_sha256 when the adjacent occurrence has alarms.")
        }
        _ = timeZoneOrError(expectedTimeZone, "expected_time_zone")
        if expectedAllDay && !expectedTimeZone.isEmpty {
            emitCalendarApplyError("error", "unsupported_time_zone_for_all_day", "Calendar expected_time_zone is supported only for timed events.")
        }
        guard let expectedAlarmOffsetsMinutes = intArrayValue(request, "expected_alarm_offsets_minutes") else {
            emitCalendarApplyError("error", "invalid_alarm_offsets", "Calendar expected alarm offsets must be integer minute offsets.")
        }
        guard let expectedAlarmAbsoluteDates = dateStringArrayValue(request, "expected_alarm_absolute_dates") else {
            emitCalendarApplyError("error", "invalid_alarm_absolute_dates", "Calendar expected absolute alarm dates must be ISO 8601 timestamps with timezones.")
        }
        if !expectedAlarmOffsetsMinutes.isEmpty && !expectedAlarmAbsoluteDates.isEmpty {
            emitCalendarApplyError("error", "conflicting_alarm_fields", "Use either expected alarm offsets or expected absolute alarm dates, not both.")
        }
        guard let expectedAlarmSoundName = alarmSoundNameValue(request, "expected_alarm_sound_name") else {
            emitCalendarApplyError("error", "invalid_alarm_sound_name", "Calendar expected alarm sound name must be a bounded system sound name.")
        }
        if !expectedAlarmSoundName.isEmpty && expectedAlarmOffsetsMinutes.isEmpty && expectedAlarmAbsoluteDates.isEmpty {
            emitCalendarApplyError("error", "missing_alarm_trigger", "Calendar expected alarm sound name requires expected alarm offsets or absolute alarm dates.")
        }
        let expectedAlarmEmailAddressSHA256 = stringValue(request, "expected_alarm_email_address_sha256")
        if !isSHA256Hex(expectedAlarmEmailAddressSHA256) {
            emitCalendarApplyError("error", "invalid_expected_alarm_email_address_sha256", "Calendar expected alarm email address SHA-256 must be empty or lowercase hex.")
        }
        if !expectedAlarmEmailAddressSHA256.isEmpty && expectedAlarmOffsetsMinutes.isEmpty && expectedAlarmAbsoluteDates.isEmpty {
            emitCalendarApplyError("error", "missing_alarm_trigger", "Calendar expected alarm email address requires expected alarm offsets or absolute alarm dates.")
        }
        guard let expectedAlarmProximity = alarmProximityValue(request, "expected_alarm_proximity") else {
            emitCalendarApplyError("error", "invalid_alarm_proximity", "Calendar expected alarm proximity must be enter or leave.")
        }
        let expectedAlarmStructuredLocation = structuredLocationRequest(request, "expected_alarm_structured_location")
        if !expectedAlarmProximity.isEmpty && expectedAlarmStructuredLocation == nil {
            emitCalendarApplyError("error", "missing_alarm_structured_location", "Calendar expected alarm proximity requires expected alarm structured location.")
        }
        if expectedAlarmProximity.isEmpty && expectedAlarmStructuredLocation != nil {
            emitCalendarApplyError("error", "missing_alarm_proximity", "Calendar expected alarm structured location requires expected alarm proximity.")
        }
        if !expectedAlarmProximity.isEmpty && (!expectedAlarmOffsetsMinutes.isEmpty || !expectedAlarmAbsoluteDates.isEmpty || !expectedAlarmSoundName.isEmpty || !expectedAlarmEmailAddressSHA256.isEmpty) {
            emitCalendarApplyError("error", "conflicting_alarm_fields", "Use only one expected alarm trigger: offsets, absolute dates, or geofence.")
        }
        if [!expectedAlarmSoundName.isEmpty, !expectedAlarmProximity.isEmpty, !expectedAlarmEmailAddressSHA256.isEmpty].filter({ $0 }).count > 1 {
            emitCalendarApplyError("error", "conflicting_alarm_fields", "Use only one expected alarm action: sound, geofence, or email.")
        }
        let expectedLocation = stringValue(request, "expected_location")
        let expectedStructuredLocationPresent = boolValue(request, "expected_structured_location_present")
        let expectedStructuredLocation = structuredLocationRequest(request, "expected_structured_location")
        let expectedNotes = stringValue(request, "expected_notes")
        if eventId.isEmpty || expectedTitle.isEmpty || expectedCalendarTitle.isEmpty || expectedStartDateValue.isEmpty || expectedEndDateValue.isEmpty {
            emitCalendarApplyError("error", "missing_required_field", "Calendar update requires event_id and expected current state.")
        }
        guard let expectedStartDate = eventDate(from: expectedStartDateValue),
              let expectedEndDate = eventDate(from: expectedEndDateValue),
              expectedEndDate > expectedStartDate
        else {
            emitCalendarApplyError("error", "invalid_expected_state", "Calendar expected state dates could not be parsed.")
        }
        if futureSeriesScalarUpdateRequested {
            let scalarChanged = title != expectedTitle || location != expectedLocation || notes != expectedNotes
            if !scalarChanged {
                emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series scalar update requires a title, plain location, or notes change.")
            }
        }
        if futureSeriesRescheduleRequested {
            let timedChanged = !eventDatesMatch(startDate, expectedStartDate)
                || !eventDatesMatch(endDate, expectedEndDate)
                || timeZoneIdentifier != expectedTimeZone
            if !timedChanged {
                emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series timed reschedule requires a start, end, or time-zone change.")
            }
            if allDay || expectedAllDay {
                emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series timed reschedule supports timed events only.")
            }
            if timeZoneIdentifier.isEmpty || expectedTimeZone.isEmpty {
                emitCalendarApplyError("error", "missing_required_field", "Calendar future-series timed reschedule requires explicit time_zone and expected_time_zone.")
            }
        }
        if futureSeriesAvailabilityUpdateRequested && (futureSeriesScalarUpdateRequested || futureSeriesRescheduleRequested) {
            emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series availability update cannot co-mutate scalar or timed fields.")
        }
        if futureSeriesAvailabilityUpdateRequested {
            guard let proposedAvailability = proposedAvailability,
                  let expectedAvailability = expectedAvailability else {
                emitCalendarApplyError("error", "missing_required_field", "Calendar future-series availability update requires availability and expected_availability.")
            }
            if proposedAvailability.rawValue == expectedAvailability.rawValue {
                emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series availability update requires availability different from expected_availability.")
            }
        }
        if futureSeriesEventURLUpdateRequested && (futureSeriesScalarUpdateRequested || futureSeriesRescheduleRequested || futureSeriesAvailabilityUpdateRequested) {
            emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series event URL update cannot co-mutate scalar, timed, or availability fields.")
        }
        if futureSeriesEventURLUpdateRequested && !proposedEventURLRequested && !proposedEventURLClearRequested {
            emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series event URL update requires event_url or clear_event_url.")
        }
        if futureSeriesEventURLUpdateRequested && proposedEventURLRequested && expectedEventURLPresent && proposedEventURLSHA256 == expectedEventURLSHA256 {
            emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series event URL update requires a URL different from expected_event_url_sha256.")
        }
        if futureSeriesStructuredLocationUpdateRequested && (futureSeriesScalarUpdateRequested || futureSeriesRescheduleRequested || futureSeriesAvailabilityUpdateRequested || futureSeriesEventURLUpdateRequested) {
            emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series structured-location update cannot co-mutate scalar, timed, availability, or event URL fields.")
        }
        if futureSeriesStructuredLocationUpdateRequested && proposedStructuredLocation == nil && !proposedStructuredLocationClearRequested {
            emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series structured-location update requires structured_location or clear_structured_location.")
        }
        if futureSeriesStructuredLocationUpdateRequested
            && proposedStructuredLocationClearRequested
            && expectedStructuredLocation == nil {
            emitCalendarApplyError("error", "missing_required_field", "Calendar future-series structured-location clear requires expected_structured_location.")
        }
        if futureSeriesStructuredLocationUpdateRequested,
           let proposedStructuredLocation = proposedStructuredLocation,
           structuredLocationPayloadsEqual(proposedStructuredLocation, expectedStructuredLocation),
           location == expectedLocation {
            emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series structured-location update requires a value different from expected_structured_location.")
        }
        if futureSeriesDisplayAlarmUpdateRequested && (futureSeriesScalarUpdateRequested || futureSeriesRescheduleRequested || futureSeriesAvailabilityUpdateRequested || futureSeriesEventURLUpdateRequested || futureSeriesStructuredLocationUpdateRequested) {
            emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series display-alarm update cannot co-mutate scalar, timed, availability, event URL, or structured-location fields.")
        }
        if futureSeriesDisplayAlarmUpdateRequested
            && proposedAlarmOffsetsMinutes.isEmpty
            && proposedAlarmAbsoluteDates.isEmpty
            && expectedAlarmOffsetsMinutes.isEmpty
            && expectedAlarmAbsoluteDates.isEmpty {
            emitCalendarApplyError("error", "missing_required_field", "Calendar future-series display-alarm clear requires expected alarm offsets or absolute alarm dates.")
        }
        if futureSeriesDisplayAlarmUpdateRequested
            && proposedAlarmOffsetsMinutes == expectedAlarmOffsetsMinutes
            && proposedAlarmAbsoluteDates == expectedAlarmAbsoluteDates {
            emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series display-alarm update requires alarm offsets or absolute dates different from the expected display-alarm state.")
        }
        if futureSeriesActionAlarmUpdateRequested && (futureSeriesScalarUpdateRequested || futureSeriesRescheduleRequested || futureSeriesAvailabilityUpdateRequested || futureSeriesEventURLUpdateRequested || futureSeriesStructuredLocationUpdateRequested || futureSeriesDisplayAlarmUpdateRequested) {
            emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series action-alarm update cannot co-mutate scalar, timed, availability, event URL, structured-location, or display-alarm fields.")
        }
        if futureSeriesActionAlarmUpdateRequested
            && proposedAlarmSoundName.isEmpty
            && proposedAlarmEmailAddressSHA256.isEmpty
            && proposedAlarmProximity.isEmpty
            && proposedAlarmStructuredLocation == nil
            && expectedAlarmSoundName.isEmpty
            && expectedAlarmEmailAddressSHA256.isEmpty
            && expectedAlarmProximity.isEmpty
            && expectedAlarmStructuredLocation == nil {
            emitCalendarApplyError("error", "missing_required_field", "Calendar future-series action-alarm clear requires expected action-alarm state.")
        }
        if futureSeriesActionAlarmUpdateRequested
            && proposedAlarmSoundName == expectedAlarmSoundName
            && proposedAlarmEmailAddressSHA256 == expectedAlarmEmailAddressSHA256
            && proposedAlarmProximity == expectedAlarmProximity
            && structuredLocationPayloadsEqual(proposedAlarmStructuredLocation, expectedAlarmStructuredLocation) {
            emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series action-alarm update requires an action-alarm state different from the expected action-alarm state.")
        }
        if futureSeriesAllDayUpdateRequested && (futureSeriesScalarUpdateRequested || futureSeriesRescheduleRequested || futureSeriesAvailabilityUpdateRequested || futureSeriesEventURLUpdateRequested || futureSeriesStructuredLocationUpdateRequested || futureSeriesDisplayAlarmUpdateRequested || futureSeriesActionAlarmUpdateRequested) {
            emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series all-day update cannot co-mutate scalar, timed, availability, event URL, structured-location, display-alarm, or action-alarm fields.")
        }
        if futureSeriesAllDayUpdateRequested
            && allDay
            && (!isDateOnlyString(startDateValue) || !isDateOnlyString(endDateValue)) {
            emitCalendarApplyError("error", "missing_required_field", "Calendar future-series all-day update requires date-only start_date and end_date.")
        }
        if futureSeriesAllDayUpdateRequested
            && allDay
            && !expectedAllDay
            && expectedTimeZone.isEmpty {
            emitCalendarApplyError("error", "missing_required_field", "Calendar future-series all-day update requires expected_time_zone when the current occurrence is timed.")
        }
        if futureSeriesAllDayUpdateRequested
            && !allDay
            && expectedAllDay
            && timeZoneIdentifier.isEmpty {
            emitCalendarApplyError("error", "missing_required_field", "Calendar future-series timed update from all-day requires explicit time_zone.")
        }
        if futureSeriesAllDayUpdateRequested
            && allDay == expectedAllDay
            && (!allDay
                || (eventDatesMatch(startDate, expectedStartDate) && eventDatesMatch(endDate, expectedEndDate))) {
            emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series all-day update requires an all-day state change or an all-day date-only reschedule.")
        }
        if futureSeriesCalendarMoveRequested && (futureSeriesScalarUpdateRequested || futureSeriesRescheduleRequested || futureSeriesAvailabilityUpdateRequested || futureSeriesEventURLUpdateRequested || futureSeriesStructuredLocationUpdateRequested || futureSeriesDisplayAlarmUpdateRequested || futureSeriesActionAlarmUpdateRequested || futureSeriesAllDayUpdateRequested) {
            emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series target-calendar move cannot co-mutate scalar, timed, availability, event URL, structured-location, display-alarm, action-alarm, or all-day fields.")
        }
        if futureSeriesUpdateRequested {
            if !eventDatesMatch(startDate, expectedStartDate)
                || !eventDatesMatch(endDate, expectedEndDate)
                || allDay != expectedAllDay {
                if !futureSeriesAllDayUpdateRequested
                    && (!futureSeriesRescheduleRequested || allDay != expectedAllDay) {
                    emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series update cannot change time/all-day state outside the timed reschedule or all-day gates.")
                }
            }
            if proposedAvailability != nil && !futureSeriesAvailabilityUpdateRequested {
                emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series update cannot change availability.")
            }
            if (proposedEventURLRequested || proposedEventURLClearRequested) && !futureSeriesEventURLUpdateRequested {
                emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series event URL update cannot co-mutate scalar, timed, availability, recurrence, calendar, structured-location, or alarm fields.")
            }
            if (proposedStructuredLocation != nil || proposedStructuredLocationClearRequested) && !futureSeriesStructuredLocationUpdateRequested {
                emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series structured-location update cannot co-mutate scalar, timed, availability, event URL, recurrence, calendar, or alarm fields.")
            }
            if (proposedAlarmOffsetsMinutes != expectedAlarmOffsetsMinutes
                || proposedAlarmAbsoluteDates != expectedAlarmAbsoluteDates)
                && !futureSeriesDisplayAlarmUpdateRequested
                && !futureSeriesActionAlarmUpdateRequested {
                emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series display-alarm update cannot co-mutate scalar, timed, availability, event URL, structured-location, recurrence, or calendar fields.")
            }
            if (proposedAlarmSoundName != expectedAlarmSoundName
                || proposedAlarmEmailAddressSHA256 != expectedAlarmEmailAddressSHA256
                || proposedAlarmProximity != expectedAlarmProximity
                || !structuredLocationPayloadsEqual(proposedAlarmStructuredLocation, expectedAlarmStructuredLocation))
                && !futureSeriesActionAlarmUpdateRequested {
                emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series update cannot change action alarms.")
            }
        }
        let event: EKEvent
        var futureOccurrenceStartDate: Date? = nil
        var futureOccurrenceEndDate: Date? = nil
        var adjacentOccurrenceStartDate: Date? = nil
        var adjacentOccurrenceEndDate: Date? = nil
        var previousOccurrenceVerifiedAbsent = false
        var previousOccurrenceVerifiedPresent = false
        var previousOccurrenceStartDate: Date? = nil
        var previousOccurrenceEndDate: Date? = nil
        if recurrenceClearRequested {
            let occurrenceStartDateValue = stringValue(request, "occurrence_start_date")
            let occurrenceEndDateValue = stringValue(request, "occurrence_end_date")
            let futureOccurrenceStartDateValue = stringValue(request, "future_occurrence_start_date")
            let futureOccurrenceEndDateValue = stringValue(request, "future_occurrence_end_date")
            let previousOccurrenceStartDateValue = stringValue(request, "previous_occurrence_start_date")
            let previousOccurrenceEndDateValue = stringValue(request, "previous_occurrence_end_date")
            guard let occurrenceStartDate = eventDate(from: occurrenceStartDateValue),
                  let occurrenceEndDate = eventDate(from: occurrenceEndDateValue),
                  occurrenceEndDate > occurrenceStartDate
            else {
                emitCalendarApplyError("error", "missing_occurrence_identity", "Calendar clear_recurrence requires selected occurrence start/end identity.")
            }
            if !eventDatesMatch(occurrenceStartDate, expectedStartDate) || !eventDatesMatch(occurrenceEndDate, expectedEndDate) {
                emitCalendarApplyError("error", "expected_state_mismatch", "Calendar occurrence identity did not match expected state.")
            }
            guard let futureStartDate = eventDate(from: futureOccurrenceStartDateValue),
                  let futureEndDate = eventDate(from: futureOccurrenceEndDateValue),
                  futureEndDate > futureStartDate
            else {
                emitCalendarApplyError("error", "missing_future_occurrence_identity", "Calendar clear_recurrence requires future occurrence identity.")
            }
            if futureStartDate <= occurrenceStartDate {
                emitCalendarApplyError("error", "invalid_recurrence_clear_scope", "Calendar clear_recurrence requires selected and future occurrence order.")
            }
            if recurrenceUpdateScope == "future_events" {
                guard let previousStartDate = eventDate(from: previousOccurrenceStartDateValue),
                      let previousEndDate = eventDate(from: previousOccurrenceEndDateValue),
                      previousEndDate > previousStartDate
                else {
                    emitCalendarApplyError("error", "missing_previous_occurrence_identity", "Calendar mid-series clear_recurrence requires previous occurrence identity.")
                }
                if previousStartDate >= occurrenceStartDate {
                    emitCalendarApplyError("error", "invalid_recurrence_clear_scope", "Calendar mid-series clear_recurrence requires previous, selected, and future occurrence order.")
                }
                previousOccurrenceStartDate = previousStartDate
                previousOccurrenceEndDate = previousEndDate
            }
            let candidates = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: occurrenceStartDate,
                endDate: occurrenceEndDate
            )
            if candidates.isEmpty {
                emitCalendarApplyError("not_found", "target_not_found", "Calendar target occurrence was not found.")
            }
            if candidates.count > 1 {
                emitCalendarApplyError("error", "ambiguous_event_occurrence", "Calendar occurrence handle matched more than one event.")
            }
            let previousCandidates = relativeOccurrenceCandidates(
                store,
                eventId: eventId,
                selectedStartDate: occurrenceStartDate,
                direction: "previous"
            )
            if recurrenceUpdateScope == "future_events" {
                let exactPreviousCandidates = occurrenceCandidates(
                    store,
                    eventId: eventId,
                    startDate: previousOccurrenceStartDate!,
                    endDate: previousOccurrenceEndDate!
                )
                if exactPreviousCandidates.isEmpty {
                    emitCalendarApplyError("error", "previous_occurrence_not_found", "Calendar previous occurrence was not found before mid-series recurrence clear.")
                }
                if exactPreviousCandidates.count > 1 {
                    emitCalendarApplyError("error", "ambiguous_previous_occurrence", "Calendar previous occurrence identity matched more than one event.")
                }
                if previousCandidates.isEmpty
                    || !eventDatesMatch(exactPreviousCandidates[0].startDate, previousCandidates[0].startDate)
                    || !eventDatesMatch(exactPreviousCandidates[0].endDate, previousCandidates[0].endDate) {
                    emitCalendarApplyError("error", "stale_occurrence_identity", "Calendar previous occurrence identity did not match the selected series.")
                }
                previousOccurrenceVerifiedPresent = true
            } else if !previousCandidates.isEmpty {
                emitCalendarApplyError("error", "previous_occurrence_present", "Calendar clear_recurrence requires selecting the first same-series occurrence.")
            }
            let futureCandidates = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: futureStartDate,
                endDate: futureEndDate
            )
            if futureCandidates.isEmpty {
                emitCalendarApplyError("error", "future_occurrence_not_found", "Calendar future occurrence was not found before recurrence clear.")
            }
            if futureCandidates.count > 1 {
                emitCalendarApplyError("error", "ambiguous_future_occurrence", "Calendar future occurrence identity matched more than one event.")
            }
            event = candidates[0]
            futureOccurrenceStartDate = futureStartDate
            futureOccurrenceEndDate = futureEndDate
            previousOccurrenceVerifiedAbsent = recurrenceUpdateScope != "future_events"
        } else if midSeriesRecurrenceReplaceRequested {
            let occurrenceStartDateValue = stringValue(request, "occurrence_start_date")
            let occurrenceEndDateValue = stringValue(request, "occurrence_end_date")
            let previousOccurrenceStartDateValue = stringValue(request, "previous_occurrence_start_date")
            let previousOccurrenceEndDateValue = stringValue(request, "previous_occurrence_end_date")
            let futureOccurrenceStartDateValue = stringValue(request, "future_occurrence_start_date")
            let futureOccurrenceEndDateValue = stringValue(request, "future_occurrence_end_date")
            guard let occurrenceStartDate = eventDate(from: occurrenceStartDateValue),
                  let occurrenceEndDate = eventDate(from: occurrenceEndDateValue),
                  occurrenceEndDate > occurrenceStartDate
            else {
                emitCalendarApplyError("error", "missing_occurrence_identity", "Calendar recurrence replacement requires selected occurrence start/end identity.")
            }
            if !eventDatesMatch(occurrenceStartDate, expectedStartDate) || !eventDatesMatch(occurrenceEndDate, expectedEndDate) {
                emitCalendarApplyError("error", "expected_state_mismatch", "Calendar occurrence identity did not match expected state.")
            }
            guard let previousStartDate = eventDate(from: previousOccurrenceStartDateValue),
                  let previousEndDate = eventDate(from: previousOccurrenceEndDateValue),
                  previousEndDate > previousStartDate
            else {
                emitCalendarApplyError("error", "missing_previous_occurrence_identity", "Calendar mid-series recurrence replacement requires previous occurrence identity.")
            }
            guard let futureStartDate = eventDate(from: futureOccurrenceStartDateValue),
                  let futureEndDate = eventDate(from: futureOccurrenceEndDateValue),
                  futureEndDate > futureStartDate
            else {
                emitCalendarApplyError("error", "missing_future_occurrence_identity", "Calendar mid-series recurrence replacement requires future occurrence identity.")
            }
            if previousStartDate >= occurrenceStartDate || futureStartDate <= occurrenceStartDate {
                emitCalendarApplyError("error", "invalid_recurrence_replacement_scope", "Calendar mid-series recurrence replacement requires previous, selected, and future occurrence order.")
            }
            let candidates = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: occurrenceStartDate,
                endDate: occurrenceEndDate
            )
            if candidates.isEmpty {
                emitCalendarApplyError("not_found", "target_not_found", "Calendar target occurrence was not found.")
            }
            if candidates.count > 1 {
                emitCalendarApplyError("error", "ambiguous_event_occurrence", "Calendar occurrence handle matched more than one event.")
            }
            let exactPreviousCandidates = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: previousStartDate,
                endDate: previousEndDate
            )
            let previousCandidates = relativeOccurrenceCandidates(
                store,
                eventId: eventId,
                selectedStartDate: occurrenceStartDate,
                direction: "previous"
            )
            if exactPreviousCandidates.isEmpty {
                emitCalendarApplyError("error", "previous_occurrence_not_found", "Calendar previous occurrence was not found before mid-series recurrence replacement.")
            }
            if exactPreviousCandidates.count > 1 {
                emitCalendarApplyError("error", "ambiguous_previous_occurrence", "Calendar previous occurrence identity matched more than one event.")
            }
            if previousCandidates.isEmpty
                || !eventDatesMatch(exactPreviousCandidates[0].startDate, previousCandidates[0].startDate)
                || !eventDatesMatch(exactPreviousCandidates[0].endDate, previousCandidates[0].endDate) {
                emitCalendarApplyError("error", "stale_occurrence_identity", "Calendar previous occurrence identity did not match the selected series.")
            }
            let futureCandidates = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: futureStartDate,
                endDate: futureEndDate
            )
            if futureCandidates.isEmpty {
                emitCalendarApplyError("error", "future_occurrence_not_found", "Calendar future occurrence was not found before recurrence replacement.")
            }
            if futureCandidates.count > 1 {
                emitCalendarApplyError("error", "ambiguous_future_occurrence", "Calendar future occurrence identity matched more than one event.")
            }
            event = candidates[0]
            previousOccurrenceStartDate = previousStartDate
            previousOccurrenceEndDate = previousEndDate
            futureOccurrenceStartDate = futureStartDate
            futureOccurrenceEndDate = futureEndDate
            previousOccurrenceVerifiedPresent = true
        } else if futureSeriesUpdateRequested {
            let occurrenceStartDateValue = stringValue(request, "occurrence_start_date")
            let occurrenceEndDateValue = stringValue(request, "occurrence_end_date")
            let previousOccurrenceStartDateValue = stringValue(request, "previous_occurrence_start_date")
            let previousOccurrenceEndDateValue = stringValue(request, "previous_occurrence_end_date")
            let futureOccurrenceStartDateValue = stringValue(request, "future_occurrence_start_date")
            let futureOccurrenceEndDateValue = stringValue(request, "future_occurrence_end_date")
            guard let occurrenceStartDate = eventDate(from: occurrenceStartDateValue),
                  let occurrenceEndDate = eventDate(from: occurrenceEndDateValue),
                  occurrenceEndDate > occurrenceStartDate
            else {
                emitCalendarApplyError("error", "missing_occurrence_identity", "Calendar future-series update requires selected occurrence start/end identity.")
            }
            if !eventDatesMatch(occurrenceStartDate, expectedStartDate) || !eventDatesMatch(occurrenceEndDate, expectedEndDate) {
                emitCalendarApplyError("error", "expected_state_mismatch", "Calendar occurrence identity did not match expected state.")
            }
            guard let previousStartDate = eventDate(from: previousOccurrenceStartDateValue),
                  let previousEndDate = eventDate(from: previousOccurrenceEndDateValue),
                  previousEndDate > previousStartDate
            else {
                emitCalendarApplyError("error", "missing_previous_occurrence_identity", "Calendar future-series update requires previous occurrence identity.")
            }
            guard let futureStartDate = eventDate(from: futureOccurrenceStartDateValue),
                  let futureEndDate = eventDate(from: futureOccurrenceEndDateValue),
                  futureEndDate > futureStartDate
            else {
                emitCalendarApplyError("error", "missing_future_occurrence_identity", "Calendar future-series update requires future occurrence identity.")
            }
            if previousStartDate >= occurrenceStartDate || futureStartDate <= occurrenceStartDate {
                emitCalendarApplyError("error", "invalid_future_series_update_scope", "Calendar future-series update requires previous, selected, and future occurrence order.")
            }
            let candidates = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: occurrenceStartDate,
                endDate: occurrenceEndDate
            )
            if candidates.isEmpty {
                emitCalendarApplyError("not_found", "target_not_found", "Calendar target occurrence was not found.")
            }
            if candidates.count > 1 {
                emitCalendarApplyError("error", "ambiguous_event_occurrence", "Calendar occurrence handle matched more than one event.")
            }
            let exactPreviousCandidates = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: previousStartDate,
                endDate: previousEndDate
            )
            let previousCandidates = relativeOccurrenceCandidates(
                store,
                eventId: eventId,
                selectedStartDate: occurrenceStartDate,
                direction: "previous"
            )
            if exactPreviousCandidates.isEmpty {
                emitCalendarApplyError("error", "previous_occurrence_not_found", "Calendar previous occurrence was not found before future-series update.")
            }
            if exactPreviousCandidates.count > 1 {
                emitCalendarApplyError("error", "ambiguous_previous_occurrence", "Calendar previous occurrence identity matched more than one event.")
            }
            if previousCandidates.isEmpty
                || !eventDatesMatch(exactPreviousCandidates[0].startDate, previousCandidates[0].startDate)
                || !eventDatesMatch(exactPreviousCandidates[0].endDate, previousCandidates[0].endDate) {
                emitCalendarApplyError("error", "stale_occurrence_identity", "Calendar previous occurrence identity did not match the selected series.")
            }
            let futureCandidates = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: futureStartDate,
                endDate: futureEndDate
            )
            if futureCandidates.isEmpty {
                emitCalendarApplyError("error", "future_occurrence_not_found", "Calendar future occurrence was not found before future-series update.")
            }
            if futureCandidates.count > 1 {
                emitCalendarApplyError("error", "ambiguous_future_occurrence", "Calendar future occurrence identity matched more than one event.")
            }
            event = candidates[0]
            previousOccurrenceStartDate = previousStartDate
            previousOccurrenceEndDate = previousEndDate
            futureOccurrenceStartDate = futureStartDate
            futureOccurrenceEndDate = futureEndDate
            previousOccurrenceVerifiedPresent = true
        } else if selectedOccurrenceUpdateRequested {
            let occurrenceStartDateValue = stringValue(request, "occurrence_start_date")
            let occurrenceEndDateValue = stringValue(request, "occurrence_end_date")
            let adjacentOccurrenceStartDateValue = stringValue(request, "adjacent_occurrence_start_date")
            let adjacentOccurrenceEndDateValue = stringValue(request, "adjacent_occurrence_end_date")
            guard let occurrenceStartDate = eventDate(from: occurrenceStartDateValue),
                  let occurrenceEndDate = eventDate(from: occurrenceEndDateValue),
                  occurrenceEndDate > occurrenceStartDate
            else {
                emitCalendarApplyError("error", "missing_occurrence_identity", "Calendar selected occurrence update requires selected occurrence start/end identity.")
            }
            if !eventDatesMatch(occurrenceStartDate, expectedStartDate) || !eventDatesMatch(occurrenceEndDate, expectedEndDate) {
                emitCalendarApplyError("error", "expected_state_mismatch", "Calendar occurrence identity did not match expected state.")
            }
            guard let adjacentStartDate = eventDate(from: adjacentOccurrenceStartDateValue),
                  let adjacentEndDate = eventDate(from: adjacentOccurrenceEndDateValue),
                  adjacentEndDate > adjacentStartDate
            else {
                emitCalendarApplyError("error", "missing_adjacent_occurrence_identity", "Calendar selected occurrence update requires adjacent occurrence identity.")
            }
            let candidates = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: occurrenceStartDate,
                endDate: occurrenceEndDate
            )
            if candidates.isEmpty {
                emitCalendarApplyError("not_found", "target_not_found", "Calendar target occurrence was not found.")
            }
            if candidates.count > 1 {
                emitCalendarApplyError("error", "ambiguous_event_occurrence", "Calendar occurrence handle matched more than one event.")
            }
            let adjacentCandidates = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: adjacentStartDate,
                endDate: adjacentEndDate
            )
            if adjacentCandidates.isEmpty {
                emitCalendarApplyError("error", "adjacent_occurrence_not_found", "Calendar adjacent occurrence was not found before selected occurrence update.")
            }
            if adjacentCandidates.count > 1 {
                emitCalendarApplyError("error", "ambiguous_adjacent_occurrence", "Calendar adjacent occurrence identity matched more than one event.")
            }
            if !eventURLStateMatches(adjacentCandidates[0], present: adjacentOccurrenceEventURLPresent, sha256: adjacentOccurrenceEventURLSHA256) {
                emitCalendarApplyError("error", "expected_state_mismatch", "Calendar adjacent occurrence URL state did not match expected state.")
            }
            if !eventLocationProofStateMatches(
                adjacentCandidates[0],
                locationPresent: adjacentOccurrenceLocationPresent,
                locationSHA256: adjacentOccurrenceLocationSHA256,
                structuredLocationPresent: adjacentOccurrenceStructuredLocationPresent,
                structuredLocationSHA256: adjacentOccurrenceStructuredLocationSHA256
            ) {
                emitCalendarApplyError("error", "expected_state_mismatch", "Calendar adjacent occurrence location state did not match expected state.")
            }
            if !eventAlarmProofStateMatches(adjacentCandidates[0], present: adjacentOccurrenceAlarmStatePresent, sha256: adjacentOccurrenceAlarmStateSHA256) {
                emitCalendarApplyError("error", "expected_state_mismatch", "Calendar adjacent occurrence alarm state did not match expected state.")
            }
            event = candidates[0]
            adjacentOccurrenceStartDate = adjacentStartDate
            adjacentOccurrenceEndDate = adjacentEndDate
        } else {
            guard let resolvedEvent = store.event(withIdentifier: eventId) else {
                emitCalendarApplyError("not_found", "target_not_found", "Calendar target was not found.")
            }
            event = resolvedEvent
        }
        if (event.calendar?.title ?? "") == expectedCalendarTitle && calendarTitleIsAmbiguous(store, expectedCalendarTitle) {
            emitCalendarApplyError("error", "ambiguous_expected_calendar", "Calendar expected calendar title matched more than one calendar.")
        }
        if eventHasUnsupportedAttendeeOrAlarmState(event) {
            emitCalendarApplyError("error", "unsupported_event_state", "Calendar event has unsupported attendee or alarm state.")
        }
        if let expectedStructuredLocationPresent = expectedStructuredLocationPresent,
           (structuredLocationPayload(event) != nil) != expectedStructuredLocationPresent {
            emitCalendarApplyError("error", "expected_state_mismatch", "Calendar event did not match expected structured location state.")
        }
        if !eventMatchesState(event, title: expectedTitle, calendarTitle: expectedCalendarTitle, startDate: expectedStartDate, endDate: expectedEndDate, expectedTimeZone: expectedTimeZone, allDay: expectedAllDay, expectedAvailability: expectedAvailability, alarmOffsetsMinutes: expectedAlarmOffsetsMinutes, alarmAbsoluteDates: expectedAlarmAbsoluteDates, alarmSoundName: expectedAlarmSoundName, alarmEmailAddressSHA256: expectedAlarmEmailAddressSHA256, alarmProximity: expectedAlarmProximity, alarmStructuredLocation: expectedAlarmStructuredLocation, eventURLPresent: expectedEventURLPresent, eventURLSHA256: expectedEventURLSHA256, location: expectedLocation, structuredLocation: expectedStructuredLocation, notes: expectedNotes) {
            emitCalendarApplyError("error", "expected_state_mismatch", "Calendar event did not match expected state.")
        }
        let targetCalendarId = stringValue(request, "target_calendar_id")
        if futureSeriesCalendarMoveRequested && targetCalendarId.isEmpty {
            emitCalendarApplyError("error", "missing_required_field", "Calendar future-series target-calendar move requires an exact resolved target calendar.")
        }
        if futureSeriesUpdateRequested && !futureSeriesCalendarMoveRequested && !targetCalendarId.isEmpty {
            emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar future-series update cannot move calendars.")
        }
        if (recurrenceClearRequested || midSeriesRecurrenceReplaceRequested) && !targetCalendarId.isEmpty {
            emitCalendarApplyError("error", "unsupported_future_series_update_shape", "Calendar recurrence clear or replacement cannot move calendars.")
        }
        let originalCalendarIdentifier = event.calendar?.calendarIdentifier ?? ""
        if selectedOccurrenceUpdateRequested {
            if allDay && (!isDateOnlyString(startDateValue) || !isDateOnlyString(endDateValue)) {
                emitCalendarApplyError("error", "missing_required_field", "Selected recurring occurrence all-day update requires date-only start_date and end_date.")
            }
            if allDay && !expectedAllDay && expectedTimeZone.isEmpty {
                emitCalendarApplyError("error", "missing_required_field", "Selected recurring occurrence all-day update requires expected_time_zone when the current occurrence is timed.")
            }
            if !allDay && expectedAllDay && timeZoneIdentifier.isEmpty {
                emitCalendarApplyError("error", "missing_required_field", "Selected recurring occurrence timed update from all-day requires explicit time_zone.")
            }
        }
        let targetCalendar: EKCalendar?
        if !targetCalendarId.isEmpty {
            guard let resolvedTargetCalendar = store.calendar(withIdentifier: targetCalendarId) else {
                emitCalendarApplyError("not_found", "target_calendar_not_found", "Calendar target was not found.")
            }
            if !resolvedTargetCalendar.allowsContentModifications {
                emitCalendarApplyError("error", "target_calendar_not_writable", "Calendar target does not allow event changes.")
            }
            targetCalendar = resolvedTargetCalendar
        } else {
            targetCalendar = nil
        }
        if let proposedAvailability = proposedAvailability,
           !calendarSupportsAvailability(targetCalendar ?? event.calendar, proposedAvailability) {
            emitCalendarApplyError("error", "availability_not_supported", "Calendar target does not support the requested availability value.")
        }
        if let expectedRecurrencePresent = boolValue(request, "expected_recurrence_present"),
           eventHasRecurrence(event) != expectedRecurrencePresent {
            emitCalendarApplyError("error", "expected_state_mismatch", "Calendar event did not match expected recurrence state.")
        }
        if recurrenceClearRequested {
            if !eventHasRecurrence(event) || !recurrenceMatches(event, expectedRecurrence) {
                emitCalendarApplyError("error", "expected_state_mismatch", "Calendar event did not match expected recurrence state.")
            }
        } else if selectedOccurrenceUpdateRequested || midSeriesRecurrenceReplaceRequested || futureSeriesUpdateRequested {
            if !eventHasRecurrence(event) || !recurrenceMatches(event, expectedRecurrence) {
                emitCalendarApplyError("error", "expected_state_mismatch", "Calendar event did not match expected recurrence state.")
            }
        } else if eventIsUnsupportedForBoundedMutation(event) {
            emitCalendarApplyError("error", "unsupported_event_state", "Calendar event has unsupported recurrence state.")
        }
        let proposedEventURLPresent: Bool? = proposedEventURLClearRequested ? false : (proposedEventURLRequested ? true : nil)
        if !recurrenceClearRequested
            && !selectedOccurrenceUpdateRequested
            && !midSeriesRecurrenceReplaceRequested
            && !futureSeriesUpdateRequested
            && eventMatchesState(event, title: title, calendarTitle: expectedCalendarTitle, startDate: startDate, endDate: endDate, expectedTimeZone: timeZoneIdentifier, allDay: allDay, expectedAvailability: proposedAvailability, alarmOffsetsMinutes: proposedAlarmOffsetsMinutes, alarmAbsoluteDates: proposedAlarmAbsoluteDates, alarmSoundName: proposedAlarmSoundName, alarmEmailAddressSHA256: proposedAlarmEmailAddressSHA256, alarmProximity: proposedAlarmProximity, alarmStructuredLocation: proposedAlarmStructuredLocation, eventURLPresent: proposedEventURLPresent, eventURLSHA256: proposedEventURLSHA256, location: location, structuredLocation: proposedStructuredLocation, notes: notes)
            && (!recurrenceUpdateRequested || recurrenceMatches(event, proposedRecurrence)) {
            if let payload = eventPayload(
                event,
                includeContent: false,
                includeAlarmOffsets: true,
                includeTimeZone: true,
                includeURLProof: true,
                includeStructuredLocation: proposedStructuredLocation != nil || proposedStructuredLocationClearRequested
            ) {
                emit([
                    "schema_version": 1,
                    "status": "ok",
                    "source": "calendar",
                    "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .event)),
                    "event": payload,
                    "warnings": [warning("already_applied", "Calendar update already matches the requested event state.")],
                ])
            }
        }

        event.title = title
        event.startDate = startDate
        event.endDate = endDate
        if let proposedTimeZone = proposedTimeZone {
            event.timeZone = proposedTimeZone
        }
        if let targetCalendar = targetCalendar {
            event.calendar = targetCalendar
        }
        if let proposedAvailability = proposedAvailability {
            event.availability = proposedAvailability
        }
        event.isAllDay = allDay
        if (!selectedOccurrenceUpdateRequested && !midSeriesRecurrenceReplaceRequested && !futureSeriesUpdateRequested) || selectedOccurrenceAlarmUpdateRequested || futureSeriesDisplayAlarmUpdateRequested || futureSeriesActionAlarmUpdateRequested {
            applyAlarms(event, offsets: proposedAlarmOffsetsMinutes, absoluteDates: proposedAlarmAbsoluteDates, soundName: proposedAlarmSoundName, emailAddress: proposedAlarmEmailAddress, proximity: proposedAlarmProximity, structuredLocation: proposedAlarmStructuredLocation)
        }
        if recurrenceClearRequested {
            event.recurrenceRules = nil
        } else if recurrenceUpdateRequested {
            applyRecurrence(event, recurrence: proposedRecurrence)
        }
        if proposedEventURLClearRequested {
            event.url = nil
        } else if proposedEventURLRequested {
            event.url = proposedEventURL
        }
        if proposedStructuredLocationClearRequested {
            event.structuredLocation = nil
            event.location = nil
        } else {
            applyStructuredLocation(event, proposedStructuredLocation, fallbackLocation: location)
        }
        event.notes = notes.isEmpty ? nil : notes
        do {
            try store.save(event, span: (recurrenceClearRequested || midSeriesRecurrenceReplaceRequested || futureSeriesUpdateRequested) ? .futureEvents : .thisEvent, commit: true)
        } catch {
            emitCalendarApplyError("error", "eventkit_apply_failed", "Calendar event update could not be applied.")
        }
        var payloadEvent: EKEvent
        var recurrenceClearReadBack: [String: Any]? = nil
        var recurrenceReplaceReadBack: [String: Any]? = nil
        var futureSeriesUpdateReadBack: [String: Any]? = nil
        var recurringOccurrenceUpdateReadBack: [String: Any]? = nil
        if recurrenceClearRequested {
            let selectedRemaining = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: expectedStartDate,
                endDate: expectedEndDate
            )
            if selectedRemaining.count != 1 || eventHasRecurrence(selectedRemaining[0]) {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar recurrence clear lacked selected occurrence non-recurring proof.")
            }
            payloadEvent = selectedRemaining[0]
            let futureRemaining = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: futureOccurrenceStartDate!,
                endDate: futureOccurrenceEndDate!
            )
            if !futureRemaining.isEmpty {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar recurrence clear lacked future occurrence absence proof.")
            }
            let previousRemaining = relativeOccurrenceCandidates(
                store,
                eventId: eventId,
                selectedStartDate: expectedStartDate,
                direction: "previous"
            )
            if previousOccurrenceVerifiedPresent {
                let previousAfterClear = occurrenceCandidates(
                    store,
                    eventId: eventId,
                    startDate: previousOccurrenceStartDate!,
                    endDate: previousOccurrenceEndDate!
                )
                if previousAfterClear.count != 1 || previousRemaining.isEmpty {
                    emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar mid-series recurrence clear lacked previous occurrence preservation proof.")
                }
            } else if !previousOccurrenceVerifiedAbsent || !previousRemaining.isEmpty {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar recurrence clear lacked previous occurrence absence proof.")
            }
            recurrenceClearReadBack = [
                "recurrence_cleared_verified": true,
                "future_occurrence_verified_absent": true,
                previousOccurrenceVerifiedPresent ? "previous_occurrence_verified_present" : "previous_occurrence_verified_absent": true,
            ]
        } else if midSeriesRecurrenceReplaceRequested {
            let selectedReadBackEventId = event.eventIdentifier ?? eventId
            var selectedRemaining = occurrenceCandidates(
                store,
                eventId: selectedReadBackEventId,
                startDate: expectedStartDate,
                endDate: expectedEndDate
            )
            if selectedRemaining.isEmpty && selectedReadBackEventId != eventId {
                selectedRemaining = occurrenceCandidates(
                    store,
                    eventId: eventId,
                    startDate: expectedStartDate,
                    endDate: expectedEndDate
                )
            }
            if selectedRemaining.count != 1 || !eventHasRecurrence(selectedRemaining[0]) || !recurrenceMatches(selectedRemaining[0], proposedRecurrence) {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar mid-series recurrence replacement lacked selected occurrence recurrence proof.")
            }
            payloadEvent = selectedRemaining[0]
            let previousAfterReplace = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: previousOccurrenceStartDate!,
                endDate: previousOccurrenceEndDate!
            )
            if previousAfterReplace.count != 1 || !eventHasRecurrence(previousAfterReplace[0]) || !recurrenceMatches(previousAfterReplace[0], expectedRecurrence) {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar mid-series recurrence replacement lacked previous occurrence preservation proof.")
            }
            var futureAfterReplace = relativeOccurrenceCandidates(
                store,
                eventId: selectedReadBackEventId,
                selectedStartDate: expectedStartDate,
                direction: "future"
            )
            if futureAfterReplace.isEmpty && selectedReadBackEventId != eventId {
                futureAfterReplace = relativeOccurrenceCandidates(
                    store,
                    eventId: eventId,
                    selectedStartDate: expectedStartDate,
                    direction: "future"
                )
            }
            if futureAfterReplace.isEmpty || !eventHasRecurrence(futureAfterReplace[0]) || !recurrenceMatches(futureAfterReplace[0], proposedRecurrence) {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar mid-series recurrence replacement lacked future occurrence recurrence proof.")
            }
            let selectedFutureOriginalSlot = occurrenceCandidates(
                store,
                eventId: selectedReadBackEventId,
                startDate: futureOccurrenceStartDate!,
                endDate: futureOccurrenceEndDate!
            )
            var originalFutureOriginalSlot: [EKEvent] = []
            if selectedReadBackEventId != eventId {
                originalFutureOriginalSlot = occurrenceCandidates(
                    store,
                    eventId: eventId,
                    startDate: futureOccurrenceStartDate!,
                    endDate: futureOccurrenceEndDate!
                )
            }
            let futureOriginalSlot = selectedFutureOriginalSlot + originalFutureOriginalSlot
            if futureOriginalSlot.count > 1 {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar mid-series recurrence replacement left duplicate future-slot occurrences.")
            }
            if futureOriginalSlot.count == 1
                && (!eventHasRecurrence(futureOriginalSlot[0]) || !recurrenceMatches(futureOriginalSlot[0], proposedRecurrence)) {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar mid-series recurrence replacement left the original future slot unreplaced.")
            }
            recurrenceReplaceReadBack = [
                "recurrence_replaced_verified": true,
                "previous_occurrence_verified_present": true,
                "future_occurrence_verified_present": true,
                "future_original_slot_verified_replaced_or_absent": true,
            ]
        } else if futureSeriesUpdateRequested {
            let selectedReadBackEventId = event.eventIdentifier ?? eventId
            let selectedDatesChanged = !eventDatesMatch(startDate, expectedStartDate)
                || !eventDatesMatch(endDate, expectedEndDate)
                || allDay != expectedAllDay
            let selectedReadBackStartDate = selectedDatesChanged ? startDate : expectedStartDate
            let selectedReadBackEndDate = selectedDatesChanged ? endDate : expectedEndDate
            let futureReadBackStartDate: Date
            let futureReadBackEndDate: Date
            if futureSeriesAllDayUpdateRequested {
                // All-day set/clear/date-only reschedule always changes the
                // stored date representation; shift the future occurrence by
                // whole calendar days anchored to the proposed wall-clock
                // time (midnight in the local calendar for all-day results,
                // the proposed time zone for all-day-to-timed clears) so DST
                // transitions between the selected and future days cannot
                // skew the read-back slot the way absolute TimeInterval
                // deltas would.
                var dayCalendar = Calendar.current
                if !allDay, let proposedTimeZone = proposedTimeZone {
                    dayCalendar.timeZone = proposedTimeZone
                }
                futureReadBackStartDate = dayShiftedReadBackDate(
                    futureOccurrenceStartDate!,
                    expectedSelectedDate: expectedStartDate,
                    proposedSelectedDate: startDate,
                    calendar: dayCalendar
                )
                futureReadBackEndDate = dayShiftedReadBackDate(
                    futureOccurrenceEndDate!,
                    expectedSelectedDate: expectedEndDate,
                    proposedSelectedDate: endDate,
                    calendar: dayCalendar
                )
            } else if selectedDatesChanged {
                futureReadBackStartDate = futureOccurrenceStartDate!.addingTimeInterval(startDate.timeIntervalSince(expectedStartDate))
                futureReadBackEndDate = futureOccurrenceEndDate!.addingTimeInterval(endDate.timeIntervalSince(expectedEndDate))
            } else {
                futureReadBackStartDate = futureOccurrenceStartDate!
                futureReadBackEndDate = futureOccurrenceEndDate!
            }
            let futureSeriesReadBackAvailability = futureSeriesAvailabilityUpdateRequested ? proposedAvailability : expectedAvailability
            let futureSeriesReadBackEventURLPresent: Bool? = futureSeriesEventURLUpdateRequested ? (proposedEventURLClearRequested ? false : (proposedEventURLRequested ? true : nil)) : expectedEventURLPresent
            let futureSeriesReadBackEventURLSHA256 = futureSeriesEventURLUpdateRequested && proposedEventURLRequested ? proposedEventURLSHA256 : expectedEventURLSHA256
            let futureSeriesReadBackStructuredLocation = futureSeriesStructuredLocationUpdateRequested ? (proposedStructuredLocationClearRequested ? nil : proposedStructuredLocation) : expectedStructuredLocation
            let futureSeriesReadBackAlarmOffsets = (futureSeriesDisplayAlarmUpdateRequested || futureSeriesActionAlarmUpdateRequested) ? proposedAlarmOffsetsMinutes : expectedAlarmOffsetsMinutes
            let futureSeriesReadBackAlarmAbsoluteDates = (futureSeriesDisplayAlarmUpdateRequested || futureSeriesActionAlarmUpdateRequested) ? proposedAlarmAbsoluteDates : expectedAlarmAbsoluteDates
            let futureSeriesReadBackAlarmSoundName = futureSeriesActionAlarmUpdateRequested ? proposedAlarmSoundName : expectedAlarmSoundName
            let futureSeriesReadBackAlarmEmailSHA256 = futureSeriesActionAlarmUpdateRequested ? proposedAlarmEmailAddressSHA256 : expectedAlarmEmailAddressSHA256
            let futureSeriesReadBackAlarmProximity = futureSeriesActionAlarmUpdateRequested ? proposedAlarmProximity : expectedAlarmProximity
            let futureSeriesReadBackAlarmStructuredLocation = futureSeriesActionAlarmUpdateRequested ? proposedAlarmStructuredLocation : expectedAlarmStructuredLocation
            // Selected/future occurrences must verify against the PROPOSED
            // target calendar title after a future-series calendar move; the
            // previous occurrence keeps the ORIGINAL expected calendar title
            // below, which is the core preservation proof.
            let futureSeriesReadBackCalendarTitle = futureSeriesCalendarMoveRequested ? (targetCalendar?.title ?? expectedCalendarTitle) : expectedCalendarTitle
            var selectedRemaining = occurrenceCandidates(
                store,
                eventId: selectedReadBackEventId,
                startDate: selectedReadBackStartDate,
                endDate: selectedReadBackEndDate
            )
            if selectedRemaining.isEmpty && selectedReadBackEventId != eventId {
                selectedRemaining = occurrenceCandidates(
                    store,
                    eventId: eventId,
                    startDate: selectedReadBackStartDate,
                    endDate: selectedReadBackEndDate
                )
            }
            if selectedRemaining.count != 1
                || !eventHasRecurrence(selectedRemaining[0])
                || !recurrenceMatches(selectedRemaining[0], expectedRecurrence) {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar future-series update lacked selected occurrence proof.")
            }
            payloadEvent = selectedRemaining[0]
            if !eventMatchesState(payloadEvent, title: title, calendarTitle: futureSeriesReadBackCalendarTitle, startDate: selectedReadBackStartDate, endDate: selectedReadBackEndDate, expectedTimeZone: timeZoneIdentifier, allDay: allDay, expectedAvailability: futureSeriesReadBackAvailability, alarmOffsetsMinutes: futureSeriesReadBackAlarmOffsets, alarmAbsoluteDates: futureSeriesReadBackAlarmAbsoluteDates, alarmSoundName: futureSeriesReadBackAlarmSoundName, alarmEmailAddressSHA256: futureSeriesReadBackAlarmEmailSHA256, alarmProximity: futureSeriesReadBackAlarmProximity, alarmStructuredLocation: futureSeriesReadBackAlarmStructuredLocation, eventURLPresent: futureSeriesReadBackEventURLPresent, eventURLSHA256: futureSeriesReadBackEventURLSHA256, location: location, structuredLocation: futureSeriesReadBackStructuredLocation, notes: notes) {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar future-series update selected occurrence read-back did not match approved fields.")
            }
            if let targetCalendar = targetCalendar,
               futureSeriesCalendarMoveRequested,
               payloadEvent.calendar?.calendarIdentifier != targetCalendar.calendarIdentifier {
                emitCalendarApplyError("apply_unknown", "target_calendar_read_back_mismatch", "Calendar future-series update selected occurrence read-back calendar did not match approved target.")
            }
            let previousAfterUpdate = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: previousOccurrenceStartDate!,
                endDate: previousOccurrenceEndDate!
            )
            if previousAfterUpdate.count != 1
                || !eventHasRecurrence(previousAfterUpdate[0])
                || !recurrenceMatches(previousAfterUpdate[0], expectedRecurrence)
                || !eventMatchesState(previousAfterUpdate[0], title: expectedTitle, calendarTitle: expectedCalendarTitle, startDate: previousOccurrenceStartDate!, endDate: previousOccurrenceEndDate!, expectedTimeZone: expectedTimeZone, allDay: expectedAllDay, expectedAvailability: expectedAvailability, alarmOffsetsMinutes: expectedAlarmOffsetsMinutes, alarmAbsoluteDates: expectedAlarmAbsoluteDates, alarmSoundName: expectedAlarmSoundName, alarmEmailAddressSHA256: expectedAlarmEmailAddressSHA256, alarmProximity: expectedAlarmProximity, alarmStructuredLocation: expectedAlarmStructuredLocation, eventURLPresent: expectedEventURLPresent, eventURLSHA256: expectedEventURLSHA256, location: expectedLocation, structuredLocation: expectedStructuredLocation, notes: expectedNotes) {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar future-series update lacked previous occurrence preservation proof.")
            }
            if futureSeriesCalendarMoveRequested
                && !originalCalendarIdentifier.isEmpty
                && previousAfterUpdate[0].calendar?.calendarIdentifier != originalCalendarIdentifier {
                emitCalendarApplyError("apply_unknown", "previous_occurrence_calendar_read_back_mismatch", "Calendar future-series update did not preserve previous occurrence calendar state.")
            }
            var futureAfterUpdate = occurrenceCandidates(
                store,
                eventId: selectedReadBackEventId,
                startDate: futureReadBackStartDate,
                endDate: futureReadBackEndDate
            )
            if futureAfterUpdate.isEmpty && selectedReadBackEventId != eventId {
                futureAfterUpdate = occurrenceCandidates(
                    store,
                    eventId: eventId,
                    startDate: futureReadBackStartDate,
                    endDate: futureReadBackEndDate
                )
            }
            if futureAfterUpdate.count != 1
                || !eventHasRecurrence(futureAfterUpdate[0])
                || !recurrenceMatches(futureAfterUpdate[0], expectedRecurrence) {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar future-series update lacked future occurrence proof.")
            }
            if !eventMatchesState(futureAfterUpdate[0], title: title, calendarTitle: futureSeriesReadBackCalendarTitle, startDate: futureReadBackStartDate, endDate: futureReadBackEndDate, expectedTimeZone: timeZoneIdentifier, allDay: allDay, expectedAvailability: futureSeriesReadBackAvailability, alarmOffsetsMinutes: futureSeriesReadBackAlarmOffsets, alarmAbsoluteDates: futureSeriesReadBackAlarmAbsoluteDates, alarmSoundName: futureSeriesReadBackAlarmSoundName, alarmEmailAddressSHA256: futureSeriesReadBackAlarmEmailSHA256, alarmProximity: futureSeriesReadBackAlarmProximity, alarmStructuredLocation: futureSeriesReadBackAlarmStructuredLocation, eventURLPresent: futureSeriesReadBackEventURLPresent, eventURLSHA256: futureSeriesReadBackEventURLSHA256, location: location, structuredLocation: futureSeriesReadBackStructuredLocation, notes: notes) {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar future-series update future occurrence read-back did not match approved fields.")
            }
            if let targetCalendar = targetCalendar,
               futureSeriesCalendarMoveRequested,
               futureAfterUpdate[0].calendar?.calendarIdentifier != targetCalendar.calendarIdentifier {
                emitCalendarApplyError("apply_unknown", "target_calendar_read_back_mismatch", "Calendar future-series update future occurrence read-back calendar did not match approved target.")
            }
            if selectedDatesChanged {
                var originalSelectedRemaining = occurrenceCandidates(
                    store,
                    eventId: selectedReadBackEventId,
                    startDate: expectedStartDate,
                    endDate: expectedEndDate
                )
                if selectedReadBackEventId != eventId {
                    originalSelectedRemaining += occurrenceCandidates(
                        store,
                        eventId: eventId,
                        startDate: expectedStartDate,
                        endDate: expectedEndDate
                    )
                }
                var originalFutureRemaining = occurrenceCandidates(
                    store,
                    eventId: selectedReadBackEventId,
                    startDate: futureOccurrenceStartDate!,
                    endDate: futureOccurrenceEndDate!
                )
                if selectedReadBackEventId != eventId {
                    originalFutureRemaining += occurrenceCandidates(
                        store,
                        eventId: eventId,
                        startDate: futureOccurrenceStartDate!,
                        endDate: futureOccurrenceEndDate!
                    )
                }
                let originalSelectedSlotApproved = eventSlotMatches(expectedStartDate, expectedEndDate, selectedReadBackStartDate, selectedReadBackEndDate)
                    || eventSlotMatches(expectedStartDate, expectedEndDate, futureReadBackStartDate, futureReadBackEndDate)
                let originalFutureSlotApproved = eventSlotMatches(futureOccurrenceStartDate!, futureOccurrenceEndDate!, selectedReadBackStartDate, selectedReadBackEndDate)
                    || eventSlotMatches(futureOccurrenceStartDate!, futureOccurrenceEndDate!, futureReadBackStartDate, futureReadBackEndDate)
                let originalSelectedVerified = originalSelectedSlotApproved
                    ? originalSelectedRemaining.count == 1
                        && eventMatchesState(originalSelectedRemaining[0], title: title, calendarTitle: expectedCalendarTitle, startDate: expectedStartDate, endDate: expectedEndDate, expectedTimeZone: timeZoneIdentifier, allDay: allDay, expectedAvailability: futureSeriesReadBackAvailability, alarmOffsetsMinutes: futureSeriesReadBackAlarmOffsets, alarmAbsoluteDates: futureSeriesReadBackAlarmAbsoluteDates, alarmSoundName: futureSeriesReadBackAlarmSoundName, alarmEmailAddressSHA256: futureSeriesReadBackAlarmEmailSHA256, alarmProximity: futureSeriesReadBackAlarmProximity, alarmStructuredLocation: futureSeriesReadBackAlarmStructuredLocation, eventURLPresent: futureSeriesReadBackEventURLPresent, eventURLSHA256: futureSeriesReadBackEventURLSHA256, location: location, structuredLocation: futureSeriesReadBackStructuredLocation, notes: notes)
                    : originalSelectedRemaining.isEmpty
                let originalFutureVerified = originalFutureSlotApproved
                    ? originalFutureRemaining.count == 1
                        && eventMatchesState(originalFutureRemaining[0], title: title, calendarTitle: expectedCalendarTitle, startDate: futureOccurrenceStartDate!, endDate: futureOccurrenceEndDate!, expectedTimeZone: timeZoneIdentifier, allDay: allDay, expectedAvailability: futureSeriesReadBackAvailability, alarmOffsetsMinutes: futureSeriesReadBackAlarmOffsets, alarmAbsoluteDates: futureSeriesReadBackAlarmAbsoluteDates, alarmSoundName: futureSeriesReadBackAlarmSoundName, alarmEmailAddressSHA256: futureSeriesReadBackAlarmEmailSHA256, alarmProximity: futureSeriesReadBackAlarmProximity, alarmStructuredLocation: futureSeriesReadBackAlarmStructuredLocation, eventURLPresent: futureSeriesReadBackEventURLPresent, eventURLSHA256: futureSeriesReadBackEventURLSHA256, location: location, structuredLocation: futureSeriesReadBackStructuredLocation, notes: notes)
                    : originalFutureRemaining.isEmpty
                if !originalSelectedVerified || !originalFutureVerified {
                    emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar future-series update lacked original-slot absence or approved-replacement proof.")
                }
            }
            var readBack: [String: Any] = [
                "selected_occurrence_updated_verified": true,
                "future_occurrence_updated_verified": true,
                "previous_occurrence_verified_present": true,
            ]
            if futureSeriesScalarUpdateRequested {
                readBack["future_series_scalar_updated_verified"] = true
            }
            if futureSeriesRescheduleRequested {
                readBack["future_series_rescheduled_verified"] = true
            }
            if futureSeriesAvailabilityUpdateRequested {
                readBack["future_series_availability_updated_verified"] = true
            }
            if futureSeriesEventURLUpdateRequested {
                readBack["future_series_event_url_updated_verified"] = true
            }
            if futureSeriesStructuredLocationUpdateRequested {
                readBack["future_series_structured_location_updated_verified"] = true
            }
            if futureSeriesDisplayAlarmUpdateRequested {
                readBack["future_series_display_alarm_updated_verified"] = true
            }
            if futureSeriesActionAlarmUpdateRequested {
                readBack["future_series_action_alarm_updated_verified"] = true
            }
            if futureSeriesAllDayUpdateRequested {
                readBack["future_series_all_day_updated_verified"] = true
            }
            if futureSeriesCalendarMoveRequested {
                readBack["future_series_calendar_move_verified"] = true
                readBack["previous_occurrence_calendar_verified"] = true
            }
            if selectedDatesChanged {
                readBack["original_occurrence_verified_absent"] = true
                readBack["future_original_occurrence_verified_absent"] = true
                readBack["original_occurrence_verified_absent_or_replaced"] = true
                readBack["future_original_occurrence_verified_absent_or_replaced"] = true
            }
            futureSeriesUpdateReadBack = readBack
        } else if selectedOccurrenceUpdateRequested {
            let selectedRescheduled = !eventDatesMatch(startDate, expectedStartDate)
                || !eventDatesMatch(endDate, expectedEndDate)
            let selectedReadBackStartDate = selectedRescheduled ? startDate : expectedStartDate
            let selectedReadBackEndDate = selectedRescheduled ? endDate : expectedEndDate
            let selectedReadBackEventId = event.eventIdentifier ?? eventId
            var selectedRemaining = occurrenceCandidates(
                store,
                eventId: selectedReadBackEventId,
                startDate: selectedReadBackStartDate,
                endDate: selectedReadBackEndDate
            )
            if selectedRemaining.isEmpty && selectedReadBackEventId != eventId {
                selectedRemaining = occurrenceCandidates(
                    store,
                    eventId: eventId,
                    startDate: selectedReadBackStartDate,
                    endDate: selectedReadBackEndDate
                )
            }
            if selectedRemaining.count != 1 {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar selected occurrence update lacked selected occurrence read-back proof.")
            }
            payloadEvent = selectedRemaining[0]
            let selectedOccurrenceCalendarMoved = targetCalendar != nil
            if let targetCalendar = targetCalendar,
               payloadEvent.calendar?.calendarIdentifier != targetCalendar.calendarIdentifier {
                emitCalendarApplyError("apply_unknown", "target_calendar_read_back_mismatch", "Calendar selected occurrence update read-back calendar did not match approved target.")
            }
            if proposedAvailability != nil && !availabilityMatches(payloadEvent, proposedAvailability) {
                emitCalendarApplyError("apply_unknown", "availability_read_back_mismatch", "Calendar selected occurrence update read-back availability did not match approved availability.")
            }
            if proposedEventURLRequested {
                let currentURL = eventURLString(payloadEvent)
                if currentURL.isEmpty || sha256Hex(currentURL) != proposedEventURLSHA256 {
                    emitCalendarApplyError("apply_unknown", "event_url_read_back_mismatch", "Calendar selected occurrence update read-back event URL did not match approved value.")
                }
            }
            if proposedEventURLClearRequested && !eventURLString(payloadEvent).isEmpty {
                emitCalendarApplyError("apply_unknown", "event_url_clear_read_back_mismatch", "Calendar selected occurrence update read-back event URL absence was not verified.")
            }
            if let proposedStructuredLocation = proposedStructuredLocation,
               !structuredLocationPayloadMatches(structuredLocationPayload(payloadEvent), proposedStructuredLocation) {
                emitCalendarApplyError("apply_unknown", "structured_location_read_back_mismatch", "Calendar selected occurrence update read-back structured location did not match approved value.")
            }
            if proposedStructuredLocationClearRequested
                && (structuredLocationPayload(payloadEvent) != nil || !(payloadEvent.location ?? "").isEmpty) {
                emitCalendarApplyError("apply_unknown", "structured_location_clear_read_back_mismatch", "Calendar selected occurrence update read-back structured location absence was not verified.")
            }
            let readBackAvailability = proposedAvailability ?? expectedAvailability
            let readBackEventURLPresent: Bool? = proposedEventURLClearRequested ? false : (proposedEventURLRequested ? true : expectedEventURLPresent)
            let readBackEventURLSHA256 = proposedEventURLRequested ? proposedEventURLSHA256 : expectedEventURLSHA256
            let readBackStructuredLocation = proposedStructuredLocationClearRequested ? nil : proposedStructuredLocation
            let readBackAlarmOffsetsMinutes = selectedOccurrenceAlarmUpdateRequested ? proposedAlarmOffsetsMinutes : expectedAlarmOffsetsMinutes
            let readBackAlarmAbsoluteDates = selectedOccurrenceAlarmUpdateRequested ? proposedAlarmAbsoluteDates : expectedAlarmAbsoluteDates
            let readBackAlarmSoundName = selectedOccurrenceAlarmUpdateRequested ? proposedAlarmSoundName : expectedAlarmSoundName
            let readBackAlarmEmailAddressSHA256 = selectedOccurrenceAlarmUpdateRequested ? proposedAlarmEmailAddressSHA256 : expectedAlarmEmailAddressSHA256
            let readBackAlarmProximity = selectedOccurrenceAlarmUpdateRequested ? proposedAlarmProximity : expectedAlarmProximity
            let readBackAlarmStructuredLocation = selectedOccurrenceAlarmUpdateRequested ? proposedAlarmStructuredLocation : expectedAlarmStructuredLocation
            let displayAlarmUpdated = selectedOccurrenceAlarmUpdateRequested
                && (proposedAlarmOffsetsMinutes != expectedAlarmOffsetsMinutes
                    || proposedAlarmAbsoluteDates != expectedAlarmAbsoluteDates)
            let actionAlarmUpdated = selectedOccurrenceAlarmUpdateRequested
                && (proposedAlarmSoundName != expectedAlarmSoundName
                    || proposedAlarmEmailAddressSHA256 != expectedAlarmEmailAddressSHA256
                    || proposedAlarmProximity != expectedAlarmProximity
                    || !structuredLocationPayloadsEqual(proposedAlarmStructuredLocation, expectedAlarmStructuredLocation))
            let allDayUpdated = allDay != expectedAllDay
            let allDayVerified = allDayUpdated || (allDay && expectedAllDay && selectedRescheduled)
            let readBackCalendarTitle = targetCalendar?.title ?? expectedCalendarTitle
            if !eventMatchesState(payloadEvent, title: title, calendarTitle: readBackCalendarTitle, startDate: startDate, endDate: endDate, expectedTimeZone: timeZoneIdentifier, allDay: allDay, expectedAvailability: readBackAvailability, alarmOffsetsMinutes: readBackAlarmOffsetsMinutes, alarmAbsoluteDates: readBackAlarmAbsoluteDates, alarmSoundName: readBackAlarmSoundName, alarmEmailAddressSHA256: readBackAlarmEmailAddressSHA256, alarmProximity: readBackAlarmProximity, alarmStructuredLocation: readBackAlarmStructuredLocation, eventURLPresent: readBackEventURLPresent, eventURLSHA256: readBackEventURLSHA256, location: location, structuredLocation: readBackStructuredLocation, notes: notes) {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar selected occurrence update read-back did not match approved scalar fields.")
            }
            let adjacentRemaining = occurrenceCandidates(
                store,
                eventId: eventId,
                startDate: adjacentOccurrenceStartDate!,
                endDate: adjacentOccurrenceEndDate!
            )
            if adjacentRemaining.count != 1 || !eventHasRecurrence(adjacentRemaining[0]) {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar selected occurrence update lacked adjacent occurrence preservation proof.")
            }
            if selectedOccurrenceCalendarMoved
                && !originalCalendarIdentifier.isEmpty
                && adjacentRemaining[0].calendar?.calendarIdentifier != originalCalendarIdentifier {
                emitCalendarApplyError("apply_unknown", "adjacent_occurrence_calendar_read_back_mismatch", "Calendar selected occurrence update did not preserve adjacent occurrence calendar state.")
            }
            if !eventURLStateMatches(adjacentRemaining[0], present: adjacentOccurrenceEventURLPresent, sha256: adjacentOccurrenceEventURLSHA256) {
                emitCalendarApplyError("apply_unknown", "adjacent_occurrence_event_url_read_back_mismatch", "Calendar selected occurrence update did not preserve adjacent occurrence URL state.")
            }
            if !eventLocationProofStateMatches(
                adjacentRemaining[0],
                locationPresent: adjacentOccurrenceLocationPresent,
                locationSHA256: adjacentOccurrenceLocationSHA256,
                structuredLocationPresent: adjacentOccurrenceStructuredLocationPresent,
                structuredLocationSHA256: adjacentOccurrenceStructuredLocationSHA256
            ) {
                emitCalendarApplyError("apply_unknown", "adjacent_occurrence_location_read_back_mismatch", "Calendar selected occurrence update did not preserve adjacent occurrence location state.")
            }
            if !eventAlarmProofStateMatches(adjacentRemaining[0], present: adjacentOccurrenceAlarmStatePresent, sha256: adjacentOccurrenceAlarmStateSHA256) {
                emitCalendarApplyError("apply_unknown", "adjacent_occurrence_alarm_read_back_mismatch", "Calendar selected occurrence update did not preserve adjacent occurrence alarm state.")
            }
            if selectedRescheduled {
                let originalRemaining = occurrenceCandidates(
                    store,
                    eventId: eventId,
                    startDate: expectedStartDate,
                    endDate: expectedEndDate
                )
                if !originalRemaining.isEmpty {
                    emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar selected occurrence update lacked original occurrence absence proof.")
                }
            }
            recurringOccurrenceUpdateReadBack = [
                "selected_occurrence_updated_verified": true,
                "adjacent_occurrence_verified_present": true,
                "adjacent_occurrence_event_url_verified": true,
                "adjacent_occurrence_location_verified": true,
                "adjacent_occurrence_alarm_verified": true,
                "selected_occurrence_rescheduled_verified": selectedRescheduled,
                "original_occurrence_verified_absent": selectedRescheduled,
                "selected_occurrence_calendar_move_verified": selectedOccurrenceCalendarMoved,
                "adjacent_occurrence_calendar_verified": !selectedOccurrenceCalendarMoved || originalCalendarIdentifier.isEmpty || adjacentRemaining[0].calendar?.calendarIdentifier == originalCalendarIdentifier,
                "structured_location_verified": proposedStructuredLocation != nil,
                "structured_location_cleared_verified": proposedStructuredLocationClearRequested,
                "display_alarm_verified": displayAlarmUpdated,
                "action_alarm_verified": actionAlarmUpdated,
                "all_day_verified": allDayVerified,
            ]
        } else {
            let readBackEventId = event.eventIdentifier ?? eventId
            let reloadedEvent = store.event(withIdentifier: readBackEventId)
                ?? (readBackEventId == eventId ? nil : store.event(withIdentifier: eventId))
            guard let reloadedEvent = reloadedEvent else {
                emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar event was updated but read-back was unavailable.")
            }
            payloadEvent = reloadedEvent
        }
        guard let payload = eventPayload(
            payloadEvent,
            includeContent: false,
            includeAlarmOffsets: true,
            includeTimeZone: true,
            includeURLProof: true,
            includeStructuredLocation: proposedStructuredLocation != nil || proposedStructuredLocationClearRequested
        ) else {
            emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar event was updated but read-back was unavailable.")
        }
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .event)),
            "event": payload,
                "read_back": recurrenceClearReadBack ?? recurrenceReplaceReadBack ?? futureSeriesUpdateReadBack ?? recurringOccurrenceUpdateReadBack ?? [:],
            "warnings": [],
        ])
    }

    let calendarTitle = stringValue(request, "calendar_title")
    let calendarId = stringValue(request, "calendar_id")
    if calendarTitle.isEmpty && calendarId.isEmpty {
        emitCalendarApplyError("error", "missing_required_field", "Calendar create requires calendar title or calendar id.")
    }

    let calendar: EKCalendar
    if !calendarId.isEmpty {
        guard let resolvedCalendar = store.calendar(withIdentifier: calendarId) else {
            emitCalendarApplyError("not_found", "target_calendar_not_found", "Calendar was not found.")
        }
        calendar = resolvedCalendar
    } else {
        let matchingCalendars = store.calendars(for: .event).filter { $0.title == calendarTitle }
        if matchingCalendars.isEmpty {
            emitCalendarApplyError("not_found", "target_calendar_not_found", "Calendar was not found.")
        }
        if matchingCalendars.count > 1 {
            emitCalendarApplyError("error", "ambiguous_target_calendar", "Calendar title matched more than one calendar.")
        }
        calendar = matchingCalendars[0]
    }
    if !calendar.allowsContentModifications {
        emitCalendarApplyError("error", "target_calendar_not_writable", "Calendar target does not allow event changes.")
    }
    if let proposedAvailability = proposedAvailability,
       !calendarSupportsAvailability(calendar, proposedAvailability) {
        emitCalendarApplyError("error", "availability_not_supported", "Calendar target does not support the requested availability value.")
    }

    let searchStart = Calendar.current.date(byAdding: .minute, value: -1, to: startDate) ?? startDate
    let searchEnd = Calendar.current.date(byAdding: .minute, value: 1, to: endDate) ?? endDate
    let predicate = store.predicateForEvents(withStart: searchStart, end: searchEnd, calendars: [calendar])
    let existing = store.events(matching: predicate).first {
        ($0.title ?? "") == title
            && eventDatesMatch($0.startDate, startDate)
            && eventDatesMatch($0.endDate, endDate)
            && (timeZoneIdentifier.isEmpty || eventTimeZoneIdentifier($0) == timeZoneIdentifier)
            && $0.isAllDay == allDay
            && availabilityMatches($0, proposedAvailability)
            && alarmState($0).offsets == proposedAlarmOffsetsMinutes
            && alarmState($0).absoluteDates == proposedAlarmAbsoluteDates
            && recurrenceMatches($0, proposedRecurrence)
            && eventMatchesState($0, title: title, calendarTitle: calendar.title, startDate: startDate, endDate: endDate, expectedTimeZone: timeZoneIdentifier, allDay: allDay, expectedAvailability: proposedAvailability, alarmOffsetsMinutes: proposedAlarmOffsetsMinutes, alarmAbsoluteDates: proposedAlarmAbsoluteDates, alarmSoundName: proposedAlarmSoundName, alarmEmailAddressSHA256: proposedAlarmEmailAddressSHA256, alarmProximity: proposedAlarmProximity, alarmStructuredLocation: proposedAlarmStructuredLocation, eventURLPresent: proposedEventURLRequested ? true : false, eventURLSHA256: proposedEventURLSHA256, location: location, structuredLocation: proposedStructuredLocation, notes: notes)
            && ($0.location ?? "") == location
            && ($0.notes ?? "") == notes
    }
    if let existing = existing, let payload = eventPayload(
        existing,
        includeContent: false,
        includeAlarmOffsets: true,
        includeTimeZone: true,
        includeURLProof: true,
        includeStructuredLocation: proposedStructuredLocation != nil
    ) {
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "calendar",
            "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .event)),
            "event": payload,
            "warnings": [warning("already_applied", "Calendar create already matches an existing event.")],
        ])
    }

    let event = EKEvent(eventStore: store)
    event.title = title
    event.calendar = calendar
    event.startDate = startDate
    event.endDate = endDate
    if let proposedTimeZone = proposedTimeZone {
        event.timeZone = proposedTimeZone
    }
    if let proposedAvailability = proposedAvailability {
        event.availability = proposedAvailability
    }
    event.isAllDay = allDay
    applyAlarms(event, offsets: proposedAlarmOffsetsMinutes, absoluteDates: proposedAlarmAbsoluteDates, soundName: proposedAlarmSoundName, emailAddress: proposedAlarmEmailAddress, proximity: proposedAlarmProximity, structuredLocation: proposedAlarmStructuredLocation)
    applyRecurrence(event, recurrence: proposedRecurrence)
    if proposedEventURLRequested {
        event.url = proposedEventURL
    }
    applyStructuredLocation(event, proposedStructuredLocation, fallbackLocation: location)
    if !notes.isEmpty {
        event.notes = notes
    }
    do {
        try store.save(event, span: .thisEvent, commit: true)
    } catch {
        emitCalendarApplyError("error", "eventkit_apply_failed", "Calendar event could not be created.")
    }
    guard let payload = eventPayload(
        event,
        includeContent: false,
        includeAlarmOffsets: true,
        includeTimeZone: true,
        includeURLProof: true,
        includeStructuredLocation: proposedStructuredLocation != nil
    ) else {
        emitCalendarApplyError("apply_unknown", "read_back_unavailable", "Calendar event was created but read-back was unavailable.")
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "calendar",
        "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .event)),
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

if command == "reminder_lists" {
    let store = ensureAccess(
        .reminder,
        source: "reminders",
        warningCode: "reminders_access_unavailable"
    )!
    let query = stringValue(request, "query").lowercased()
    let limit = max(1, min(intValue(request, "limit", 20), 10000))
    let includeCounts = (request["include_counts"] as? Bool) ?? false
    let fetchedReminders = includeCounts ? fetchReminders(store) : nil
    if includeCounts && fetchedReminders == nil {
        emit([
            "schema_version": 1,
            "status": "degraded",
            "source": "reminders",
            "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
            "lists": [],
            "warnings": [warning("reminders_fetch_timeout", "Reminders list count proof timed out through EventKit.")],
        ])
    }
    let lists = store.calendars(for: .reminder).sorted {
        if $0.title == $1.title {
            return $0.calendarIdentifier < $1.calendarIdentifier
        }
        return $0.title < $1.title
    }
    var results: [[String: Any]] = []
    for list in lists {
        if !query.isEmpty && !list.title.lowercased().contains(query) {
            continue
        }
        results.append(reminderListPayload(list, reminders: fetchedReminders))
        if results.count >= limit {
            break
        }
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "reminders",
        "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
        "lists": results,
        "warnings": [],
    ])
}

if command == "reminders_for_list" {
    let store = ensureAccess(
        .reminder,
        source: "reminders",
        warningCode: "reminders_access_unavailable"
    )!
    let listId = stringValue(request, "list_id")
    let limit = max(1, min(intValue(request, "limit", 20), 10000))
    let includeCompleted = (request["include_completed"] as? Bool) ?? false
    guard let list = store.calendars(for: .reminder).first(where: { $0.calendarIdentifier == listId }) else {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "reminders",
            "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
            "list": NSNull(),
            "reminders": [],
            "warnings": [],
        ])
    }
    guard let reminders = fetchReminders(store, calendars: [list]) else {
        emit([
            "schema_version": 1,
            "status": "degraded",
            "source": "reminders",
            "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
            "list": reminderListPayload(list),
            "reminders": [],
            "warnings": [warning("reminders_fetch_timeout", "Selected Reminders list fetch timed out through EventKit.")],
        ])
    }
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
        "list": reminderListPayload(list, reminders: reminders),
        "reminders": results,
        "scanned": scanned,
        "warnings": [],
    ])
}

if command == "reminder_list_apply_change" {
    let store = ensureAccess(
        .reminder,
        source: "reminders",
        warningCode: "reminders_access_unavailable"
    )!
    let operation = stringValue(request, "operation")

    func emitReminderListManagementError(_ status: String, _ code: String, _ message: String, mutationApplied: Bool = false) -> Never {
        emit([
            "schema_version": 1,
            "status": status,
            "source": "reminders",
            "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
            "mutation_applied": mutationApplied,
            "list": NSNull(),
            "read_back": NSNull(),
            "warnings": [warning(code, message)],
        ])
    }

    func remindersOrManagementError() -> [EKReminder] {
        guard let reminders = fetchReminders(store) else {
            emitReminderListManagementError("degraded", "reminders_fetch_timeout", "Reminders list empty proof timed out through EventKit.")
        }
        return reminders
    }

    func listWithTitleInSource(_ title: String, sourceIdentifier: String, excluding listIdentifier: String = "") -> EKCalendar? {
        return store.calendars(for: .reminder).first {
            $0.title == title
                && $0.source.sourceIdentifier == sourceIdentifier
                && (listIdentifier.isEmpty || $0.calendarIdentifier != listIdentifier)
        }
    }

    func reminderCount(_ list: EKCalendar) -> Int {
        return remindersOrManagementError().filter {
            $0.calendar.calendarIdentifier == list.calendarIdentifier
        }.count
    }

    func listIsReminderOnly(_ list: EKCalendar) -> Bool {
        return entityTypeNames(list.allowedEntityTypes) == ["reminder"]
    }

    if operation == "create_list" {
        let sourceListId = stringValue(request, "source_list_id")
        let listTitle = stringValue(request, "list_title")
        if sourceListId.isEmpty || listTitle.isEmpty {
            emitReminderListManagementError("error", "missing_required_field", "Reminder create-list requires source_list_id and list_title.")
        }
        guard let sourceList = store.calendar(withIdentifier: sourceListId) else {
            emitReminderListManagementError("not_found", "target_list_not_found", "Reminder source list was not found.")
        }
        if sourceList.source.sourceType == .subscribed || sourceList.source.sourceType == .birthdays {
            emitReminderListManagementError("error", "unsupported_list_source", "Reminder list creation refuses subscribed or birthday sources.")
        }
        if sourceList.isSubscribed || sourceList.isImmutable {
            emitReminderListManagementError("error", "unsupported_list_source", "Reminder list creation refuses subscribed or immutable source lists.")
        }
        if !sourceList.allowsContentModifications {
            emitReminderListManagementError("error", "target_list_not_writable", "Reminder list source does not allow changes.")
        }
        if !listIsReminderOnly(sourceList) {
            emitReminderListManagementError("error", "unsupported_list_source", "Reminder list creation refuses non-reminder-only calendars.")
        }
        if listWithTitleInSource(listTitle, sourceIdentifier: sourceList.source.sourceIdentifier) != nil {
            emitReminderListManagementError("error", "list_already_exists", "A Reminders list with that title already exists in the selected source.")
        }
        let list = EKCalendar(for: .reminder, eventStore: store)
        list.title = listTitle
        list.source = sourceList.source
        do {
            try store.saveCalendar(list, commit: true)
        } catch {
            emitReminderListManagementError("error", "eventkit_apply_failed", "Reminder list could not be created.")
        }
        guard let readBack = store.calendar(withIdentifier: list.calendarIdentifier),
              readBack.title == listTitle,
              readBack.source.sourceIdentifier == sourceList.source.sourceIdentifier
        else {
            emitReminderListManagementError("apply_unknown", "read_back_unavailable", "Reminder list was created but read-back was unavailable.", mutationApplied: true)
        }
        let reminders = remindersOrManagementError()
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
            "mutation_applied": true,
            "list": reminderListPayload(readBack, reminders: reminders),
            "read_back": [
                "source_list_verified": true,
                "list_empty_verified": reminderCount(readBack) == 0,
            ],
            "warnings": [],
        ])
    }

    if operation == "delete_list_with_migration" {
        let listId = stringValue(request, "list_id")
        let targetListId = stringValue(request, "target_list_id")
        let expectedTitle = stringValue(request, "expected_list_title")
        let expectedSourceType = stringValue(request, "expected_source_type")
        let expectedTargetTitle = stringValue(request, "expected_target_list_title")
        let expectedTargetSourceType = stringValue(request, "expected_target_source_type")
        let expectedMigrationCount = intValue(request, "expected_migration_count", -1)
        let expectedTargetCount = intValue(request, "expected_target_count", -1)
        let migrateBeforeDelete = boolValue(request, "migrate_before_delete") ?? false
        if listId.isEmpty || targetListId.isEmpty || expectedTitle.isEmpty || expectedTargetTitle.isEmpty || !migrateBeforeDelete {
            emitReminderListManagementError("error", "missing_required_field", "Reminder list migration delete requires source, target, expected state, and migrate_before_delete.")
        }
        if expectedMigrationCount <= 0 || expectedMigrationCount > 50 || expectedTargetCount < 0 {
            emitReminderListManagementError("error", "invalid_migration_count", "Reminder list migration count is outside the approved bounded range.")
        }
        guard let list = store.calendar(withIdentifier: listId) else {
            emitReminderListManagementError("not_found", "target_list_not_found", "Reminder list target was not found.")
        }
        guard let targetList = store.calendar(withIdentifier: targetListId) else {
            emitReminderListManagementError("not_found", "target_list_not_found", "Reminder migration target list was not found.")
        }
        if list.calendarIdentifier == targetList.calendarIdentifier {
            emitReminderListManagementError("error", "same_list_target", "Reminder list migration requires a different target list.")
        }
        if list.title != expectedTitle || sourceTypeName(list.source.sourceType) != expectedSourceType {
            emitReminderListManagementError("error", "expected_state_mismatch", "Reminder list target did not match expected state.")
        }
        if targetList.title != expectedTargetTitle || sourceTypeName(targetList.source.sourceType) != expectedTargetSourceType {
            emitReminderListManagementError("error", "expected_state_mismatch", "Reminder migration target did not match expected state.")
        }
        if list.source.sourceIdentifier != targetList.source.sourceIdentifier {
            emitReminderListManagementError("error", "cross_source_list_migration_refused", "Reminder list migration refuses cross-source targets.")
        }
        for candidate in [list, targetList] {
            if candidate.title.isEmpty || candidate.isSubscribed || candidate.isImmutable {
                emitReminderListManagementError("error", "unsupported_list_state", "Reminder list management refuses untitled, subscribed, or immutable lists.")
            }
            if !candidate.allowsContentModifications {
                emitReminderListManagementError("error", "target_list_not_writable", "Reminder list target does not allow changes.")
            }
            if !listIsReminderOnly(candidate) {
                emitReminderListManagementError("error", "unsupported_list_state", "Reminder list management refuses non-reminder-only calendars.")
            }
        }
        let beforeReminders = remindersOrManagementError()
        let sourceReminders = beforeReminders.filter {
            $0.calendar.calendarIdentifier == list.calendarIdentifier
        }
        let targetCountBefore = beforeReminders.filter {
            $0.calendar.calendarIdentifier == targetList.calendarIdentifier
        }.count
        if sourceReminders.count != expectedMigrationCount || targetCountBefore != expectedTargetCount {
            emitReminderListManagementError("error", "expected_state_mismatch", "Reminder list migration count did not match expected state.")
        }
        var movedCount = 0
        for reminder in sourceReminders {
            reminder.calendar = targetList
            do {
                try store.save(reminder, commit: true)
                movedCount += 1
            } catch {
                emitReminderListManagementError("apply_unknown", "eventkit_apply_failed", "Reminder list migration failed while moving reminders.", mutationApplied: true)
            }
        }
        let afterMoveReminders = remindersOrManagementError()
        let sourceCountAfterMove = afterMoveReminders.filter {
            $0.calendar.calendarIdentifier == list.calendarIdentifier
        }.count
        let targetCountAfterMove = afterMoveReminders.filter {
            $0.calendar.calendarIdentifier == targetList.calendarIdentifier
        }.count
        if sourceCountAfterMove != 0 || targetCountAfterMove != targetCountBefore + movedCount {
            emitReminderListManagementError("apply_unknown", "list_migration_read_back_mismatch", "Reminder list migration proof did not match the approved state.", mutationApplied: true)
        }
        do {
            try store.removeCalendar(list, commit: true)
        } catch {
            emitReminderListManagementError("apply_unknown", "eventkit_apply_failed", "Reminder list was migrated but could not be deleted.", mutationApplied: true)
        }
        if store.calendar(withIdentifier: listId) != nil {
            emitReminderListManagementError("apply_unknown", "list_delete_read_back_mismatch", "Reminder list was migrated and deleted but absence proof failed.", mutationApplied: true)
        }
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
            "mutation_applied": true,
            "list": NSNull(),
            "read_back": [
                "list_migrated_verified": true,
                "migrated_count": movedCount,
                "target_count_before": targetCountBefore,
                "target_count_after": targetCountAfterMove,
                "source_list_empty_verified": true,
                "target_list_verified": true,
                "list_deleted_verified": true,
                "list_absent_verified": true,
            ],
            "warnings": [],
        ])
    }

    if operation == "rename_list" || operation == "delete_list" {
        let listId = stringValue(request, "list_id")
        let expectedTitle = stringValue(request, "expected_list_title")
        let expectedSourceType = stringValue(request, "expected_source_type")
        let expectedEmptyList = boolValue(request, "expected_empty_list") ?? false
        if listId.isEmpty || expectedTitle.isEmpty || !expectedEmptyList {
            emitReminderListManagementError("error", "missing_required_field", "Reminder list management requires list_id, expected_list_title, and expected_empty_list.")
        }
        guard let list = store.calendar(withIdentifier: listId) else {
            emitReminderListManagementError("not_found", "target_list_not_found", "Reminder list target was not found.")
        }
        if list.title != expectedTitle || sourceTypeName(list.source.sourceType) != expectedSourceType {
            emitReminderListManagementError("error", "expected_state_mismatch", "Reminder list target did not match expected state.")
        }
        if list.title.isEmpty || list.isSubscribed || list.isImmutable {
            emitReminderListManagementError("error", "unsupported_list_state", "Reminder list management refuses untitled, subscribed, or immutable lists.")
        }
        if !list.allowsContentModifications {
            emitReminderListManagementError("error", "target_list_not_writable", "Reminder list target does not allow changes.")
        }
        if !listIsReminderOnly(list) {
            emitReminderListManagementError("error", "unsupported_list_state", "Reminder list management refuses non-reminder-only calendars.")
        }
        if reminderCount(list) != 0 {
            emitReminderListManagementError("error", "list_not_empty", "Reminder list management refuses non-empty lists.")
        }
        if operation == "rename_list" {
            let newTitle = stringValue(request, "new_list_title")
            if newTitle.isEmpty {
                emitReminderListManagementError("error", "missing_required_field", "Reminder rename-list requires new_list_title.")
            }
            if listWithTitleInSource(newTitle, sourceIdentifier: list.source.sourceIdentifier, excluding: list.calendarIdentifier) != nil {
                emitReminderListManagementError("error", "list_already_exists", "A Reminders list with that title already exists in the selected source.")
            }
            list.title = newTitle
            do {
                try store.saveCalendar(list, commit: true)
            } catch {
                emitReminderListManagementError("error", "eventkit_apply_failed", "Reminder list could not be renamed.")
            }
            guard let readBack = store.calendar(withIdentifier: list.calendarIdentifier),
                  readBack.title == newTitle
            else {
                emitReminderListManagementError("apply_unknown", "read_back_unavailable", "Reminder list was renamed but read-back was unavailable.", mutationApplied: true)
            }
            let reminders = remindersOrManagementError()
            let listEmptyVerified = reminderCount(readBack) == 0
            if !listEmptyVerified {
                emitReminderListManagementError("apply_unknown", "list_rename_read_back_mismatch", "Reminder list was renamed but empty-list proof failed.", mutationApplied: true)
            }
            emit([
                "schema_version": 1,
                "status": "ok",
                "source": "reminders",
                "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
                "mutation_applied": true,
                "list": reminderListPayload(readBack, reminders: reminders),
                "read_back": [
                    "list_renamed_verified": true,
                    "list_empty_verified": listEmptyVerified,
                ],
                "warnings": [],
            ])
        }
        if operation == "delete_list" {
            do {
                try store.removeCalendar(list, commit: true)
            } catch {
                emitReminderListManagementError("error", "eventkit_apply_failed", "Reminder list could not be deleted.")
            }
            if store.calendar(withIdentifier: listId) != nil {
                emitReminderListManagementError("apply_unknown", "list_delete_read_back_mismatch", "Reminder list was deleted but absence proof failed.", mutationApplied: true)
            }
            emit([
                "schema_version": 1,
                "status": "ok",
                "source": "reminders",
                "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
                "mutation_applied": true,
                "list": NSNull(),
                "read_back": [
                    "list_deleted_verified": true,
                    "list_absent_verified": true,
                    "list_empty_verified": true,
                ],
                "warnings": [],
            ])
        }
    }

    emitReminderListManagementError("error", "invalid_operation", "Unsupported Reminder list operation.")
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
    let includeContent = boolValue(request, "include_content") ?? true
    let includeURLProof = boolValue(request, "include_url_proof") ?? false
    let includeAlarmProof = boolValue(request, "include_alarm_proof") ?? false
    let includeRecurrenceProof = boolValue(request, "include_recurrence_proof") ?? false
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "reminders",
        "reminder": reminderPayload(
            reminder,
            includeContent: includeContent,
            includeURLProof: includeURLProof,
            includeAlarmProof: includeAlarmProof,
            includeRecurrenceProof: includeRecurrenceProof
        ),
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
    if operation != "create"
        && operation != "create_with_start_date"
        && operation != "create_with_recurrence"
        && operation != "complete"
        && operation != "uncomplete"
        && operation != "update_due_date"
        && operation != "update_start_date"
        && operation != "update_recurrence"
        && operation != "update_title"
        && operation != "update_notes"
        && operation != "update_priority"
        && operation != "update_url"
        && operation != "clear_url"
        && operation != "set_absolute_display_alarm"
        && operation != "set_relative_display_alarm"
        && operation != "set_mixed_display_alarm"
        && operation != "clear_display_alarm"
        && operation != "move_to_list"
        && operation != "delete" {
        emitReminderApplyError("error", "invalid_operation", "Unsupported Reminder apply operation.")
    }

    if operation == "create" || operation == "create_with_start_date" || operation == "create_with_recurrence" {
        let title = stringValue(request, "title")
        let listName = stringValue(request, "list_name")
        let dueDate = stringValue(request, "due_date")
        let startDate = stringValue(request, "start_date")
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
        guard startDate.isEmpty || dateComponents(fromDueDate: startDate) != nil else {
            emitReminderApplyError("error", "invalid_start_date", "Reminder start date could not be parsed.")
        }
        var proposedRecurrence: [String: Any] = emptyRecurrencePayload()
        if operation == "create_with_recurrence" {
            guard let parsedRecurrence = recurrenceRequest(request) else {
                emitReminderApplyError("error", "invalid_recurrence", "Reminder recurrence must be a bounded daily, weekly, monthly, or yearly rule.")
            }
            proposedRecurrence = parsedRecurrence
            if (proposedRecurrence["recurrence_present"] as? Bool) != true {
                emitReminderApplyError("error", "invalid_recurrence", "Reminder recurrence must be a bounded daily, weekly, monthly, or yearly rule.")
            }
            if dueDate.isEmpty {
                emitReminderApplyError("error", "missing_required_field", "Reminder recurrence requires a due date anchor.")
            }
        }
        let list = matchingLists[0]
        if operation == "create" {
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
        }

        let reminder = EKReminder(eventStore: store)
        reminder.title = title
        reminder.calendar = list
        if !notes.isEmpty {
            reminder.notes = notes
        }
        reminder.dueDateComponents = dateComponents(fromDueDate: dueDate)
        if operation == "create_with_start_date" {
            reminder.startDateComponents = startDate.isEmpty ? nil : dateComponents(fromDueDate: startDate)
        }
        if operation == "create_with_recurrence" {
            applyRecurrence(reminder, recurrence: proposedRecurrence)
        }
        do {
            try store.save(reminder, commit: true)
        } catch {
            emitReminderApplyError("error", "eventkit_apply_failed", "Reminder create could not be applied.")
        }
        if operation == "create_with_start_date" {
            guard let refreshed = fetchReminders(store)?.first(where: { $0.calendarItemIdentifier == reminder.calendarItemIdentifier }) else {
                emitReminderApplyError("apply_unknown", "read_back_unavailable", "Reminder start-date create read-back did not return the changed reminder.", mutationApplied: true)
            }
            guard dueDateMatches(refreshed.startDateComponents, startDate) else {
                emitReminderApplyError("apply_unknown", "start_date_read_back_mismatch", "Reminder start-date create read-back did not match the approved value.", mutationApplied: true)
            }
            emit([
                "schema_version": 1,
                "status": "ok",
                "source": "reminders",
                "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
                "reminder": reminderPayload(refreshed, includeContent: false),
                "warnings": [],
            ])
        }
        if operation == "create_with_recurrence" {
            guard let refreshed = fetchReminders(store)?.first(where: { $0.calendarItemIdentifier == reminder.calendarItemIdentifier }) else {
                emitReminderApplyError("apply_unknown", "read_back_unavailable", "Reminder recurrence create read-back did not return the changed reminder.", mutationApplied: true)
            }
            guard recurrenceMatches(refreshed, proposedRecurrence) else {
                emitReminderApplyError("apply_unknown", "recurrence_read_back_mismatch", "Reminder recurrence create read-back did not match the approved value.", mutationApplied: true)
            }
            emit([
                "schema_version": 1,
                "status": "ok",
                "source": "reminders",
                "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
                "reminder": reminderPayload(refreshed, includeContent: false, includeRecurrenceProof: true),
                "warnings": [],
            ])
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

    if let expectedCompleted = boolValue(request, "expected_completed"),
       reminder.isCompleted != expectedCompleted {
        emitReminderApplyError("error", "expected_state_mismatch", "Reminder completion state did not match expected state.")
    }

    var targetListIdForReadBack: String? = nil
    var expectedURLSHA256ForReadBack = ""
    var verifyURLClearReadBack = false
    var expectedAlarmDatesForReadBack: [String] = []
    var expectedAlarmOffsetsForReadBack: [Int] = []
    var verifyAlarmClearReadBack = false
    var expectedStartDateForReadBack = ""
    var verifyStartDateClearReadBack = false
    var proposedRecurrenceForReadBack: [String: Any] = emptyRecurrencePayload()
    var verifyRecurrenceClearReadBack = false

    if operation == "complete" || operation == "uncomplete" {
        let targetCompleted = operation == "complete"
        if reminder.isCompleted == targetCompleted {
            let alreadyMessage = targetCompleted ? "Reminder is already complete." : "Reminder is already incomplete."
            emit([
                "schema_version": 1,
                "status": "ok",
                "source": "reminders",
                "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
                "reminder": reminderPayload(reminder, includeContent: false),
                "warnings": [warning("already_applied", alreadyMessage)],
            ])
        }
        reminder.isCompleted = targetCompleted
        reminder.completionDate = targetCompleted ? Date() : nil
    } else if operation == "update_due_date" {
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
    } else if operation == "update_start_date" {
        let startDate = stringValue(request, "start_date")
        let expectedStartDate = stringValue(request, "expected_start_date")
        guard startDate.isEmpty || dateComponents(fromDueDate: startDate) != nil else {
            emitReminderApplyError("error", "invalid_start_date", "Reminder start date could not be parsed.")
        }
        if !dueDateMatches(reminder.startDateComponents, expectedStartDate) {
            emitReminderApplyError("error", "expected_state_mismatch", "Reminder start date did not match expected state.")
        }
        if dueDateMatches(reminder.startDateComponents, startDate) {
            emit([
                "schema_version": 1,
                "status": "ok",
                "source": "reminders",
                "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
                "reminder": reminderPayload(reminder, includeContent: false),
                "warnings": [warning("already_applied", "Reminder start date already matches.")],
            ])
        }
        expectedStartDateForReadBack = startDate
        verifyStartDateClearReadBack = startDate.isEmpty
        reminder.startDateComponents = startDate.isEmpty ? nil : dateComponents(fromDueDate: startDate)
    } else if operation == "update_recurrence" {
        let clearRecurrence = boolValue(request, "clear_recurrence") ?? false
        guard let parsedRecurrence = recurrenceRequest(request) else {
            emitReminderApplyError("error", "invalid_recurrence", "Reminder recurrence must be a bounded daily, weekly, monthly, or yearly rule.")
        }
        guard let expectedRecurrence = recurrenceRequest(request, key: "expected_recurrence") else {
            emitReminderApplyError("error", "invalid_recurrence", "Reminder expected recurrence must be a bounded daily, weekly, monthly, or yearly rule.")
        }
        let recurrencePresent = (parsedRecurrence["recurrence_present"] as? Bool) == true
        if clearRecurrence && recurrencePresent {
            emitReminderApplyError("error", "conflicting_recurrence_fields", "Use either recurrence fields or clear_recurrence, not both.")
        }
        if !clearRecurrence && !recurrencePresent {
            emitReminderApplyError("error", "missing_required_field", "Reminder update_recurrence requires recurrence fields or clear_recurrence.")
        }
        if !recurrenceMatches(reminder, expectedRecurrence) {
            emitReminderApplyError("error", "expected_state_mismatch", "Reminder recurrence did not match expected state.")
        }
        if !clearRecurrence {
            let dueDate = reminderDateString(reminder.dueDateComponents)
            if dueDate.isEmpty {
                emitReminderApplyError("error", "missing_required_field", "Reminder recurrence requires a due date anchor.")
            }
        }
        if clearRecurrence {
            verifyRecurrenceClearReadBack = true
            proposedRecurrenceForReadBack = emptyRecurrencePayload()
            reminder.recurrenceRules = nil
        } else {
            proposedRecurrenceForReadBack = parsedRecurrence
            applyRecurrence(reminder, recurrence: parsedRecurrence)
        }
    } else if operation == "update_title" {
        let title = stringValue(request, "title")
        if title.isEmpty {
            emitReminderApplyError("error", "missing_required_field", "Reminder title update requires a title.")
        }
        if (reminder.title ?? "") == title {
            emit([
                "schema_version": 1,
                "status": "ok",
                "source": "reminders",
                "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
                "reminder": reminderPayload(reminder, includeContent: false),
                "warnings": [warning("already_applied", "Reminder title already matches.")],
            ])
        }
        reminder.title = title
    } else if operation == "update_notes" {
        let notes = stringValue(request, "notes")
        if (reminder.notes ?? "") == notes {
            emit([
                "schema_version": 1,
                "status": "ok",
                "source": "reminders",
                "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
                "reminder": reminderPayload(reminder, includeContent: false),
                "warnings": [warning("already_applied", "Reminder notes already match.")],
            ])
        }
        reminder.notes = notes.isEmpty ? nil : notes
    } else if operation == "update_url" || operation == "clear_url" {
        guard let expectedURLPresent = boolValue(request, "expected_url_present") else {
            emitReminderApplyError("error", "missing_required_field", "Reminder URL change requires expected_url_present.")
        }
        let expectedURLSHA256 = stringValue(request, "expected_url_sha256")
        let currentURLString = reminder.url?.absoluteString ?? ""
        if expectedURLPresent != !currentURLString.isEmpty {
            emitReminderApplyError("error", "expected_state_mismatch", "Reminder URL state did not match expected state.")
        }
        if expectedURLPresent {
            if expectedURLSHA256.isEmpty || !isSHA256Hex(expectedURLSHA256) {
                emitReminderApplyError("error", "invalid_expected_sha256", "Reminder expected_url_sha256 must be a SHA-256 hex digest.")
            }
            if sha256Hex(currentURLString) != expectedURLSHA256 {
                emitReminderApplyError("error", "expected_state_mismatch", "Reminder URL state did not match expected state.")
            }
        } else if !expectedURLSHA256.isEmpty {
            emitReminderApplyError("error", "unexpected_expected_url_sha256", "Reminder expected_url_sha256 requires expected_url_present=true.")
        }
        if operation == "update_url" {
            let urlString = stringValue(request, "url")
            guard let proposedURL = normalizedReminderURLOrError(urlString, "url") else {
                emitReminderApplyError("error", "missing_required_field", "Reminder URL update requires url.")
            }
            let proposedURLSHA256 = sha256Hex(urlString)
            if currentURLString == proposedURL.absoluteString {
                emit([
                    "schema_version": 1,
                    "status": "ok",
                    "source": "reminders",
                    "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
                    "reminder": reminderPayload(reminder, includeContent: false, includeURLProof: true),
                    "warnings": [warning("already_applied", "Reminder URL already matches.")],
                ])
            }
            expectedURLSHA256ForReadBack = proposedURLSHA256
            reminder.url = proposedURL
        } else {
            if currentURLString.isEmpty {
                emit([
                    "schema_version": 1,
                    "status": "ok",
                    "source": "reminders",
                    "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
                    "reminder": reminderPayload(reminder, includeContent: false, includeURLProof: true),
                    "warnings": [warning("already_applied", "Reminder URL is already clear.")],
                ])
            }
            verifyURLClearReadBack = true
            reminder.url = nil
        }
    } else if operation == "set_absolute_display_alarm"
        || operation == "set_relative_display_alarm"
        || operation == "set_mixed_display_alarm"
        || operation == "clear_display_alarm" {
        guard let expectedCompleted = boolValue(request, "expected_completed") else {
            emitReminderApplyError("error", "missing_required_field", "Reminder alarm change requires expected completion state.")
        }
        if reminder.isCompleted != expectedCompleted {
            emitReminderApplyError("error", "expected_state_mismatch", "Reminder completion state did not match expected state.")
        }
        guard let expectedAlarmsCount = optionalIntValue(request, "expected_alarms_count"),
              expectedAlarmsCount >= 0 else {
            emitReminderApplyError("error", "invalid_expected_alarms_count", "Reminder expected_alarms_count must be a non-negative integer.")
        }
        let expectedAlarmsSHA256 = stringValue(request, "expected_alarms_sha256")
        let currentAlarmsCount = reminder.alarms?.count ?? 0
        if currentAlarmsCount != expectedAlarmsCount {
            emitReminderApplyError("error", "expected_state_mismatch", "Reminder alarm state did not match expected state.")
        }
        if expectedAlarmsCount > 0 {
            if expectedAlarmsSHA256.isEmpty || !isSHA256Hex(expectedAlarmsSHA256) {
                emitReminderApplyError("error", "invalid_expected_sha256", "Reminder expected_alarms_sha256 must be a SHA-256 hex digest.")
            }
            if reminderAlarmStateSafeSHA256(reminder) != expectedAlarmsSHA256 {
                emitReminderApplyError("error", "expected_state_mismatch", "Reminder alarm state did not match expected state.")
            }
            if !reminderDisplayAlarmStateSupported(reminder) {
                emitReminderApplyError("error", "unsupported_alarm_state", "Reminder alarm state is not a supported display-alarm state.")
            }
        } else if !expectedAlarmsSHA256.isEmpty {
            emitReminderApplyError("error", "unexpected_expected_alarms_sha256", "Reminder expected_alarms_sha256 requires expected_alarms_count greater than zero.")
        }
        if operation == "set_absolute_display_alarm" {
            guard let alarmAbsoluteDates = dateStringArrayValue(request, "alarm_absolute_dates"),
                  !alarmAbsoluteDates.isEmpty else {
                emitReminderApplyError("error", "invalid_alarm_absolute_dates", "Reminder absolute alarm dates must be ISO 8601 timestamps with timezones.")
            }
            let alarms = alarmAbsoluteDates.compactMap { value -> EKAlarm? in
                guard let date = eventDate(from: value) else {
                    return nil
                }
                return EKAlarm(absoluteDate: date)
            }
            if alarms.count != alarmAbsoluteDates.count {
                emitReminderApplyError("error", "invalid_alarm_absolute_dates", "Reminder absolute alarm dates must be ISO 8601 timestamps with timezones.")
            }
            expectedAlarmDatesForReadBack = alarmAbsoluteDates
            reminder.alarms = alarms
        } else if operation == "set_relative_display_alarm" {
            guard let alarmOffsetsMinutes = intArrayValue(request, "alarm_offsets_minutes"),
                  !alarmOffsetsMinutes.isEmpty else {
                emitReminderApplyError("error", "invalid_alarm_offsets", "Reminder relative alarm offsets must be integer minute offsets.")
            }
            let alarms = alarmOffsetsMinutes.map {
                EKAlarm(relativeOffset: TimeInterval($0) * 60.0)
            }
            expectedAlarmOffsetsForReadBack = alarmOffsetsMinutes
            reminder.alarms = alarms
        } else if operation == "set_mixed_display_alarm" {
            guard let alarmOffsetsMinutes = intArrayValue(request, "alarm_offsets_minutes"),
                  !alarmOffsetsMinutes.isEmpty else {
                emitReminderApplyError("error", "invalid_alarm_offsets", "Reminder relative alarm offsets must be integer minute offsets.")
            }
            guard let alarmAbsoluteDates = dateStringArrayValue(request, "alarm_absolute_dates"),
                  !alarmAbsoluteDates.isEmpty else {
                emitReminderApplyError("error", "invalid_alarm_absolute_dates", "Reminder absolute alarm dates must be ISO 8601 timestamps with timezones.")
            }
            if alarmOffsetsMinutes.count + alarmAbsoluteDates.count > maxAlarmOffsets {
                emitReminderApplyError("error", "too_many_alarms", "Reminder mixed display alarms support at most 8 combined offsets and dates.")
            }
            let dateAlarms = alarmAbsoluteDates.compactMap { value -> EKAlarm? in
                guard let date = eventDate(from: value) else {
                    return nil
                }
                return EKAlarm(absoluteDate: date)
            }
            if dateAlarms.count != alarmAbsoluteDates.count {
                emitReminderApplyError("error", "invalid_alarm_absolute_dates", "Reminder absolute alarm dates must be ISO 8601 timestamps with timezones.")
            }
            let offsetAlarms = alarmOffsetsMinutes.map {
                EKAlarm(relativeOffset: TimeInterval($0) * 60.0)
            }
            expectedAlarmOffsetsForReadBack = alarmOffsetsMinutes
            expectedAlarmDatesForReadBack = alarmAbsoluteDates
            reminder.alarms = offsetAlarms + dateAlarms
        } else {
            if expectedAlarmsCount == 0 {
                emitReminderApplyError("error", "missing_required_field", "Reminder clear_display_alarm requires expected_alarms_count greater than zero.")
            }
            verifyAlarmClearReadBack = true
            reminder.alarms = []
        }
    } else if operation == "move_to_list" {
        let targetListId = stringValue(request, "target_list_id")
        let expectedListId = stringValue(request, "expected_list_id")
        let expectedListName = stringValue(request, "expected_list_name")
        guard let expectedCompleted = boolValue(request, "expected_completed") else {
            emitReminderApplyError("error", "missing_required_field", "Reminder list move requires expected completion state.")
        }
        if targetListId.isEmpty || expectedListId.isEmpty || expectedListName.isEmpty {
            emitReminderApplyError("error", "missing_required_field", "Reminder list move requires target list and exact expected current list.")
        }
        if reminder.isCompleted != expectedCompleted {
            emitReminderApplyError("error", "expected_state_mismatch", "Reminder completion state did not match expected state.")
        }
        guard let targetList = store.calendars(for: .reminder).first(where: { $0.calendarIdentifier == targetListId }) else {
            emitReminderApplyError("not_found", "target_list_not_found", "Reminder target list was not found.")
        }
        if reminder.calendar.source.sourceIdentifier != targetList.source.sourceIdentifier {
            emitReminderApplyError("error", "cross_account_list_move", "Reminder list move across accounts is not approved.")
        }
        if reminder.calendar.title != expectedListName {
            emitReminderApplyError("error", "expected_state_mismatch", "Reminder list did not match expected state.")
        }
        if reminder.calendar.calendarIdentifier != expectedListId {
            emitReminderApplyError("error", "expected_state_mismatch", "Reminder current list identity did not match expected state.")
        }
        if reminder.calendar.calendarIdentifier == targetList.calendarIdentifier {
            emit([
                "schema_version": 1,
                "status": "ok",
                "source": "reminders",
                "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
                "reminder": reminderPayload(reminder, includeContent: false),
                "target_list_verified": true,
                "warnings": [warning("already_applied", "Reminder already belongs to the target list.")],
            ])
        }
        targetListIdForReadBack = targetList.calendarIdentifier
        reminder.calendar = targetList
    } else if operation == "delete" {
        guard let expectedPriority = optionalIntValue(request, "expected_priority") else {
            emitReminderApplyError("error", "missing_required_field", "Reminder delete requires expected priority.")
        }
        if reminder.priority != expectedPriority {
            emitReminderApplyError("error", "expected_state_mismatch", "Reminder priority did not match expected state.")
        }
        do {
            try store.remove(reminder, commit: true)
        } catch {
            emitReminderApplyError("error", "eventkit_apply_failed", "Reminder delete could not be applied.")
        }
        let stillPresent = fetchReminders(store)?.contains(where: { $0.calendarItemIdentifier == reminderId }) ?? true
        if stillPresent {
            emitReminderApplyError("apply_unknown", "read_back_unavailable", "Reminder delete read-back did not prove target absence.")
        }
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "reminders",
            "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
            "deleted": true,
            "read_back": [
                "deleted": true,
                "verified_absent": true,
            ],
            "warnings": [],
        ])
    } else {
        guard let priority = optionalIntValue(request, "priority"),
              priority >= 0,
              priority <= 9 else {
            emitReminderApplyError("error", "invalid_priority", "Reminder priority must be an integer from 0 to 9.")
        }
        if let expectedPriority = optionalIntValue(request, "expected_priority"),
           reminder.priority != expectedPriority {
            emitReminderApplyError("error", "expected_state_mismatch", "Reminder priority did not match expected state.")
        }
        if reminder.priority == priority {
            emit([
                "schema_version": 1,
                "status": "ok",
                "source": "reminders",
                "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
                "reminder": reminderPayload(reminder, includeContent: false),
                "warnings": [warning("already_applied", "Reminder priority already matches.")],
            ])
        }
        reminder.priority = priority
    }

    do {
        try store.save(reminder, commit: true)
    } catch {
        emitReminderApplyError("error", "eventkit_apply_failed", "Reminder change could not be applied.")
    }
    var response: [String: Any] = [
        "schema_version": 1,
        "status": "ok",
        "source": "reminders",
        "authorization_status": authorizationName(EKEventStore.authorizationStatus(for: .reminder)),
        "reminder": reminderPayload(
            reminder,
            includeContent: false,
            includeURLProof: operation == "update_url" || operation == "clear_url",
            includeAlarmProof: operation == "set_absolute_display_alarm" || operation == "set_relative_display_alarm" || operation == "set_mixed_display_alarm" || operation == "clear_display_alarm",
            includeAlarmDates: operation == "set_absolute_display_alarm" || operation == "set_mixed_display_alarm",
            includeAlarmOffsets: operation == "set_relative_display_alarm" || operation == "set_mixed_display_alarm",
            includeRecurrenceProof: operation == "update_recurrence"
        ),
        "warnings": [],
    ]
    if operation == "move_to_list" {
        if let targetListId = targetListIdForReadBack {
            if let refreshed = fetchReminders(store)?.first(where: { $0.calendarItemIdentifier == reminderId }) {
                response["reminder"] = reminderPayload(refreshed, includeContent: false)
                response["target_list_verified"] = refreshed.calendar.calendarIdentifier == targetListId
            } else {
                emitReminderApplyError("apply_unknown", "read_back_unavailable", "Reminder list-move read-back did not return the changed reminder.")
            }
        } else {
            response["target_list_verified"] = false
        }
    }
    if operation == "update_url" {
        guard let refreshed = fetchReminders(store)?.first(where: { $0.calendarItemIdentifier == reminderId }) else {
            emitReminderApplyError("apply_unknown", "read_back_unavailable", "Reminder URL read-back did not return the changed reminder.", mutationApplied: true)
        }
        let refreshedURLString = refreshed.url?.absoluteString ?? ""
        if refreshedURLString.isEmpty || sha256Hex(refreshedURLString) != expectedURLSHA256ForReadBack {
            emitReminderApplyError("apply_unknown", "url_read_back_mismatch", "Reminder URL read-back did not match the approved value.", mutationApplied: true)
        }
        response["reminder"] = reminderPayload(refreshed, includeContent: false, includeURLProof: true)
    }
    if operation == "clear_url" {
        guard let refreshed = fetchReminders(store)?.first(where: { $0.calendarItemIdentifier == reminderId }) else {
            emitReminderApplyError("apply_unknown", "read_back_unavailable", "Reminder URL clear read-back did not return the changed reminder.", mutationApplied: true)
        }
        if verifyURLClearReadBack && refreshed.url != nil {
            emitReminderApplyError("apply_unknown", "url_read_back_mismatch", "Reminder URL clear read-back did not prove absence.", mutationApplied: true)
        }
        response["reminder"] = reminderPayload(refreshed, includeContent: false, includeURLProof: true)
    }
    if operation == "set_absolute_display_alarm" {
        guard let refreshed = fetchReminders(store)?.first(where: { $0.calendarItemIdentifier == reminderId }) else {
            emitReminderApplyError("apply_unknown", "read_back_unavailable", "Reminder absolute alarm read-back did not return the changed reminder.", mutationApplied: true)
        }
        let readBackDates = reminderAbsoluteAlarmDates(refreshed) ?? []
        if readBackDates != expectedAlarmDatesForReadBack {
            emitReminderApplyError("apply_unknown", "alarm_read_back_mismatch", "Reminder absolute alarm read-back did not match the approved value.", mutationApplied: true)
        }
        response["reminder"] = reminderPayload(
            refreshed,
            includeContent: false,
            includeAlarmProof: true,
            includeAlarmDates: true
        )
    }
    if operation == "set_relative_display_alarm" {
        guard let refreshed = fetchReminders(store)?.first(where: { $0.calendarItemIdentifier == reminderId }) else {
            emitReminderApplyError("apply_unknown", "read_back_unavailable", "Reminder relative alarm read-back did not return the changed reminder.", mutationApplied: true)
        }
        let readBackOffsets = reminderRelativeAlarmOffsets(refreshed) ?? []
        if readBackOffsets != expectedAlarmOffsetsForReadBack {
            emitReminderApplyError("apply_unknown", "alarm_read_back_mismatch", "Reminder relative alarm read-back did not match the approved value.", mutationApplied: true)
        }
        response["reminder"] = reminderPayload(
            refreshed,
            includeContent: false,
            includeAlarmProof: true,
            includeAlarmOffsets: true
        )
    }
    if operation == "set_mixed_display_alarm" {
        guard let refreshed = fetchReminders(store)?.first(where: { $0.calendarItemIdentifier == reminderId }) else {
            emitReminderApplyError("apply_unknown", "read_back_unavailable", "Reminder mixed alarm read-back did not return the changed reminder.", mutationApplied: true)
        }
        guard let mixedState = reminderMixedDisplayAlarmState(refreshed),
              mixedState.offsets == expectedAlarmOffsetsForReadBack,
              mixedState.absoluteDates == expectedAlarmDatesForReadBack else {
            emitReminderApplyError("apply_unknown", "alarm_read_back_mismatch", "Reminder mixed alarm read-back did not match the approved value.", mutationApplied: true)
        }
        response["reminder"] = reminderPayload(
            refreshed,
            includeContent: false,
            includeAlarmProof: true,
            includeAlarmDates: true,
            includeAlarmOffsets: true
        )
    }
    if operation == "clear_display_alarm" {
        guard let refreshed = fetchReminders(store)?.first(where: { $0.calendarItemIdentifier == reminderId }) else {
            emitReminderApplyError("apply_unknown", "read_back_unavailable", "Reminder alarm clear read-back did not return the changed reminder.", mutationApplied: true)
        }
        if verifyAlarmClearReadBack && refreshed.alarms?.isEmpty == false {
            emitReminderApplyError("apply_unknown", "alarm_read_back_mismatch", "Reminder alarm clear read-back did not prove absence.", mutationApplied: true)
        }
        response["reminder"] = reminderPayload(refreshed, includeContent: false, includeAlarmProof: true)
    }
    if operation == "update_start_date" {
        guard let refreshed = fetchReminders(store)?.first(where: { $0.calendarItemIdentifier == reminderId }) else {
            emitReminderApplyError("apply_unknown", "read_back_unavailable", "Reminder start-date read-back did not return the changed reminder.", mutationApplied: true)
        }
        if verifyStartDateClearReadBack {
            if reminderDateString(refreshed.startDateComponents).isEmpty == false {
                emitReminderApplyError("apply_unknown", "start_date_read_back_mismatch", "Reminder start-date clear read-back did not prove absence.", mutationApplied: true)
            }
        } else if !dueDateMatches(refreshed.startDateComponents, expectedStartDateForReadBack) {
            emitReminderApplyError("apply_unknown", "start_date_read_back_mismatch", "Reminder start-date read-back did not match the approved value.", mutationApplied: true)
        }
        response["reminder"] = reminderPayload(refreshed, includeContent: false)
    }
    if operation == "update_recurrence" {
        guard let refreshed = fetchReminders(store)?.first(where: { $0.calendarItemIdentifier == reminderId }) else {
            emitReminderApplyError("apply_unknown", "read_back_unavailable", "Reminder recurrence read-back did not return the changed reminder.", mutationApplied: true)
        }
        if verifyRecurrenceClearReadBack {
            if refreshed.recurrenceRules?.isEmpty == false {
                emitReminderApplyError("apply_unknown", "recurrence_read_back_mismatch", "Reminder recurrence clear read-back did not prove absence.", mutationApplied: true)
            }
        } else if !recurrenceMatches(refreshed, proposedRecurrenceForReadBack) {
            emitReminderApplyError("apply_unknown", "recurrence_read_back_mismatch", "Reminder recurrence read-back did not match the approved value.", mutationApplied: true)
        }
        response["reminder"] = reminderPayload(refreshed, includeContent: false, includeRecurrenceProof: true)
    }
    emit(response)
}

emit([
    "schema_version": 1,
    "status": "error",
    "source": "eventkit",
    "warnings": [warning("unknown_command", "Unsupported EventKit helper command.")],
])
