import AppKit
import Contacts
import CryptoKit
import Dispatch
import Foundation

let isoFormatter = ISO8601DateFormatter()
isoFormatter.formatOptions = [.withFullDate]

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

func stringValue(_ request: [String: Any], _ key: String) -> String {
    return (request[key] as? String) ?? ""
}

func authorizationName(_ status: CNAuthorizationStatus) -> String {
    switch status {
    case .authorized:
        return "authorized"
    case .denied:
        return "denied"
    case .notDetermined:
        return "not_determined"
    case .restricted:
        return "restricted"
    @unknown default:
        // `limited` is not currently exposed by the macOS Contacts SDK, but
        // Apple reserves raw value 4 for it on platforms that support limited
        // Contacts authorization. Recognize it without referencing an SDK
        // symbol that is unavailable when compiling this macOS helper.
        if status.rawValue == 4 {
            return "limited"
        }
        return "unknown"
    }
}

func ensureAccess() -> CNContactStore? {
    let status = CNContactStore.authorizationStatus(for: .contacts)
    if status != .authorized {
        emit([
            "schema_version": 1,
            "status": "degraded",
            "source": "contacts",
            "authorization_status": authorizationName(status),
            "contacts": [],
            "contact": NSNull(),
            "warnings": [
                warning(
                    "contacts_access_unavailable",
                    "Contacts access is not authorized for this process."
                )
            ],
        ])
    }
    return CNContactStore()
}

final class ContactsAccessDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        NSApp.activate(ignoringOtherApps: true)
        let store = CNContactStore()
        store.requestAccess(for: .contacts) { granted, error in
            DispatchQueue.main.async {
                let finalStatus = CNContactStore.authorizationStatus(for: .contacts)
                if granted && finalStatus == .authorized {
                    emit([
                        "schema_version": 1,
                        "status": "ok",
                        "source": "contacts",
                        "authorization_status": authorizationName(finalStatus),
                        "request_result": "granted",
                        "warnings": [],
                    ])
                }
                if authorizationName(finalStatus) == "limited" {
                    emit([
                        "schema_version": 1,
                        "status": "degraded",
                        "source": "contacts",
                        "authorization_status": "limited",
                        "request_result": "limited",
                        "warnings": [
                            warning(
                                "contacts_full_access_required",
                                "Full Contacts access is required for this local helper."
                            )
                        ],
                    ])
                }
                emit([
                    "schema_version": 1,
                    "status": "degraded",
                    "source": "contacts",
                    "authorization_status": authorizationName(finalStatus),
                    "request_result": error == nil ? "not_granted" : "failed",
                    "warnings": [
                        warning(
                            "contacts_access_unavailable",
                            "Contacts access was not granted to this process."
                        )
                    ],
                ])
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 180) {
            emit([
                "schema_version": 1,
                "status": "degraded",
                "source": "contacts",
                "authorization_status": authorizationName(
                    CNContactStore.authorizationStatus(for: .contacts)
                ),
                "request_result": "timeout",
                "warnings": [
                    warning(
                        "contacts_access_request_timeout",
                        "Contacts access prompt did not complete before timeout."
                    )
                ],
            ])
        }
    }
}

private var contactsAccessDelegate: ContactsAccessDelegate?

func requestContactsAccess() -> Never {
    let initialStatus = CNContactStore.authorizationStatus(for: .contacts)
    let initialStatusName = authorizationName(initialStatus)
    if initialStatus == .authorized {
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": authorizationName(initialStatus),
            "request_result": "already_authorized",
            "warnings": [],
        ])
    }
    if initialStatus == .denied || initialStatus == .restricted {
        emit([
            "schema_version": 1,
            "status": "degraded",
            "source": "contacts",
            "authorization_status": authorizationName(initialStatus),
            "request_result": "not_granted",
            "warnings": [
                warning(
                    "contacts_access_unavailable",
                    "Contacts access is not authorized for this process."
                )
            ],
        ])
    }
    if initialStatusName == "limited" {
        emit([
            "schema_version": 1,
            "status": "degraded",
            "source": "contacts",
            "authorization_status": "limited",
            "request_result": "limited",
            "warnings": [
                warning(
                    "contacts_full_access_required",
                    "Full Contacts access is required for this local helper."
                )
            ],
        ])
    }

    let delegate = ContactsAccessDelegate()
    contactsAccessDelegate = delegate
    let app = NSApplication.shared
    app.setActivationPolicy(.regular)
    app.delegate = delegate
    app.run()
    emit([
        "schema_version": 1,
        "status": "degraded",
        "source": "contacts",
        "authorization_status": authorizationName(
            CNContactStore.authorizationStatus(for: .contacts)
        ),
        "request_result": "not_granted",
        "warnings": [
            warning(
                "contacts_access_unavailable",
                "Contacts access was not granted to this process."
            )
        ],
    ])
}

let baseKeys: [CNKeyDescriptor] = [
    CNContactFormatter.descriptorForRequiredKeys(for: .fullName),
    CNContactIdentifierKey as CNKeyDescriptor,
    CNContactTypeKey as CNKeyDescriptor,
    CNContactNamePrefixKey as CNKeyDescriptor,
    CNContactGivenNameKey as CNKeyDescriptor,
    CNContactMiddleNameKey as CNKeyDescriptor,
    CNContactFamilyNameKey as CNKeyDescriptor,
    CNContactPreviousFamilyNameKey as CNKeyDescriptor,
    CNContactNameSuffixKey as CNKeyDescriptor,
    CNContactNicknameKey as CNKeyDescriptor,
    CNContactOrganizationNameKey as CNKeyDescriptor,
    CNContactDepartmentNameKey as CNKeyDescriptor,
    CNContactJobTitleKey as CNKeyDescriptor,
    CNContactEmailAddressesKey as CNKeyDescriptor,
    CNContactPhoneNumbersKey as CNKeyDescriptor,
    CNContactPostalAddressesKey as CNKeyDescriptor,
    CNContactUrlAddressesKey as CNKeyDescriptor,
    CNContactBirthdayKey as CNKeyDescriptor,
    CNContactDatesKey as CNKeyDescriptor,
    CNContactSocialProfilesKey as CNKeyDescriptor,
    CNContactInstantMessageAddressesKey as CNKeyDescriptor,
    CNContactRelationsKey as CNKeyDescriptor,
    CNContactImageDataAvailableKey as CNKeyDescriptor,
]

let detailKeys: [CNKeyDescriptor] = baseKeys + [
    CNContactImageDataKey as CNKeyDescriptor,
]

let updateStateKeys: [CNKeyDescriptor] = detailKeys

let noteStateKeys: [CNKeyDescriptor] = [
    CNContactIdentifierKey as CNKeyDescriptor,
    CNContactNoteKey as CNKeyDescriptor,
]

let archiveKeysWithoutNotes: [CNKeyDescriptor] = detailKeys

let archiveKeysWithNotes: [CNKeyDescriptor] = archiveKeysWithoutNotes + [
    CNContactVCardSerialization.descriptorForRequiredKeys(),
    CNContactNoteKey as CNKeyDescriptor,
]

func labelName(_ label: String?) -> String {
    guard let label = label else {
        return ""
    }
    return CNLabeledValue<NSString>.localizedString(forLabel: label)
}

func displayName(_ contact: CNContact) -> String {
    if let name = CNContactFormatter.string(from: contact, style: .fullName),
       !name.isEmpty {
        return name
    }
    if !contact.organizationName.isEmpty {
        return contact.organizationName
    }
    return [contact.givenName, contact.familyName]
        .filter { !$0.isEmpty }
        .joined(separator: " ")
}

func contactTypeName(_ contact: CNContact) -> String {
    switch contact.contactType {
    case .person:
        return "person"
    case .organization:
        return "organization"
    @unknown default:
        return "unknown"
    }
}

func containerTypeName(_ container: CNContainer) -> String {
    switch container.type {
    case .unassigned:
        return "unassigned"
    case .local:
        return "local"
    case .exchange:
        return "exchange"
    case .cardDAV:
        return "carddav"
    @unknown default:
        return "unknown"
    }
}

func dateComponentsPayload(_ components: DateComponents?) -> [String: Any] {
    guard let components = components else {
        return [:]
    }
    var payload: [String: Any] = [:]
    if let year = components.year {
        payload["year"] = year
    }
    if let month = components.month {
        payload["month"] = month
    }
    if let day = components.day {
        payload["day"] = day
    }
    return payload
}

func stringLabeledValues(_ values: [CNLabeledValue<NSString>]) -> [[String: Any]] {
    return values.map {
        [
            "label": labelName($0.label),
            "value": String($0.value),
        ]
    }
}

func phonePayloads(_ values: [CNLabeledValue<CNPhoneNumber>]) -> [[String: Any]] {
    return values.map {
        [
            "label": labelName($0.label),
            "value": $0.value.stringValue,
        ]
    }
}

func postalPayloads(_ values: [CNLabeledValue<CNPostalAddress>]) -> [[String: Any]] {
    return values.map {
        let address = $0.value
        return [
            "label": labelName($0.label),
            "street": address.street,
            "city": address.city,
            "state": address.state,
            "postal_code": address.postalCode,
            "country": address.country,
            "iso_country_code": address.isoCountryCode,
        ]
    }
}

func datedPayloads(_ values: [CNLabeledValue<NSDateComponents>]) -> [[String: Any]] {
    return values.map {
        [
            "label": labelName($0.label),
            "date": dateComponentsPayload($0.value as DateComponents),
        ]
    }
}

func socialPayloads(_ values: [CNLabeledValue<CNSocialProfile>]) -> [[String: Any]] {
    return values.map {
        let profile = $0.value
        return [
            "label": labelName($0.label),
            "service": profile.service,
            "username": profile.username,
            "url": profile.urlString,
        ]
    }
}

func instantMessagePayloads(_ values: [CNLabeledValue<CNInstantMessageAddress>]) -> [[String: Any]] {
    return values.map {
        let address = $0.value
        return [
            "label": labelName($0.label),
            "service": address.service,
            "username": address.username,
        ]
    }
}

func relationPayloads(_ values: [CNLabeledValue<CNContactRelation>]) -> [[String: Any]] {
    return values.map {
        [
            "label": labelName($0.label),
            "name": $0.value.name,
        ]
    }
}

func sha256Hex(_ data: Data) -> String {
    let digest = SHA256.hash(data: data)
    return digest.map { String(format: "%02x", $0) }.joined()
}

func contactPayload(_ contact: CNContact, includeDetails: Bool, includeNote: Bool = false) -> [String: Any] {
    var payload: [String: Any] = [
        "contact_id": contact.identifier,
        "display_name": displayName(contact),
        "contact_type": contactTypeName(contact),
        "given_name": contact.givenName,
        "family_name": contact.familyName,
        "nickname": contact.nickname,
        "organization_name": contact.organizationName,
        "department_name": contact.departmentName,
        "job_title": contact.jobTitle,
        "email_count": contact.emailAddresses.count,
        "phone_count": contact.phoneNumbers.count,
        "postal_address_count": contact.postalAddresses.count,
        "url_count": contact.urlAddresses.count,
        "social_profile_count": contact.socialProfiles.count,
        "instant_message_count": contact.instantMessageAddresses.count,
        "relation_count": contact.contactRelations.count,
        "dates_count": contact.dates.count,
        "birthday_present": contact.birthday != nil,
        "image_available": contact.imageDataAvailable,
        "note_status": "requires_entitlement",
    ]
    if includeNote {
        if contact.isKeyAvailable(CNContactNoteKey) {
            payload["note_status"] = "available"
            payload["note_text"] = contact.note
            payload["note_chars"] = contact.note.count
        } else {
            payload["note_status"] = "unavailable"
        }
    }
    if includeDetails {
        payload["name_prefix"] = contact.namePrefix
        payload["middle_name"] = contact.middleName
        payload["previous_family_name"] = contact.previousFamilyName
        payload["name_suffix"] = contact.nameSuffix
        payload["email_addresses"] = stringLabeledValues(contact.emailAddresses)
        payload["phone_numbers"] = phonePayloads(contact.phoneNumbers)
        payload["postal_addresses"] = postalPayloads(contact.postalAddresses)
        payload["url_addresses"] = stringLabeledValues(contact.urlAddresses)
        payload["birthday"] = dateComponentsPayload(contact.birthday)
        payload["dates"] = datedPayloads(contact.dates)
        payload["social_profiles"] = socialPayloads(contact.socialProfiles)
        payload["instant_message_addresses"] = instantMessagePayloads(contact.instantMessageAddresses)
        payload["contact_relations"] = relationPayloads(contact.contactRelations)
        if contact.isKeyAvailable(CNContactImageDataKey), let imageData = contact.imageData {
            payload["image_bytes"] = imageData.count
            payload["image_sha256"] = sha256Hex(imageData)
        } else {
            payload["image_bytes"] = 0
            payload["image_sha256"] = ""
        }
    }
    return payload
}

func contactNoteStatePayload(_ contact: CNContact) -> [String: Any] {
    var payload: [String: Any] = [
        "contact_id": contact.identifier,
        "note_status": "requires_entitlement",
        "note_text": "",
        "note_chars": 0,
    ]
    if contact.isKeyAvailable(CNContactNoteKey) {
        payload["note_status"] = "available"
        payload["note_text"] = contact.note
        payload["note_chars"] = contact.note.count
    }
    return payload
}

func groupPayload(_ store: CNContactStore, _ group: CNGroup) -> [String: Any] {
    let contacts = (try? store.unifiedContacts(
        matching: CNContact.predicateForContactsInGroup(withIdentifier: group.identifier),
        keysToFetch: [CNContactIdentifierKey as CNKeyDescriptor]
    )) ?? []
    return [
        "group_id": group.identifier,
        "name": group.name,
        "member_count": contacts.count,
        "member_ids": contacts.map { $0.identifier }.sorted(),
    ]
}

func sortedGroupContacts(_ contacts: [CNContact]) -> [CNContact] {
    return contacts.sorted {
        let left = displayName($0).localizedCaseInsensitiveCompare(displayName($1))
        if left == .orderedSame {
            return $0.identifier < $1.identifier
        }
        return left == .orderedAscending
    }
}

func containerPayload(_ container: CNContainer) -> [String: Any] {
    return [
        "container_id": container.identifier,
        "name": container.name,
        "type": containerTypeName(container),
    ]
}

func groupState(_ store: CNContactStore, _ group: CNGroup) -> [String: String] {
    let payload = groupPayload(store, group)
    return [
        "name": canonicalString(payload["name"] ?? ""),
        "member_count": canonicalString(payload["member_count"] ?? 0),
        "member_ids": canonicalString(payload["member_ids"] ?? []),
    ]
}

func containerState(_ container: CNContainer) -> [String: String] {
    let payload = containerPayload(container)
    return [
        "name": canonicalString(payload["name"] ?? ""),
        "type": canonicalString(payload["type"] ?? ""),
    ]
}

func containerMatchesExpected(_ container: CNContainer, expected: [String: String]) -> Bool {
    let current = containerState(container)
    for key in ["name", "type"] {
        if current[key] != expected[key] {
            return false
        }
    }
    return true
}

func groupMatchesExpected(_ store: CNContactStore, _ group: CNGroup, expected: [String: String]) -> Bool {
    let current = groupState(store, group)
    for key in ["name", "member_count", "member_ids"] {
        if current[key] != expected[key] {
            return false
        }
    }
    return true
}

func containers(_ store: CNContactStore) -> [CNContainer] {
    return (try? store.containers(matching: nil)) ?? []
}

func containerById(_ store: CNContactStore, _ containerId: String) -> CNContainer? {
    guard !containerId.isEmpty else {
        return nil
    }
    return containers(store).first { $0.identifier == containerId }
}

func groups(_ store: CNContactStore, containerId: String = "") -> [CNGroup] {
    if containerId.isEmpty {
        return (try? store.groups(matching: nil)) ?? []
    }
    let predicate = CNGroup.predicateForGroupsInContainer(withIdentifier: containerId)
    return (try? store.groups(matching: predicate)) ?? []
}

func groupWithName(_ store: CNContactStore, _ name: String, containerId: String = "") -> CNGroup? {
    return groups(store, containerId: containerId).first { $0.name == name }
}

func groupById(_ store: CNContactStore, _ groupId: String) -> CNGroup? {
    guard !groupId.isEmpty else {
        return nil
    }
    return groups(store).first { $0.identifier == groupId }
}

func emitContactsApplyError(_ status: String, _ code: String, _ message: String) -> Never {
    emit([
        "schema_version": 1,
        "status": status,
        "source": "contacts",
        "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
        "contacts": [],
        "contact": NSNull(),
        "warnings": [warning(code, message)],
    ])
}

// Verbatim label equality consistent with the Python free-form label contract
// (v1.180A): custom labels are preserved exactly (case, spaces, punctuation) and are
// NOT lowercased or underscored. `expected` is the caller's verbatim label string as
// sent by the Python plan; `storedRaw` is the raw CNLabeledValue label, which for a
// known standard label is a `CNLabel*` constant (e.g. `_$!<Home>!$_`).
//
// A stored label matches the expected label when either:
//   * the raw stored label equals the CN constant that this helper would store for
//     the expected label (`contactsLabel(expected)`) — this handles standard labels
//     like "home"/"work"/"mobile" whose stored form is a CNLabel constant; or
//   * stripping only the CN prefix (`labelName`, which passes non-constant custom
//     strings through unchanged) yields the expected label byte-for-byte — this
//     handles arbitrary custom labels verbatim, with no lowercasing/underscoring.
func labelsMatchVerbatim(_ storedRaw: String?, _ expected: String) -> Bool {
    let stored = storedRaw ?? ""
    if stored == contactsLabel(expected) {
        return true
    }
    return labelName(storedRaw) == expected
}

func contactsLabel(_ label: String) -> String {
    switch label.lowercased() {
    case "home":
        return CNLabelHome
    case "work":
        return CNLabelWork
    case "mobile":
        return CNLabelPhoneNumberMobile
    case "iphone":
        return CNLabelPhoneNumberiPhone
    case "main":
        return CNLabelPhoneNumberMain
    case "home_fax":
        return CNLabelPhoneNumberHomeFax
    case "work_fax":
        return CNLabelPhoneNumberWorkFax
    case "other":
        return CNLabelOther
    default:
        return label
    }
}

func requestLabeledEntries(_ request: [String: Any], _ key: String) -> [[String: String]] {
    guard let raw = request[key] as? [[String: Any]] else {
        return []
    }
    return raw.compactMap { item in
        guard let value = item["value"] as? String else {
            return nil
        }
        let label = (item["label"] as? String) ?? "other"
        return ["label": label, "value": value]
    }
}

func requestObjectEntries(_ request: [String: Any], _ key: String) -> [[String: Any]] {
    return (request[key] as? [[String: Any]]) ?? []
}

func requestDateComponents(_ request: [String: Any], _ key: String) -> DateComponents? {
    guard let raw = request[key] as? [String: Any] else {
        return nil
    }
    if raw.isEmpty {
        return nil
    }
    var components = DateComponents()
    if let year = raw["year"] as? Int {
        components.year = year
    }
    if let month = raw["month"] as? Int {
        components.month = month
    }
    if let day = raw["day"] as? Int {
        components.day = day
    }
    return components
}

func postalAddressValues(_ request: [String: Any], _ key: String) -> [CNLabeledValue<CNPostalAddress>] {
    return requestObjectEntries(request, key).map { item in
        let address = CNMutablePostalAddress()
        address.street = (item["street"] as? String) ?? ""
        address.city = (item["city"] as? String) ?? ""
        address.state = (item["state"] as? String) ?? ""
        address.postalCode = (item["postal_code"] as? String) ?? ""
        address.country = (item["country"] as? String) ?? ""
        address.isoCountryCode = (item["iso_country_code"] as? String) ?? ""
        return CNLabeledValue(label: contactsLabel((item["label"] as? String) ?? "other"), value: address)
    }
}

func datedValues(_ request: [String: Any], _ key: String) -> [CNLabeledValue<NSDateComponents>] {
    return requestObjectEntries(request, key).compactMap { item in
        guard let date = item["date"] as? [String: Any] else {
            return nil
        }
        var components = DateComponents()
        if let year = date["year"] as? Int {
            components.year = year
        }
        if let month = date["month"] as? Int {
            components.month = month
        }
        if let day = date["day"] as? Int {
            components.day = day
        }
        return CNLabeledValue(label: contactsLabel((item["label"] as? String) ?? "other"), value: components as NSDateComponents)
    }
}

func socialProfileValues(_ request: [String: Any], _ key: String) -> [CNLabeledValue<CNSocialProfile>] {
    return requestObjectEntries(request, key).map { item in
        let profile = CNSocialProfile(
            urlString: (item["url"] as? String) ?? "",
            username: (item["username"] as? String) ?? "",
            userIdentifier: "",
            service: (item["service"] as? String) ?? ""
        )
        return CNLabeledValue(label: contactsLabel((item["label"] as? String) ?? "other"), value: profile)
    }
}

func instantMessageValues(_ request: [String: Any], _ key: String) -> [CNLabeledValue<CNInstantMessageAddress>] {
    return requestObjectEntries(request, key).map { item in
        let address = CNInstantMessageAddress(
            username: (item["username"] as? String) ?? "",
            service: (item["service"] as? String) ?? ""
        )
        return CNLabeledValue(label: contactsLabel((item["label"] as? String) ?? "other"), value: address)
    }
}

func relationValues(_ request: [String: Any], _ key: String) -> [CNLabeledValue<CNContactRelation>] {
    return requestObjectEntries(request, key).map { item in
        let relation = CNContactRelation(name: (item["name"] as? String) ?? "")
        return CNLabeledValue(label: contactsLabel((item["label"] as? String) ?? "other"), value: relation)
    }
}

func labeledStringsMatch(_ actual: [CNLabeledValue<NSString>], _ expected: [[String: String]]) -> Bool {
    if actual.count != expected.count {
        return false
    }
    for (left, right) in zip(actual, expected) {
        if !labelsMatchVerbatim(left.label, right["label"] ?? "other") {
            return false
        }
        if String(left.value) != (right["value"] ?? "") {
            return false
        }
    }
    return true
}

func phoneNumbersMatch(_ actual: [CNLabeledValue<CNPhoneNumber>], _ expected: [[String: String]]) -> Bool {
    if actual.count != expected.count {
        return false
    }
    for (left, right) in zip(actual, expected) {
        if !labelsMatchVerbatim(left.label, right["label"] ?? "other") {
            return false
        }
        if left.value.stringValue != (right["value"] ?? "") {
            return false
        }
    }
    return true
}

func contactMatchesCreate(_ contact: CNContact, request: [String: Any]) -> Bool {
    let requestedType = stringValue(request, "contact_type")
    if requestedType == "organization" && contact.contactType != .organization {
        return false
    }
    if requestedType == "person" && contact.contactType != .person {
        return false
    }
    if contact.givenName != stringValue(request, "given_name") {
        return false
    }
    if contact.familyName != stringValue(request, "family_name") {
        return false
    }
    if contact.organizationName != stringValue(request, "organization_name") {
        return false
    }
    if contact.departmentName != stringValue(request, "department_name") {
        return false
    }
    if contact.jobTitle != stringValue(request, "job_title") {
        return false
    }
    if contact.nickname != stringValue(request, "nickname") {
        return false
    }
    if !labeledStringsMatch(contact.emailAddresses, requestLabeledEntries(request, "email_addresses")) {
        return false
    }
    if !phoneNumbersMatch(contact.phoneNumbers, requestLabeledEntries(request, "phone_numbers")) {
        return false
    }
    if !labeledStringsMatch(contact.urlAddresses, requestLabeledEntries(request, "url_addresses")) {
        return false
    }
    return true
}

func contactUpdateState(_ contact: CNContact) -> [String: String] {
    let payload = contactPayload(contact, includeDetails: true)
    return [
        "contact_type": contactTypeName(contact),
        "given_name": contact.givenName,
        "family_name": contact.familyName,
        "organization_name": contact.organizationName,
        "department_name": contact.departmentName,
        "job_title": contact.jobTitle,
        "nickname": contact.nickname,
        "email_addresses": canonicalString(stringLabeledValues(contact.emailAddresses)),
        "phone_numbers": canonicalString(phonePayloads(contact.phoneNumbers)),
        "url_addresses": canonicalString(stringLabeledValues(contact.urlAddresses)),
        "postal_addresses": canonicalString(payload["postal_addresses"] ?? []),
        "birthday": canonicalString(payload["birthday"] ?? [:]),
        "dates": canonicalString(payload["dates"] ?? []),
        "social_profiles": canonicalString(payload["social_profiles"] ?? []),
        "instant_message_addresses": canonicalString(payload["instant_message_addresses"] ?? []),
        "contact_relations": canonicalString(payload["contact_relations"] ?? []),
        "image_available": canonicalString(contact.imageDataAvailable),
        "image_sha256": canonicalString(payload["image_sha256"] ?? ""),
        "image_bytes": canonicalString(payload["image_bytes"] ?? 0),
    ]
}

func contactUpdateStatePayload(_ contact: CNContact) -> [String: Any] {
    var payload = contactUpdateState(contact) as [String: Any]
    payload["contact_id"] = contact.identifier
    return payload
}

func requestStringMap(_ request: [String: Any], _ key: String) -> [String: String] {
    guard let raw = request[key] as? [String: Any] else {
        return [:]
    }
    var payload: [String: String] = [:]
    for (name, value) in raw {
        payload[name] = (value as? String) ?? ""
    }
    return payload
}

func canonicalString(_ value: Any) -> String {
    if value is NSNull {
        return ""
    }
    if let text = value as? String {
        return text
    }
    if let bool = value as? Bool {
        return bool ? "true" : "false"
    }
    if let int = value as? Int {
        return String(int)
    }
    if let double = value as? Double {
        return String(double)
    }
    if let data = try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes]),
       let text = String(data: data, encoding: .utf8) {
        return text
    }
    return "\(value)"
}

func contactDeleteState(_ contact: CNContact) -> [String: String] {
    let payload = contactPayload(contact, includeDetails: true)
    let keys = [
        "display_name",
        "contact_type",
        "given_name",
        "family_name",
        "nickname",
        "organization_name",
        "department_name",
        "job_title",
        "email_count",
        "phone_count",
        "postal_address_count",
        "url_count",
        "social_profile_count",
        "instant_message_count",
        "relation_count",
        "dates_count",
        "birthday_present",
        "image_available",
        "note_status",
        "name_prefix",
        "middle_name",
        "previous_family_name",
        "name_suffix",
        "email_addresses",
        "phone_numbers",
        "postal_addresses",
        "url_addresses",
        "birthday",
        "dates",
        "social_profiles",
        "instant_message_addresses",
        "contact_relations",
    ]
    var state: [String: String] = [:]
    for key in keys {
        state[key] = canonicalString(payload[key] ?? "")
    }
    return state
}

func contactMatchesExpectedUpdate(_ contact: CNContact, expected: [String: String]) -> Bool {
    let current = contactUpdateState(contact)
    for key in [
        "contact_type",
        "given_name",
        "family_name",
        "organization_name",
        "department_name",
        "job_title",
        "nickname",
        "email_addresses",
        "phone_numbers",
        "url_addresses",
        "postal_addresses",
        "birthday",
        "dates",
        "social_profiles",
        "instant_message_addresses",
        "contact_relations",
        "image_available",
        "image_sha256",
        "image_bytes",
    ] {
        if current[key] != expected[key] {
            return false
        }
    }
    return true
}

func contactMatchesExpectedDelete(_ contact: CNContact, expected: [String: String]) -> Bool {
    let current = contactDeleteState(contact)
    for (key, value) in current {
        if expected[key] != value {
            return false
        }
    }
    return true
}

func matches(_ contact: CNContact, query: String) -> Bool {
    if query.isEmpty {
        return true
    }
    let haystack = [
        displayName(contact),
        contact.givenName,
        contact.familyName,
        contact.nickname,
        contact.organizationName,
        contact.departmentName,
        contact.jobTitle,
    ].joined(separator: " ").lowercased()
    return haystack.contains(query)
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
        "source": "contacts",
        "warnings": [warning("invalid_request", "Expected JSON request.")],
    ])
}

let command = stringValue(request, "command")

if command == "request_contacts_access" {
    requestContactsAccess()
}

if command == "contacts_apply_change" {
    let store = ensureAccess()!
    let operation = stringValue(request, "operation")
    if operation != "create" && operation != "update" && operation != "delete" && operation != "append_note" && operation != "set_note" && operation != "add_group_member" && operation != "remove_group_member" && operation != "create_group" && operation != "rename_group" && operation != "delete_group" {
        emitContactsApplyError("error", "invalid_operation", "Unsupported Contacts apply operation.")
    }
    if operation == "add_group_member" || operation == "remove_group_member" {
        let contactId = stringValue(request, "contact_id")
        let groupId = stringValue(request, "group_id")
        if contactId.isEmpty || groupId.isEmpty {
            emitContactsApplyError("error", "missing_required_field", "Contacts group membership requires exact contact and group identifiers.")
        }
        let expectedContact = requestStringMap(request, "expected_current")
        let expectedGroup = requestStringMap(request, "expected_group")
        let existing: CNContact
        do {
            existing = try store.unifiedContact(withIdentifier: contactId, keysToFetch: updateStateKeys)
        } catch {
            emitContactsApplyError("error", "contacts_not_found", "Contacts group target could not be read.")
        }
        guard let group = groupById(store, groupId) else {
            emitContactsApplyError("error", "group_not_found", "Contacts group target could not be read.")
        }
        if !contactMatchesExpectedUpdate(existing, expected: expectedContact) {
            emitContactsApplyError("error", "current_contact_changed", "Contacts target state changed before group membership update.")
        }
        if !groupMatchesExpected(store, group, expected: expectedGroup) {
            emitContactsApplyError("error", "current_group_changed", "Contacts group state changed before membership update.")
        }
        let save = CNSaveRequest()
        if operation == "add_group_member" {
            save.addMember(existing, to: group)
        } else {
            save.removeMember(existing, from: group)
        }
        do {
            try store.execute(save)
        } catch {
            emitContactsApplyError("error", "contacts_apply_failed", "Contacts group membership could not be updated.")
        }
        guard let updatedGroup = groupById(store, groupId) else {
            emitContactsApplyError("apply_unknown", "read_back_unavailable", "Contacts group was updated but read-back was unavailable.")
        }
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
            "group": groupPayload(store, updatedGroup),
            "membership_changed": true,
            "membership_verified": true,
            "warnings": [],
        ])
    }
    if operation == "create_group" {
        let groupName = stringValue(request, "group_name")
        if groupName.isEmpty {
            emitContactsApplyError("error", "missing_required_field", "Contacts group create requires group_name.")
        }
        let containerId = stringValue(request, "container_id")
        if !containerId.isEmpty {
            guard let container = containerById(store, containerId) else {
                emitContactsApplyError("error", "container_not_found", "Contacts container target could not be read.")
            }
            let expectedContainer = requestStringMap(request, "expected_container")
            if !containerMatchesExpected(container, expected: expectedContainer) {
                emitContactsApplyError("error", "current_container_changed", "Contacts container state changed before group create.")
            }
        }
        if groupWithName(store, groupName, containerId: containerId) != nil {
            emitContactsApplyError("error", "already_applied", "Contacts group already exists in the selected container.")
        }
        let group = CNMutableGroup()
        group.name = groupName
        let save = CNSaveRequest()
        save.add(group, toContainerWithIdentifier: containerId.isEmpty ? nil : containerId)
        do {
            try store.execute(save)
        } catch {
            emitContactsApplyError("error", "contacts_apply_failed", "Contacts group could not be created.")
        }
        if let created = groupById(store, group.identifier) ?? groupWithName(store, groupName, containerId: containerId) {
            emit([
                "schema_version": 1,
                "status": "ok",
                "source": "contacts",
                "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
                "group": groupPayload(store, created),
                "warnings": [],
            ])
        }
        emitContactsApplyError("apply_unknown", "read_back_unavailable", "Contacts group was created but read-back was unavailable.")
    }
    if operation == "rename_group" || operation == "delete_group" {
        let groupId = stringValue(request, "group_id")
        if groupId.isEmpty {
            emitContactsApplyError("error", "invalid_group_id", "Contacts group change requires an exact group identifier.")
        }
        let expectedGroup = requestStringMap(request, "expected_group")
        guard let group = groupById(store, groupId) else {
            emitContactsApplyError("error", "group_not_found", "Contacts group target could not be read.")
        }
        if !groupMatchesExpected(store, group, expected: expectedGroup) {
            emitContactsApplyError("error", "current_group_changed", "Contacts group state changed before apply.")
        }
        guard let mutable = group.mutableCopy() as? CNMutableGroup else {
            emitContactsApplyError("error", "contacts_apply_failed", "Contacts group could not be prepared for apply.")
        }
        let save = CNSaveRequest()
        if operation == "rename_group" {
            let groupName = stringValue(request, "group_name")
            if groupName.isEmpty {
                emitContactsApplyError("error", "missing_required_field", "Contacts group rename requires group_name.")
            }
            mutable.name = groupName
            save.update(mutable)
        } else {
            save.delete(mutable)
        }
        do {
            try store.execute(save)
        } catch {
            emitContactsApplyError("error", "contacts_apply_failed", "Contacts group could not be changed.")
        }
        if operation == "delete_group" {
            if groupById(store, groupId) == nil {
                emit([
                    "schema_version": 1,
                    "status": "ok",
                    "source": "contacts",
                    "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
                    "group": NSNull(),
                    "deleted": true,
                    "verified_absent": true,
                    "warnings": [],
                ])
            }
            emitContactsApplyError("apply_unknown", "read_back_unavailable", "Contacts group was deleted but absence proof failed.")
        }
        guard let updatedGroup = groupById(store, groupId) else {
            emitContactsApplyError("apply_unknown", "read_back_unavailable", "Contacts group was renamed but read-back was unavailable.")
        }
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
            "group": groupPayload(store, updatedGroup),
            "warnings": [],
        ])
    }
    if operation == "append_note" || operation == "set_note" {
        let contactId = stringValue(request, "contact_id")
        if contactId.isEmpty {
            emitContactsApplyError("error", "invalid_contact_id", "Contacts note update requires an exact contact identifier.")
        }
        let expectedCurrentNoteText = stringValue(request, "expected_current_note_text")
        let requestedNoteText = stringValue(request, "note_text")
        if operation == "append_note" && requestedNoteText.isEmpty {
            emitContactsApplyError("error", "missing_required_field", "Contacts note append requires note_text.")
        }
        let existing: CNContact
        do {
            existing = try store.unifiedContact(withIdentifier: contactId, keysToFetch: noteStateKeys)
        } catch {
            emitContactsApplyError("error", "contacts_note_unavailable", "Contacts note state could not be read.")
        }
        if !existing.isKeyAvailable(CNContactNoteKey) {
            emitContactsApplyError("error", "contacts_note_unavailable", "Contacts note state could not be read.")
        }
        if existing.note != expectedCurrentNoteText {
            emitContactsApplyError("error", "current_contact_changed", "Contacts note state changed before append.")
        }
        guard let mutable = existing.mutableCopy() as? CNMutableContact else {
            emitContactsApplyError("error", "contacts_apply_failed", "Contact could not be prepared for note update.")
        }
        if operation == "append_note" {
            mutable.note = existing.note + requestedNoteText
        } else {
            mutable.note = requestedNoteText
        }

        let save = CNSaveRequest()
        save.update(mutable)
        do {
            try store.execute(save)
        } catch {
            emitContactsApplyError("error", "contacts_apply_failed", "Contact note could not be updated.")
        }
        do {
            let updated = try store.unifiedContact(withIdentifier: contactId, keysToFetch: noteStateKeys)
            emit([
                "schema_version": 1,
                "status": "ok",
                "source": "contacts",
                "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
                "contact": contactNoteStatePayload(updated),
                "warnings": [],
            ])
        } catch {
            emitContactsApplyError("apply_unknown", "read_back_unavailable", "Contact note was updated but read-back was unavailable.")
        }
    }
    if operation == "update" {
        let contactId = stringValue(request, "contact_id")
        if contactId.isEmpty {
            emitContactsApplyError("error", "invalid_contact_id", "Contacts update requires an exact contact identifier.")
        }
        let expected = requestStringMap(request, "expected_current")
        let existing: CNContact
        do {
            existing = try store.unifiedContact(withIdentifier: contactId, keysToFetch: updateStateKeys)
        } catch {
            emitContactsApplyError("error", "contacts_not_found", "Contacts update target could not be read.")
        }
        if !contactMatchesExpectedUpdate(existing, expected: expected) {
            emitContactsApplyError("error", "current_contact_changed", "Contacts target state changed before update.")
        }
        guard let mutable = existing.mutableCopy() as? CNMutableContact else {
            emitContactsApplyError("error", "contacts_apply_failed", "Contact could not be prepared for update.")
        }
        mutable.givenName = stringValue(request, "given_name")
        mutable.familyName = stringValue(request, "family_name")
        mutable.organizationName = stringValue(request, "organization_name")
        mutable.departmentName = stringValue(request, "department_name")
        mutable.jobTitle = stringValue(request, "job_title")
        mutable.nickname = stringValue(request, "nickname")
        if (request["replace_email_addresses"] as? Bool) == true {
            mutable.emailAddresses = requestLabeledEntries(request, "email_addresses").map {
                CNLabeledValue(label: contactsLabel($0["label"] ?? "other"), value: NSString(string: $0["value"] ?? ""))
            }
        }
        if (request["replace_phone_numbers"] as? Bool) == true {
            mutable.phoneNumbers = requestLabeledEntries(request, "phone_numbers").map {
                CNLabeledValue(label: contactsLabel($0["label"] ?? "other"), value: CNPhoneNumber(stringValue: $0["value"] ?? ""))
            }
        }
        if (request["replace_url_addresses"] as? Bool) == true {
            mutable.urlAddresses = requestLabeledEntries(request, "url_addresses").map {
                CNLabeledValue(label: contactsLabel($0["label"] ?? "other"), value: NSString(string: $0["value"] ?? ""))
            }
        }
        if (request["replace_postal_addresses"] as? Bool) == true {
            mutable.postalAddresses = postalAddressValues(request, "postal_addresses")
        }
        if (request["replace_birthday"] as? Bool) == true {
            mutable.birthday = requestDateComponents(request, "birthday")
        }
        if (request["replace_dates"] as? Bool) == true {
            mutable.dates = datedValues(request, "dates")
        }
        if (request["replace_social_profiles"] as? Bool) == true {
            mutable.socialProfiles = socialProfileValues(request, "social_profiles")
        }
        if (request["replace_instant_message_addresses"] as? Bool) == true {
            mutable.instantMessageAddresses = instantMessageValues(request, "instant_message_addresses")
        }
        if (request["replace_contact_relations"] as? Bool) == true {
            mutable.contactRelations = relationValues(request, "contact_relations")
        }
        let imageAction = stringValue(request, "image_action")
        if imageAction == "clear" {
            mutable.imageData = nil
        } else if imageAction == "set" {
            guard let imageText = request["image_data_base64"] as? String,
                  let imageData = Data(base64Encoded: imageText),
                  !imageData.isEmpty else {
                emitContactsApplyError("error", "invalid_image_data", "Contact image payload was invalid.")
            }
            mutable.imageData = imageData
        }

        let save = CNSaveRequest()
        save.update(mutable)
        do {
            try store.execute(save)
        } catch {
            emitContactsApplyError("error", "contacts_apply_failed", "Contact could not be updated.")
        }
        do {
            let updated = try store.unifiedContact(withIdentifier: contactId, keysToFetch: detailKeys)
            emit([
                "schema_version": 1,
                "status": "ok",
                "source": "contacts",
                "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
                "contact": contactPayload(updated, includeDetails: true),
                "warnings": [],
            ])
        } catch {
            emitContactsApplyError("apply_unknown", "read_back_unavailable", "Contact was updated but read-back was unavailable.")
        }
    }
    if operation == "delete" {
        let contactId = stringValue(request, "contact_id")
        if contactId.isEmpty {
            emitContactsApplyError("error", "invalid_contact_id", "Contacts delete requires an exact contact identifier.")
        }
        let expected = requestStringMap(request, "expected_current")
        let existing: CNContact
        do {
            existing = try store.unifiedContact(withIdentifier: contactId, keysToFetch: baseKeys)
        } catch {
            emitContactsApplyError("error", "contacts_not_found", "Contacts delete target could not be read.")
        }
        if !contactMatchesExpectedDelete(existing, expected: expected) {
            emitContactsApplyError("error", "current_contact_changed", "Contacts target state changed before delete.")
        }
        guard let mutable = existing.mutableCopy() as? CNMutableContact else {
            emitContactsApplyError("error", "contacts_apply_failed", "Contact could not be prepared for delete.")
        }

        let save = CNSaveRequest()
        save.delete(mutable)
        do {
            try store.execute(save)
        } catch {
            emitContactsApplyError("error", "contacts_apply_failed", "Contact could not be deleted.")
        }
        do {
            _ = try store.unifiedContact(withIdentifier: contactId, keysToFetch: updateStateKeys)
            emitContactsApplyError("apply_unknown", "read_back_unavailable", "Contact was deleted but absence proof failed.")
        } catch {
            let nsError = error as NSError
            if nsError.domain == CNErrorDomain && nsError.code == CNError.Code.recordDoesNotExist.rawValue {
                emit([
                    "schema_version": 1,
                    "status": "ok",
                    "source": "contacts",
                    "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
                    "contact": NSNull(),
                    "deleted": true,
                    "verified_absent": true,
                    "warnings": [],
                ])
            }
            emitContactsApplyError("apply_unknown", "read_back_unavailable", "Contact was deleted but absence proof failed.")
        }
    }
    let contactType = stringValue(request, "contact_type")
    if contactType != "person" && contactType != "organization" {
        emitContactsApplyError("error", "invalid_contact_type", "Expected contact_type person or organization.")
    }
    let givenName = stringValue(request, "given_name")
    let familyName = stringValue(request, "family_name")
    let organizationName = stringValue(request, "organization_name")
    if contactType == "person" && givenName.isEmpty && familyName.isEmpty {
        emitContactsApplyError("error", "missing_required_field", "Person contact create requires given_name or family_name.")
    }
    if contactType == "organization" && organizationName.isEmpty {
        emitContactsApplyError("error", "missing_required_field", "Organization contact create requires organization_name.")
    }
    let containerId = stringValue(request, "container_id")
    if !containerId.isEmpty {
        guard let container = containerById(store, containerId) else {
            emitContactsApplyError("error", "container_not_found", "Contacts container target could not be read.")
        }
        let expectedContainer = requestStringMap(request, "expected_container")
        if !containerMatchesExpected(container, expected: expectedContainer) {
            emitContactsApplyError("error", "current_container_changed", "Contacts container state changed before contact create.")
        }
    }

    let fetch = CNContactFetchRequest(keysToFetch: baseKeys)
    fetch.sortOrder = .userDefault
    fetch.unifyResults = true
    do {
        try store.enumerateContacts(with: fetch) { contact, stop in
            if contactMatchesCreate(contact, request: request) {
                emit([
                    "schema_version": 1,
                    "status": "ok",
                    "source": "contacts",
                    "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
                    "contact": contactPayload(contact, includeDetails: true),
                    "warnings": [warning("already_applied", "Contacts create already matches an existing contact.")],
                ])
            }
        }
    } catch {
        emitContactsApplyError("error", "contacts_fetch_failed", "Contacts could not be checked before create.")
    }

    let contact = CNMutableContact()
    if contactType == "organization" {
        contact.contactType = .organization
    } else {
        contact.contactType = .person
    }
    contact.givenName = givenName
    contact.familyName = familyName
    contact.organizationName = organizationName
    contact.departmentName = stringValue(request, "department_name")
    contact.jobTitle = stringValue(request, "job_title")
    contact.nickname = stringValue(request, "nickname")
    contact.emailAddresses = requestLabeledEntries(request, "email_addresses").map {
        CNLabeledValue(label: contactsLabel($0["label"] ?? "other"), value: NSString(string: $0["value"] ?? ""))
    }
    contact.phoneNumbers = requestLabeledEntries(request, "phone_numbers").map {
        CNLabeledValue(label: contactsLabel($0["label"] ?? "other"), value: CNPhoneNumber(stringValue: $0["value"] ?? ""))
    }
    contact.urlAddresses = requestLabeledEntries(request, "url_addresses").map {
        CNLabeledValue(label: contactsLabel($0["label"] ?? "other"), value: NSString(string: $0["value"] ?? ""))
    }

    let save = CNSaveRequest()
    save.add(contact, toContainerWithIdentifier: containerId.isEmpty ? nil : containerId)
    do {
        try store.execute(save)
    } catch {
        emitContactsApplyError("error", "contacts_apply_failed", "Contact could not be created.")
    }

    do {
        let saved = try store.unifiedContact(withIdentifier: contact.identifier, keysToFetch: baseKeys)
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
            "contact": contactPayload(saved, includeDetails: true),
            "warnings": [],
        ])
    } catch {
        emitContactsApplyError("apply_unknown", "read_back_unavailable", "Contact was created but read-back was unavailable.")
    }
}

if command == "contacts" {
    let store = ensureAccess()!
    let query = stringValue(request, "query").lowercased()
    let limit = max(1, min(intValue(request, "limit", 20), 10000))
    let maxContacts = max(1, min(intValue(request, "max_contacts", 10000), 10000))
    let fetch = CNContactFetchRequest(keysToFetch: baseKeys)
    fetch.sortOrder = .userDefault
    fetch.unifyResults = true

    var scanned = 0
    var scanTruncated = false
    var results: [[String: Any]] = []
    do {
        try store.enumerateContacts(with: fetch) { contact, stop in
            if scanned >= maxContacts {
                scanTruncated = true
                stop.pointee = true
                return
            }
            scanned += 1
            if !matches(contact, query: query) {
                return
            }
            results.append(contactPayload(contact, includeDetails: false))
            if results.count >= limit {
                stop.pointee = true
            }
        }
    } catch {
        emit([
            "schema_version": 1,
            "status": "degraded",
            "source": "contacts",
            "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
            "contacts": [],
            "warnings": [warning("contacts_fetch_failed", "Contacts could not be fetched safely.")],
        ])
    }

    var warnings: [[String: String]] = []
    if scanTruncated {
        warnings.append(warning("scan_truncated", "Contacts scan stopped at the scan limit."))
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
        "contacts": results,
        "scanned": scanned,
        "warnings": warnings,
    ])
}

if command == "contact_containers" {
    let store = ensureAccess()!
    let query = stringValue(request, "query").lowercased()
    let limit = max(1, min(intValue(request, "limit", 20), 100))
    let allContainers = containers(store)
    var results: [[String: Any]] = []
    for container in allContainers {
        let haystack = [container.name, containerTypeName(container)].joined(separator: " ").lowercased()
        if !query.isEmpty && !haystack.contains(query) {
            continue
        }
        results.append(containerPayload(container))
        if results.count >= limit {
            break
        }
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
        "containers": results,
        "warnings": [],
    ])
}

if command == "contact_container_by_id" {
    let store = ensureAccess()!
    let containerId = stringValue(request, "container_id")
    guard let container = containerById(store, containerId) else {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "contacts",
            "container": NSNull(),
            "warnings": [],
        ])
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
        "container": containerPayload(container),
        "warnings": [],
    ])
}

if command == "contact_groups" {
    let store = ensureAccess()!
    let query = stringValue(request, "query").lowercased()
    let limit = max(1, min(intValue(request, "limit", 20), 10000))
    do {
        let groups = try store.groups(matching: nil)
        var results: [[String: Any]] = []
        for group in groups {
            if !query.isEmpty && !group.name.lowercased().contains(query) {
                continue
            }
            results.append(groupPayload(store, group))
            if results.count >= limit {
                break
            }
        }
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
            "groups": results,
            "warnings": [],
        ])
    } catch {
        emit([
            "schema_version": 1,
            "status": "degraded",
            "source": "contacts",
            "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
            "groups": [],
            "warnings": [warning("groups_fetch_failed", "Contacts groups could not be fetched safely.")],
        ])
    }
}

if command == "contact_group_by_id" {
    let store = ensureAccess()!
    let groupId = stringValue(request, "group_id")
    guard let group = groupById(store, groupId) else {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "contacts",
            "group": NSNull(),
            "warnings": [],
        ])
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
        "group": groupPayload(store, group),
        "warnings": [],
    ])
}

if command == "contact_container_members" {
    let store = ensureAccess()!
    let containerId = stringValue(request, "container_id")
    let limit = max(1, min(intValue(request, "limit", 20), 50))
    guard let container = containerById(store, containerId) else {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "contacts",
            "container": NSNull(),
            "contacts": [],
            "warnings": [],
        ])
    }
    do {
        let contacts = try store.unifiedContacts(
            matching: CNContact.predicateForContactsInContainer(withIdentifier: container.identifier),
            keysToFetch: baseKeys
        )
        let sortedContacts = sortedGroupContacts(contacts)
        let limitedContacts = Array(sortedContacts.prefix(limit))
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
            "container": containerPayload(container),
            "contacts": limitedContacts.map { contactPayload($0, includeDetails: false) },
            "truncated": sortedContacts.count > limit,
            "warnings": [],
        ])
    } catch {
        emit([
            "schema_version": 1,
            "status": "degraded",
            "source": "contacts",
            "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
            "container": containerPayload(container),
            "contacts": [],
            "warnings": [warning("contacts_fetch_failed", "Contacts container members could not be fetched safely.")],
        ])
    }
}

if command == "contact_group_members" {
    let store = ensureAccess()!
    let groupId = stringValue(request, "group_id")
    let limit = max(1, min(intValue(request, "limit", 20), 50))
    guard let group = groupById(store, groupId) else {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "contacts",
            "group": NSNull(),
            "contacts": [],
            "warnings": [],
        ])
    }
    do {
        let contacts = try store.unifiedContacts(
            matching: CNContact.predicateForContactsInGroup(withIdentifier: group.identifier),
            keysToFetch: baseKeys
        )
        let sortedContacts = sortedGroupContacts(contacts)
        let limitedContacts = Array(sortedContacts.prefix(limit))
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
            "group": groupPayload(store, group),
            "contacts": limitedContacts.map { contactPayload($0, includeDetails: false) },
            "truncated": sortedContacts.count > limit,
            "warnings": [],
        ])
    } catch {
        emit([
            "schema_version": 1,
            "status": "degraded",
            "source": "contacts",
            "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
            "group": groupPayload(store, group),
            "contacts": [],
            "warnings": [warning("contacts_fetch_failed", "Contacts group members could not be fetched safely.")],
        ])
    }
}

if command == "contacts_count" {
    let store = ensureAccess()!
    let maxContacts = max(1, min(intValue(request, "max_contacts", 50000), 100000))
    let fetch = CNContactFetchRequest(keysToFetch: [CNContactIdentifierKey as CNKeyDescriptor])
    fetch.sortOrder = .userDefault
    fetch.unifyResults = true

    var count = 0
    var scanTruncated = false
    do {
        try store.enumerateContacts(with: fetch) { _contact, stop in
            if count >= maxContacts {
                scanTruncated = true
                stop.pointee = true
                return
            }
            count += 1
        }
    } catch {
        emit([
            "schema_version": 1,
            "status": "degraded",
            "source": "contacts",
            "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
            "contact_count": 0,
            "warnings": [warning("contacts_fetch_failed", "Contacts could not be counted safely.")],
        ])
    }

    var warnings: [[String: String]] = []
    if scanTruncated {
        warnings.append(warning("scan_truncated", "Contacts count stopped at the scan limit."))
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
        "contact_count": count,
        "scan_truncated": scanTruncated,
        "warnings": warnings,
    ])
}

if command == "contacts_archive" {
    let store = ensureAccess()!
    let maxContacts = max(1, min(intValue(request, "max_contacts", 50000), 100000))
    var scanned = 0
    var scanTruncated = false
    var results: [[String: Any]] = []
    var vcardContacts: [CNContact] = []

    func fetchArchive(
        keysToFetch: [CNKeyDescriptor],
        includeNotes: Bool
    ) -> Bool {
        scanned = 0
        scanTruncated = false
        results = []
        vcardContacts = []
        let fetch = CNContactFetchRequest(keysToFetch: keysToFetch)
        fetch.sortOrder = .userDefault
        fetch.unifyResults = true
        do {
            try store.enumerateContacts(with: fetch) { contact, stop in
                if scanned >= maxContacts {
                    scanTruncated = true
                    stop.pointee = true
                    return
                }
                scanned += 1
                results.append(
                    contactPayload(
                        contact,
                        includeDetails: true,
                        includeNote: includeNotes
                    )
                )
                vcardContacts.append(contact)
            }
        } catch {
            return false
        }
        return true
    }

    var notesExported = fetchArchive(
        keysToFetch: archiveKeysWithNotes,
        includeNotes: true
    )
    if !notesExported {
        notesExported = false
        if !fetchArchive(
            keysToFetch: archiveKeysWithoutNotes,
            includeNotes: false
        ) {
            emit([
                "schema_version": 1,
                "status": "degraded",
                "source": "contacts",
                "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
                "contact_count": 0,
                "contacts": [],
                "vcard_text": "",
                "notes_exported": false,
                "warnings": [warning("contacts_fetch_failed", "Contacts archive could not be fetched safely.")],
            ])
        }
    }

    var vcardText = ""
    var vcardAvailable = true
    do {
        let vcardData = try CNContactVCardSerialization.data(with: vcardContacts)
        vcardText = String(data: vcardData, encoding: .utf8) ?? ""
    } catch {
        vcardAvailable = false
    }

    var warnings: [[String: String]] = []
    if scanTruncated {
        warnings.append(warning("scan_truncated", "Contacts archive stopped at the scan limit."))
    }
    if !notesExported {
        warnings.append(
            warning(
                "contacts_notes_unavailable",
                "Contact notes were unavailable and were omitted from the archive."
            )
        )
    }
    if !vcardAvailable {
        warnings.append(
            warning(
                "contacts_vcard_export_failed",
                "Contacts vCard archive could not be generated safely."
            )
        )
    }
    emit([
        "schema_version": 1,
        "status": "ok",
        "source": "contacts",
        "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
        "contact_count": scanned,
        "contacts": results,
        "vcard_text": vcardText,
        "notes_exported": notesExported,
        "scan_truncated": scanTruncated,
        "warnings": warnings,
    ])
}

if command == "contact_by_id" {
    let store = ensureAccess()!
    let contactId = stringValue(request, "contact_id")
    if contactId.isEmpty {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "contacts",
            "contact": NSNull(),
            "warnings": [warning("invalid_contact_id", "Expected Contacts identifier.")],
        ])
    }
    do {
        let contact = try store.unifiedContact(withIdentifier: contactId, keysToFetch: detailKeys)
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "contact": contactPayload(contact, includeDetails: true),
            "warnings": [],
        ])
    } catch {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "contacts",
            "contact": NSNull(),
            "warnings": [],
        ])
    }
}

if command == "contact_note_state_by_id" {
    let store = ensureAccess()!
    let contactId = stringValue(request, "contact_id")
    if contactId.isEmpty {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "contacts",
            "contact": NSNull(),
            "warnings": [warning("invalid_contact_id", "Contact identifier is required.")],
        ])
    }
    do {
        let contact = try store.unifiedContact(withIdentifier: contactId, keysToFetch: noteStateKeys)
        if !contact.isKeyAvailable(CNContactNoteKey) {
            emit([
                "schema_version": 1,
                "status": "degraded",
                "source": "contacts",
                "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
                "contact": NSNull(),
                "warnings": [warning("contacts_note_unavailable", "Contacts note state could not be read.")],
            ])
        }
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
            "contact": contactNoteStatePayload(contact),
            "warnings": [],
        ])
    } catch {
        emit([
            "schema_version": 1,
            "status": "degraded",
            "source": "contacts",
            "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
            "contact": NSNull(),
            "warnings": [warning("contacts_note_unavailable", "Contacts note state could not be read.")],
        ])
    }
}

if command == "contact_update_state_by_id" {
    let store = ensureAccess()!
    let contactId = stringValue(request, "contact_id")
    if contactId.isEmpty {
        emit([
            "schema_version": 1,
            "status": "error",
            "source": "contacts",
            "contact": NSNull(),
            "warnings": [warning("invalid_contact_id", "Contact identifier is required.")],
        ])
    }
    do {
        let contact = try store.unifiedContact(withIdentifier: contactId, keysToFetch: updateStateKeys)
        emit([
            "schema_version": 1,
            "status": "ok",
            "source": "contacts",
            "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
            "contact": contactUpdateStatePayload(contact),
            "warnings": [],
        ])
    } catch {
        emit([
            "schema_version": 1,
            "status": "not_found",
            "source": "contacts",
            "authorization_status": authorizationName(CNContactStore.authorizationStatus(for: .contacts)),
            "contact": NSNull(),
            "warnings": [warning("contacts_not_found", "Contact was not found.")],
        ])
    }
}

emit([
    "schema_version": 1,
    "status": "error",
    "source": "contacts",
    "warnings": [warning("unknown_command", "Unsupported Contacts helper command.")],
])
